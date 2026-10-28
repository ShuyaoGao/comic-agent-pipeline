# -*- coding: utf-8 -*-
"""pytest 入口：把 tests/run_all.py 里的每个脚本式测试各作为一个用例跑一遍（子进程，UTF-8 输出）。

    python -m pytest -q          # 内部目录和公开仓库里都能跑；没有 Node.js 时 test_parity.py 自己会跳过比对
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_all import TESTS  # noqa: E402

SCRIPTS = [t for t in TESTS if (HERE / t).exists()]


@pytest.mark.parametrize("script", SCRIPTS)
def test_script(script):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / script)], cwd=str(HERE.parent), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    assert r.returncode == 0, f"{script} failed (exit {r.returncode})\n--- stdout ---\n{r.stdout[-4000:]}\n--- stderr ---\n{r.stderr[-2000:]}"
