#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
冒烟测试：离线 mock 模式跑完整闭环，校验关键不变量（无需 pytest，直接 python 运行）。

  python tests/smoke_test.py

校验：① 全部 9 个阶段产出（含导演台/合成/质检）；② 角色/镜头 JSON 严格含 需求文档 附录字段；
     ③ 角色参考图与分镜图都已落盘；④ 一致性不变量：分镜以锚点角色的 seed 出图；
     ⑤ 合规判定存在；⑥ 生成日志有记录；⑦ 合成草样片/配音；⑧ 质检角色一致性。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Windows 控制台 UTF-8 兜底（与 main.py 一致），避免打印 ✅/❌ 报错
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manhua.config import Config  # noqa: E402
from manhua.engine import STAGE_KEYS, new_project_state  # noqa: E402
from manhua.pipeline import build_workflow, make_context  # noqa: E402
from manhua.schemas import Character, Shot  # noqa: E402

# 需求文档 附录 12.1 / 12.2 必须存在的字段
CHAR_FIELDS = {"character_id", "name", "age", "identity",
               "fixed_visual_features", "variable_features", "forbidden_changes", "voice_profile"}
SHOT_FIELDS = {"shot_id", "scene", "characters", "camera", "lighting",
               "action", "duration", "negative_prompt"}

_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond:
        _failures.append(msg)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "proj"
        cfg = Config(mode="mock", seed=20260529)
        ctx = make_context(cfg, out_dir)
        state = new_project_state("末日里少女带着会说话的猫寻找信号源", "smoke")
        state = build_workflow().run(state, ctx)

        print("\n— 校验 —")
        # ① 6 阶段产出
        for k in STAGE_KEYS:
            check(state.stage_done(k), f"阶段 {k} 有产出")

        # ② 附录字段对齐
        check(CHAR_FIELDS.issubset(set(Character.model_fields)), "Character 含 需求文档 附录 12.1 全部字段")
        check(SHOT_FIELDS.issubset(set(Shot.model_fields)), "Shot 含 需求文档 附录 12.2 全部字段")
        check(len(state.characters.characters) >= 1, "至少 1 个角色")
        check(all(c.character_id.startswith("CHAR_") for c in state.characters.characters),
              "角色使用 CHAR_ 前缀的 character_id")
        check(len(state.storyboard.shots) >= 1, "至少 1 个镜头")
        check(all(s.image_prompt and s.video_prompt for s in state.storyboard.shots),
              "每个镜头都有 image_prompt 与 video_prompt")

        # ③ 图像落盘
        check(len(state.art.character_references) == len(state.characters.characters),
              "角色参考图数量 == 角色数")
        check(len(state.art.shot_images) == len(state.storyboard.shots),
              "分镜图数量 == 镜头数")
        check(all(Path(a.image_path).exists() for a in state.art.character_references + state.art.shot_images),
              "所有图像文件已落盘")

        # ④ 一致性不变量：角色 seed 已回填，且分镜复用锚点角色 seed
        seed_map = {c.character_id: c.reference_seed for c in state.characters.characters}
        check(all(c.reference_seed is not None for c in state.characters.characters),
              "每个角色都锁定了 reference_seed")
        ok_anchor = True
        for sh, asset in zip(state.storyboard.shots, state.art.shot_images):
            if sh.characters:
                if asset.seed != seed_map.get(sh.characters[0]):
                    ok_anchor = False
        check(ok_anchor, "分镜图复用了首位出场角色的锁定 seed（一致性锚点）")

        # ⑤ 合规
        check(state.review.compliance_status in {"pass", "warn", "fail"}, "审稿产出合规判定")

        # ⑥ 生成日志
        s = ctx.genlog.summary()
        check(s["total_generations"] >= 10, f"生成日志有记录（{s['total_generations']} 条）")
        check(s["llm_calls"] == 5 and s["image_calls"] >= 1, "LLM/图像调用均被记录")
        check(s["audio_calls"] >= 1 and s["video_calls"] >= 1, "配音/草样片生成均被记录")

        # ⑦ 合成/后期阶段（阶段二）
        check(state.compose is not None, "合成阶段有产出")
        check(len(state.compose.audio_clips) == len(state.storyboard.shots), "每镜都有占位配音")
        check(len(state.compose.timeline.clips) == len(state.storyboard.shots), "剪辑时间线含全部镜头")
        check(state.compose.timeline.aspect_ratio == "9:16", "时间线画幅为竖屏 9:16")
        check(state.compose.reel_path is not None and Path(state.compose.reel_path).exists(),
              "草样片 GIF 已落盘")
        check(all(Path(a.audio_path).exists() for a in state.compose.audio_clips),
              "所有占位配音 .wav 已落盘")
        check(Path(state.compose.assemble_script).exists(), "FFmpeg 成片脚本已生成")
        # 配音时长不超过镜头时长（音画时长对齐）
        clip_dur = {c.shot_id: c.duration_seconds for c in state.compose.timeline.clips}
        check(all(a.duration_seconds <= clip_dur[a.shot_id] + 0.01 for a in state.compose.audio_clips),
              "占位配音时长不超过镜头时长")

        # ⑧ 质检阶段（阶段二）：角色一致性命门
        check(state.qc is not None, "质检阶段有产出")
        check(state.qc.consistency_score >= 0.99,
              f"角色一致性达标（{state.qc.consistency_score:.2f}，应=1.0：分镜复用了锚点 seed/参考图 + 提示词双侧约束）")
        check(state.qc.passed, "质检综合通过")
        dims = {m.dimension for m in state.qc.metrics}
        check({"人物一致性", "结构完整性", "音画同步", "平台适配度"}.issubset(dims),
              "质检覆盖 需求文档 8.1 关键质量维度")

    print()
    if _failures:
        print(f"❌ 冒烟测试失败：{len(_failures)} 项")
        return 1
    print("✅ 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
