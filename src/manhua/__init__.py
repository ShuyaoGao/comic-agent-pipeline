"""
manhua —— AIGC 漫剧多 Agent 生成平台 MVP（需求文档 第 10.1 节：AI 漫剧前期策划 + 分镜提示词生产平台）。

设计内核（对应 需求文档 第五章「工作流引擎 + Agent 作为节点」）：
  - engine：自研轻量工作流引擎（共享 State / 检查点 / 单步重跑）。
  - agents：6 个 Agent 节点（选题→编剧→审稿合规→角色设定→分镜→美术），每个节点输入输出都是结构化 JSON。
  - schemas：Pydantic 数据结构，严格对齐 需求文档 附录 12.1 角色结构 / 12.2 镜头结构。
  - llm：可切换的 LLM 客户端（离线 mock / 真实 DeepSeek）。
  - image：可切换的图像生成器（离线 Pillow 占位图 / 真实云端 API），演示「锁 seed + 同一参考图」一致性。
  - genlog / assets：生成日志（需求文档 第七章）与项目资产库雏形。
"""

__version__ = "0.1.0"  # 第一阶段 MVP
