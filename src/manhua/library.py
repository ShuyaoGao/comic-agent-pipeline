"""
跨项目资产库与检索（需求文档 第七章：资产库支撑系列化生产与复用）。

单个项目的 asset_library.json 只覆盖一次生成；要"系列化/团队复用"，需要一个**跨项目**的
可检索资产库：把 output/ 下所有项目的角色/提示词/场景资产汇总建索引，支持关键词检索，
方便"新项目复用已有角色设定/提示词模板/场景"。

离线零依赖实现：不引入向量库；中文检索用"字 + 二元组(bigram)重合度"打分（无需分词），
作为 MVP 的轻量检索。第二阶段可平滑替换为 pgvector / Chroma 等向量检索。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

_PUNCT = re.compile(r"[\s，。、；：！？,.;:!?()（）\[\]【】\"'`/\\|+\-_=]+")


def _features(text: str) -> set[str]:
    """把字符串变成"单字 + 相邻二元组"的特征集合，用于无分词的中文重合度匹配。"""
    s = _PUNCT.sub("", text or "")
    chars = set(s)
    bigrams = {s[i:i + 2] for i in range(len(s) - 1)}
    return chars | bigrams


def build_index(output_root: Path) -> dict[str, Any]:
    """扫描 output/ 下每个含 asset_library.json 的项目，汇总成可检索条目。"""
    entries: list[dict] = []
    projects: list[str] = []
    if output_root.exists():
        for d in sorted(p for p in output_root.iterdir() if p.is_dir()):
            lib = d / "asset_library.json"
            if not lib.exists():
                continue
            try:
                data = json.loads(lib.read_text(encoding="utf-8"))
            except Exception:
                continue
            pid = data.get("project_id", d.name)
            projects.append(pid)
            for c in data.get("character_assets", []):
                text = " ".join([c.get("name", ""), *c.get("fixed_visual_features", []),
                                 c.get("voice_profile", "")])
                entries.append({"type": "character", "project_id": pid, "title": c.get("name", ""),
                                "text": text, "payload": c})
            for p in data.get("prompt_assets", []):
                entries.append({"type": "prompt", "project_id": pid, "title": p.get("shot_id", ""),
                                "text": p.get("image_prompt", ""), "payload": p})
            for s in data.get("scene_assets", []):
                entries.append({"type": "scene", "project_id": pid, "title": s.get("location", ""),
                                "text": s.get("location", ""), "payload": s})
    return {"projects": projects, "entries": entries}


def search(index: dict, query: str, *, kind: Optional[str] = None, top_k: int = 5) -> list[dict]:
    """按关键词检索资产，返回打分排序后的条目（含 score）。"""
    q = _features(query)
    if not q:
        return []
    scored = []
    for e in index["entries"]:
        if kind and e["type"] != kind:
            continue
        overlap = len(q & _features(e["text"]))
        if overlap > 0:
            scored.append({**e, "score": overlap})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def save_index(index: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def stats(index: dict) -> dict[str, int]:
    by: dict[str, int] = {}
    for e in index["entries"]:
        by[e["type"]] = by.get(e["type"], 0) + 1
    return {"projects": len(index["projects"]), **by, "entries": len(index["entries"])}
