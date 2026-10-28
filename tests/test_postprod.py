#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""后期合成工具（需求文档 4.7）单元测试：配音时长估计、占位音轨写出、草样片 GIF 合成。"""
from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

from _util import Checker, ROOT
sys.path.insert(0, str(ROOT / "src"))
from PIL import Image  # noqa: E402
from manhua.postprod import (build_reel_gif, estimate_speech_seconds,  # noqa: E402
                             write_voice_wav)


def main() -> int:
    c = Checker()

    # 配音时长估计：随字数增长、被上下限夹住
    s_short = estimate_speech_seconds("好")
    s_long = estimate_speech_seconds("这是一句相当长的台词" * 5, max_seconds=6.0)
    c.ok("短文本不低于 0.6s 下限", s_short >= 0.6)
    c.ok("长文本被 max 上限夹住", s_long <= 6.0)
    c.ok("长文本时长 > 短文本", s_long > s_short)

    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        # 写占位音轨，时长应接近请求值
        wav = td / "a.wav"
        dur = write_voice_wav(wav, 2.0)
        c.ok("音轨文件已写出", wav.exists())
        with wave.open(str(wav)) as w:
            actual = w.getnframes() / w.getframerate()
        c.ok(f"音轨时长≈2s（实际 {actual:.2f}）", abs(actual - 2.0) < 0.1)
        c.ok("write_voice_wav 返回时长≈2s", abs(dur - 2.0) < 0.1)

        # 草样片 GIF：用两张临时图，4 帧/镜 → 8 帧
        img = td / "s.png"
        Image.new("RGB", (120, 160), (40, 80, 120)).save(img)
        clips = [
            {"shot_id": "S01", "scene": "A", "image_path": str(img), "subtitle": "字幕一", "duration_seconds": 5},
            {"shot_id": "S02", "scene": "B", "image_path": str(img), "subtitle": "字幕二", "duration_seconds": 5},
        ]
        gif = td / "reel.gif"
        ok = build_reel_gif(clips, gif, frames_per_shot=4)
        c.ok("草样片 GIF 生成成功", ok and gif.exists())
        with Image.open(gif) as g:
            c.ok("GIF 是动图(>=8 帧)", getattr(g, "n_frames", 1) >= 8)

        # 无图片输入时应优雅返回 False（不崩）
        c.ok("空输入不崩、返回 False", build_reel_gif([], td / "x.gif") is False)

    return c.done("后期合成测试")


if __name__ == "__main__":
    raise SystemExit(main())
