"""
把 3D 导演台（play/director.html）导出的镜头 JSON 导入为结构化 Storyboard。

闭环：3D 导演台摆机位/灯光 → 导出 director_export.json → 本模块校验并转成 Storyboard →
      喂回流水线（python main.py --resume <项目> --storyboard-from 导出.json）重跑 美术→合成→质检。

接受三种导出格式：{"shots":[...]} / [shot, ...] / 单个 shot 对象。每个 shot 都用 Pydantic 严格校验，
不合规会报清晰错误（这正是平台"结构化可控"的体现）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import Shot, Storyboard


def load_storyboard(path: str | Path) -> Storyboard:
    """读取导出文件 → 校验 → 返回 Storyboard。"""
    raw_text = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw_text)

    if isinstance(data, dict) and "shots" in data:
        raw_shots = data["shots"]
    elif isinstance(data, list):
        raw_shots = data
    elif isinstance(data, dict):
        raw_shots = [data]
    else:
        raise ValueError("无法识别的导出格式：应为 {\"shots\":[...]} / [shot,...] / 单个 shot 对象")

    if not raw_shots:
        raise ValueError("导出文件中没有任何镜头")

    shots = []
    for i, s in enumerate(raw_shots):
        try:
            shots.append(Shot.model_validate(s))
        except Exception as e:  # 给出定位到第几镜的清晰错误
            raise ValueError(f"第 {i+1} 个镜头不符合 Shot 结构：{e}") from e
    return Storyboard(shots=shots)


def unknown_character_ids(storyboard: Storyboard, known_ids: set[str]) -> set[str]:
    """返回导入镜头里引用了、但项目角色表中不存在的 character_id（供调用方提示）。"""
    used = {cid for sh in storyboard.shots for cid in sh.characters}
    return used - known_ids
