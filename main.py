#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AIGC 漫剧多 Agent 生成平台 · MVP 命令行入口（需求文档 第 10.1 节）。

用法示例：
  # 离线零预算跑通完整闭环（默认 mock 模式，无需任何 API key）
  python main.py "一个程序员意外重生回到大学，要在毕业前阻止一场实验室事故"

  # 指定项目名、随机种子
  python main.py "末日里，少女带着会说话的猫寻找信号源" --project end_of_world --seed 42

  # 单步重跑/回滚：只重跑分镜及其后续（保留前面已确认产物）
  python main.py --resume <project_id> --from storyboard

  # 切真实模型（需先在 config.yaml 把 runtime.mode 改 real，并在 .env 填 key）
  python main.py "..." --mode real
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows 控制台中文/UTF-8 输出兜底
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from manhua.assets import save_asset_library, write_report  # noqa: E402
from manhua.config import Config  # noqa: E402
from manhua.costing import estimate_cost, save_cost_report  # noqa: E402
from manhua.dispatch import dispatch_models, save_dispatch_plan  # noqa: E402
from manhua.engine import STAGE_KEYS, ProjectState, new_project_state  # noqa: E402
from manhua.pipeline import build_workflow, make_context  # noqa: E402
from manhua.viewer import write_viewer  # noqa: E402


def _slugify(text: str, maxlen: int = 16) -> str:
    keep = "".join(ch for ch in text if ch.isalnum() or "一" <= ch <= "鿿")
    return (keep[:maxlen] or "project")


