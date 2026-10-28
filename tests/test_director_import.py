#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""3D 导演台导入（需求文档 第六章闭环）测试：导出 JSON 严格按 Shot 校验，能拦非法、能识别未知角色。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _util import Checker, ROOT
sys.path.insert(0, str(ROOT / "src"))
from manhua.director_import import load_storyboard, unknown_character_ids  # noqa: E402


def main() -> int:
    c = Checker()
    sample = ROOT / "tools" / "sample_director_export.json"

    sb = load_storyboard(sample)
    c.ok("样例导出解析出 3 个镜头", len(sb.shots) == 3)
    c.ok("镜头相机参数正确解析", sb.shots[0].camera.shot_size == "全景")
    c.ok("导入镜头均含 image/video/negative 提示词",
         all(s.image_prompt and s.video_prompt and s.negative_prompt for s in sb.shots))

    # 容错：缺字段的非法导出应被 Pydantic 拦下
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text('{"shots":[{"shot_id":"X"}]}', encoding="utf-8")
        raised = False
        try:
            load_storyboard(bad)
        except ValueError:
            raised = True
        c.ok("缺字段非法导出被拦下并报错", raised)

        # 单个 shot 对象 / 裸列表 两种格式也能解析
        one = Path(tmp) / "one.json"
        one.write_text(sb.shots[0].model_dump_json(), encoding="utf-8")
        c.ok("单个 shot 对象格式可解析", len(load_storyboard(one).shots) == 1)

    # 未知角色 id 检测（喂回流水线前用于提示）
    unknown = unknown_character_ids(sb, {"CHAR_001"})
    c.ok("能识别项目未定义的 character_id", unknown == {"CHAR_002"})

    return c.done("3D 导演台导入测试")


if __name__ == "__main__":
    raise SystemExit(main())
