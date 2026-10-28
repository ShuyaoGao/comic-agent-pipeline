"""
真实云端图像生成适配器骨架（即梦/Seedream、Nano Banana Pro 等）。

⚠️ 不同服务商的请求/返回字段差异很大，且模型 id 与定价 3~6 个月就换代，
   本文件给出**接入位置与一致性参数传递方式**，真实字段请按所选服务商官方文档补全。
   一致性要点：把 seed 与 reference_image（参考图/多参考图）一并传给 API（即梦做法），
   并把 negative_prompt 一并下发。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import ImageConfig
from .base import ImageGenerator, ImageResult


class CloudImageGenerator(ImageGenerator):
    def __init__(self, cfg: ImageConfig):
        self.cfg = cfg
        self.name = cfg.model
        if not cfg.base_url or not cfg.api_key:
            raise RuntimeError(
                "云端图像生成需要在 config.yaml 配置 image.base_url，并在环境变量 "
                f"{cfg.api_key_env} 中提供 key。当前为占位骨架，请按所选服务商文档补全 _call_api()。"
            )

    def _call_api(self, *, prompt, negative_prompt, seed, reference_image) -> bytes:
        """按服务商文档补全：构造请求 -> 拿到图像字节。下面是通用示意（需替换）。"""
        import requests  # 延迟导入

        payload = {
            "model": self.cfg.model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": seed,                       # 锁 seed
            "size": f"{self.cfg.size[0]}x{self.cfg.size[1]}",
        }
        if reference_image:
            # 即梦/Nano Banana 风格：上传参考图保身份一致（字段名按官方文档改）
            payload["reference_image"] = str(reference_image)
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"}
        resp = requests.post(self.cfg.base_url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        # TODO: 不同服务商返回 url 或 base64，这里按实际返回解析为图像字节
        raise NotImplementedError("请按所选图像服务商的返回格式解析图像字节。")

    def generate(self, *, prompt, negative_prompt, seed, reference_image, out_path, label) -> ImageResult:
        data = self._call_api(
            prompt=prompt, negative_prompt=negative_prompt, seed=seed, reference_image=reference_image
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return ImageResult(
            image_path=str(out_path),
            seed=seed,
            prompt=prompt,
            negative_prompt=negative_prompt,
            reference_image=reference_image,
            model=self.name,
            cost_usd=self.cfg.price_per_image_usd,
        )
