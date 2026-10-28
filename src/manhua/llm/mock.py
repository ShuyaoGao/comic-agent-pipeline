"""
离线 mock LLM —— 不联网、零花费、确定性输出。

它**不是真实模型**：而是根据上游结构化数据（创意/剧本/角色）确定性地『编造』连贯内容，
让整条多 Agent 流水线在没有任何 API key 的情况下也能完整跑通、现场演示。
内容全部原创、与具体在世作品/创作者无关（合规，需求文档 第八章）。

填了真实 DeepSeek key 并把 config 的 mode 改成 real，即用真实模型替换它，agents 代码无需改动。
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

from pydantic import BaseModel

from .base import LLMClient, LLMResult

# 题材关键词 -> （题材名, 默认场景, 情绪基调, 服装/标志元素）
_GENRE_MAP: list[tuple[tuple[str, ...], dict[str, str]]] = [
    (("校园", "青春", "同学", "高中", "大学"),
     {"genre": "校园情感", "scene": "教学楼天台", "tone": "青涩而炽热", "wardrobe": "藏青校服"}),
    (("悬疑", "推理", "凶案", "真相", "失踪"),
     {"genre": "都市悬疑", "scene": "老旧公寓走廊", "tone": "紧张压抑", "wardrobe": "深色风衣"}),
    (("古风", "宫廷", "江湖", "侠", "王朝"),
     {"genre": "古风权谋", "scene": "雕花长廊", "tone": "暗流涌动", "wardrobe": "素色长袍"}),
    (("末日", "丧尸", "废土", "病毒", "幸存"),
     {"genre": "末日科幻", "scene": "地下实验室走廊", "tone": "冷峻压抑", "wardrobe": "战术夹克"}),
    (("赛博", "机甲", "黑客", "霓虹", "义体"),
     {"genre": "赛博奇幻", "scene": "霓虹雨夜街道", "tone": "迷离冷艳", "wardrobe": "发光风衣"}),
    (("豪门", "婚恋", "总裁", "联姻", "契约"),
     {"genre": "豪门婚恋", "scene": "落地窗会客厅", "tone": "克制而暗涌", "wardrobe": "剪裁西装"}),
    (("复仇", "重生", "逆袭", "打脸", "归来"),
     {"genre": "都市复仇", "scene": "高层写字楼", "tone": "凌厉决绝", "wardrobe": "黑色西装"}),
]
_DEFAULT_GENRE = {"genre": "都市情感", "scene": "城市街角咖啡馆", "tone": "温暖治愈", "wardrobe": "米色风衣"}

_SURNAMES = ["林", "沈", "江", "顾", "苏", "陆", "白", "云", "夜", "商", "温", "裴"]
_GIVEN = ["未央", "知夏", "行舟", "时砚", "南乔", "听澜", "怀瑾", "向晚", "斯年", "晏清", "执初", "屿安"]

_HAIR = ["黑色长发", "栗棕色短发", "银灰色束发", "墨色齐肩发", "深棕卷发"]
_EYES = ["浅灰色瞳孔", "琥珀色眼眸", "深褐色眼睛", "冷蓝色瞳孔", "墨绿色眼眸"]
_MARKS = ["左眼下方小痣", "右眉骨浅疤", "颈侧蝶形胎记", "无明显标记", "左耳银色耳骨钉"]
_VOICES = ["清冷、低声、语速中等", "温润、偏低、语速偏慢", "明亮、轻快、语速偏快", "沙哑、磁性、语速沉稳"]

# 合规红线关键词（需求文档 第八章：不复刻具体作品/不模仿在世创作者）
_COMPLIANCE_RED_FLAGS = ["同款", "复刻", "一模一样", "照搬", "模仿某博主", "抄", "翻拍", "原班"]


class MockLLM(LLMClient):
    name = "mock-llm-offline"

    def __init__(self, seed: int = 20260529):
        self.base_seed = seed

    # ---- 工具：确定性随机数 ----
    def _rng(self, *parts: Any) -> random.Random:
        h = hashlib.md5("|".join(map(str, parts)).encode("utf-8")).hexdigest()
        return random.Random((self.base_seed + int(h[:8], 16)) % (2**31))

    @staticmethod
    def _est_tokens(text: str) -> int:
        # 粗略估计：中文约 1 字 ≈ 1~2 token，这里取保守值供日志展示
        return max(1, len(text) // 2)

    def _genre_for(self, idea_text: str) -> dict[str, str]:
        for keys, info in _GENRE_MAP:
            if any(k in idea_text for k in keys):
                return info
        return _DEFAULT_GENRE

    # ---- 主入口 ----
    def generate_structured(self, *, task, system, user, schema, context) -> LLMResult:
        fab = {
            "idea": self._fab_idea,
            "script": self._fab_script,
            "review": self._fab_review,
            "character": self._fab_character,
            "storyboard": self._fab_storyboard,
        }.get(task)
        if fab is None:
            raise ValueError(f"mock LLM 不认识的任务: {task}")

        output: BaseModel = fab(context, schema)
        out_text = output.model_dump_json()
        return LLMResult(
            output=output,
            model=self.name,
            prompt=(system + "\n\n" + user)[:4000],
            input_tokens=self._est_tokens(system + user),
            output_tokens=self._est_tokens(out_text),
            cost_usd=0.0,  # 离线，零成本
            params={"task": task, "offline": True},
        )

    # ---- 各 Agent 的内容编造器（确定性，依赖上游 context 保持连贯）----
    def _fab_idea(self, context, schema):
        idea_text: str = context.get("idea_text", "一个普通人意外卷入风波的故事")
        g = self._genre_for(idea_text)
        rng = self._rng("idea", idea_text)

        # 生成 3 个原创角色雏形，名字一次定下，后续 Agent 复用 -> 天然一致
        roles = ["主角", "对手/反派", "关键配角"]
        seeds = []
        used = set()
        for r in roles:
            while True:
                name = rng.choice(_SURNAMES) + rng.choice(_GIVEN)
                if name not in used:
                    used.add(name)
                    break
            one_line = {
                "主角": f"在『{g['genre']}』情境中被迫直面{g['tone']}处境、逐步觉醒的核心人物",
                "对手/反派": "手握资源、与主角立场对立、推动核心冲突升级的施压者",
                "关键配角": "串联信息、在转折点给主角关键助力或刺激的人物",
            }[r]
            seeds.append({"name": name, "role": r, "one_line": one_line})

        return schema.model_validate({
            "premise": f"围绕『{idea_text.strip()}』展开的{g['genre']}短篇漫剧：{seeds[0]['name']}"
                       f"因一桩意外被卷入漩涡，与{seeds[1]['name']}展开博弈。",
            "genre": g["genre"],
            "target_audience": "18-30 岁短视频与漫剧受众",
            "core_conflict": f"{seeds[0]['name']} 的目标与 {seeds[1]['name']} 的利益正面相撞，且时间紧迫。",
            "emotional_tone": g["tone"],
            "opening_hook": "前 3 秒抛出一个反常画面 + 一句悬念旁白，制造『这是怎么回事』的追看欲。",
            "series_potential": "采用单元式悬念结构，每集留钩子，便于系列化扩展为多集漫剧。",
            "type_structure_notes": [
                f"{g['genre']}类型常见节奏：钩子→冲突铺陈→中段反转→高潮对决→留白",
                "只借鉴该类型的『节奏与结构规律』，不复制任何具体作品的剧情/台词/角色（合规）",
            ],
            "character_seeds": seeds,
            "candidate_directions": [
                f"方向A（强冲突）：开篇即把 {seeds[0]['name']} 推到绝境，靠反转翻盘。",
                f"方向B（强情感）：放慢节奏，突出 {seeds[0]['name']} 与 {seeds[2]['name']} 的羁绊。",
                f"方向C（强悬念）：以谜题驱动，每集揭一层真相。",
            ],
        })

    def _fab_script(self, context, schema):
        idea = context.get("idea", {})
        idea_text = context.get("idea_text", "")
        g = self._genre_for(idea_text + idea.get("genre", ""))
        seeds = idea.get("character_seeds", [])
        names = [s["name"] for s in seeds] or ["主角"]
        hero = names[0]
        rival = names[1] if len(names) > 1 else "对手"
        ally = names[2] if len(names) > 2 else hero

        scenes = []
        scene_defs = [
            ("SC01", g["scene"], "深夜",
             f"{hero} 察觉异常，独自前往{g['scene']}查探，气氛{g['tone']}。",
             [hero],
             [("旁白", "narration", "有些门，一旦推开就再也关不上。"),
              (hero, "action", f"{hero} 屏住呼吸，缓步走向走廊尽头。"),
              (hero, "dialogue", "……这里到底发生过什么？")]),
            ("SC02", g["scene"], "紧接上场",
             f"{rival} 现身，与 {hero} 正面交锋，核心冲突点燃。",
             [hero, rival],
             [(rival, "dialogue", "我劝你别再往前一步。"),
              (hero, "dialogue", "晚了。我已经看见了。"),
              (rival, "action", f"{rival} 眼神骤冷，逼近一步。")]),
            ("SC03", "转场·关键地点", "稍后",
             f"{ally} 带来关键信息，{hero} 做出抉择，留下钩子。",
             [hero, ally],
             [(ally, "dialogue", f"{hero}，你要的证据，我找到了。"),
              (hero, "narration", "原来从一开始，我就站在棋盘里。"),
              (hero, "action", f"{hero} 攥紧手中之物，转身走入夜色。")]),
        ]
        for sid, loc, tod, summary, on_stage, lines in scene_defs:
            scenes.append({
                "scene_id": sid, "location": loc, "time_of_day": tod, "summary": summary,
                "on_stage": on_stage,
                "script_lines": [
                    {"speaker": sp, "kind": kind, "content": c} for sp, kind, c in lines
                ],
            })

        return schema.model_validate({
            "title": f"《{g['scene'][:2]}夜·{hero}》",
            "logline": f"{hero} 因一桩意外被卷入{g['genre']}漩涡，与 {rival} 展开博弈，最终被迫直面真相。",
            "synopsis": idea.get("premise", "") + " 全片三场推进：察觉异常 → 正面交锋 → 抉择留钩。",
            "target_platform": "主流短视频平台 · 竖屏",
            "target_duration_seconds": 45,
            "scenes": scenes,
        })

    def _fab_review(self, context, schema):
        idea = context.get("idea", {})
        script = context.get("script", {})
        blob = (str(idea) + str(script)).lower()
        raw_blob = str(idea) + str(script)

        # 合规扫描（需求文档 第八章红线）
        hits = [w for w in _COMPLIANCE_RED_FLAGS if w in raw_blob]
        if hits:
            compliance_status, overall = "warn", True
            compliance_notes = [f"检测到疑似『借用他作』关键词：{hits}，请人工确认是否为原创表达。"]
        else:
            compliance_status, overall = "pass", True
            compliance_notes = ["未检测到复刻具体作品/模仿在世创作者的红线词；内容为原创生成。"]

        # 需求文档 8.1 八维质量指标：前期可评的给分，需成片的标注待后期
        dims = [
            ("剧情吸引力", 8.0, "钩子明确、三场递进，有反转动力。"),
            ("人物一致性", 7.5, "已用 character_id 绑定，待美术/视频阶段校验外观稳定。"),
            ("画风统一性", None, "待美术 Agent 出图后评估。"),
            ("镜头连贯性", 7.0, "分镜阶段再核对景别/机位衔接。"),
            ("动作自然度", None, "需视频生成阶段评估。"),
            ("音画同步", None, "需配音阶段评估。"),
            ("成片可用率", None, "需成片阶段评估。"),
            ("平台适配度", 8.0, "竖屏 45s 适配主流短视频平台节奏。"),
        ]
        return schema.model_validate({
            "logic_issues": ["第二场冲突动机可再前置一句，避免观众疑惑。"],
            "pacing_notes": ["开场 3 秒钩子达标；建议第三场抉择再压缩，强化留白。"],
            "continuity_notes": ["确认三场之间的时间线（深夜→紧接→稍后）连贯。"],
            "compliance_status": compliance_status,
            "compliance_notes": compliance_notes,
            "quality_scores": [
                {"dimension": d, "score": s, "comment": c} for d, s, c in dims
            ],
            "suggestions": ["进入角色设定前，确认主角的『不可变化项』，为后续一致性打基础。"],
            "overall_pass": overall,
        })

    def _fab_character(self, context, schema):
        idea = context.get("idea", {})
        seeds = idea.get("character_seeds", [])
        if not seeds:
            seeds = [{"name": "主角", "role": "主角", "one_line": "核心人物"}]

        genre = idea.get("genre", "都市")
        identity_by_role = {"主角": f"{genre}主角", "对手/反派": "主要对手/反派", "关键配角": "关键配角"}

        characters = []
        for i, s in enumerate(seeds, start=1):
            rng = self._rng("char", s["name"])
            hair = rng.choice(_HAIR)
            eyes = rng.choice(_EYES)
            mark = rng.choice(_MARKS)
            voice = _VOICES[(i - 1) % len(_VOICES)]   # 按序取，保证各角色音色不同
            characters.append({
                "character_id": f"CHAR_{i:03d}",
                "name": s["name"],
                "age": rng.choice([19, 22, 24, 26, 28, 31]),
                "identity": identity_by_role.get(s["role"], s["role"]),
                "fixed_visual_features": [hair, eyes, mark],
                "variable_features": ["表情", "动作", "光线", "景别"],
                "forbidden_changes": ["不要改变发色", "不要改变瞳色", "不要更换主要服装", "不要改变标志性特征"],
                "voice_profile": voice,
            })

        return schema.model_validate({
            "characters": characters,
            "consistency_strategy": (
                "锁定每个角色专属 seed + 固定参考图（三视图），跨镜头复用同一参考图与 seed；"
                "并把 fixed_visual_features 写入每镜 image_prompt、把 forbidden_changes 写入 negative_prompt，"
                "从『提示词约束 + 视觉锚点』两侧抑制角色漂移（需求文档 4.5 一致性机制）。"
            ),
        })

    def _fab_storyboard(self, context, schema):
        script = context.get("script", {})
        charset = context.get("characters", {})
        chars = {c["name"]: c for c in charset.get("characters", [])}
        # 也允许按 character_id 反查
        name_to_id = {c["name"]: c["character_id"] for c in charset.get("characters", [])}

        shot_sizes = ["中近景", "近景", "特写", "中景", "远景"]
        angles = ["平视", "低机位", "俯视", "侧后方"]
        moves = ["缓慢推进", "跟拍", "定镜", "环绕", "横移"]

        shots = []
        n = 1
        for scene in script.get("scenes", []):
            on_stage_names = scene.get("on_stage", [])
            on_ids = [name_to_id.get(nm) for nm in on_stage_names if name_to_id.get(nm)]
            # 每场拆 2 个镜头：建立镜 + 重点镜
            for j in range(2):
                rng = self._rng("shot", scene["scene_id"], j)
                cam = {
                    "shot_size": shot_sizes[(n + j) % len(shot_sizes)],
                    "angle": rng.choice(angles),
                    "movement": rng.choice(moves),
                }
                light = {"key_light": "冷蓝侧光", "rim_light": "弱白色轮廓光", "intensity": "中等"}
                # 把出场角色的固定外貌特征拼进 image_prompt -> 结构化数据贯穿，保一致性
                feat_bits = []
                for nm in on_stage_names:
                    c = chars.get(nm)
                    if c:
                        feat_bits.append(f"{nm}（{'、'.join(c['fixed_visual_features'])}）")
                feat_str = "；".join(feat_bits) if feat_bits else "场景空镜"
                action = scene.get("summary", "")
                emotion = "紧张悬疑" if j == 1 else "克制铺陈"
                # 取该场一句台词作为镜头对白
                lines = scene.get("script_lines", [])
                dialogue = ""
                for ln in lines:
                    if ln.get("kind") in ("dialogue", "narration"):
                        dialogue = f"{ln['speaker']}：{ln['content']}"
                        break

                image_prompt = (
                    f"{scene.get('location','')}，{cam['shot_size']}{cam['angle']}，"
                    f"{light['key_light']}+{light['rim_light']}，人物：{feat_str}；"
                    f"动作：{action}；情绪：{emotion}；漫剧风格，竖屏构图，电影感打光"
                )
                video_prompt = (
                    f"{image_prompt}；镜头运动：{cam['movement']}；时长 5s；"
                    f"保持人物外貌与服装一致，首帧=该镜分镜图"
                )
                shots.append({
                    "shot_id": f"S{n:02d}",
                    "scene": scene.get("location", ""),
                    "characters": on_ids,
                    "camera": cam,
                    "lighting": light,
                    "action": action,
                    "duration": "5s",
                    "negative_prompt": "不要字幕,不要角色漂移,不要多出人物,不要手部畸形,不要改变发色瞳色服装",
                    "emotion": emotion,
                    "dialogue": dialogue,
                    "image_prompt": image_prompt,
                    "video_prompt": video_prompt,
                })
                n += 1

        return schema.model_validate({"shots": shots})
