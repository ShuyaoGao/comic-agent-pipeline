/* =====================================================================
 * names.js —— 页面上出现的名称集中在这里（不出现任何商业模型 / 平台的真实名称）
 *
 * 引擎里的模型标识（如 image-strong-example）都是中性的“示例 ID”；这里给它们配上中文说明。
 * Python 版 config.yaml 里可以填真实服务的模型名（那是“可配置示例”，上线前请自行核对）；
 * 浏览器版只做离线演示，不连接任何服务。
 * ===================================================================== */
window.APP_NAMES = {
  APP_NAME: "漫剧多 Agent 流水线",
  APP_NAME_EN: "Comic Agent Pipeline",
  TAGLINE: "一句创意 → 9 个 Agent → 剧本、角色、分镜、导演台、草样片、质检、成本，全程结构化 JSON",

  MODEL_LABELS: {
    "mock-llm-offline": "离线编造器（mock，不是真实模型）",
    "text-llm-example": "云端文本模型（示例）",
    "placeholder-offline": "离线占位图生成器",
    "image-strong-example": "强一致性图像模型（示例）",
    "image-cheap-example": "性价比图像模型（示例）",
    "video-real-example": "视频生成模型（示例）",
    "storyboard-image": "分镜图 + 轻动效（占位）",
    "mock-tts-offline": "离线占位配音",
    "pillow-gif-offline": "离线草样片",
    "director-board-offline": "离线导演台",
    "offline-postprod": "离线后期合成",
  },
  label(id) { return this.MODEL_LABELS[id] || id; },

  STAGE_HELP: {
    idea: "把一句创意发展成可生产的方向：题材、受众、核心冲突、开头钩子、3 个角色雏形、3 个可选方向。",
    script: "写成结构化剧本（不是一段纯文本）：3 场戏，每场有地点、时间、出场角色和逐条台词 / 旁白 / 动作。",
    review: "审稿与合规：扫描“同款 / 照搬 / 翻拍”等红线词，给出八维质量分。注意：这里的分数是离线示意分，不是模型评出来的。",
    characters: "角色设定：固定外貌（跨镜头不可变）、可变项、不可变化项、音色。角色名在选题阶段就定下来，后面全部复用。",
    storyboard: "分镜表：每场拆 2 个镜头，绑定 character_id；把固定外貌写进 image_prompt、把不可变化项写进 negative_prompt。",
    director: "导演台：从分镜算出站位、机位高度、灯光方位、三分法构图，画出俯视图，再把这些镜头语言追加进提示词。",
    art: "美术：每个角色锁一个专属 seed 和一张参考图；每个分镜复用首位出场角色的 seed + 参考图 —— 同一角色颜色一致。",
    compose: "合成：按台词字数估配音时长（约 4.5 字 / 秒），排出剪辑时间线，做成草样片（分镜图 + 字幕 + 轻缩放）。",
    qc: "质检（不是 LLM，是确定性规则）：每镜 4 项一致性检查 + 结构 / 连贯 / 音画 / 时长 / 平台，汇总成可复核的分数。",
  },
};
