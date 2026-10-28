"""手机 / 电脑尺寸验收(公用,v2 第八节)。

用 Playwright 驱动**本机已装的 Edge**(channel="msedge"),通过 DevTools 协议模拟设备尺寸、DPR、
mobile 视口和触屏——不要用 --window-size(Edge 无头窗口最窄约 500px,会得到“假溢出”)。

用法(命令行,只做通用检查 + 截图):
    python mobile_check.py <play/index.html 的路径或 file:// / http:// 地址> <截图输出目录>

用法(项目里 import,加自己的场景断言):
    from tools.mobile_check import run, SIZES      # 本仓库自带这一份
    def scenario(page, size):          # size 是 SIZES 里的一项;返回 list[str] 的失败说明,空表示通过
        fails = []
        if size["kind"] == "mobile":
            page.tap("#tab-play")      # 模拟触摸
            page.wait_for_timeout(300)
            if page.evaluate("document.documentElement.scrollHeight > innerHeight + 1"):
                fails.append("操作模式整页还能滚动")
        return fails
    report = run(url, out_dir, scenario=scenario)
    assert report["ok"], report

通用检查(每个尺寸都做):没有横向溢出(scrollWidth ≤ innerWidth)、没有 JS 报错(pageerror + console.error)、
截一张视口图。电脑尺寸 1920×1080、1366×768 一起跑。

同一时间全机只允许一个 Edge:用系统临时目录下的 claude/e----/edge.lock 排队(其他代理在跑时会等待,最多 10 分钟);
启动前要求空闲内存 ≥ 1500 MB,不够就等。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
import time
from pathlib import Path

SIZES = [
    {"name": "m390x844", "kind": "mobile", "w": 390, "h": 844, "dpr": 3},
    {"name": "m414x896", "kind": "mobile", "w": 414, "h": 896, "dpr": 3},
    {"name": "m360x780", "kind": "mobile", "w": 360, "h": 780, "dpr": 3},
    {"name": "t768x1024", "kind": "mobile", "w": 768, "h": 1024, "dpr": 2},
    {"name": "d1920x1080", "kind": "desktop", "w": 1920, "h": 1080, "dpr": 1},
    {"name": "d1366x768", "kind": "desktop", "w": 1366, "h": 768, "dpr": 1},
]

# 锁文件放在系统临时目录下（和本系列其他项目共用同一把锁，不含用户目录）
LOCK = Path(os.environ.get("EDGE_LOCK", os.path.join(tempfile.gettempdir(), "claude", "e----", "edge.lock")))
MIN_FREE_MB = 1500


def free_mb() -> float:
    if os.name != "nt":
        return 1e9

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    ms = MS(); ms.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    return ms.ullAvailPhys / 1048576


class EdgeLock:
    """全机只跑一个 Edge。锁文件超过 15 分钟视为失效(上一个进程崩了)。"""

    def __init__(self, timeout_s: int = 600):
        self.timeout_s = timeout_s
        self.fd = None

    def __enter__(self):
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                if LOCK.exists() and time.time() - LOCK.stat().st_mtime > 900:
                    LOCK.unlink()
                self.fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                break
            except FileExistsError:
                if time.time() - t0 > self.timeout_s:
                    raise TimeoutError("等待 Edge 锁超时(别的代理在跑浏览器):%s" % LOCK)
                time.sleep(5)
        while free_mb() < MIN_FREE_MB:
            if time.time() - t0 > self.timeout_s:
                self.__exit__(None, None, None)
                raise TimeoutError("空闲内存不足 %d MB,放弃启动 Edge" % MIN_FREE_MB)
            time.sleep(10)
        return self

    def __exit__(self, *a):
        if self.fd is not None:
            os.close(self.fd); self.fd = None
        try:
            LOCK.unlink()
        except OSError:
            pass


def to_url(target: str) -> str:
    if target.startswith(("http://", "https://", "file://")):
        return target
    return Path(target).resolve().as_uri()


def run(target: str, out_dir: str | os.PathLike, scenario=None, sizes=None, settle_ms: int = 1500, headless: bool = True) -> dict:
    from playwright.sync_api import sync_playwright

    url = to_url(target)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    sizes = sizes or SIZES
    report = {"url": url, "ok": True, "sizes": []}
    with EdgeLock(), sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=headless)
        try:
            for s in sizes:
                mobile = s["kind"] == "mobile"
                ctx = browser.new_context(viewport={"width": s["w"], "height": s["h"]}, device_scale_factor=s["dpr"],
                                          is_mobile=mobile, has_touch=mobile, locale="zh-CN")
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
                page.on("console", lambda m: errors.append("console.error: %s" % m.text) if m.type == "error" else None)
                page.goto(url); page.wait_for_timeout(settle_ms)
                fails: list[str] = []
                dims = page.evaluate("({sw:document.documentElement.scrollWidth, iw:innerWidth, sh:document.documentElement.scrollHeight, ih:innerHeight})")
                # 手机模拟下,内容比视口宽时 Chrome 会自动缩小初始比例,innerWidth 会跟着变大(例如 390 变 584),
                # 所以要和设备宽度比,不能只和 innerWidth 比
                if dims["sw"] > s["w"] + 1 or dims["iw"] > s["w"] + 1:
                    fails.append("横向溢出 scrollWidth=%d innerWidth=%d > 设备宽 %d" % (dims["sw"], dims["iw"], s["w"]))
                if scenario is not None:
                    try:
                        fails += list(scenario(page, s) or [])
                    except Exception as e:  # 场景本身抛错也算失败
                        fails.append("场景异常:%r" % (e,))
                # 过滤 file:// 下常见的无害报错(favicon)
                errors = [e for e in errors if "favicon" not in e.lower()]
                fails += errors
                shot = out / ("%s.png" % s["name"])
                page.screenshot(path=str(shot), full_page=False)
                rec = {**s, "dims": dims, "fails": fails, "screenshot": str(shot)}
                report["sizes"].append(rec)
                if fails:
                    report["ok"] = False
                ctx.close()
        finally:
            browser.close()
    (out / "mobile_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv):
    if len(argv) < 3:
        print(__doc__); return 2
    rep = run(argv[1], argv[2])
    for s in rep["sizes"]:
        print("%-11s %4dx%-4d %s" % (s["name"], s["w"], s["h"], "通过" if not s["fails"] else "失败:" + " | ".join(s["fails"])))
    print("总结:", "全部通过" if rep["ok"] else "有失败项")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
