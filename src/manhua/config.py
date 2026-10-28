"""
配置加载：读取 config.yaml，可被命令行参数覆盖（如 --mode / --seed）。

模型名与价格全部来自配置文件（项目约束），代码里不写死任何模型 id / 单价。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.7
    max_retries: int = 2
    timeout_seconds: float = 120.0      # 单次请求超时；本地小模型首次加载较慢，可在 config.yaml 放宽
    price_input_per_mtok_usd: float = 0.14
    price_input_cached_per_mtok_usd: float = 0.0028
    price_output_per_mtok_usd: float = 0.28

    @property
    def api_key(self) -> str | None:
        """从环境变量读取密钥（real 模式才需要）。"""
        return os.environ.get(self.api_key_env)


@dataclass
class ImageConfig:
    provider: str = "placeholder"
    size: tuple[int, int] = (768, 1024)
    model: str = "seedream-4.0"
    base_url: str = ""
    api_key_env: str = "IMAGE_API_KEY"
    price_per_image_usd: float = 0.1

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


@dataclass
class ComposeConfig:
    """后期合成（草样片/配音/剪辑时间线）参数。MVP 离线默认值。"""
    aspect_ratio: str = "9:16"
    fps: int = 25
    reel_max_shots: int = 8        # 草样片最多收录多少镜（超出会截断并提示）
    reel_width: int = 360          # 草样片 GIF 画布宽（9:16）
    bgm_note: str = "MVP 占位：阶段二接入情绪匹配 BGM（需求文档 4.7）"


@dataclass
class CostConfig:
    """成本估算用的示意单价（需求文档 成本控制）。LLM/图像单价复用各自配置。"""
    video_per_second_usd: float = 0.10
    tts_per_1k_chars_usd: float = 0.15


@dataclass
class DispatchConfig:
    """多模型调度（需求文档 4.6 / 10.3）。模型名可配置；不绑死单一模型。"""
    image_model_strong: str = "nano-banana-pro"   # 强一致性（特写/多角色/关键镜）
    image_model_cheap: str = "seedream-4.0"       # 性价比（远景/单角色）
    video_model_real: str = "kling-3.0"           # 关键镜真实视频
    video_placeholder: str = "storyboard-image"   # 其余镜：分镜图+轻动效占位
    key_shot_max: int = 2                          # 最多几镜用真实视频（成本控制）


def _default_ollama_config() -> "LLMConfig":
    """本地 Ollama 的默认连接参数（模型名/地址都可在 config.yaml 的 ollama 段覆盖）。"""
    return LLMConfig(
        provider="ollama",
        model="qwen3:4b",
        base_url="http://localhost:11434/v1",   # Ollama 的 OpenAI 兼容接口
        api_key_env="OLLAMA_API_KEY",           # 本地无需 key，留环境变量名仅为接口统一
        timeout_seconds=300.0,                  # 本地小模型生成长 JSON 较慢，放宽超时
        price_input_per_mtok_usd=0.0,           # 本地推理零费用
        price_input_cached_per_mtok_usd=0.0,
        price_output_per_mtok_usd=0.0,
    )


@dataclass
class Config:
    mode: str = "mock"                  # mock | ollama | real
    output_dir: str = "output"
    seed: int = 20260529
    llm: LLMConfig = field(default_factory=LLMConfig)
    ollama: LLMConfig = field(default_factory=_default_ollama_config)
    review_llm_use_main: bool = True
    review_llm: LLMConfig = field(default_factory=LLMConfig)
    image: ImageConfig = field(default_factory=ImageConfig)
    compose: ComposeConfig = field(default_factory=ComposeConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    dispatch: DispatchConfig = field(default_factory=DispatchConfig)
    video_enabled: bool = False

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Config":
        path = Path(path)
        data: dict[str, Any] = {}
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        runtime = data.get("runtime", {})
        llm_d = data.get("llm", {})
        review_d = data.get("review_llm", {})
        image_d = data.get("image", {})
        video_d = data.get("video", {})

        llm = LLMConfig(**{k: v for k, v in llm_d.items() if k in LLMConfig.__dataclass_fields__})

        # 本地 Ollama 段：在默认值基础上按 config.yaml 覆盖（模型名/地址/超时全部可配）
        ollama = _default_ollama_config()
        for k, v in data.get("ollama", {}).items():
            if k in LLMConfig.__dataclass_fields__:
                setattr(ollama, k, v)

        review_use_main = review_d.get("use_main", True)
        if review_use_main:
            review_llm = llm
        else:
            review_llm = LLMConfig(
                **{k: v for k, v in review_d.items() if k in LLMConfig.__dataclass_fields__}
            )

        image_kwargs = {k: v for k, v in image_d.items() if k in ImageConfig.__dataclass_fields__}
        if "size" in image_kwargs and isinstance(image_kwargs["size"], list):
            image_kwargs["size"] = tuple(image_kwargs["size"])
        image = ImageConfig(**image_kwargs)

        compose_d = data.get("compose", {})
        compose = ComposeConfig(
            **{k: v for k, v in compose_d.items() if k in ComposeConfig.__dataclass_fields__}
        )

        cost_d = data.get("cost", {})
        cost = CostConfig(
            **{k: v for k, v in cost_d.items() if k in CostConfig.__dataclass_fields__}
        )

        dispatch_d = data.get("dispatch", {})
        dispatch = DispatchConfig(
            **{k: v for k, v in dispatch_d.items() if k in DispatchConfig.__dataclass_fields__}
        )

        return cls(
            mode=runtime.get("mode", "mock"),
            output_dir=runtime.get("output_dir", "output"),
            seed=int(runtime.get("seed", 20260529)),
            llm=llm,
            ollama=ollama,
            review_llm_use_main=review_use_main,
            review_llm=review_llm,
            image=image,
            compose=compose,
            cost=cost,
            dispatch=dispatch,
            video_enabled=bool(video_d.get("enabled", False)),
        )
