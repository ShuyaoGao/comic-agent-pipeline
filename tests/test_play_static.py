#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
play/ 静态页检查（无需 pytest、不启动浏览器）：

  python tests/test_play_static.py

① index.html / director.html 只用普通 <script src> 引本地文件（file:// 双击可用，不用 module、不连 CDN）；
② play/ 里没有 fetch / XHR / WebSocket / 动态 import / service worker；
③ 页面上不出现商业模型 / 平台的真实名称（中性名称集中在 play/names.js）；
④ play/js/credits.js 与 credits.json 一致；three.js 附带 MIT LICENSE；
⑤ 页面外壳要素齐全（三个模式、说明、退出、大屏、页脚、结束页文案）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _util import Checker, ROOT

PLAY = ROOT / "play"
BRANDS = ["DeepSeek", "deepseek", "即梦", "Seedream", "seedream", "可灵", "Kling", "kling", "Vidu", "Sora", "抖音", "B站",
          "B 站", "小红书", "YouTube", "Nano Banana", "nano-banana", "Gemini", "CosyVoice", "IndexTTS", "腾讯", "火山",
          "Wan2", "Hunyuan", "Qwen", "qwen", "ComfyUI", "SDXL", "OpenAI", "GPT", "Claude", "Ollama", "ollama", "PDF"]


def own_files():
    """自写的页面文件（vendor/ 里的第三方库不查）。"""
    return [p for p in PLAY.rglob("*") if p.is_file() and p.suffix in {".html", ".js", ".css"} and "vendor" not in p.parts]


def main() -> int:
    c = Checker()
    for page in ("index.html", "director.html"):
        html = (PLAY / page).read_text(encoding="utf-8")
        srcs = re.findall(r'<script[^>]*\ssrc="([^"]+)"', html)
        hrefs = re.findall(r'<link[^>]*\shref="([^"]+)"', html)
        c.ok(f"{page}：没有 type=module", 'type="module"' not in html)
        c.ok(f"{page}：脚本 / 样式都是本地文件且存在",
             bool(srcs) and all(not re.match(r"^(https?:)?//", r) and (PLAY / r).is_file() for r in srcs + hrefs))

    banned = [r"\bfetch\s*\(", r"XMLHttpRequest", r"\bimport\s*\(", r"^\s*import\s", r"serviceWorker", r"WebSocket",
              r"sendBeacon"]
    bad = []
    for p in own_files():
        text = p.read_text(encoding="utf-8")
        bad += [f"{p.name}:{pat}" for pat in banned if re.search(pat, text, re.M)]
        if p.name not in ("credits.js",):
            bad += [f"{p.name}:URL" for _ in re.finditer(r"https?://", text)]
    c.ok("play/ 没有网络请求 / 动态加载 / 外部 URL" + (f"：{bad}" if bad else ""), not bad)

    hits = []
    for p in own_files():
        text = p.read_text(encoding="utf-8")
        hits += [f"{p.relative_to(PLAY).as_posix()}:{b}" for b in BRANDS if b in text]
    c.ok("页面上没有商业模型 / 平台真实名称" + (f"：{hits}" if hits else ""), not hits)

    credits = json.loads((ROOT / "credits.json").read_text(encoding="utf-8"))
    js = (PLAY / "js" / "credits.js").read_text(encoding="utf-8")
    payload = json.loads(js.split("window.CREDITS = ", 1)[1].rstrip().rstrip(";"))
    c.ok("credits.js 与 credits.json 一致", payload == {k: v for k, v in credits.items() if not k.startswith("_")})
    sample = (PLAY / "js" / "sample_export.js").read_text(encoding="utf-8")
    c.ok("sample_export.js 与 tools/sample_director_export.json 一致",
         json.loads(sample.split("window.SAMPLE_DIRECTOR_EXPORT = ", 1)[1].rstrip().rstrip(";"))
         == json.loads((ROOT / "tools" / "sample_director_export.json").read_text(encoding="utf-8")))
    lic = PLAY / "vendor" / "three" / "LICENSE"
    c.ok("three.js r128 附带 MIT LICENSE", lic.is_file() and "MIT License" in lic.read_text(encoding="utf-8")
         and "Three.js Authors" in (PLAY / "vendor" / "three" / "three.min.js").read_text(encoding="utf-8")[:200])

    html = (PLAY / "index.html").read_text(encoding="utf-8")
    for needle in ['data-mode="watch"', 'data-mode="edit"', 'data-mode="practice"', 'id="help-btn"', 'id="exit-btn"',
                   'id="bigscreen"', 'id="footer"', 'id="dlg-help"', 'id="cost-presets"', 'id="speed-presets"',
                   "所有计算都已结束，可以直接关闭这个标签页",
                   # 手机竖屏（v2 第八节）：☰ 菜单、过程面板全屏按钮与「返回」、横屏提示、触屏图解、手机样式与脚本
                   'id="menu-btn"', 'id="menu"', 'id="menu-help"', 'id="menu-exit"', 'id="panel-btn"', 'id="panel-close"',
                   'id="rotate-hint"', 'class="touch-only"', 'href="css/mobile.css"', 'src="js/mobile.js"']:
        c.ok(f"index.html 含 {needle}", needle in html)
    c.ok("帮助浮层的触屏图解是内联 SVG（不引用外部图片）", "<svg" in html.split('id="dlg-help"', 1)[1])
    c.ok("credits.json 含 AUTHOR_EMAIL（页脚、README、CITATION.cff、LICENSE-docs 共用）", bool(credits.get("AUTHOR_EMAIL")))
    app_js = (PLAY / "js" / "app.js").read_text(encoding="utf-8")
    c.ok("页脚会写出联系邮箱", "AUTHOR_EMAIL" in app_js and "AUTHOR_EMAIL" in (PLAY / "director.html").read_text(encoding="utf-8"))
    return c.done("play/ 静态页检查")


if __name__ == "__main__":
    sys.exit(main())
