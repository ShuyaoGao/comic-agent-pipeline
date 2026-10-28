"""
结构化数据契约（Pydantic v2）。

这是整个平台「可控」的命门（需求文档 第五章）：每个 Agent 的输入输出都是结构化 JSON，
而不是纯文本提示词串联。其中 Character 与 Shot **严格对齐 需求文档 附录 12.1 / 12.2**，
并按 需求文档 4.4 / 4.5 补充了 image_prompt / video_prompt / 情绪 / 台词等生产必需字段。
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# 1. 选题 Agent 输出（需求文档 4.1 创意与选题）
# ============================================================================
class CharacterSeed(BaseModel):
    """角色雏形（选题阶段的粗略人物设定，供编剧/角色设定 Agent 细化）。"""
    name: str = Field(description="角色名（原创，勿用真实在世人物）")
    role: str = Field(description="角色定位：主角 / 配角 / 反派 / 工具人 等")
    one_line: str = Field(description="一句话人物雏形")


class StoryIdea(BaseModel):
    """把模糊创意发展为可生产方向（需求文档 4.1：输出多个可选方向）。"""
    premise: str = Field(description="打磨后的故事前提（一两句）")
    genre: str = Field(description="题材类型，如 都市复仇/校园情感/古风悬疑/末日科幻/赛博奇幻/豪门婚恋")
    target_audience: str = Field(description="目标受众")
    core_conflict: str = Field(description="核心冲突")
    emotional_tone: str = Field(description="情绪基调")
    opening_hook: str = Field(description="开头钩子（前 3 秒抓人）")
    series_potential: str = Field(description="系列化潜力说明")
    type_structure_notes: list[str] = Field(
        default_factory=list,
        description="热播类型的结构/节奏规律分析（需求文档 4.3：只学类型特征，不复制具体作品）",
    )
    character_seeds: list[CharacterSeed] = Field(description="2-4 个角色雏形")
    candidate_directions: list[str] = Field(description="2-3 个可选故事方向，供人工挑选")


# ============================================================================
# 2. 编剧 Agent 输出（需求文档 4.2 剧本：优先保存结构化剧本而非纯文本）
# ============================================================================
class ScriptLine(BaseModel):
    """一条剧本内容（台词 / 旁白 / 动作提示）。"""
    speaker: str = Field(description="说话者角色名，旁白填『旁白』")
    kind: Literal["dialogue", "narration", "action"] = Field(description="台词/旁白/动作")
    content: str = Field(description="具体内容")


class Scene(BaseModel):
    scene_id: str = Field(description="场景编号，如 SC01")
    location: str = Field(description="所属场景，如『地下实验室走廊』")
    time_of_day: str = Field(description="时间/光照环境，如『深夜』")
    summary: str = Field(description="本场剧情概要")
    on_stage: list[str] = Field(description="出场角色名列表")
    script_lines: list[ScriptLine] = Field(description="镜头级剧本：台词/旁白/动作")


class Script(BaseModel):
    title: str = Field(description="作品标题（原创）")
    logline: str = Field(description="一句话故事梗概")
    synopsis: str = Field(description="分集/整体大纲")
    target_platform: str = Field(description="目标平台，如 抖音/小红书/B站/YouTube Shorts")
    target_duration_seconds: int = Field(description="目标成片时长（秒）")
    scenes: list[Scene] = Field(description="按顺序的场景列表")


# ============================================================================
# 3. 审稿与合规 Agent 输出（需求文档 4.2 审稿/合规子 Agent + 第八章质量与合规）
# ============================================================================
class QualityDimension(BaseModel):
    """需求文档 8.1 八维质量指标之一。前期能评的给分，需成片才能评的标注『待后期』。"""
    dimension: str = Field(description="维度名（如 剧情吸引力）")
    score: Optional[float] = Field(default=None, description="0-10 分；前期无法评估则为 null")
    comment: str = Field(description="评语或『待后期/成片阶段评估』")


class ReviewReport(BaseModel):
    logic_issues: list[str] = Field(default_factory=list, description="逻辑漏洞")
    pacing_notes: list[str] = Field(default_factory=list, description="节奏/拖沓/钩子建议")
    continuity_notes: list[str] = Field(default_factory=list, description="连贯性/动机建议")
    compliance_status: Literal["pass", "warn", "fail"] = Field(description="合规判定")
    compliance_notes: list[str] = Field(default_factory=list, description="合规说明/触发的红线")
    quality_scores: list[QualityDimension] = Field(description="八维质量指标（需求文档 8.1）")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    overall_pass: bool = Field(description="是否建议进入下一阶段")


# ============================================================================
# 4. 角色设定 Agent 输出（★严格对齐 需求文档 附录 12.1 角色数据结构）
# ============================================================================
class Character(BaseModel):
    """
    需求文档 附录 12.1 字段全部保留且同名：
      character_id / name / age / identity /
      fixed_visual_features / variable_features / forbidden_changes / voice_profile
    reference_image / reference_seed 为美术 Agent 回填的一致性锚点（不属附录，可空）。
    """
    character_id: str = Field(description="全局唯一角色 ID，如 CHAR_001")
    name: str = Field(description="姓名（原创）")
    age: int = Field(description="年龄")
    identity: str = Field(description="身份")
    fixed_visual_features: list[str] = Field(
        description="固定外貌特征（跨镜头不可变），如 黑色长发/浅灰色瞳孔/左眼下方小痣"
    )
    variable_features: list[str] = Field(
        description="可变化项，如 表情/动作/光线/景别"
    )
    forbidden_changes: list[str] = Field(
        description="不可变化项（一致性硬约束），如 不要改变发色/不要改变瞳色/不要更换主要服装"
    )
    voice_profile: str = Field(description="音色画像，如 清冷、低声、语速中等（对应 需求文档 配音）")

    # —— 以下为一致性机制锚点，由美术 Agent 回填，附录未列，可为空 ——
    reference_image: Optional[str] = Field(default=None, description="三视图/参考图路径")
    reference_seed: Optional[int] = Field(default=None, description="该角色锁定的生成 seed")


class CharacterSet(BaseModel):
    characters: list[Character] = Field(description="本项目全部角色")
    consistency_strategy: str = Field(
        description="角色一致性策略说明（如 锁 seed + 固定参考图 + forbidden_changes 约束）"
    )


# ============================================================================
# 5. 分镜 Agent 输出（★严格对齐 需求文档 附录 12.2 镜头数据结构 + 需求文档 4.4 字段）
# ============================================================================
class Camera(BaseModel):
    shot_size: str = Field(description="景别：远景/中景/近景/特写 等")
    angle: str = Field(description="机位：平视/俯视/仰视/侧后方 等")
    movement: str = Field(description="镜头运动：推/拉/摇/移/跟拍/环绕/定镜 等")


class Lighting(BaseModel):
    key_light: str = Field(description="主光，如 冷蓝侧光")
    rim_light: str = Field(description="轮廓光/边缘光，如 弱白色轮廓光")
    intensity: str = Field(description="强度：弱/中等/强")


class Shot(BaseModel):
    """
    需求文档 附录 12.2 字段全部保留且同名：
      shot_id / scene / characters / camera / lighting / action / duration / negative_prompt
    其余为 需求文档 4.4 分镜字段表要求（情绪氛围、台词/旁白、提示词），是 MVP 必交付的
    『分镜图提示词 + 视频提示词』。
    """
    shot_id: str = Field(description="镜头编号，如 S01")
    scene: str = Field(description="所属场景")
    characters: list[str] = Field(description="出场角色的 character_id 列表（绑定 ID 避免混乱）")
    camera: Camera
    lighting: Lighting
    action: str = Field(description="镜头内人物的具体动作")
    duration: str = Field(description="时长，如 5s")
    negative_prompt: str = Field(description="禁止项，如 不要字幕,不要角色漂移,不要多出人物,不要手部畸形")

    # —— 需求文档 4.4 补充字段 ——
    emotion: str = Field(description="情绪氛围")
    dialogue: str = Field(default="", description="镜头内对白/旁白内容")
    image_prompt: str = Field(description="图像生成提示词（分镜图）")
    video_prompt: str = Field(description="视频生成提示词（首尾帧/图生视频用，阶段二接入）")


class Storyboard(BaseModel):
    shots: list[Shot] = Field(description="按播放顺序的镜头表")


# ============================================================================
# 6. 美术 Agent 输出（需求文档 4.5 原画资产 + 一致性机制）
# ============================================================================
class ArtAsset(BaseModel):
    asset_type: Literal["character_reference", "shot"] = Field(description="资产类型")
    ref_id: str = Field(description="关联的 character_id 或 shot_id")
    image_path: str = Field(description="图像文件路径")
    seed: int = Field(description="本图使用的 seed（一致性锚点）")
    reference_image: Optional[str] = Field(default=None, description="参考图路径（保身份一致）")
    prompt: str = Field(description="使用的图像提示词")
    negative_prompt: str = Field(default="", description="使用的负面提示词")
    model: str = Field(description="生成模型/方式")
    cost_usd: float = Field(default=0.0, description="本图成本（USD）")


class ArtResult(BaseModel):
    character_references: list[ArtAsset] = Field(description="各角色三视图/参考图")
    shot_images: list[ArtAsset] = Field(description="各分镜图")
    consistency_note: str = Field(description="本次一致性机制如何应用的说明")


# ============================================================================
# 6.5 导演台 Agent 输出（需求文档 第六章 3D 导演台与分镜控制系统，平台最差异化功能）
#     MVP 离线雏形：用确定性规则做"2D 俯视预演"——角色站位 / 机位 / 灯光方位 / 构图，
#     渲染俯视构图图，并把这些镜头参数翻译进精炼后的 image/video 提示词（需求文档 第六章"输出数据"）。
#     完整可拖拽 3D 导演台(Three.js)是第三阶段；本阶段先把"可控镜头参数"这一内核做出来。
# ============================================================================
class ActorBlocking(BaseModel):
    """一个角色在舞台上的站位（俯视，归一化坐标 0~1）。"""
    character_id: str = Field(description="角色 ID")
    x: float = Field(description="左右位置 0(左)~1(右)")
    y: float = Field(description="纵深位置 0(近镜头)~1(远)")
    facing: str = Field(description="朝向，如 朝向镜头/侧身/背向")


class DirectorShot(BaseModel):
    """一个镜头的导演台预演参数（需求文档 第六章：角色摆放/摄像机/灯光/构图/输出数据）。"""
    shot_id: str
    camera_x: float = Field(description="摄像机左右位置 0~1")
    camera_y: float = Field(description="摄像机纵深 0~1（<0 表示在舞台前方）")
    camera_height: str = Field(description="机位高度：仰拍(低机位)/平视/俯拍(高机位)")
    focal_hint: str = Field(description="焦段/景深提示，如 长焦浅景深虚化背景")
    framing: str = Field(description="构图：主体所在三分线/居中等（含竖屏安全框）")
    light_direction: str = Field(description="主光方位，如 左前方冷蓝侧光")
    actors: list[ActorBlocking] = Field(description="各角色站位")
    blocking_diagram: str = Field(description="俯视构图图路径（PNG）")
    refined_image_prompt: str = Field(description="叠加导演台镜头语言后的图像提示词")
    refined_video_prompt: str = Field(description="叠加导演台镜头语言后的视频提示词")
    notes: str = Field(default="", description="导演台备注")


class DirectorBoard(BaseModel):
    shots: list[DirectorShot] = Field(description="各镜头的导演台预演")
    note: str = Field(description="导演台机制说明")


# ============================================================================
# 7. 合成/后期 Agent 输出（需求文档 4.7 自动剪辑与后期 / 第十章 10.2）
#    MVP 离线实现：mock 配音(占位音轨) + 草样片 GIF + 结构化剪辑时间线 +
#    可灵/FFmpeg 真实成片脚本骨架。真实视频/配音模型在阶段二接入。
# ============================================================================
class AudioClip(BaseModel):
    """一条镜头配音（离线为占位音轨，记录时长/音色，供时间线对齐）。"""
    shot_id: str = Field(description="所属镜头")
    speaker: str = Field(description="说话者")
    text: str = Field(description="台词/旁白内容")
    voice_profile: str = Field(description="音色画像（取自角色 voice_profile）")
    audio_path: str = Field(description="音频文件路径（.wav）")
    duration_seconds: float = Field(description="音频时长（秒）")
    model: str = Field(description="配音方式/模型")


class VideoClip(BaseModel):
    """剪辑时间线上的一个片段（需求文档 4.7：按分镜顺序建立时间线）。"""
    shot_id: str
    scene: str
    image_path: Optional[str] = Field(default=None, description="该镜分镜图（首帧）")
    audio_path: Optional[str] = Field(default=None, description="该镜配音轨")
    subtitle: str = Field(default="", description="该镜字幕（台词/旁白）")
    start_seconds: float = Field(description="片段在成片中的起始时间")
    duration_seconds: float = Field(description="片段时长")
    transition: str = Field(default="硬切", description="转场方式")


class EditTimeline(BaseModel):
    """结构化剪辑时间线（需求文档 4.7：时间线/字幕/配音/BGM/多比例）。"""
    aspect_ratio: str = Field(description="画幅比例，如 9:16")
    fps: int = Field(description="帧率")
    bgm: str = Field(description="背景音乐说明（MVP 占位）")
    total_duration_seconds: float = Field(description="成片总时长（秒）")
    clips: list[VideoClip] = Field(description="按播放顺序的片段")


class ComposeResult(BaseModel):
    """合成/后期 Agent 产出。"""
    timeline: EditTimeline = Field(description="结构化剪辑时间线")
    audio_clips: list[AudioClip] = Field(description="各镜配音（占位）")
    reel_path: Optional[str] = Field(default=None, description="草样片预览（GIF 故事板卷）")
    assemble_script: Optional[str] = Field(default=None, description="真实成片用的 FFmpeg 脚本路径")
    shots_total: int = Field(description="分镜总数")
    shots_in_reel: int = Field(description="实际进入草样片的镜数（可能因上限截断）")
    note: str = Field(description="本次合成方式与限制说明")
    model: str = Field(description="合成方式/模型")


# ============================================================================
# 8. 质检 Agent 输出（需求文档 第八章 8 维质量 + 10.3 角色一致性检测，前移到 MVP）
#    确定性检测（非 LLM）：把"角色一致性"这个命门做成可量化、可复核的指标。
# ============================================================================
class QCMetric(BaseModel):
    dimension: str = Field(description="质量维度名（对齐 需求文档 8.1）")
    score: float = Field(description="0-10 分")
    detail: str = Field(description="评分依据")
    issues: list[str] = Field(default_factory=list, description="发现的具体问题")


class QCReport(BaseModel):
    consistency_score: float = Field(description="角色一致性得分 0-1（命门指标）")
    metrics: list[QCMetric] = Field(description="各维度质量指标")
    overall_score: float = Field(description="综合得分 0-10")
    passed: bool = Field(description="是否通过质检阈值")
    issues: list[str] = Field(default_factory=list, description="汇总问题清单")
    note: str = Field(description="质检方法说明")


# ============================================================================
# 9. 成本控制（需求文档 第五/十一章「成本控制 Agent」）—— 非工作流阶段，运行后估算
#    作用：离线也能回答「若改用真实云端模型生产本片，大约花多少钱」，支撑成本权衡。
# ============================================================================
class CostLine(BaseModel):
    category: str = Field(description="成本类别：文本(LLM)/图像/视频/配音")
    quantity: str = Field(description="计量（如 12340 tokens / 9 张 / 30s / 86 字）")
    unit_price: str = Field(description="使用的示意单价")
    estimated_usd: float = Field(description="该类别估算成本（USD）")
    note: str = Field(default="", description="说明/省钱建议")


class CostReport(BaseModel):
    """本片成本估算报告（mock 实跑成本≈0；real 估算为若用真实模型的花费）。"""
    actual_cost_usd: float = Field(description="本次实跑实际成本（mock=0）")
    estimated_real_cost_usd: float = Field(description="若用真实云端模型生产本片的估算总成本")
    lines: list[CostLine] = Field(description="各成本类别明细")
    assumptions: list[str] = Field(description="估算所用单价与假设（务必上线前核对）")
    saving_tips: list[str] = Field(description="降本建议")


# ============================================================================
# 10. 多模型调度（需求文档 4.6「视频生成多模型调度，不绑死一个模型」/ 10.3）
#     为每个镜头按规则选「图像/视频模型」：关键镜用强一致性/真实视频模型，
#     普通镜用性价比/占位方案——与成本控制联动（只对关键镜花真实视频的钱）。
# ============================================================================
class DispatchShot(BaseModel):
    shot_id: str
    importance: int = Field(description="重要度评分（越高越关键）")
    image_model: str = Field(description="为该镜选用的图像模型")
    video_model: str = Field(description="为该镜选用的视频方案/模型")
    real_video: bool = Field(description="是否生成真实视频（否则用分镜图+轻动效占位）")
    reason: str = Field(description="选择理由")


class DispatchPlan(BaseModel):
    shots: list[DispatchShot]
    real_video_shots: int = Field(description="用真实视频的镜数")
    placeholder_shots: int = Field(description="用占位/图生视频的镜数")
    full_video_cost_usd: float = Field(description="若全部镜都出真实视频的成本")
    dispatched_video_cost_usd: float = Field(description="调度后（仅关键镜真实视频）的视频成本")
    note: str = Field(description="调度策略说明")


# 任务名 -> 对应输出 schema（mock LLM 与真实 LLM 都靠它做结构化校验/路由）
# 注：compose / qc / cost / dispatch 不是 LLM 型 Agent（确定性产出），不进入本表。
TASK_SCHEMAS: dict[str, type[BaseModel]] = {
    "idea": StoryIdea,
    "script": Script,
    "review": ReviewReport,
    "character": CharacterSet,
    "storyboard": Storyboard,
}
