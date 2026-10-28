"""
离线占位图生成器（Pillow，CPU，零成本）。

它**不画真实画面**，而是把『提示词 + seed + 参考图 + 编号』可视化成一张卡片图，
用来在没有 GPU / 没有图像 API 的情况下，演示平台最关键的一致性机制：

  锁 seed + 同一参考图  ->  相同 seed 派生相同主色调与头像图形  ->  同一角色的各分镜图肉眼可见一致。

填了真实图像 API（即梦/Seedream/Nano Banana Pro）并切到 real 模式，即用真实出图替换它。
"""
from __future__ import annotations

import colorsys
import hashlib
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from ..config import ImageConfig
from .base import ImageGenerator, ImageResult

# 常见 Windows 中文字体路径（保证占位图上的中文能正常渲染）
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
    r"C:\Windows\Fonts\simsun.ttc",    # 宋体
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _palette_from_seed(seed: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """seed -> 确定性主色调（同 seed 同色 = 一致性可视化）。返回(深色, 浅色)。"""
    h = int(hashlib.md5(str(seed).encode()).hexdigest()[:8], 16)
    hue = (h % 360) / 360.0
    dark = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.45))
    light = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.30, 0.92))
    return dark, light  # type: ignore[return-value]


def _wrap_cjk(text: str, max_chars: int) -> list[str]:
    """按字符数硬换行（中文无空格，textwrap 不适用）。"""
    lines: list[str] = []
    for raw in text.split("\n"):
        while len(raw) > max_chars:
            lines.append(raw[:max_chars])
            raw = raw[max_chars:]
        lines.append(raw)
    return lines


class PlaceholderImageGenerator(ImageGenerator):
    name = "placeholder-offline"

    def __init__(self, cfg: ImageConfig):
        self.cfg = cfg

    def generate(self, *, prompt, negative_prompt, seed, reference_image, out_path, label) -> ImageResult:
        w, h = self.cfg.size
        dark, light = _palette_from_seed(seed)
        img = Image.new("RGB", (w, h), light)
        draw = ImageDraw.Draw(img)

        # 顶部色条 + 编号（颜色由 seed 决定 -> 一致性锚点可视化）
        draw.rectangle([0, 0, w, 90], fill=dark)
        f_title = _load_font(40)
        f_body = _load_font(22)
        f_small = _load_font(18)
        draw.text((24, 24), label, font=f_title, fill=(255, 255, 255))

        # 中部「角色头像」几何图形：形状/颜色由 seed 决定，同 seed 必然相同
        cx, cy, r = w // 2, 300, 130
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dark, outline=(255, 255, 255), width=6)
        # 内部用 seed 派生一个简单图案，增强「同 seed 同脸」的直观感
        inner = (seed % 5)
        draw.rectangle([cx - 50, cy - 20 - inner * 8, cx + 50, cy + 40 + inner * 8],
                       fill=light, outline=dark, width=4)

        # 提示词区
        y = 470
        draw.text((24, y), "image_prompt:", font=f_body, fill=dark)
        y += 32
        for line in _wrap_cjk(prompt, max_chars=max(10, w // 24))[:9]:
            draw.text((24, y), line, font=f_small, fill=(40, 40, 40))
            y += 26

        # 一致性元信息
        y = h - 200
        draw.line([24, y - 12, w - 24, y - 12], fill=dark, width=2)
        ref_txt = Path(reference_image).name if reference_image else "无（首图/参考基准）"
        meta = [
            f"SEED（锁定）：{seed}",
            f"参考图（保身份）：{ref_txt}",
            f"negative：{negative_prompt[:40]}",
            "离线占位图 · 非真实绘画 · 同 seed → 同主色调，演示角色一致性",
        ]
        for line in meta:
            for sub in _wrap_cjk(line, max_chars=max(10, w // 20)):
                draw.text((24, y), sub, font=f_small, fill=(70, 70, 70))
                y += 24

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return ImageResult(
            image_path=str(out_path),
            seed=seed,
            prompt=prompt,
            negative_prompt=negative_prompt,
            reference_image=reference_image,
            model=self.name,
            cost_usd=0.0,
        )
