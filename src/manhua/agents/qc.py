"""
质检 Agent（需求文档 第八章 8 维质量指标 + 第十章 10.3 角色一致性检测，前移到 MVP）。

这是确定性检测（非 LLM）：把平台命门"角色一致性"做成**可量化、可复核**的硬指标，
并对结构完整性 / 镜头连贯性 / 音画同步 / 时长与平台适配做客观检查。
教学价值：让"一致性"从一句口号变成能打分、能定位问题的工程指标。
"""
from __future__ import annotations

from pathlib import Path

from ..engine import ProjectState, RunContext
from ..schemas import QCMetric, QCReport

# negative_prompt 里出现这些词，视为对"角色漂移"做了抑制
_ANTI_DRIFT = ["漂移", "发色", "瞳色", "服装", "一致", "畸形"]


class QCAgent:
    key = "qc"
    display_name = "质检 Agent"

    def run(self, state: ProjectState, ctx: RunContext) -> None:
        chars = state.characters.characters if state.characters else []
        shots = state.storyboard.shots if state.storyboard else []
        seed_by_id = {c.character_id: c.reference_seed for c in chars}
        ref_by_id = {c.character_id: c.reference_image for c in chars}
        fixed_by_id = {c.character_id: c.fixed_visual_features for c in chars}
        valid_ids = set(seed_by_id)
        shot_asset = {a.ref_id: a for a in state.art.shot_images} if state.art else {}

        issues: list[str] = []
        metrics: list[QCMetric] = []

        # ---------- 1) 角色一致性（命门）----------
        ratios: list[float] = []
        cons_issues: list[str] = []
        for sh in shots:
            if not sh.characters:
                continue
            anchor = sh.characters[0]
            asset = shot_asset.get(sh.shot_id)
            checks = {
                "seed复用": bool(asset and asset.seed == seed_by_id.get(anchor)),
                "参考图复用": bool(asset and asset.reference_image == ref_by_id.get(anchor)),
                "固定特征入image_prompt": any(f in (sh.image_prompt or "") for f in fixed_by_id.get(anchor, [])),
                "负面词抑制漂移": bool(sh.negative_prompt) and any(k in sh.negative_prompt for k in _ANTI_DRIFT),
            }
            passed = sum(checks.values())
            ratios.append(passed / len(checks))
            for name, okk in checks.items():
                if not okk:
                    cons_issues.append(f"{sh.shot_id}: 未满足『{name}』")
        consistency_score = round(sum(ratios) / len(ratios), 3) if ratios else 1.0
        metrics.append(QCMetric(
            dimension="人物一致性", score=round(consistency_score * 10, 1),
            detail=f"对 {len(ratios)} 个有角色的镜头做 4 项一致性检查（seed/参考图复用 + 提示词双侧约束）",
            issues=cons_issues[:12],
        ))
        issues += cons_issues[:6]

        # ---------- 2) 结构完整性 ----------
        struct_checks, struct_issues = [], []
        for sh in shots:
            for cid in sh.characters:
                ok_id = cid in valid_ids
                struct_checks.append(ok_id)
                if not ok_id:
                    struct_issues.append(f"{sh.shot_id}: 引用了不存在的 character_id {cid}")
        appeared = {cid for sh in shots for cid in sh.characters}
        for c in chars:
            ok_app = c.character_id in appeared
            struct_checks.append(ok_app)
            if not ok_app:
                struct_issues.append(f"角色 {c.character_id} {c.name} 未出现在任何镜头")
        for sh in shots:
            asset = shot_asset.get(sh.shot_id)
            ok_img = bool(asset and Path(asset.image_path).exists())
            struct_checks.append(ok_img)
            if not ok_img:
                struct_issues.append(f"{sh.shot_id}: 缺少分镜图文件")
        struct_score = 10.0 * (sum(struct_checks) / len(struct_checks)) if struct_checks else 10.0
        metrics.append(QCMetric(
            dimension="结构完整性", score=round(struct_score, 1),
            detail="校验 character_id 引用合法、角色均有出镜、每镜分镜图已落盘",
            issues=struct_issues[:12]))
        issues += struct_issues[:6]

        # ---------- 3) 镜头连贯性 ----------
        cont_issues = []
        seq_ok = all(sh.shot_id == f"S{i+1:02d}" for i, sh in enumerate(shots))
        if not seq_ok:
            cont_issues.append("镜头编号非连续 S01..SNN")
        empty_scene = [sh.shot_id for sh in shots if not sh.scene]
        if empty_scene:
            cont_issues.append(f"以下镜头缺少场景：{empty_scene}")
        cont_score = 10.0 - 2.0 * len(cont_issues)
        metrics.append(QCMetric(
            dimension="镜头连贯性", score=round(max(0.0, cont_score), 1),
            detail="检查镜号连续性与场景完整性（成片级连贯性需视频阶段再评）", issues=cont_issues))

        # ---------- 4) 音画同步（依赖合成阶段）----------
        if state.compose:
            clips = state.compose.timeline.clips
            audio_by_shot = {a.shot_id: a for a in state.compose.audio_clips}
            fit = 0
            sync_issues = []
            for cl in clips:
                a = audio_by_shot.get(cl.shot_id)
                if a and a.duration_seconds <= cl.duration_seconds + 0.01:
                    fit += 1
                else:
                    sync_issues.append(f"{cl.shot_id}: 配音时长超出镜头时长或缺失")
            sync_score = 10.0 * (fit / len(clips)) if clips else 0.0
            metrics.append(QCMetric(
                dimension="音画同步", score=round(sync_score, 1),
                detail=f"{fit}/{len(clips)} 镜配音时长落在镜头时长内（占位音轨，真实口型对齐待阶段二）",
                issues=sync_issues[:8]))
        else:
            metrics.append(QCMetric(dimension="音画同步", score=0.0,
                                    detail="未运行合成阶段", issues=["缺少 compose 产出"]))

        # ---------- 5) 成片可用率 / 时长达标 ----------
        target = state.script.target_duration_seconds if state.script else 45
        total = state.compose.timeline.total_duration_seconds if state.compose else 0.0
        ratio = (total / target) if target else 0.0
        # 与目标时长越接近越高分；0.7~1.3 倍视为达标
        dur_score = max(0.0, 10.0 - abs(1.0 - ratio) * 12.0)
        dur_issues = [] if 0.7 <= ratio <= 1.3 else [f"成片时长 {total}s 与目标 {target}s 偏差较大（{ratio:.2f}x）"]
        metrics.append(QCMetric(
            dimension="成片可用率", score=round(min(10.0, dur_score), 1),
            detail=f"草样片总时长 {total}s vs 目标 {target}s", issues=dur_issues))

        # ---------- 6) 平台适配度 ----------
        aspect = state.compose.timeline.aspect_ratio if state.compose else "?"
        plat_ok = aspect == "9:16" and total <= 90
        metrics.append(QCMetric(
            dimension="平台适配度", score=10.0 if plat_ok else 6.0,
            detail=f"画幅 {aspect}，时长 {total}s（竖屏短视频偏好 9:16 且 ≤90s）",
            issues=[] if plat_ok else ["画幅或时长不完全契合竖屏短视频"]))

        overall = round(sum(m.score for m in metrics) / len(metrics), 2)
        passed = consistency_score >= 0.8 and not struct_issues
        state.qc = QCReport(
            consistency_score=consistency_score, metrics=metrics,
            overall_score=overall, passed=passed, issues=issues[:12],
            note=(
                "确定性质检（非 LLM）：角色一致性=每镜 seed/参考图复用 + 提示词双侧约束的达成率；"
                "另含结构完整性/镜头连贯性/音画同步/时长与平台适配。真实画面级一致性(人脸相似度)待阶段二接检测模型。"
            ),
        )
        print(f"   [质检] 角色一致性 {consistency_score:.2f} ｜ 综合 {overall}/10 ｜ {'通过' if passed else '需关注'}")
