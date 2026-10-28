"""把配置、模型客户端、Agent 节点组装成可运行的工作流。"""
from __future__ import annotations

from pathlib import Path

from .agents import default_nodes
from .config import Config
from .engine import RunContext, Workflow
from .genlog import GenerationLog
from .image import build_image_generator
from .llm import build_llm


def make_context(config: Config, out_dir: Path) -> RunContext:
    llm = build_llm(config)
    if config.mode == "real" and not config.review_llm_use_main:
        review_llm = build_llm(config, config.review_llm)   # 审稿用独立(更强)模型
    else:
        review_llm = llm
    image_gen = build_image_generator(config)
    return RunContext(
        config=config, llm=llm, review_llm=review_llm,
        image_gen=image_gen, genlog=GenerationLog(), out_dir=out_dir,
    )


def build_workflow() -> Workflow:
    return Workflow(default_nodes())
