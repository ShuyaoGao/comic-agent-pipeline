#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""成本控制（需求文档 第五/十一章）测试：离线实跑成本=0，真实模型估算合理且视频占大头。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _util import Checker, run_pipeline, ROOT
sys.path.insert(0, str(ROOT / "src"))
from manhua.costing import estimate_cost  # noqa: E402


def main() -> int:
    c = Checker()
    with tempfile.TemporaryDirectory() as tmp:
        state, ctx, cfg = run_pipeline(Path(tmp) / "p")
        rep = estimate_cost(state, ctx.genlog, cfg)

        c.ok("离线实跑成本 = 0", rep.actual_cost_usd == 0.0)
        c.ok("真实模型估算 > 0", rep.estimated_real_cost_usd > 0)
        cats = {l.category for l in rep.lines}
        c.ok("含 文本/图像/视频/配音 四类", {"文本生成(LLM)", "图像生成(分镜图+参考图)", "视频生成", "配音(TTS)"} <= cats)
        by = {l.category: l.estimated_usd for l in rep.lines}
        c.ok("视频是成本大头", by["视频生成"] == max(by.values()))
        c.ok("有降本建议", len(rep.saving_tips) >= 2)
        c.ok("有估算假设(提示上线核对)", any("核对" in s for s in rep.assumptions))

        # 估算总额 ≈ 各行之和
        s = round(sum(l.estimated_usd for l in rep.lines), 4)
        c.ok(f"估算总额≈各行之和（{rep.estimated_real_cost_usd} vs {s}）",
             abs(rep.estimated_real_cost_usd - s) < 0.01)

    return c.done("成本控制测试")


if __name__ == "__main__":
    raise SystemExit(main())
