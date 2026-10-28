#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""导演台（需求文档 第六章）单元 + 集成测试：站位/机位/灯光推导、俯视图渲染、提示词精炼、一致性保持。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from _util import Checker, run_pipeline, ROOT  # noqa: E402
import sys
sys.path.insert(0, str(ROOT / "src"))
from PIL import Image  # noqa: E402
from manhua.director import compute_blocking, refine_prompts  # noqa: E402
from manhua.schemas import Camera, Lighting, Shot  # noqa: E402


def _shot(angle="低机位", size="特写", chars=("CHAR_001",)):
    return Shot(
        shot_id="S01", scene="测试场景", characters=list(chars),
        camera=Camera(shot_size=size, angle=angle, movement="缓慢推进"),
        lighting=Lighting(key_light="冷蓝侧光", rim_light="弱白色轮廓光", intensity="中等"),
        action="测试动作", duration="5s", negative_prompt="不要漂移",
        emotion="紧张", dialogue="测试", image_prompt="基础提示词 黑色长发", video_prompt="基础视频提示词",
    )


def main() -> int:
    c = Checker()

    # —— 单元：几何/规则推导 ——
    blk = compute_blocking(_shot(angle="低机位", size="特写"), base_seed=1)
    c.ok("低机位 → 仰拍", "仰拍" in blk["camera_height"])
    c.ok("特写 → 长焦/浅景深", "长焦" in blk["focal_hint"] or "浅景深" in blk["focal_hint"])
    c.ok("构图含三分法/竖屏安全框", "三分" in blk["framing"] and "9:16" in blk["framing"])
    c.ok("单角色站位坐标在 [0,1]", all(0 <= a["x"] <= 1 and 0 <= a["y"] <= 1 for a in blk["actors"]))

    blk2 = compute_blocking(_shot(angle="俯视", size="远景", chars=("CHAR_001", "CHAR_002")), base_seed=1)
    c.ok("俯视 → 俯拍", "俯拍" in blk2["camera_height"])
    c.ok("远景 → 广角大景深", "广角" in blk2["focal_hint"])
    c.ok("双角色 → 两个站位", len(blk2["actors"]) == 2)

    # —— 单元：提示词精炼保留固定特征 ——
    sh = _shot()
    img_p, vid_p = refine_prompts(sh, blk)
    c.ok("精炼后含【导演台】镜头语言", "【导演台】" in img_p)
    c.ok("精炼后仍保留原固定特征(黑色长发)", "黑色长发" in img_p)
    c.ok("视频提示词含机位信息", "机位" in vid_p)

    # —— 集成：跑全流程，校验导演台落盘 + 不破坏一致性 ——
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "p"
        state, ctx, cfg = run_pipeline(out)
        c.ok("导演台阶段有产出", state.director is not None)
        c.ok("导演台镜数 == 分镜数", len(state.director.shots) == len(state.storyboard.shots))
        c.ok("每镜俯视构图图已落盘",
             all(Path(ds.blocking_diagram).exists() for ds in state.director.shots))
        with Image.open(state.director.shots[0].blocking_diagram) as diag:
            c.ok("俯视图是 640x430 PNG", diag.format == "PNG" and diag.size == (640, 430))
        c.ok("分镜 image_prompt 已被导演台增强",
             all("【导演台】" in s.image_prompt for s in state.storyboard.shots))
        c.ok("导演台增强后角色一致性仍=1.0（固定特征未丢）",
             state.qc.consistency_score >= 0.99)

    return c.done("导演台测试")


if __name__ == "__main__":
    raise SystemExit(main())
