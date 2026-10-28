#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨项目资产库检索 CLI（需求文档 第七章）—— 独立小工具，不影响主流水线。

用法：
  # 扫描 output/ 建立跨项目资产索引（落盘 output/_library/index.json）
  python library_tool.py build

  # 关键词检索（可加 --type character|prompt|scene，--top N）
  python library_tool.py search "长发 冷蓝 少女"
  python library_tool.py search "实验室走廊" --type scene --top 3

  # 列出已索引的项目
  python library_tool.py list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from manhua.library import build_index, save_index, search, stats  # noqa: E402

OUTPUT = ROOT / "output"
INDEX_PATH = OUTPUT / "_library" / "index.json"


def _load_or_build() -> dict:
    idx = build_index(OUTPUT)
    return idx


def main() -> int:
    p = argparse.ArgumentParser(description="跨项目资产库检索")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("build", help="扫描 output/ 建立索引")
    s = sub.add_parser("search", help="关键词检索资产")
    s.add_argument("query", help="检索词（中文可空格分隔多个词）")
    s.add_argument("--type", dest="kind", choices=["character", "prompt", "scene"], help="只搜某类资产")
    s.add_argument("--top", type=int, default=5, help="返回前 N 条")
    sub.add_parser("list", help="列出已索引项目")

    args = p.parse_args()
    idx = _load_or_build()

    if args.cmd == "build":
        save_index(idx, INDEX_PATH)
        print(f"已建立跨项目资产索引：{INDEX_PATH}")
        print(f"统计：{stats(idx)}")
        return 0

    if args.cmd == "list":
        if not idx["projects"]:
            print("（output/ 下暂无项目资产；先用 main.py 生成几个项目）")
            return 0
        for pid in idx["projects"]:
            print(f"- {pid}")
        print(f"\n共 {len(idx['projects'])} 个项目，{stats(idx)['entries']} 条资产。")
        return 0

    if args.cmd == "search":
        hits = search(idx, args.query, kind=args.kind, top_k=args.top)
        if not hits:
            print("未检索到相关资产。换个词，或先 build 出更多项目。")
            return 0
        print(f"检索『{args.query}』命中 {len(hits)} 条：")
        for h in hits:
            print(f"  [{h['type']}] {h['title']}  (项目 {h['project_id']} ｜ 相关度 {h['score']})")
            print(f"      {h['text'][:60]}")
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
