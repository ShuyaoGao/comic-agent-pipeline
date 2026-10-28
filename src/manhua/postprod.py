"""
后期合成工具（需求文档 4.7 自动剪辑与后期）—— 全部离线、零依赖外部服务。

三件事，都用标准库 / Pillow 完成，保证零预算、无 GPU、无 FFmpeg 也能产出可演示物：
  1. mock 配音：用标准库 wave 写出占位 .wav（按字数估时长 + 极低音量提示音），
     代表"配音轨"的时长与存在，供剪辑时间线对齐。真实 TTS（CosyVoice/IndexTTS）阶段二替换。
  2. 草样片：用 Pillow 把各分镜图合成一个带字幕、轻微缩放(Ken Burns)的 GIF"故事板卷"，
     主机不装任何视频软件也能直接播放预览。真实视频（可灵/Wan2.2）阶段二替换。
  3. 真实成片脚本：生成 FFmpeg 命令脚本（assemble.ps1 / assemble.sh），
     当主机装了 FFmpeg、且有真实分镜图/配音时，一键拼成 9:16 mp4。

设计原则：能离线产出"看得见、听得见时长"的草样片，又为真实成片留好可执行的升级路径。
"""
from __future__ import annotations

import array
import math
import wave
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

# 复用占位图模块里的中文字体加载与换行（避免重复实现）
from .image.placeholder import _load_font, _wrap_cjk


def estimate_speech_seconds(text: str, *, max_seconds: float = 8.0) -> float:
    """按字数粗估中文配音时长（约 4.5 字/秒），夹在 [0.6, max] 之间。"""
    n = len([c for c in text if c.strip()])
    return max(0.6, min(max_seconds, round(n / 4.5 + 0.4, 2)))


