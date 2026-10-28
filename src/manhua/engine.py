"""
自研轻量工作流引擎（对应 需求文档 第五章「工作流引擎 + Agent 作为节点」）。

为什么不用全自由对话：漫剧生产链条长、依赖多、返工频繁，必须**可控、可追踪、可回滚**。
本引擎提供：
  - 共享 State（ProjectState）：所有 Agent 读写同一份结构化状态。
  - 检查点：每个节点跑完即把 State 落盘（state.json + NN_阶段.json），可断点续跑。
  - 单步重跑/回滚：--from <阶段> 清空该阶段及其后续并重跑（不动前面已确认的产物）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol

from .config import Config
from .genlog import GenerationLog
from .image.base import ImageGenerator
from .llm.base import LLMClient
from .schemas import (ArtResult, CharacterSet, ComposeResult, DirectorBoard,
                      QCReport, ReviewReport, Script, Storyboard, StoryIdea)

# 阶段顺序（严格对齐 需求文档 第三章业务流程：…分镜 → 导演台预演 → 分镜图…）：阶段 key -> 对应 schema
STAGE_FIELDS: list[tuple[str, type]] = [
    ("idea", StoryIdea),
    ("script", Script),
    ("review", ReviewReport),
    ("characters", CharacterSet),
    ("storyboard", Storyboard),
    ("director", DirectorBoard),  # 第六章：导演台预演（可控镜头参数 + 俯视构图图）
    ("art", ArtResult),
    ("compose", ComposeResult),   # 阶段二：后期合成（草样片/配音/时间线）
    ("qc", QCReport),             # 阶段二：质检（角色一致性检测）
]
STAGE_KEYS = [k for k, _ in STAGE_FIELDS]
# 落盘文件名前缀，便于按顺序查看
_STAGE_FILE = {k: f"{i+1:02d}_{k}" for i, (k, _) in enumerate(STAGE_FIELDS)}


@dataclass
class ProjectState:
    project_id: str
    idea_text: str
    created_at: str
    idea: Optional[StoryIdea] = None
    script: Optional[Script] = None
    review: Optional[ReviewReport] = None
    characters: Optional[CharacterSet] = None
    storyboard: Optional[Storyboard] = None
    director: Optional[DirectorBoard] = None
    art: Optional[ArtResult] = None
    compose: Optional[ComposeResult] = None
    qc: Optional[QCReport] = None

    def stage_done(self, key: str) -> bool:
        return getattr(self, key) is not None

    def reset_from(self, key: str) -> None:
        """清空指定阶段及其后续所有阶段（用于单步重跑/回滚）。"""
        idx = STAGE_KEYS.index(key)
        for k in STAGE_KEYS[idx:]:
            setattr(self, k, None)

    def to_dict(self) -> dict:
        d = {"project_id": self.project_id, "idea_text": self.idea_text, "created_at": self.created_at}
        for k, _ in STAGE_FIELDS:
            v = getattr(self, k)
            d[k] = v.model_dump() if v is not None else None
        return d

    def save(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "state.json").write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 同时把每个已完成阶段单独落盘，方便逐步查看
        for k, _ in STAGE_FIELDS:
            v = getattr(self, k)
            if v is not None:
                (out_dir / f"{_STAGE_FILE[k]}.json").write_text(
                    json.dumps(v.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
                )

    @classmethod
    def load(cls, out_dir: Path) -> "ProjectState":
        data = json.loads((out_dir / "state.json").read_text(encoding="utf-8"))
        st = cls(project_id=data["project_id"], idea_text=data["idea_text"], created_at=data["created_at"])
        for k, schema in STAGE_FIELDS:
            if data.get(k) is not None:
                setattr(st, k, schema.model_validate(data[k]))
        return st


@dataclass
class RunContext:
    """一次运行的依赖容器：所有 Agent 通过它访问模型/日志/输出目录。"""
    config: Config
    llm: LLMClient
    review_llm: LLMClient
    image_gen: ImageGenerator
    genlog: GenerationLog
    out_dir: Path


class Agent(Protocol):
    key: str
    display_name: str
    def run(self, state: ProjectState, ctx: RunContext) -> None: ...


@dataclass
class Node:
    agent: Agent

    @property
    def key(self) -> str:
        return self.agent.key

    @property
    def name(self) -> str:
        return self.agent.display_name


class Workflow:
    def __init__(self, nodes: list[Node]):
        self.nodes = nodes

    def run(self, state: ProjectState, ctx: RunContext, *, start_from: Optional[str] = None) -> ProjectState:
        # 说明：这里只用 ASCII 标记（>> / [OK] / -- / <<），不用 ▶✔ 等装饰字符，
        # 以免在默认 GBK 编码的 Windows 控制台报 UnicodeEncodeError（库代码不应依赖控制台编码）。
        if start_from:
            if start_from not in STAGE_KEYS:
                raise ValueError(f"未知阶段 {start_from}，可选：{STAGE_KEYS}")
            state.reset_from(start_from)
            print(f"<< 从阶段『{start_from}』重跑（已清空该阶段及后续）")

        for node in self.nodes:
            if state.stage_done(node.key):
                print(f"-- 跳过 [{node.key}] {node.name}（已有检查点）")
                continue
            print(f">> 运行 [{node.key}] {node.name} ...")
            node.agent.run(state, ctx)
            if not state.stage_done(node.key):
                raise RuntimeError(f"节点 {node.key} 运行后未写入产物")
            state.save(ctx.out_dir)            # 检查点：每步落盘
            ctx.genlog.save(ctx.out_dir / "generation_log.jsonl")
            print(f"[OK] 完成 [{node.key}] 已写检查点")
        return state


def new_project_state(idea_text: str, project_id: str) -> ProjectState:
    return ProjectState(
        project_id=project_id,
        idea_text=idea_text,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
