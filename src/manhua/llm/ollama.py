"""
本地 Ollama 适配器（零费用、零 API key 的真实 LLM，OpenAI 兼容接口）。

定位（介于 mock 与云端 DeepSeek 之间的第三条路）：
  - mock     ：离线确定性编造，零依赖零费用，但不是真实模型；
  - ollama   ：本地真实小模型（默认 qwen3:4b），零费用、无需 key，质量真实但受限于小模型；
  - deepseek ：云端大模型，质量最好，但需要 key 与预算。

启用方式（任选其一，模型名/地址都在 config.yaml 可配，代码不写死）：
  1) config.yaml 把 runtime.mode 改为 ollama（推荐，一键切换，图像仍走 placeholder）；
  2) runtime.mode 改 real，且 llm.provider 改 ollama。

本地小模型的两个工程现实，本适配器都做了健壮处理：
  - qwen3 系思考模型会输出 <think>...</think> 段 → strip_think() 剥离（含未闭合残段）；
  - 小模型常把 JSON 包在解释文字 / Markdown 代码块里 → extract_json() 稳健提取
    （整体解析 → 代码块 → 括号配平扫描，三级回退），再交 Pydantic 严格校验，失败带错误回灌重试。

依赖 requests（已在 requirements.txt），仅在选择 ollama 时才会真正联本地端口。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from ..config import LLMConfig
from .base import LLMClient, LLMResult

# qwen3 等思考模型的思考段标记
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
# Markdown 代码块（```json ... ``` 或 ``` ... ```）
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """剥离思考模型输出的 <think>...</think> 段。

    覆盖三种真实形态：
      1. 正常闭合的 <think>...</think>（可多段）；
      2. 只有开标签（生成被截断）→ 丢弃开标签之后的全部内容；
      3. 只有闭标签（部分聊天模板会吃掉开头的 <think>）→ 取闭标签之后的内容。
    """
    text = _THINK_BLOCK_RE.sub("", text)
    lower = text.lower()
    if "<think>" in lower:                      # 未闭合：截断到开标签前
        text = text[: lower.index("<think>")]
    lower = text.lower()
    if "</think>" in lower:                     # 只剩闭标签：取其后内容
        text = text[lower.rindex("</think>") + len("</think>") :]
    return text.strip()


def _balanced_candidates(text: str):
    """从文本中扫描出所有括号配平的 {...} / [...] 片段（忽略字符串字面量内的括号）。"""
    for start, ch in enumerate(text):
        if ch not in "{[":
            continue
        close = "}" if ch == "{" else "]"
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == ch:
                    depth += 1
                elif c == close:
                    depth -= 1
                    if depth == 0:
                        yield text[start : i + 1]
                        break


def extract_json(text: str) -> Any:
    """从模型输出中稳健提取并解析 JSON（容忍 JSON 外包裹解释文字 / 代码块）。

    三级回退：① 整体即合法 JSON；② Markdown 代码块内；③ 括号配平扫描首个合法片段。
    都失败则抛 ValueError（调用方会带错误信息回灌模型重试）。
    """
    text = strip_think(text)
    # ① 整体就是 JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # ② 代码块包裹
    for m in _CODE_FENCE_RE.finditer(text):
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
    # ③ 文字中混有 JSON：括号配平扫描
    for cand in _balanced_candidates(text):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    raise ValueError("未能从模型输出中提取出合法 JSON（已尝试整体解析/代码块/括号配平扫描）")


class OllamaLLM(LLMClient):
    """通过 Ollama 的 OpenAI 兼容接口（/v1/chat/completions）调用本地模型。"""

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.name = f"ollama:{cfg.model}"
        # 本地推理零费用（电费不计）；保留字段以便日志/成本模块统一处理
        self.cost_per_call_usd = 0.0

    # ---- HTTP 层（拆出来便于测试注入假响应，不真联网）----
    def _http_post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        import requests  # 延迟导入：mock 模式不要求安装

        resp = requests.post(url, json=payload, timeout=self.cfg.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def _post_with_retry(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """连接失败/超时做有限重试；最终失败给出清晰的排查指引（而非裸堆栈）。"""
        import requests  # 延迟导入

        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                return self._http_post(url, payload)
            except requests.exceptions.ConnectionError as e:
                last_err = e            # 服务未启动/端口不对：重试大概率无效，但给一次机会（服务可能正在启动）
            except requests.exceptions.Timeout as e:
                last_err = e            # 本地小模型偶发首次加载慢：重试有意义
            except requests.exceptions.HTTPError as e:
                # 404 常见于模型未拉取；直接给出可操作的提示
                body = ""
                try:
                    body = e.response.text[:300]
                except Exception:
                    pass
                raise RuntimeError(
                    f"Ollama 返回 HTTP 错误（{e}）。常见原因：模型未拉取，请先执行 "
                    f"`ollama pull {self.cfg.model}`，或在 config.yaml 的 llm.model 填入 "
                    f"`ollama list` 中已有的模型名。服务端信息：{body}"
                ) from e
            if attempt < self.cfg.max_retries:
                time.sleep(min(2.0 * (attempt + 1), 5.0))   # 简单退避后重试
        raise RuntimeError(
            f"无法连接本地 Ollama 服务（{url}）：{last_err}\n"
            f"  排查：1) 确认已安装并启动 Ollama（运行 `ollama serve` 或启动桌面端）；\n"
            f"        2) 确认已拉取模型：`ollama pull {self.cfg.model}`（用 `ollama list` 查看）；\n"
            f"        3) 确认 config.yaml 的 llm.base_url 正确（默认 http://localhost:11434/v1）。\n"
            f"  若暂不使用本地模型，把 config.yaml 的 runtime.mode 改回 mock 即可离线零依赖运行。"
        )

    # ---- 主入口：结构化生成（与 DeepSeek 适配器同一契约）----
    def generate_structured(self, *, task, system, user, schema, context) -> LLMResult:
        # 把目标 schema 注入系统提示，要求严格输出该结构（与 deepseek.py 同思路）
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
        sys_prompt = (
            f"{system}\n\n"
            f"你必须只输出一个 JSON 对象，且严格符合以下 JSON Schema（字段名、类型、必填项都要满足）：\n"
            f"{schema_json}\n"
            f"不要输出任何解释或 Markdown 代码块标记，只输出 JSON。所有内容用中文。"
        )
        ctx_text = json.dumps(context, ensure_ascii=False, default=str)
        user_prompt = f"{user}\n\n【上游结构化输入】\n{ctx_text}"

        url = f"{self.cfg.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.cfg.temperature,
            "stream": False,
            # Ollama 的 OpenAI 兼容层支持 json_object（映射为 format=json 语法约束）；
            # 即便个别版本忽略该参数，下方 extract_json 仍能稳健兜底。
            "response_format": {"type": "json_object"},
        }

        last_err: Exception | None = None
        input_tokens = output_tokens = 0
        for attempt in range(self.cfg.max_retries + 1):
            data = self._post_with_retry(url, payload)
            usage = data.get("usage") or {}
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            try:
                text = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError) as e:
                raise RuntimeError(f"Ollama 响应格式异常（task={task}）：{data}") from e

            try:
                obj = extract_json(text)                 # 剥 <think> + 稳健提取 JSON
                output = schema.model_validate(obj)      # Pydantic 严格校验（结构化命门）
                return LLMResult(
                    output=output,
                    model=self.name,
                    prompt=(sys_prompt + "\n\n" + user_prompt)[:4000],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=0.0,   # 本地推理零费用
                    params={"task": task, "temperature": self.cfg.temperature,
                            "attempt": attempt, "backend": "ollama"},
                )
            except (ValidationError, ValueError) as e:
                last_err = e
                # 把错误回灌，让模型自我纠正后重试（与 deepseek.py 同策略）
                payload["messages"].append({"role": "assistant", "content": text[:4000]})
                payload["messages"].append({
                    "role": "user",
                    "content": f"上次输出不符合要求，错误：{e}。请只重新输出符合 JSON Schema 的 JSON，"
                               f"不要任何解释、思考过程或代码块标记。",
                })

        raise RuntimeError(
            f"Ollama 结构化输出多次校验失败（task={task}, model={self.cfg.model}）：{last_err}\n"
            f"  小模型偶发不稳：可换更大模型（如 qwen3:8b）、调低 temperature，"
            f"或把 runtime.mode 改回 mock 演示工程闭环。"
        )
