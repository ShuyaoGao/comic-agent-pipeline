"""图像层：可切换的图像生成器（离线 Pillow 占位图 / 真实云端 API）。"""
from __future__ import annotations

from ..config import Config
from .base import ImageGenerator, ImageResult
from .placeholder import PlaceholderImageGenerator


def build_image_generator(cfg: Config) -> ImageGenerator:
    """根据运行模式与 provider 构造图像生成器。"""
    if cfg.mode == "mock" or cfg.image.provider == "placeholder":
        return PlaceholderImageGenerator(cfg.image)
    # real 模式 + 云端 provider
    from .cloud import CloudImageGenerator

    return CloudImageGenerator(cfg.image)


__all__ = ["ImageGenerator", "ImageResult", "PlaceholderImageGenerator", "build_image_generator"]
