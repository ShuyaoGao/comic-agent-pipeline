"""LLM 客户端抽象基类与返回结构。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass
class LLMResult:
    """一次 LLM 调用的结果 + 计量信息（喂给生成日志，需求文档 第七章）。"""
    output: BaseModel                     # 已通过 Pydantic 校验的结构化输出
    model: str                            # 实际使用的模型名/方式
    prompt: str                           # 发送的提示词（用于日志）
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)


class LLMClient(ABC):
    """所有 LLM 客户端的统一接口：给定任务+提示词+目标 schema，返回结构化对象。"""

    name: str = "llm"

    @abstractmethod
    def generate_structured(
        self,
        *,
        task: str,                # 任务标识：idea/script/review/character/storyboard
        system: str,              # 系统提示词（角色与规则）
        user: str,                # 用户提示词（含上游结构化输入）
        schema: type[BaseModel],  # 期望输出的 Pydantic 模型
        context: dict[str, Any],  # 上游结构化数据（mock 据此保持连贯，真实模型用于拼 prompt）
    ) -> LLMResult:
        ...
