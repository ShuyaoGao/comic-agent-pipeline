#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目看板（需求文档 第九章前端看板最小实现）测试：自包含 HTML、各段齐全、资产引用全部可解析。"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from _util import Checker, run_pipeline, ROOT
sys.path.insert(0, str(ROOT / "src"))
from manhua.costing import estimate_cost  # noqa: E402
from manhua.dispatch import dispatch_models  # noqa: E402
from manhua.viewer import build_viewer_html, write_viewer  # noqa: E402


def main() -> int:
    c = Checker()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "p"
        state, ctx, cfg = run_pipeline(out_dir)   # 会把分镜图/俯视图/草样片/配音落到 out_dir
        summary = ctx.genlog.summary()
        cost = estimate_cost(state, ctx.genlog, cfg)
        plan = dispatch_models(state, cfg)

        html = build_viewer_html(state, summary, cost, plan)
        for tok in ["<table", "<audio", "<img", "选题", "导演台预演", "草样片",
                    "质检", "成本估算", "多模型调度"]:
            c.ok(f"看板含『{tok}』", tok in html)

        vpath = write_viewer(state, out_dir, summary, cost, plan)
        c.ok("viewer.html 已落盘", vpath.exists())

        refs = re.findall(r'src="([^"]+)"', html)
        missing = [r for r in refs if not (out_dir / r).exists()]
        c.ok(f"引用资产 ≥ 8 处（{len(refs)}）", len(refs) >= 8)
        c.ok(f"所有资产引用都能解析（缺失 {missing}）", not missing)
        c.ok("含导演台俯视图引用", any("assets/director/" in r for r in refs))
        c.ok("含草样片 GIF 引用", any(r.endswith("preview.gif") for r in refs))

    return c.done("项目看板测试")


if __name__ == "__main__":
    raise SystemExit(main())
