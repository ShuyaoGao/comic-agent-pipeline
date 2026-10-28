"""测试公共工具：跑一遍离线 mock 流水线 + 一个极简断言器（无需 pytest）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from manhua.config import Config  # noqa: E402
from manhua.engine import new_project_state  # noqa: E402
from manhua.pipeline import build_workflow, make_context  # noqa: E402


def run_pipeline(out_dir: Path, idea: str = "末日里少女带着会说话的猫寻找信号源", seed: int = 20260529):
    """离线跑完整流水线，返回 (state, ctx, config)。"""
    cfg = Config(mode="mock", seed=seed)
    ctx = make_context(cfg, out_dir)
    state = new_project_state(idea, "test")
    state = build_workflow().run(state, ctx)
    return state, ctx, cfg


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, name: str, cond: bool) -> None:
        if cond:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed += 1
            print(f"  [FAIL] {name}")

    def done(self, title: str) -> int:
        print(f"\n{title}：{self.passed} 通过，{self.failed} 失败")
        return 0 if self.failed == 0 else 1
