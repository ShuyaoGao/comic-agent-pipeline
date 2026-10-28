"""图像生成器抽象基类与返回结构。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ImageResult:
    image_path: str
    seed: int
    prompt: str
    negative_prompt: str
    reference_image: Optional[str]
    model: str
    cost_usd: float


class ImageGenerator(ABC):
    name: str = "image"

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        seed: int,                      # 锁 seed = 一致性锚点
        reference_image: Optional[str], # 同一参考图 = 一致性锚点
        out_path: Path,
        label: str,                     # 画在图上的标识（如 CHAR_001 / S01）
    ) -> ImageResult:
        ...
