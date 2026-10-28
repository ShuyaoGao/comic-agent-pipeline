"""LLM 层：可切换的语言模型客户端（离线 mock / 本地 Ollama / 真实 DeepSeek）。"""
from __future__ import annotations

from ..config import Config, LLMConfig
from .base import LLMClient, LLMResult
from .mock import MockLLM


def build_llm(cfg: Config, llm_cfg: LLMConfig | None = None) -> LLMClient:
    """根据运行模式构造 LLM 客户端。

    三条路（见 config.yaml 注释）：
      - mode=mock                 → 离线确定性 mock（默认，零依赖零费用）；
      - mode=ollama               → 本地 Ollama 真实小模型（零费用、无需 key）；
      - mode=real + provider=...  → 云端 API（deepseek，需 key），provider=ollama 亦可。
    """
    if cfg.mode == "mock":
        return MockLLM(seed=cfg.seed)

    # runtime.mode=ollama 是「一键切本地模型」的快捷方式：直接用 config.yaml 的 ollama 段
    if cfg.mode == "ollama":
        from .ollama import OllamaLLM

        return OllamaLLM(llm_cfg or cfg.ollama)

    lc = llm_cfg or cfg.llm
    if lc.provider == "ollama":   # real 模式也允许把 llm.provider 配成 ollama
        from .ollama import OllamaLLM

        return OllamaLLM(lc)

    # real 模式：目前内置 DeepSeek 适配器；其它云端 provider 可在此扩展。
    from .deepseek import DeepSeekLLM

    return DeepSeekLLM(lc)


__all__ = ["LLMClient", "LLMResult", "MockLLM", "build_llm"]
