"""Agent 基类。每个 LLM 型 Agent 都是『结构化输入 → LLM → Pydantic 校验 → 结构化输出 + 写日志』。"""
from __future__ import annotations

from abc import abstractmethod

from ..engine import ProjectState, RunContext
from ..schemas import TASK_SCHEMAS


class LLMAgent:
    """LLM 型 Agent 的通用骨架；子类只需实现 build_prompt()。"""

    key: str = ""              # 对应 ProjectState 的字段名（也是阶段名）
    display_name: str = ""
    task: str = ""             # 对应 schemas.TASK_SCHEMAS 的键
    use_review_llm: bool = False

    @abstractmethod
    def build_prompt(self, state: ProjectState) -> tuple[str, str, dict]:
        """返回 (system_prompt, user_prompt, context_dict)。"""
        ...

    def run(self, state: ProjectState, ctx: RunContext) -> None:
        llm = ctx.review_llm if self.use_review_llm else ctx.llm
        system, user, context = self.build_prompt(state)
        result = llm.generate_structured(
            task=self.task, system=system, user=user,
            schema=TASK_SCHEMAS[self.task], context=context,
        )
        ctx.genlog.log_llm(self.key, result)
        setattr(state, self.key, result.output)   # 写入共享 State（字段名 == key）
