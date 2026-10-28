"""9 个 Agent 节点（需求文档 业务流程的 MVP + 阶段二/三子集）。"""
from __future__ import annotations

from ..engine import Node
from .art import ArtAgent
from .compose import ComposeAgent
from .director import DirectorAgent
from .qc import QCAgent
from .writers import (CharacterAgent, IdeaAgent, ReviewAgent, ScriptAgent,
                      StoryboardAgent)


def default_nodes() -> list[Node]:
    """按 需求文档 业务流程顺序组装：
    选题 → 编剧 → 审稿合规 → 角色设定 → 分镜 → 导演台预演 → 美术 →(阶段二) 合成后期 → 质检。"""
    return [
        Node(IdeaAgent()),
        Node(ScriptAgent()),
        Node(ReviewAgent()),
        Node(CharacterAgent()),
        Node(StoryboardAgent()),
        Node(DirectorAgent()),
        Node(ArtAgent()),
        Node(ComposeAgent()),
        Node(QCAgent()),
    ]


__all__ = [
    "IdeaAgent", "ScriptAgent", "ReviewAgent", "CharacterAgent",
    "StoryboardAgent", "DirectorAgent", "ArtAgent", "ComposeAgent", "QCAgent", "default_nodes",
]
