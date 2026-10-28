"""
真实 DeepSeek 适配器（仅 config mode=real 时启用）。

要点：
  - 用 JSON mode 强制结构化输出，再用 Pydantic 校验，失败自动重试（结构化是平台『可控』命门）。
  - 模型名/价格全部来自 config（不写死）；按 usage 计算成本，写入生成日志。
  - 2026-05-29 核对：模型别名 deepseek-chat 已对应 DeepSeek-V4-Flash；上线前请再核对官方文档。

依赖 requests / python-dotenv，仅在 real 模式才会被导入。
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from ..config import LLMConfig
from .base import LLMClient, LLMResult


class DeepSeekLLM(LLMClient):
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.name = cfg.model
        # 延迟导入，避免离线 mock 模式强制安装这些库
        try:
            from dotenv import load_dotenv  # type: ignore

            load_dotenv()  # 自动读取项目根 .env
        except Exception:
            pass
        if not cfg.api_key:
            raise RuntimeError(
                f"real 模式需要在环境变量 {cfg.api_key_env} 中提供 DeepSeek API key"
                f"（可在 .env 文件里设置 {cfg.api_key_env}=...）。"
            )

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        c = self.cfg
        return (
            input_tokens / 1_000_000 * c.price_input_per_mtok_usd
            + output_tokens / 1_000_000 * c.price_output_per_mtok_usd
        )

    def generate_structured(self, *, task, system, user, schema, context) -> LLMResult:
        import requests  # 延迟导入

        # 把目标 schema 的 JSON Schema 注入系统提示，约束模型严格输出该结构
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
        sys_prompt = (
            f"{system}\n\n"
            f"你必须只输出一个 JSON 对象，且严格符合以下 JSON Schema（字段名、类型、必填项都要满足）：\n"
            f"{schema_json}\n"
            f"不要输出任何解释或 Markdown 代码块标记，只输出 JSON。"
        )
        ctx_text = json.dumps(context, ensure_ascii=False, default=str)
        user_prompt = f"{user}\n\n【上游结构化输入】\n{ctx_text}"

        url = f"{self.cfg.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.cfg.temperature,
            "response_format": {"type": "json_object"},
        }

        last_err: Exception | None = None
        input_tokens = output_tokens = 0
        for attempt in range(self.cfg.max_retries + 1):
            resp = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            text = data["choices"][0]["message"]["content"]
            try:
                output = schema.model_validate_json(text)
                return LLMResult(
                    output=output,
                    model=self.cfg.model,
                    prompt=(sys_prompt + "\n\n" + user_prompt)[:4000],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=self._cost(input_tokens, output_tokens),
                    params={"task": task, "temperature": self.cfg.temperature, "attempt": attempt},
                )
            except (ValidationError, json.JSONDecodeError) as e:
                last_err = e
                # 把错误回灌，让模型自我纠正
                payload["messages"].append({"role": "assistant", "content": text})
                payload["messages"].append(
                    {"role": "user", "content": f"上次输出不符合 schema，错误：{e}。请只重新输出符合 schema 的 JSON。"}
                )

        raise RuntimeError(f"DeepSeek 结构化输出多次校验失败（task={task}）：{last_err}")
