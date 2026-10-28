#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""多模型调度（需求文档 4.6）测试：关键镜真实视频、其余占位，模型名取自可配置池，与成本联动降本。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _util import Checker, run_pipeline, ROOT
sys.path.insert(0, str(ROOT / "src"))
from manhua.dispatch import dispatch_models  # noqa: E402


def main() -> int:
    c = Checker()
    with tempfile.TemporaryDirectory() as tmp:
        state, ctx, cfg = run_pipeline(Path(tmp) / "p")
        plan = dispatch_models(state, cfg)

        n = len(state.storyboard.shots)
        c.ok("调度覆盖全部镜头", len(plan.shots) == n)
        c.ok("真实视频镜数 ≤ key_shot_max", plan.real_video_shots <= cfg.dispatch.key_shot_max)
        c.ok("真实+占位 = 总镜数", plan.real_video_shots + plan.placeholder_shots == n)
        c.ok("调度后视频成本 ≤ 全量（降本）",
             plan.dispatched_video_cost_usd <= plan.full_video_cost_usd)
        c.ok("图像模型取自可配置调度池",
             all(d.image_model in {cfg.dispatch.image_model_strong, cfg.dispatch.image_model_cheap}
                 for d in plan.shots))
        c.ok("视频方案取自可配置调度池",
             all(d.video_model in {cfg.dispatch.video_model_real, cfg.dispatch.video_placeholder}
                 for d in plan.shots))
        c.ok("被判真实视频的镜确实标记 real_video",
             all(d.real_video == (d.video_model == cfg.dispatch.video_model_real) for d in plan.shots))

    return c.done("多模型调度测试")


if __name__ == "__main__":
    raise SystemExit(main())
