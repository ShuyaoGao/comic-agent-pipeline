#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立校验工具：检查 3D 导演台导出的镜头 JSON 是否符合 Shot 结构（不修改任何项目）。

  python tools/import_storyboard.py tools/sample_director_export.json

要把导出真正喂回流水线出图，请用：
  python main.py --resume <项目ID> --storyboard-from <导出.json>
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manhua.director_import import load_storyboard  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("用法：python tools/import_storyboard.py <导出.json>")
        return 2
    try:
        sb = load_storyboard(argv[0])
    except Exception as e:
        print(f"✗ 校验失败：{e}")
        return 1
    print(f"✓ 校验通过：{len(sb.shots)} 个镜头，结构均符合 Shot（需求文档 附录 12.2）")
    for sh in sb.shots:
        print(f"  - {sh.shot_id} [{sh.scene}] {sh.camera.shot_size}/{sh.camera.angle}/{sh.camera.movement} "
              f"角色{sh.characters} {sh.duration}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
