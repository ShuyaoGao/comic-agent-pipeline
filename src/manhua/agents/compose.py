"""
合成/后期 Agent（需求文档 4.7 自动剪辑与后期；需求文档 第十章 10.2）。

把"分镜表 + 分镜图 + 角色音色"合成为可演示的草样片与结构化剪辑时间线：
  - 为每镜生成占位配音（mock TTS，记录时长/音色，供时间线对齐）。
  - 把各分镜图合成草样片 GIF（带字幕 + 轻微缩放），主机无需任何视频软件即可预览。
  - 产出结构化剪辑时间线 timeline.json（需求文档 4.7：时间线/字幕/配音/BGM/比例）。
  - 生成 FFmpeg 成片脚本（有 FFmpeg + 真实素材时一键拼 9:16 mp4）。

不是 LLM 型 Agent：确定性地从上游结构化数据合成（和美术 Agent 一样直接 run）。
真实视频(可灵/Wan2.2)与真实配音(CosyVoice/IndexTTS)在阶段二替换占位实现。
"""
from __future__ import annotations

import hashlib
import re

from ..engine import ProjectState, RunContext
from ..postprod import (build_reel_gif, estimate_speech_seconds,
                        write_ffmpeg_scripts, write_voice_wav)
from ..schemas import AudioClip, ComposeResult, EditTimeline, VideoClip


def _duration_seconds(text: str, default: float = 5.0) -> float:
    """把 '5s' / '5 秒' 之类解析成秒数。"""
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else default


def _pitch_for(speaker: str) -> float:
    """由说话者确定性派生一个占位音高（仅让不同角色音轨略有区分）。"""
    h = int(hashlib.md5(speaker.encode("utf-8")).hexdigest()[:6], 16)
    return 150.0 + (h % 70)  # 150~219 Hz


class ComposeAgent:
    key = "compose"
    display_name = "合成/后期 Agent"

    def run(self, state: ProjectState, ctx: RunContext) -> None:
        assert state.storyboard is not None and state.characters is not None
        cc = ctx.config.compose
        audio_dir = ctx.out_dir / "assets" / "audio"

        # 角色名/ID -> 音色
        voice_by_name = {c.name: c.voice_profile for c in state.characters.characters}
        voice_by_id = {c.character_id: c.voice_profile for c in state.characters.characters}
        # 分镜图路径
        shot_img = {a.ref_id: a.image_path for a in state.art.shot_images} if state.art else {}

        audio_clips: list[AudioClip] = []
        video_clips: list[VideoClip] = []
        reel_inputs: list[dict] = []
        cursor = 0.0

        for sh in state.storyboard.shots:
            dur = _duration_seconds(sh.duration)
            # 解析该镜台词：dialogue 形如 "角色：内容"
            if sh.dialogue and "：" in sh.dialogue:
                speaker, text = sh.dialogue.split("：", 1)
            elif sh.dialogue:
                speaker, text = "旁白", sh.dialogue
            else:
                speaker, text = "旁白", sh.action or sh.scene
            voice = voice_by_name.get(speaker) or (voice_by_id.get(sh.characters[0]) if sh.characters else None) or "中性解说、语速中等"

            # 占位配音：时长不超过镜头时长
            spoken = min(estimate_speech_seconds(text), dur)
            wav = audio_dir / f"{sh.shot_id}.wav"
            real = write_voice_wav(wav, spoken, pitch_hz=_pitch_for(speaker))
            audio_clips.append(AudioClip(
                shot_id=sh.shot_id, speaker=speaker, text=text, voice_profile=voice,
                audio_path=str(wav), duration_seconds=real, model="mock-tts-offline",
            ))
            ctx.genlog.log_media("compose/voice", "audio", "mock-tts-offline",
                                 prompt=f"{speaker}（{voice}）：{text}",
                                 params={"shot_id": sh.shot_id, "seconds": real})

            subtitle = sh.dialogue or sh.action
            video_clips.append(VideoClip(
                shot_id=sh.shot_id, scene=sh.scene, image_path=shot_img.get(sh.shot_id),
                audio_path=str(wav), subtitle=subtitle, start_seconds=round(cursor, 2),
                duration_seconds=dur, transition="硬切",
            ))
            reel_inputs.append({
                "shot_id": sh.shot_id, "scene": sh.scene,
                "image_path": shot_img.get(sh.shot_id), "subtitle": subtitle,
                "duration_seconds": dur,
            })
            cursor += dur

        total = round(cursor, 2)
        timeline = EditTimeline(
            aspect_ratio=cc.aspect_ratio, fps=cc.fps, bgm=cc.bgm_note,
            total_duration_seconds=total, clips=video_clips,
        )

        # 草样片 GIF（截断到上限，并诚实记录截断数）
        reel_shots = reel_inputs[: cc.reel_max_shots]
        truncated = len(reel_inputs) - len(reel_shots)
        reel_path = ctx.out_dir / "preview.gif"
        ok = build_reel_gif(reel_shots, reel_path,
                            canvas=(cc.reel_width, round(cc.reel_width * 16 / 9)))
        reel_str = str(reel_path) if ok else None
        if ok:
            ctx.genlog.log_media("compose/reel", "video", "pillow-gif-offline",
                                 prompt="草样片故事板卷（占位）",
                                 params={"shots": len(reel_shots), "seconds": total})

        # FFmpeg 真实成片脚本（升级路径）
        script_path = write_ffmpeg_scripts(ctx.out_dir, reel_inputs)

        note = (
            f"离线合成：{len(audio_clips)} 段占位配音 + 草样片 GIF（{len(reel_shots)} 镜）"
            f"{'，已截断 %d 镜' % truncated if truncated else ''}；"
            "并产出剪辑时间线与 FFmpeg 成片脚本。真实视频/配音在阶段二替换占位实现。"
        )
        if truncated:
            print(f"   [提示] 草样片仅收录前 {len(reel_shots)} 镜，截断 {truncated} 镜（可调 config.compose.reel_max_shots）")

        # 时间线单独落盘，便于查看/对接剪辑
        (ctx.out_dir / "timeline.json").write_text(
            timeline.model_dump_json(indent=2), encoding="utf-8")

        state.compose = ComposeResult(
            timeline=timeline, audio_clips=audio_clips, reel_path=reel_str,
            assemble_script=str(script_path), shots_total=len(reel_inputs),
            shots_in_reel=len(reel_shots), note=note, model="offline-postprod",
        )
