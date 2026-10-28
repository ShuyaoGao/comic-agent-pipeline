#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
质检"反例"测试：证明角色一致性检测不是恒等于 1.0，而是真的能抓到不一致。
做法：跑完流水线后人为破坏一镜（用错 seed / 丢掉固定特征 / 引用不存在角色），
再单独重跑质检，断言分数下降且报出对应问题。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _util import Checker, run_pipeline, ROOT
sys.path.insert(0, str(ROOT / "src"))
from manhua.agents.qc import QCAgent  # noqa: E402


def _rerun_qc(state, ctx):
    state.qc = None
    QCAgent().run(state, ctx)
    return state.qc


def main() -> int:
    c = Checker()
    with tempfile.TemporaryDirectory() as tmp:
        state, ctx, cfg = run_pipeline(Path(tmp) / "p")

        # 基线：正常情况应为满分一致性
        base = state.qc.consistency_score
        c.ok("基线角色一致性 = 1.0", base >= 0.99)

        # 破坏 1：第一张分镜图用错 seed（模拟跨镜变脸）
        state.art.shot_images[0].seed = 999999999
        qc1 = _rerun_qc(state, ctx)
        c.ok("用错 seed 后一致性下降", qc1.consistency_score < base)
        c.ok("报出 seed 复用问题", any("seed" in i for i in qc1.metrics[0].issues))

        # 恢复，破坏 2：分镜图丢掉参考图（模拟没锚定参考图）
        state2, ctx2, _ = run_pipeline(Path(tmp) / "p2")
        state2.art.shot_images[0].reference_image = None
        qc2 = _rerun_qc(state2, ctx2)
        c.ok("丢参考图后一致性下降", qc2.consistency_score < 1.0)

        # 破坏 3：某镜引用不存在的 character_id（结构完整性）
        state3, ctx3, _ = run_pipeline(Path(tmp) / "p3")
        state3.storyboard.shots[0].characters = ["CHAR_999"]
        qc3 = _rerun_qc(state3, ctx3)
        struct = next(m for m in qc3.metrics if m.dimension == "结构完整性")
        c.ok("引用不存在角色 → 结构完整性扣分", struct.score < 10.0)
        c.ok("结构问题被报出", any("CHAR_999" in i for i in struct.issues))
        c.ok("整体质检判为需关注", qc3.passed is False)

    return c.done("质检反例测试")


if __name__ == "__main__":
    raise SystemExit(main())
