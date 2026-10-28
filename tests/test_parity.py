#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JS 移植（play/js/）与 Python 流水线的逐字段比对（无需 pytest，直接 python 运行）。

  python tests/test_parity.py                  # 比对
  python tests/test_parity.py --write-result   # 比对并把结果写进 results/parity.json（README 的数字来自这里）

做法：用 Node 跑 tests/js/run_cases.js 得到浏览器版对 tests/parity_cases.json 里每个创意的全部产物；
再用同一份配置（Node 输出的 config）跑 Python 版流水线；把 Python 的绝对路径换成项目内相对路径、
去掉时间戳（created_at / timestamp）之后，要求 state / 生成日志 / 日志汇总 / 成本 / 调度 / 资产库 逐字段相同。
没装 Node.js 时跳过（返回 0 并打印“跳过”）。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from _util import Checker, ROOT  # noqa: F401  (_util 已把 src/ 放进 sys.path)

from manhua.assets import build_asset_library  # noqa: E402
from manhua.config import Config  # noqa: E402
from manhua.costing import estimate_cost  # noqa: E402
from manhua.dispatch import dispatch_models  # noqa: E402
from manhua.engine import new_project_state  # noqa: E402
from manhua.pipeline import build_workflow, make_context  # noqa: E402

FLOAT_FIELDS = {
    "llm": ["price_input_per_mtok_usd", "price_input_cached_per_mtok_usd", "price_output_per_mtok_usd"],
    "image": ["price_per_image_usd"],
    "cost": ["video_per_second_usd", "tts_per_1k_chars_usd"],
}


def python_config(js_cfg: dict) -> Config:
    """把 Node 输出的配置还原成 Python Config（单价按 dataclass 类型转成 float）。"""
    cfg = Config(mode="mock", seed=int(js_cfg["seed"]))
    for sec in ("llm", "image", "compose", "cost", "dispatch"):
        obj = getattr(cfg, sec)
        for k, v in js_cfg[sec].items():
            if k in FLOAT_FIELDS.get(sec, []):
                v = float(v)
            if sec == "image" and k == "size":
                v = tuple(v)
            setattr(obj, k, v)
    return cfg


def normalize(obj, prefix: str):
    """绝对路径 → 项目内相对路径（/ 分隔）；去掉时间戳字段。"""
    if isinstance(obj, dict):
        return {k: normalize(v, prefix) for k, v in obj.items() if k not in ("timestamp", "created_at")}
    if isinstance(obj, list):
        return [normalize(v, prefix) for v in obj]
    if isinstance(obj, str) and obj.startswith(prefix):
        return obj[len(prefix):].lstrip("\\/").replace("\\", "/")
    return obj


def first_diff(a, b, path="$"):
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))
                                       and not isinstance(a, bool) and not isinstance(b, bool)):
        return f"{path}: 类型不同 {type(a).__name__} vs {type(b).__name__}（{a!r} vs {b!r}）"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}: 只在一边出现"
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: 长度不同 {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} vs {b!r}"


def main() -> int:
    c = Checker()
    node = shutil.which("node")
    if not node:
        print("跳过：没有安装 Node.js（JS 版比对需要 node）")
        return 0
    cases_file = ROOT / "tests" / "parity_cases.json"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([node, str(ROOT / "tests" / "js" / "run_cases.js"), str(cases_file)],
                       capture_output=True, env=env, timeout=300)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", "replace"))
    c.ok("Node 跑完 JS 版流水线", r.returncode == 0)
    if r.returncode != 0:
        return c.done("JS / Python 逐字段比对")
    js_runs = json.loads(r.stdout.decode("utf-8"))

    summary: dict = {}
    with tempfile.TemporaryDirectory() as tmp:
        for i, js in enumerate(js_runs, 1):
            cfg = python_config(js["config"])
            out_dir = Path(tmp) / f"case{i:02d}"
            ctx = make_context(cfg, out_dir)
            state = new_project_state(js["idea"], "parity")
            with contextlib.redirect_stdout(io.StringIO()):      # 工作流逐阶段的打印不进测试输出
                state = build_workflow().run(state, ctx)
            py = {
                "state": state.to_dict(),
                "genlog": [asdict(rec) for rec in ctx.genlog.records],
                "summary": ctx.genlog.summary(),
                "cost": estimate_cost(state, ctx.genlog, cfg).model_dump(),
                "dispatch": dispatch_models(state, cfg).model_dump(),
                "library": build_asset_library(state),
            }
            py = normalize(json.loads(json.dumps(py)), str(out_dir))
            jsn = normalize(js, "\0")
            label = f"#{i} seed={js['seed']} {js['preset']}「{js['idea'][:14].strip()}」"
            for part in ("state", "genlog", "summary", "cost", "dispatch", "library"):
                d = first_diff(py[part], jsn[part], part)
                c.ok(f"{label} {part} 逐字段一致" + (f" —— {d}" if d else ""), d is None)
                summary.setdefault(label, {})[part] = d is None
    if "--write-result" in sys.argv:
        out = {
            "_note": "Generated by python tests/test_parity.py --write-result. Each case is run by the browser JS port "
                     "(Node.js) and by the Python pipeline with the same config; parts are compared field by field after "
                     "turning absolute paths into project-relative ones and dropping timestamps.",
            "python": sys.version.split()[0],
            "node": subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip(),
            "cases": len(js_runs), "parts_per_case": 6,
            "compared": c.passed + c.failed - 1, "identical": c.passed - 1, "different": c.failed,
            "per_case": summary,
        }
        path = ROOT / "results" / "parity.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return c.done("JS / Python 逐字段比对")


if __name__ == "__main__":
    raise SystemExit(main())