def write_voice_wav(out_path: Path, seconds: float, *, pitch_hz: float = 180.0,
                    amplitude: float = 0.06, rate: int = 16000) -> float:
    """
    写一段占位配音 .wav（单声道 16bit）。极低音量正弦 + 首尾淡入淡出，
    用来"占位"配音轨的时长与存在（不是真实语音合成）。返回实际时长(秒)。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = max(1, int(seconds * rate))
    fade = max(1, int(0.04 * rate))
    buf = array.array("h", bytes(2 * n))  # 全 0 初始化
    for i in range(n):
        env = min(1.0, i / fade) * min(1.0, (n - i) / fade)
        val = amplitude * env * math.sin(2 * math.pi * pitch_hz * (i / rate))
        buf[i] = int(val * 32767)
    with wave.open(str(out_path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(buf.tobytes())
    return round(n / rate, 3)


def _reel_frame(src: Optional[Image.Image], canvas: tuple[int, int], zoom: float,
                subtitle: str, header: str) -> Image.Image:
    """生成草样片的一帧：9:16 黑底 + 居中分镜图(带缩放) + 顶部镜号 + 底部字幕。"""
    cw, ch = canvas
    frame = Image.new("RGB", (cw, ch), (8, 10, 14))
    img_area_h = int(ch * 0.74)        # 上方画面区
    if src is not None:
        sw, sh = src.size
        scale = (cw / sw) * zoom        # 以宽度铺满再乘以缩放系数(Ken Burns)
        nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
        im = src.resize((nw, nh))
        frame.paste(im, ((cw - nw) // 2, (img_area_h - nh) // 2))

    draw = ImageDraw.Draw(frame)
    # 顶部镜号条
    draw.rectangle([0, 0, cw, 40], fill=(0, 0, 0))
    draw.text((12, 9), header, font=_load_font(20), fill=(220, 230, 235))
    # 底部字幕条
    sub_top = ch - int(ch * 0.20)
    draw.rectangle([0, sub_top, cw, ch], fill=(0, 0, 0))
    f_sub = _load_font(22)
    y = sub_top + 12
    for line in _wrap_cjk(subtitle, max_chars=max(8, cw // 24))[:3]:
        wln = draw.textlength(line, font=f_sub)
        draw.text(((cw - wln) // 2, y), line, font=f_sub, fill=(245, 245, 245))
        y += 30
    return frame


def build_reel_gif(clips: list[dict], out_path: Path, *, canvas=(360, 640),
                   frames_per_shot: int = 4) -> bool:
    """
    把各分镜图合成草样片 GIF（每镜按其时长停留，含 Ken Burns 轻缩放 + 字幕）。
    clips: [{shot_id, scene, image_path, subtitle, duration_seconds}]
    返回是否成功生成。
    """
    frames: list[Image.Image] = []
    durations: list[int] = []
    for c in clips:
        src = None
        p = c.get("image_path")
        if p and Path(p).exists():
            try:
                src = Image.open(p).convert("RGB")
            except Exception:
                src = None
        header = f"{c['shot_id']} · {c.get('scene', '')}"
        per = max(1, int(c["duration_seconds"] * 1000 / frames_per_shot))
        for f in range(frames_per_shot):
            zoom = 1.0 + 0.06 * (f / max(1, frames_per_shot - 1))  # 1.00 → 1.06
            frames.append(_reel_frame(src, canvas, zoom, c.get("subtitle", ""), header))
            durations.append(per)
    if not frames:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    return True


def write_ffmpeg_scripts(out_dir: Path, clips: list[dict]) -> Path:
    """
    生成真实成片用的 FFmpeg 脚本（.ps1 + .sh）。装了 FFmpeg、且有真实分镜图/配音时，
    一键把"每镜图 + 配音"拼成 9:16 mp4。MVP 离线不执行，仅产出脚本（升级路径）。
    返回 .ps1 路径。
    """
    # concat 输入清单（图片按时长展示）
    lines_concat = []
    for c in clips:
        img = c.get("image_path")
        if not img:
            continue
        rel = Path(img).as_posix()
        lines_concat.append(f"file '{rel}'")
        lines_concat.append(f"duration {c['duration_seconds']}")
    if lines_concat and clips:  # concat demuxer 要求最后一张图再写一次
        last = clips[-1].get("image_path")
        if last:
            lines_concat.append(f"file '{Path(last).as_posix()}'")
    (out_dir / "frames.txt").write_text("\n".join(lines_concat) + "\n", encoding="utf-8")

    # 拼接所有配音为一条音轨
    audio_list = [c.get("audio_path") for c in clips if c.get("audio_path")]
    (out_dir / "audio_list.txt").write_text(
        "\n".join(f"file '{Path(a).as_posix()}'" for a in audio_list) + "\n", encoding="utf-8")

    common = (
        "# 需要本机安装 FFmpeg（https://ffmpeg.org）。本脚本把每镜分镜图按时长拼成 9:16 视频，\n"
        "# 并叠加占位配音轨，输出 preview.mp4。把分镜图换成真实视频片段即为真实成片。\n"
    )
    ps1 = out_dir / "assemble.ps1"
    sh = out_dir / "assemble.sh"
    ps1.write_text(
        common.replace("# ", "# ") +
        'Set-Location $PSScriptRoot\n'
        'ffmpeg -y -f concat -safe 0 -i frames.txt -vf "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,format=yuv420p" -r 25 _video.mp4\n'
        'ffmpeg -y -f concat -safe 0 -i audio_list.txt -c copy _audio.wav\n'
        'ffmpeg -y -i _video.mp4 -i _audio.wav -c:v copy -c:a aac -shortest preview.mp4\n'
        'Write-Host "已生成 preview.mp4"\n',
        encoding="utf-8")
    sh.write_text(
        "#!/usr/bin/env bash\nset -e\ncd \"$(dirname \"$0\")\"\n" + common +
        'ffmpeg -y -f concat -safe 0 -i frames.txt -vf "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,format=yuv420p" -r 25 _video.mp4\n'
        'ffmpeg -y -f concat -safe 0 -i audio_list.txt -c copy _audio.wav\n'
        'ffmpeg -y -i _video.mp4 -i _audio.wav -c:v copy -c:a aac -shortest preview.mp4\n'
        'echo "已生成 preview.mp4"\n',
        encoding="utf-8")
    return ps1
