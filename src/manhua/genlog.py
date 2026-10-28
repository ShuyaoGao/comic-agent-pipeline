"""
生成日志（需求文档 第七章）。

每次生成都记录：模型、提示词、参考图、参数、时间、成本、评分、是否采用、失败原因、修改原因。
这些日志既支撑商业优化，也支撑后续论文研究 / 复盘。落盘为 generation_log.jsonl（一行一条）。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class GenerationRecord:
    id: str
    stage: str                       # 所属 Agent/阶段
    gen_type: str                    # "llm" | "image"
    model: str
    timestamp: str
    prompt: str = ""
    reference_images: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    score: Optional[float] = None
    adopted: bool = True
    failure_reason: str = ""
    modification_reason: str = ""


class GenerationLog:
    def __init__(self) -> None:
        self.records: list[GenerationRecord] = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"GEN_{self._counter:04d}"

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def log_llm(self, stage: str, result, *, score=None, adopted=True, modification_reason="") -> None:
        self.records.append(GenerationRecord(
            id=self._next_id(), stage=stage, gen_type="llm",
            model=result.model, timestamp=self._now(),
            prompt=result.prompt, params=result.params,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            cost_usd=result.cost_usd, score=score, adopted=adopted,
            modification_reason=modification_reason,
        ))

    def log_image(self, stage: str, result, *, score=None, adopted=True, modification_reason="") -> None:
        self.records.append(GenerationRecord(
            id=self._next_id(), stage=stage, gen_type="image",
            model=result.model, timestamp=self._now(),
            prompt=result.prompt,
            reference_images=[result.reference_image] if result.reference_image else [],
            params={"seed": result.seed, "negative_prompt": result.negative_prompt},
            cost_usd=result.cost_usd, score=score, adopted=adopted,
            modification_reason=modification_reason,
        ))

    def log_media(self, stage: str, gen_type: str, model: str, *, prompt: str = "",
                  params: Optional[dict] = None, cost_usd: float = 0.0,
                  score=None, adopted=True) -> None:
        """记录音频/视频/合成类生成（gen_type 如 "audio"/"video"）。"""
        self.records.append(GenerationRecord(
            id=self._next_id(), stage=stage, gen_type=gen_type, model=model,
            timestamp=self._now(), prompt=prompt, params=params or {},
            cost_usd=cost_usd, score=score, adopted=adopted,
        ))

    def log_failure(self, stage: str, gen_type: str, model: str, reason: str) -> None:
        self.records.append(GenerationRecord(
            id=self._next_id(), stage=stage, gen_type=gen_type, model=model,
            timestamp=self._now(), adopted=False, failure_reason=reason,
        ))

    def summary(self) -> dict[str, Any]:
        total_cost = sum(r.cost_usd for r in self.records)
        return {
            "total_generations": len(self.records),
            "llm_calls": sum(1 for r in self.records if r.gen_type == "llm"),
            "image_calls": sum(1 for r in self.records if r.gen_type == "image"),
            "audio_calls": sum(1 for r in self.records if r.gen_type == "audio"),
            "video_calls": sum(1 for r in self.records if r.gen_type == "video"),
            "total_input_tokens": sum(r.input_tokens for r in self.records),
            "total_output_tokens": sum(r.output_tokens for r in self.records),
            "total_cost_usd": round(total_cost, 6),
            "failures": sum(1 for r in self.records if r.failure_reason),
        }

    def load_existing(self, path: Path) -> None:
        """续跑时载入历史日志，避免单步重跑覆盖掉之前的生成记录（复盘/版本管理需要完整历史）。"""
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                self.records.append(GenerationRecord(**json.loads(line)))
        self._counter = len(self.records)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for r in self.records:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
