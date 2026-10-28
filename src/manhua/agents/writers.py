"""
前五个 LLM 型 Agent：选题 / 编剧 / 审稿合规 / 角色设定 / 分镜。

注意：system/user 提示词主要服务于 real 模式（真实 LLM 据此 + 注入的 JSON Schema 产出结构化结果）；
离线 mock 模式按 task 名走确定性编造器。两条路输出的都是同一套 Pydantic 结构。
"""
from __future__ import annotations

from ..engine import ProjectState
from .base import LLMAgent


class IdeaAgent(LLMAgent):
    """需求文档 4.1 创意与选题 Agent：一句话 → 故事方向/冲突/角色雏形/多个可选方向。"""
    key = "idea"
    display_name = "选题 Agent"
    task = "idea"

    def build_prompt(self, state: ProjectState):
        system = (
            "你是漫剧『创意与选题 Agent』。把用户的一句话创意，发展为可生产的漫剧项目方向。"
            "需给出题材类型、目标受众、核心冲突、情绪基调、开头钩子、系列化潜力，以及 2-4 个原创角色雏形与 2-3 个可选方向。"
            "只做类型/节奏/结构层面的规律分析，严禁复制具体作品的剧情/台词/角色，严禁使用真实在世人物（需求文档第八章合规）。"
        )
        user = f"用户创意：{state.idea_text}"
        return system, user, {"idea_text": state.idea_text}


class ScriptAgent(LLMAgent):
    """需求文档 4.2 剧本 Agent：生成结构化（而非纯文本）剧本——大纲 + 镜头级场景。"""
    key = "script"
    display_name = "编剧 Agent"
    task = "script"

    def build_prompt(self, state: ProjectState):
        system = (
            "你是漫剧『编剧 Agent』。基于选题结果生成结构化剧本：标题、logline、大纲，以及按顺序的场景列表；"
            "每个场景包含场景编号、地点、时间、概要、出场角色、镜头级台词/旁白/动作。台词要符合人物性格、适配竖屏短视频节奏。"
            "保持原创，不要复制具体作品。"
        )
        user = "请根据选题结果撰写一部 30-60 秒竖屏漫剧的结构化剧本。"
        return system, user, {"idea_text": state.idea_text, "idea": state.idea.model_dump()}


class ReviewAgent(LLMAgent):
    """需求文档 4.2 审稿/合规子 Agent + 第八章：逻辑/节奏校验 + 合规红线 + 八维质量评分。"""
    key = "review"
    display_name = "审稿与合规 Agent"
    task = "review"
    use_review_llm = True   # 可配置为更强模型做严格校验

    def build_prompt(self, state: ProjectState):
        system = (
            "你是漫剧『审稿与合规 Agent』。检查剧本的逻辑漏洞、动机不清、节奏拖沓与衔接桥段；"
            "做合规判定（pass/warn/fail）：是否复制了具体作品剧情/台词/角色、是否高度模仿在世创作者、是否含低俗/暴力/侵权风险；"
            "并对需求文档的八维质量指标打分（前期无法评估的维度 score 置空并说明『待后期』）。"
        )
        user = "请审稿并给出合规判定与质量评分。"
        return system, user, {"idea": state.idea.model_dump(), "script": state.script.model_dump()}


class CharacterAgent(LLMAgent):
    """需求文档 4.5 + 附录 12.1 角色设定 Agent：输出严格对齐附录字段的角色 JSON。"""
    key = "characters"
    display_name = "角色设定 Agent"
    task = "character"

    def build_prompt(self, state: ProjectState):
        system = (
            "你是漫剧『角色设定 Agent』。为每个角色输出完整设定，字段严格对齐："
            "character_id、name、age、identity、fixed_visual_features（固定外貌，跨镜头不可变）、"
            "variable_features（可变项）、forbidden_changes（不可变化项，一致性硬约束）、voice_profile（音色）。"
            "并给出整体一致性策略（锁 seed + 固定参考图 + forbidden_changes 约束）。角色须原创。"
        )
        user = "请基于选题与剧本生成全部角色的结构化设定。"
        return system, user, {"idea": state.idea.model_dump(), "script": state.script.model_dump()}


class StoryboardAgent(LLMAgent):
    """需求文档 4.4 + 附录 12.2 分镜 Agent：把剧本拆成镜头表，输出 image/video 提示词与负面提示词。"""
    key = "storyboard"
    display_name = "分镜 Agent"
    task = "storyboard"

    def build_prompt(self, state: ProjectState):
        system = (
            "你是漫剧『分镜 Agent』。把剧本拆解为镜头表，每个镜头字段严格对齐："
            "shot_id、scene、characters（用 character_id 绑定，避免角色混乱）、camera{shot_size,angle,movement}、"
            "lighting{key_light,rim_light,intensity}、action、duration、negative_prompt，以及 emotion、dialogue、"
            "image_prompt（分镜图提示词）、video_prompt（视频提示词）。"
            "image_prompt 中务必带上出场角色的 fixed_visual_features，negative_prompt 中务必带上 forbidden_changes，"
            "以从提示词侧抑制角色漂移（一致性）。"
        )
        user = "请生成完整镜头表，含图像与视频提示词。"
        return system, user, {
            "script": state.script.model_dump(),
            "characters": state.characters.model_dump(),
        }
