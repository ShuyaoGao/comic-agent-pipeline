#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键跑全部测试（无需 pytest）：依次运行冒烟测试与各单元/集成测试，汇总结果。

  python tests/run_all.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

HERE = Path(__file__).resolve().parent

TESTS = [
    "smoke_test.py",       # 端到端冒烟（9 阶段闭环 + 一致性不变量）
    "test_director.py",    # 导演台：几何/俯视图/提示词/一致性保持
    "test_director_import.py",  # 3D 导演台导出 → Shot 校验导入（需求文档 第六章闭环）
    "test_ollama_adapter.py",   # 本地 Ollama 适配器：think 剥离/JSON 提取/重试（不联网）
    "test_qc_negative.py",  # 质检反例：证明一致性检测能抓到不一致
    "test_costing.py",     # 成本控制估算
    "test_dispatch.py",    # 多模型调度（需求文档 4.6）
    "test_postprod.py",    # 后期合成工具（配音/草样片）
    "test_viewer.py",      # 项目看板：自包含 HTML + 资产引用可解析
    "test_library.py",     # 跨项目资产库检索
    "test_parity.py",      # 浏览器 JS 版（play/js/）与 Python 版逐字段一致（需要 Node.js，没有则跳过）
    "test_play_static.py", # play/ 静态页：file:// 规则、中性名称、署名（不启动浏览器）
]


def main() -> int:
    results = []
    for t in TESTS:
        path = HERE / t
        if not path.exists():
            print(f"… 跳过（不存在）：{t}")
            continue
        print(f"\n{'=' * 60}\n▶ 运行 {t}\n{'=' * 60}")
        r = subprocess.run([sys.executable, str(path)])
        results.append((t, r.returncode))

    print(f"\n{'#' * 60}\n# 测试汇总\n{'#' * 60}")
    ok = 0
    for t, code in results:
        flag = "通过" if code == 0 else "失败"
        if code == 0:
            ok += 1
        print(f"  [{flag}] {t}")
    total = len(results)
    print(f"\n{ok}/{total} 个测试文件通过")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
