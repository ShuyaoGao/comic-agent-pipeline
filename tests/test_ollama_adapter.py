#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ollama 适配器单测（不联网、不要求安装 Ollama）：
  - <think>...</think> 思考段剥离（qwen3 等思考模型的输出形态，含截断/残段）；
  - JSON 稳健提取（容忍模型把 JSON 包在解释文字 / Markdown 代码块里）；
  - 用假 HTTP 响应替换 _http_post，验证 结构化校验 / 错误回灌重试 / 清晰报错切回 mock 提示。

真连本地 Ollama 的端到端检查见 tests/ollama_live_check.py（服务不在时优雅跳过）。
"""
from __future__ import annotations

import sys

from pydantic import BaseModel

from _util import Checker, ROOT

sys.path.insert(0, str(ROOT / "src"))

from manhua.config import Config, LLMConfig  # noqa: E402
from manhua.llm import build_llm  # noqa: E402
from manhua.llm.ollama import OllamaLLM, extract_json, strip_think  # noqa: E402


class _Mini(BaseModel):
    """极简 schema，专测结构化校验路径。"""
    title: str
    count: int


def _cfg(**kw) -> LLMConfig:
    base = dict(provider="ollama", model="qwen3:4b",
                base_url="http://localhost:11434/v1",
                max_retries=2, timeout_seconds=5.0)
    base.update(kw)
    return LLMConfig(**base)


def _resp(content: str, pt: int = 11, ct: int = 22) -> dict:
    """构造一条 OpenAI 兼容格式的假响应。"""
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct},
    }


def main() -> int:
    c = Checker()

    # ---------- 1. <think> 剥离 ----------
    c.ok("正常闭合的 think 段被剥离",
         strip_think("<think>我先想想……</think>正文") == "正文")
    c.ok("多段 think 全部剥离",
         strip_think("<think>a</think>X<think>b</think>Y") == "XY")
    c.ok("未闭合 think（生成截断）丢弃其后内容",
         strip_think("前文<think>没想完就断了") == "前文")
    c.ok("只剩闭合标签（模板吃掉开标签）取其后内容",
         strip_think("漏头的思考…</think>真正的答案") == "真正的答案")
    c.ok("无 think 的文本原样保留（仅去首尾空白）",
         strip_think("  {\"a\":1}  ") == "{\"a\":1}")
    c.ok("大小写混合标签也能剥离",
         strip_think("<THINK>x</THINK>ok") == "ok")

    # ---------- 2. JSON 稳健提取 ----------
    c.ok("整体即合法 JSON 直接解析",
         extract_json('{"a": 1}') == {"a": 1})
    c.ok("```json 代码块内的 JSON 可提取",
         extract_json('好的，结果如下：\n```json\n{"a": [1, 2]}\n```\n以上。') == {"a": [1, 2]})
    c.ok("无语言标记的 ``` 代码块也可提取",
         extract_json('```\n{"b": "x"}\n```') == {"b": "x"})
    c.ok("JSON 前后混有解释文字时按括号配平提取",
         extract_json('我认为答案是 {"t": "夜", "n": 2}，请查收！') == {"t": "夜", "n": 2})
    c.ok("字符串值里的花括号/引号不干扰配平",
         extract_json('前缀 {"s": "含 } 和 \\" 的串", "k": 1} 后缀') == {"s": '含 } 和 " 的串', "k": 1})
    c.ok("think 段 + 代码块组合形态可提取",
         extract_json('<think>嗯…schema 要 title</think>```json\n{"title":"早","count":3}\n```')
         == {"title": "早", "count": 3})
    c.ok("顶层数组也能提取", extract_json('结果：[1, 2, 3] 完') == [1, 2, 3])
    raised = False
    try:
        extract_json("这里完全没有 JSON")
    except ValueError:
        raised = True
    c.ok("提不出 JSON 时抛 ValueError（供重试回灌）", raised)

    # ---------- 3. 假 HTTP 响应走通 generate_structured ----------
    llm = OllamaLLM(_cfg())
    sent_payloads: list[dict] = []
    canned = [_resp('<think>用户要 JSON……</think>好的：\n```json\n{"title":"夜行","count":2}\n```')]
    def fake_post(url, payload):
        sent_payloads.append(payload)
        return canned.pop(0)
    llm._http_post = fake_post  # 注入假 HTTP，全程不联网

    res = llm.generate_structured(task="idea", system="你是选题 Agent",
                                  user="给我一个故事", schema=_Mini, context={"idea_text": "测试"})
    c.ok("think+代码块包裹的输出被正确解析为 Pydantic 对象",
         isinstance(res.output, _Mini) and res.output.title == "夜行" and res.output.count == 2)
    c.ok("本地推理成本记为 0", res.cost_usd == 0.0)
    c.ok("usage token 计入日志字段", res.input_tokens == 11 and res.output_tokens == 22)
    c.ok("模型名带 ollama 前缀（便于生成日志区分）", res.model == "ollama:qwen3:4b")
    c.ok("请求体使用 config 的模型名并要求 JSON 输出",
         sent_payloads[0]["model"] == "qwen3:4b"
         and sent_payloads[0].get("response_format", {}).get("type") == "json_object")

    # ---------- 4. 校验失败 → 错误回灌 → 重试成功 ----------
    llm2 = OllamaLLM(_cfg())
    sent2: list[dict] = []
    canned2 = [
        _resp('{"title": "缺 count 字段"}'),                       # 第一次：缺必填字段
        _resp('抱歉，修正如下 {"title": "修正", "count": 7}'),      # 第二次：自纠成功
    ]
    def fake_post2(url, payload):
        sent2.append({"n_msgs": len(payload["messages"])})
        return canned2.pop(0)
    llm2._http_post = fake_post2
    res2 = llm2.generate_structured(task="idea", system="s", user="u", schema=_Mini, context={})
    c.ok("第一次校验失败后重试成功", res2.output.count == 7)
    c.ok("重试时把错误信息回灌给模型（消息数增加）",
         sent2[0]["n_msgs"] == 2 and sent2[1]["n_msgs"] == 4)
    c.ok("params 记录了重试次数", res2.params.get("attempt") == 1)

    # ---------- 5. 始终不合法 → 清晰报错并提示切回 mock ----------
    llm3 = OllamaLLM(_cfg(max_retries=1))
    llm3._http_post = lambda url, payload: _resp("我拒绝输出 JSON")
    msg = ""
    try:
        llm3.generate_structured(task="idea", system="s", user="u", schema=_Mini, context={})
    except RuntimeError as e:
        msg = str(e)
    c.ok("多次失败抛 RuntimeError 且提示可切回 mock", "mock" in msg and "qwen3:4b" in msg)

    # ---------- 6. 服务不可达 → 清晰排查指引 ----------
    import requests  # 已在 requirements.txt

    llm4 = OllamaLLM(_cfg(max_retries=0))
    def refuse(url, payload):
        raise requests.exceptions.ConnectionError("Connection refused")
    llm4._http_post = refuse
    msg4 = ""
    try:
        llm4.generate_structured(task="idea", system="s", user="u", schema=_Mini, context={})
    except RuntimeError as e:
        msg4 = str(e)
    c.ok("连接失败报清晰错误（含 ollama pull / 切回 mock 提示）",
         "ollama pull" in msg4 and "mock" in msg4)

    # ---------- 7. 工厂注册：runtime.mode=ollama / real+provider=ollama ----------
    built = build_llm(Config(mode="ollama"))
    c.ok("mode=ollama 时工厂返回 OllamaLLM（默认 qwen3:4b）",
         isinstance(built, OllamaLLM) and built.cfg.model == "qwen3:4b"
         and built.cfg.base_url.endswith("11434/v1"))
    built2 = build_llm(Config(mode="real", llm=_cfg(model="qwen3:8b")))
    c.ok("real 模式 + llm.provider=ollama 也走 OllamaLLM",
         isinstance(built2, OllamaLLM) and built2.cfg.model == "qwen3:8b")
    c.ok("mode=mock 不受影响（默认仍离线）",
         build_llm(Config(mode="mock")).name == "mock-llm-offline")

    return c.done("Ollama 适配器测试")


if __name__ == "__main__":
    raise SystemExit(main())
