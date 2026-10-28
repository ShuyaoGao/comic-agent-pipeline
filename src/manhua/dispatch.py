"""
多模型调度（需求文档 4.6「视频生成多模型调度，不绑死一个模型」/ 第十章 10.3）。

视频是成本大头（见 costing），且不同镜头对"画质/一致性/真实度"的需求不同。
本模块按规则为每个镜头选择**图像模型 + 视频方案**，并与成本控制联动：
  - 关键镜（特写/近景、多角色同框、高情绪、首尾镜）→ 强一致性图像模型 + 真实视频；
  - 普通镜 → 性价比图像模型 + 分镜图占位/图生视频（草样片即此思路）。
据此只对"少数关键镜"花真实视频的钱，显著降本（对照腾讯云"按需高清"思路）。

非工作流阶段：运行后对 storyboard 的一次确定性规则调度（模型名全部取自 config，可配置）。
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .engine import ProjectState
from .schemas import DispatchPlan, DispatchShot

_HIGH_EMOTION = ["紧张", "对峙", "决", "高潮", "冲突", "危", "震撼", "爆发"]
_CLOSE_SHOTS = ["特写", "近景"]


def _seconds(duration: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", duration or "")
    return float(m.group(1)) if m else 5.0


def _importance(shot, idx: int, total: int) -> int:
    score = 0
    if shot.camera.shot_size in _CLOSE_SHOTS:
        score += 2
    if len(shot.characters) >= 2:
        score += 1
    if any(k in (shot.emotion or "") for k in _HIGH_EMOTION):
        score += 1
    if idx == 0 or idx == total - 1:   # 首尾镜更重要
        score += 1
    return score


def dispatch_models(state: ProjectState, config: Config) -> DispatchPlan:
    dc = config.dispatch
    shots = state.storyboard.shots if state.storyboard else []
    total = len(shots)

    scored = []
    for i, sh in enumerate(shots):
        scored.append((i, sh, _importance(sh, i, total)))

    # 取重要度最高的前 key_shot_max 镜用真实视频（同分按出现顺序）
    order = sorted(scored, key=lambda t: (-t[2], t[0]))
    real_ids = {t[1].shot_id for t in order[: max(0, dc.key_shot_max)]}

    dshots: list[DispatchShot] = []
    for i, sh, imp in scored:
        strong = imp >= 2
        is_real = sh.shot_id in real_ids
        reasons = []
        if sh.camera.shot_size in _CLOSE_SHOTS:
            reasons.append("特写/近景需强一致性")
        if len(sh.characters) >= 2:
            reasons.append("多角色同框")
        if any(k in (sh.emotion or "") for k in _HIGH_EMOTION):
            reasons.append("高情绪关键镜")
        if i == 0 or i == total - 1:
            reasons.append("首/尾镜")
        if not reasons:
            reasons.append("常规镜，走性价比方案")
        dshots.append(DispatchShot(
            shot_id=sh.shot_id, importance=imp,
            image_model=dc.image_model_strong if strong else dc.image_model_cheap,
            video_model=dc.video_model_real if is_real else dc.video_placeholder,
            real_video=is_real, reason="；".join(reasons) + ("｜真实视频" if is_real else "｜占位/图生视频"),
        ))

    price = config.cost.video_per_second_usd
    full = round(sum(_seconds(s.duration) for s in shots) * price, 4)
    dispatched = round(sum(_seconds(s.duration) for s in shots if s.shot_id in real_ids) * price, 4)

    return DispatchPlan(
        shots=dshots,
        real_video_shots=len(real_ids),
        placeholder_shots=total - len(real_ids),
        full_video_cost_usd=full,
        dispatched_video_cost_usd=dispatched,
        note=(
            f"按规则把 {total} 镜分流：{len(real_ids)} 个关键镜用真实视频({dc.video_model_real})，"
            f"其余 {total - len(real_ids)} 镜用占位/图生视频({dc.video_placeholder})；"
            f"图像按重要度在 {dc.image_model_strong}/{dc.image_model_cheap} 间择优。"
            f"视频成本由全量 ${full} 降到 ${dispatched}（省 ${round(full - dispatched, 4)}）。"
            "模型名均取自 config.dispatch，可随生态更新（需求文档 4.6：不绑死单一模型）。"
        ),
    )


def save_dispatch_plan(plan: DispatchPlan, out_dir: Path) -> Path:
    path = out_dir / "model_dispatch.json"
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return path