def main() -> int:
    p = argparse.ArgumentParser(description="AIGC 漫剧多 Agent 生成平台 MVP")
    p.add_argument("idea", nargs="?", help="一句话创意（新建项目时必填）")
    p.add_argument("--config", default="config.yaml", help="配置文件路径")
    p.add_argument("--mode", choices=["mock", "ollama", "real"],
                   help="覆盖运行模式（ollama=本地真实小模型，零费用无需 key）")
    p.add_argument("--seed", type=int, help="覆盖全局随机种子")
    p.add_argument("--project", help="项目名（决定输出子目录名）")
    p.add_argument("--resume", metavar="PROJECT_ID", help="从已有项目目录续跑")
    p.add_argument("--from", dest="start_from", choices=STAGE_KEYS,
                   help="从指定阶段重跑（清空该阶段及后续）")
    p.add_argument("--storyboard-from", metavar="EXPORT_JSON",
                   help="用 3D 导演台导出的镜头 JSON 替换分镜，并重跑 美术→合成→质检（需配合 --resume）")
    args = p.parse_args()

    config = Config.load(args.config)
    if args.mode:
        config.mode = args.mode
    if args.seed is not None:
        config.seed = args.seed

    out_root = ROOT / config.output_dir

    # —— 确定项目与状态（新建 / 续跑）——
    if args.resume:
        project_id = args.resume
        out_dir = out_root / project_id
        if not (out_dir / "state.json").exists():
            print(f"✗ 找不到项目 {project_id} 的检查点：{out_dir / 'state.json'}")
            return 2
        state = ProjectState.load(out_dir)
        print(f"⟳ 续跑项目 {project_id}（创意：{state.idea_text}）")
    else:
        if not args.idea:
            p.error("新建项目需要提供一句话创意，例如：python main.py \"你的创意\"")
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_id = args.project or f"{_slugify(args.idea)}_{stamp}"
        out_dir = out_root / project_id
        state = new_project_state(args.idea, project_id)

    print("=" * 64)
    print(f"项目 ID：{project_id}")
    print(f"运行模式：{config.mode}（mock=离线零预算 / ollama=本地真实小模型 / real=云端 API）")
    llm_label = {"real": config.llm.model,
                 "ollama": f"ollama:{config.ollama.model}"}.get(config.mode, "mock-llm-offline")
    print(f"LLM：{llm_label} ｜ "
          f"图像：{config.image.provider} ｜ 全局 seed：{config.seed}")
    print(f"输出目录：{out_dir}")
    print("=" * 64)

    # —— 3D 导演台导出的分镜注入（需配合 --resume）——
    if args.storyboard_from:
        if not args.resume:
            print("✗ --storyboard-from 需配合 --resume <已有项目>（要复用其角色表出图）。")
            return 2
        from manhua.director_import import load_storyboard, unknown_character_ids
        try:
            sb = load_storyboard(args.storyboard_from)
        except Exception as e:
            print(f"✗ 导入分镜失败：{e}")
            return 2
        known = {c.character_id for c in state.characters.characters} if state.characters else set()
        unknown = unknown_character_ids(sb, known)
        if unknown:
            print(f"   [提示] 导入分镜引用了项目中不存在的角色 {sorted(unknown)}，"
                  f"这些镜将无法复用角色 seed/参考图（质检会相应扣分）。")
        state.storyboard = sb
        state.reset_from("art")   # 清空美术及之后，用新分镜重跑
        print(f"↪ 已用 3D 导演台导出替换分镜（{len(sb.shots)} 镜），将重跑 美术→合成→质检")
        args.start_from = None

    try:
        ctx = make_context(config, out_dir)
        if args.resume:
            ctx.genlog.load_existing(out_dir / "generation_log.jsonl")  # 保留历史日志
        workflow = build_workflow()
        state = workflow.run(state, ctx, start_from=args.start_from)
    except RuntimeError as e:
        # 典型场景：real 模式缺少 API key、云端图像未配置。给出干净提示而非堆栈。
        print(f"\n✗ 运行中止：{e}")
        print("  提示：默认 mock 模式无需任何 key，可直接：python main.py \"你的创意\"")
        return 2

    # —— 收尾：资产库 + 成本估算 + 看板 + 复盘报告 + 日志 ——
    ctx.genlog.save(out_dir / "generation_log.jsonl")
    lib_path = save_asset_library(state, out_dir)
    summary = ctx.genlog.summary()
    cost_report = estimate_cost(state, ctx.genlog, config)
    cost_path = save_cost_report(cost_report, out_dir)
    dispatch_plan = dispatch_models(state, config)
    dispatch_path = save_dispatch_plan(dispatch_plan, out_dir)
    report_path = write_report(state, out_dir, summary, cost_report, dispatch_plan)
    viewer_path = write_viewer(state, out_dir, summary, cost_report, dispatch_plan)

    print("\n" + "=" * 64)
    print("✅ 闭环完成。交付物：")
    print(f"  - 项目看板(浏览器打开)：{viewer_path}")
    print(f"  - 完整状态/检查点：{out_dir / 'state.json'}")
    print(f"  - 分阶段 JSON：{out_dir}/01_idea.json … 09_qc.json")
    print(f"  - 角色参考图 + 分镜图 + 导演台俯视图：{out_dir / 'assets'}")
    print(f"  - 草样片预览(GIF)：{out_dir / 'preview.gif'}")
    print(f"  - 剪辑时间线：{out_dir / 'timeline.json'} ｜ 成片脚本：{out_dir / 'assemble.ps1'}")
    print(f"  - 资产库索引：{lib_path}")
    print(f"  - 成本估算：{cost_path} ｜ 多模型调度：{dispatch_path}")
    print(f"  - 生成日志：{out_dir / 'generation_log.jsonl'}")
    print(f"  - 复盘报告：{report_path}")
    print("-" * 64)
    print(f"生成日志汇总：{summary}")
    if state.review:
        print(f"合规判定：{state.review.compliance_status}")
    if state.qc:
        print(f"质检：角色一致性 {state.qc.consistency_score:.2f} ｜ 综合 {state.qc.overall_score}/10 ｜ {'通过' if state.qc.passed else '需关注'}")
    print(f"成本：本次实跑 ${cost_report.actual_cost_usd} ｜ 真实模型估算 ${cost_report.estimated_real_cost_usd}")
    print(f"调度：{dispatch_plan.real_video_shots} 镜真实视频/{dispatch_plan.placeholder_shots} 镜占位 ｜ "
          f"视频成本 ${dispatch_plan.full_video_cost_usd}→${dispatch_plan.dispatched_video_cost_usd}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        _code = main()
    except BrokenPipeError:
        # 下游管道提前关闭（如 | head / Select-Object -First N），属正常，不算失败
        _code = 0
    raise SystemExit(_code)
