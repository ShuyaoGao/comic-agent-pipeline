"""
项目资产库雏形（需求文档 第七章）。

没有资产库，平台只是一次性生成工具；有资产库，才能支撑系列化漫剧与团队协作。
MVP 阶段把本次运行产出的角色/场景/分镜/提示词资产建立索引并落盘为 asset_library.json，
视频/音频/道具资产先建空类目并标注『阶段二接入』。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import ProjectState


def build_asset_library(state: ProjectState) -> dict[str, Any]:
    lib: dict[str, Any] = {
        "project_id": state.project_id,
        "created_at": state.created_at,
        "character_assets": [],
        "scene_assets": [],
        "prop_assets": {"items": [], "note": "MVP 未生成；阶段二由分镜/资产管理补充"},
        "storyboard_assets": [],
        "director_assets": [],
        "video_assets": {"items": [], "note": "草样片(GIF)与剪辑时间线已生成；真实视频(云端或本地视频模型)阶段二替换占位"},
        "audio_assets": {"items": [], "note": "占位配音(.wav)已生成；真实配音(开源或云端 TTS)阶段二替换"},
        "prompt_assets": [],
    }

    # 导演台资产（俯视构图图 + 可控镜头参数）
    if state.director:
        for ds in state.director.shots:
            lib["director_assets"].append({
                "shot_id": ds.shot_id, "blocking_diagram": ds.blocking_diagram,
                "camera_height": ds.camera_height, "framing": ds.framing,
                "light_direction": ds.light_direction,
            })

    # 视频/音频资产（来自合成 Agent，阶段二雏形）
    if state.compose:
        if state.compose.reel_path:
            lib["video_assets"]["items"].append({
                "type": "reel_preview", "path": state.compose.reel_path,
                "total_duration_seconds": state.compose.timeline.total_duration_seconds,
                "aspect_ratio": state.compose.timeline.aspect_ratio,
            })
        for cl in state.compose.timeline.clips:
            lib["video_assets"]["items"].append({
                "type": "clip", "shot_id": cl.shot_id, "image_path": cl.image_path,
                "start": cl.start_seconds, "duration": cl.duration_seconds,
            })
        for a in state.compose.audio_clips:
            lib["audio_assets"]["items"].append({
                "shot_id": a.shot_id, "speaker": a.speaker, "voice_profile": a.voice_profile,
                "audio_path": a.audio_path, "duration_seconds": a.duration_seconds,
            })

    # 角色资产
    if state.characters:
        for c in state.characters.characters:
            lib["character_assets"].append({
                "character_id": c.character_id, "name": c.name,
                "reference_image": c.reference_image, "reference_seed": c.reference_seed,
                "voice_profile": c.voice_profile,
                "fixed_visual_features": c.fixed_visual_features,
                "forbidden_changes": c.forbidden_changes,
            })

    # 场景资产（从剧本去重）
    if state.script:
        seen = set()
        for sc in state.script.scenes:
            if sc.location not in seen:
                seen.add(sc.location)
                lib["scene_assets"].append({"location": sc.location, "first_seen_scene": sc.scene_id})

    # 分镜资产 + 提示词资产
    shot_img = {}
    if state.art:
        shot_img = {a.ref_id: a.image_path for a in state.art.shot_images}
    if state.storyboard:
        for sh in state.storyboard.shots:
            lib["storyboard_assets"].append({
                "shot_id": sh.shot_id, "scene": sh.scene,
                "characters": sh.characters, "image_path": shot_img.get(sh.shot_id),
                "duration": sh.duration,
            })
            lib["prompt_assets"].append({
                "shot_id": sh.shot_id,
                "image_prompt": sh.image_prompt,
                "video_prompt": sh.video_prompt,
                "negative_prompt": sh.negative_prompt,
            })
    return lib


def save_asset_library(state: ProjectState, out_dir: Path) -> Path:
    lib = build_asset_library(state)
    path = out_dir / "asset_library.json"
    path.write_text(json.dumps(lib, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_report(state: ProjectState, out_dir: Path, genlog_summary: dict,
                 cost_report=None, dispatch_plan=None) -> Path:
    """生成人类可读的 Markdown 复盘报告。"""
    lines: list[str] = []
    a = lines.append
    a(f"# 漫剧项目复盘 · {state.project_id}\n")
    a(f"- 创意输入：{state.idea_text}")
    a(f"- 创建时间：{state.created_at}\n")

    if state.idea:
        a("## 一、选题")
        a(f"- 题材：{state.idea.genre} ｜ 受众：{state.idea.target_audience}")
        a(f"- 前提：{state.idea.premise}")
        a(f"- 核心冲突：{state.idea.core_conflict}")
        a(f"- 开头钩子：{state.idea.opening_hook}\n")

    if state.script:
        a("## 二、剧本")
        a(f"- 标题：{state.script.title}")
        a(f"- Logline：{state.script.logline}")
        a(f"- 平台/时长：{state.script.target_platform} ｜ {state.script.target_duration_seconds}s")
        a(f"- 场景数：{len(state.script.scenes)}\n")

    if state.review:
        a("## 三、审稿与合规")
        a(f"- 合规判定：**{state.review.compliance_status}** ｜ 建议进入下一阶段：{state.review.overall_pass}")
        for n in state.review.compliance_notes:
            a(f"  - {n}")
        a("- 八维质量评分（需求文档 8.1）：")
        for q in state.review.quality_scores:
            s = "待后期" if q.score is None else q.score
            a(f"  - {q.dimension}：{s} —— {q.comment}")
        a("")

    if state.characters:
        a("## 四、角色设定（严格对齐 需求文档 附录 12.1）")
        for c in state.characters.characters:
            a(f"- **{c.character_id} {c.name}**（{c.age}岁，{c.identity}）")
            a(f"  - 固定外貌：{'、'.join(c.fixed_visual_features)}")
            a(f"  - 不可变化：{'、'.join(c.forbidden_changes)}")
            a(f"  - 音色：{c.voice_profile} ｜ 锁定 seed：{c.reference_seed}")
        a(f"- 一致性策略：{state.characters.consistency_strategy}\n")

    if state.storyboard:
        a("## 五、分镜表（严格对齐 需求文档 附录 12.2）")
        for sh in state.storyboard.shots:
            a(f"- **{sh.shot_id}** [{sh.scene}] 角色{sh.characters} ｜ {sh.camera.shot_size}/{sh.camera.angle}/{sh.camera.movement} ｜ {sh.duration}")
            a(f"  - 动作：{sh.action}")
            a(f"  - image_prompt：{sh.image_prompt}")
            a(f"  - video_prompt：{sh.video_prompt}")
        a("")

    if state.director:
        a("## 六、导演台预演（需求文档 第六章，可控镜头参数 + 俯视构图图）")
        for ds in state.director.shots:
            pos = "、".join(f"{x.character_id}({x.x},{x.y},{x.facing})" for x in ds.actors)
            a(f"- **{ds.shot_id}** 机位：{ds.camera_height} ｜ 焦段：{ds.focal_hint}")
            a(f"  - 构图：{ds.framing}")
            a(f"  - 灯光：{ds.light_direction}")
            a(f"  - 站位：{pos}")
            a(f"  - 俯视构图图：{ds.blocking_diagram}")
        a(f"- 说明：{state.director.note}\n")

    if state.art:
        a("## 七、美术产出（占位图，演示一致性）")
        a(f"- 角色参考图：{len(state.art.character_references)} 张 ｜ 分镜图：{len(state.art.shot_images)} 张")
        a(f"- 一致性说明：{state.art.consistency_note}\n")

    if state.compose:
        cp = state.compose
        a("## 八、合成/后期（需求文档 4.7，阶段二雏形）")
        a(f"- 草样片预览：{cp.reel_path or '（未生成）'}")
        a(f"- 剪辑时间线：{len(cp.timeline.clips)} 段 ｜ 总时长 {cp.timeline.total_duration_seconds}s ｜ 画幅 {cp.timeline.aspect_ratio} ｜ {cp.timeline.fps}fps")
        a(f"- 占位配音：{len(cp.audio_clips)} 段（.wav，记录音色与时长）")
        a(f"- 真实成片脚本：{cp.assemble_script}（装 FFmpeg 后可一键拼 mp4）")
        a(f"- 说明：{cp.note}\n")

    if state.qc:
        q = state.qc
        a("## 九、质检（需求文档 第八章 / 10.3 角色一致性检测）")
        a(f"- **角色一致性得分：{q.consistency_score:.2f}（命门指标，1.0 满分）**")
        a(f"- 综合得分：{q.overall_score}/10 ｜ 质检结论：{'通过' if q.passed else '需关注'}")
        for m in q.metrics:
            a(f"  - {m.dimension}：{m.score}/10 —— {m.detail}")
            for it in m.issues[:3]:
                a(f"    · 问题：{it}")
        a("")

    if cost_report is not None:
        a("## 十、成本估算（需求文档 成本控制）")
        a(f"- 本次实跑成本：**${cost_report.actual_cost_usd}**（mock 离线，零花费）")
        a(f"- 若用真实云端模型生产本片估算：**${cost_report.estimated_real_cost_usd}**")
        for l in cost_report.lines:
            a(f"  - {l.category}：{l.quantity} × {l.unit_price} ≈ ${l.estimated_usd}")
        a("- 降本建议：")
        for t in cost_report.saving_tips:
            a(f"  - {t}")
        a("- 估算假设（务必上线前核对）：")
        for s in cost_report.assumptions:
            a(f"  - {s}")
        a("")

    if dispatch_plan is not None:
        a("## 十一、多模型调度（需求文档 4.6：不绑死一个模型）")
        a(f"- 关键镜真实视频 {dispatch_plan.real_video_shots} 个 ｜ 占位/图生视频 {dispatch_plan.placeholder_shots} 个")
        a(f"- 视频成本：全量 ${dispatch_plan.full_video_cost_usd} → 调度后 ${dispatch_plan.dispatched_video_cost_usd}")
        for d in dispatch_plan.shots:
            a(f"  - {d.shot_id}（重要度{d.importance}）→ 图像 {d.image_model} ｜ 视频 {d.video_model}：{d.reason}")
        a(f"- 说明：{dispatch_plan.note}\n")

    a("## 十二、生成日志汇总（需求文档 第七章）")
    for k, v in genlog_summary.items():
        a(f"- {k}：{v}")
    a("\n> 详见 generation_log.jsonl（逐条记录模型/提示词/参考图/参数/成本/是否采用）。")

    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
