"""
成本控制（需求文档 第五章 14 Agent 之「成本控制 Agent」 / 第十一章按量计费）。

漫剧视频按秒/按 token 计费，几十镜的片子成本不低。本模块在**离线 mock 下也能**
回答一个关键问题：「这一片子若改用真实云端模型生产，大约要花多少钱？」——
据此做模型选择与降本决策。它不是工作流阶段，而是运行后对 state + 生成日志的一次确定性核算。

口径：
  - 文本(LLM)：用生成日志里**真实的 token 计数**（mock 也按长度估了 token）× llm 配置单价。
  - 图像：图像生成次数（角色参考图 + 分镜图）× image 配置单价。
  - 视频：各镜时长之和（秒）× cost.video_per_second_usd（真实视频才会产生）。
  - 配音：台词/旁白总字数 × cost.tts_per_1k_chars_usd（本地 TTS 可为 0）。
"""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .engine import ProjectState
from .genlog import GenerationLog
from .schemas import CostLine, CostReport


def _shot_seconds(duration: str) -> float:
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", duration or "")
    return float(m.group(1)) if m else 5.0


def estimate_cost(state: ProjectState, genlog: GenerationLog, config: Config) -> CostReport:
    llm = config.llm
    # —— 文本(LLM)：用日志里的真实 token 数 ——
    in_tok = sum(r.input_tokens for r in genlog.records)
    out_tok = sum(r.output_tokens for r in genlog.records)
    llm_usd = in_tok / 1_000_000 * llm.price_input_per_mtok_usd \
        + out_tok / 1_000_000 * llm.price_output_per_mtok_usd

    # —— 图像：角色参考图 + 分镜图 ——
    n_img = 0
    if state.art:
        n_img = len(state.art.character_references) + len(state.art.shot_images)
    img_usd = n_img * config.image.price_per_image_usd

    # —— 视频：各镜时长之和（真实视频才花钱）——
    total_sec = 0.0
    n_shots = 0
    if state.storyboard:
        n_shots = len(state.storyboard.shots)
        total_sec = sum(_shot_seconds(s.duration) for s in state.storyboard.shots)
    video_usd = total_sec * config.cost.video_per_second_usd

    # —— 配音：台词/旁白总字数 ——
    n_chars = 0
    if state.compose:
        n_chars = sum(len(a.text) for a in state.compose.audio_clips)
    elif state.storyboard:
        n_chars = sum(len(s.dialogue) for s in state.storyboard.shots)
    tts_usd = n_chars / 1000 * config.cost.tts_per_1k_chars_usd

    lines = [
        CostLine(category="文本生成(LLM)", quantity=f"{in_tok}+{out_tok} tokens",
                 unit_price=f"${llm.price_input_per_mtok_usd}/{llm.price_output_per_mtok_usd} 每百万(入/出)",
                 estimated_usd=round(llm_usd, 6),
                 note="命中缓存可再降一个量级；可用更便宜模型做初稿、强模型只做审稿"),
        CostLine(category="图像生成(分镜图+参考图)", quantity=f"{n_img} 张",
                 unit_price=f"${config.image.price_per_image_usd}/张",
                 estimated_usd=round(img_usd, 6),
                 note="先低分辨率出草图、定稿再高清；批量复用角色参考图"),
        CostLine(category="视频生成", quantity=f"{n_shots} 镜 / 约 {total_sec:.0f}s",
                 unit_price=f"${config.cost.video_per_second_usd}/秒",
                 estimated_usd=round(video_usd, 6),
                 note="视频最贵；可只对关键镜出真实视频，其余用分镜图+轻动效（先低分辨率出片再转码，可进一步降本）"),
        CostLine(category="配音(TTS)", quantity=f"约 {n_chars} 字",
                 unit_price=f"${config.cost.tts_per_1k_chars_usd}/千字",
                 estimated_usd=round(tts_usd, 6),
                 note="本地开源 TTS 可做到 ~0 成本"),
    ]
    est_total = round(llm_usd + img_usd + video_usd + tts_usd, 4)
    actual = round(sum(r.cost_usd for r in genlog.records), 6)

    return CostReport(
        actual_cost_usd=actual,
        estimated_real_cost_usd=est_total,
        lines=lines,
        assumptions=[
            f"LLM 单价取自 config.llm（{llm.model}）：入 ${llm.price_input_per_mtok_usd}/出 ${llm.price_output_per_mtok_usd} 每百万 token",
            f"图像 ${config.image.price_per_image_usd}/张、视频 ${config.cost.video_per_second_usd}/秒、TTS ${config.cost.tts_per_1k_chars_usd}/千字（均为 2026-05 示意值）",
            "以上为『若用真实云端模型生产本片』的估算；当前 mock 实跑成本为 $0。务必上线前核对各家真实定价。",
        ],
        saving_tips=[
            "视频是大头：只对关键镜生成真实视频，其余镜用分镜图 + 轻动效（草样片即此思路）。",
            "图像先低分辨率出草、定稿再高清；角色参考图跨镜复用，减少重复出图。",
            "LLM 善用 prompt 缓存与便宜模型分工（初稿便宜、审稿强模型），可显著降本。",
            "配音优先本地开源 TTS，接近零成本。",
        ],
    )


def save_cost_report(report: CostReport, out_dir: Path) -> Path:
    path = out_dir / "cost_report.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
