#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨项目资产库检索（需求文档 第七章）测试：多项目建索引 + 中文关键词检索 + 类型过滤。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _util import Checker, run_pipeline, ROOT
sys.path.insert(0, str(ROOT / "src"))
from manhua.assets import save_asset_library  # noqa: E402
from manhua.library import build_index, search, stats  # noqa: E402


def main() -> int:
    c = Checker()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "output"
        s1, _, _ = run_pipeline(root / "projA", idea="末日里少女带着会说话的猫寻找信号源", seed=1)
        save_asset_library(s1, root / "projA")
        s2, _, _ = run_pipeline(root / "projB", idea="古风权谋宫廷夺嫡步步惊心", seed=2)
        save_asset_library(s2, root / "projB")

        idx = build_index(root)
        st = stats(idx)
        c.ok("索引到 2 个项目", st["projects"] == 2)
        c.ok("覆盖 角色/提示词/场景 三类条目",
             st.get("character", 0) > 0 and st.get("prompt", 0) > 0 and st.get("scene", 0) > 0)

        name = s1.characters.characters[0].name
        hits = search(idx, name, kind="character")
        c.ok(f"按角色名『{name}』检索命中", any(h["title"] == name for h in hits))

        feat = s1.characters.characters[0].fixed_visual_features[0]
        hits2 = search(idx, feat, kind="character")
        c.ok(f"按外貌特征『{feat}』检索到角色", len(hits2) > 0)

        hits3 = search(idx, name, kind="scene")
        c.ok("类型过滤生效（限定 scene 不返回角色）", all(h["type"] == "scene" for h in hits3))

        c.ok("命中结果带相关度且降序", all("score" in h for h in hits) and
             (len(hits) < 2 or hits[0]["score"] >= hits[-1]["score"]))
        c.ok("空查询安全返回空", search(idx, "") == [])

    return c.done("资产库检索测试")


if __name__ == "__main__":
    raise SystemExit(main())
