"""
美术 Agent（需求文档 4.5 原画资产 + 一致性机制）。

核心一致性做法（最省工程、业界常见做法）：
  1. 每个角色锁定一个**专属 seed**（由 character_id 确定性派生）+ 一张**参考图**（三视图基准）。
  2. 每个分镜以该镜『首位出场角色』为锚点，复用其 seed 与参考图来出图。
     -> 在离线占位图里，同 seed 派生同主色调，肉眼即可见『同一角色跨镜头一致』。
  3. image_prompt 已带 fixed_visual_features、negative_prompt 已带 forbidden_changes（分镜 Agent 完成），
     与视觉锚点形成『提示词约束 + 参考图锚定』双保险。

不是 LLM 型 Agent：它调用图像生成器（离线 Pillow 占位 / 真实云端 API）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..engine import ProjectState, RunContext
from ..schemas import ArtAsset, ArtResult


def _derive_seed(base: int, key: str) -> int:
    """由全局 seed + 标识符确定性派生一个稳定 seed（保证可复现 + 同标识同 seed）。"""
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
    return (base + h) % (2**31)


class ArtAgent:
    key = "art"
    display_name = "美术 Agent"

    def run(self, state: ProjectState, ctx: RunContext) -> None:
        assert state.characters is not None and state.storyboard is not None
        base_seed = ctx.config.seed
        char_dir = ctx.out_dir / "assets" / "characters"
        shot_dir = ctx.out_dir / "assets" / "shots"

        seed_map: dict[str, int] = {}
        ref_map: dict[str, str] = {}
        char_refs: list[ArtAsset] = []

        # 1) 为每个角色出参考图，并把 seed/参考图回填到角色设定（一致性锚点落到 JSON）
        for c in state.characters.characters:
            seed = _derive_seed(base_seed, c.character_id)
            seed_map[c.character_id] = seed
            prompt = (
                f"角色三视图参考图：{c.name}，{c.age}岁，{c.identity}；"
                f"固定外貌：{'、'.join(c.fixed_visual_features)}；漫剧风格，正面/侧面/背面，中性表情，纯色背景"
            )
            neg = "、".join(c.forbidden_changes) + ",不要多人,不要文字水印"
            out = char_dir / f"{c.character_id}_reference.png"
            res = ctx.image_gen.generate(
                prompt=prompt, negative_prompt=neg, seed=seed,
                reference_image=None, out_path=out,
                label=f"{c.character_id} {c.name} · 参考图",
            )
            c.reference_image = res.image_path     # 回填角色设定
            c.reference_seed = seed
            ref_map[c.character_id] = res.image_path
            ctx.genlog.log_image("art/character_reference", res)
            char_refs.append(ArtAsset(
                asset_type="character_reference", ref_id=c.character_id,
                image_path=res.image_path, seed=seed, reference_image=None,
                prompt=prompt, negative_prompt=neg, model=res.model, cost_usd=res.cost_usd,
            ))

        # 2) 为每个分镜出图：复用锚点角色的 seed + 参考图 -> 跨镜头一致
        shot_assets: list[ArtAsset] = []
        for shot in state.storyboard.shots:
            if shot.characters:
                anchor = shot.characters[0]
                seed = seed_map.get(anchor, _derive_seed(base_seed, shot.shot_id))
                ref_img = ref_map.get(anchor)
            else:
                seed = _derive_seed(base_seed, shot.shot_id)
                ref_img = None
            out = shot_dir / f"{shot.shot_id}.png"
            res = ctx.image_gen.generate(
                prompt=shot.image_prompt, negative_prompt=shot.negative_prompt, seed=seed,
                reference_image=ref_img, out_path=out,
                label=f"{shot.shot_id} · {shot.scene}",
            )
            ctx.genlog.log_image("art/shot", res)
            shot_assets.append(ArtAsset(
                asset_type="shot", ref_id=shot.shot_id,
                image_path=res.image_path, seed=seed, reference_image=ref_img,
                prompt=shot.image_prompt, negative_prompt=shot.negative_prompt,
                model=res.model, cost_usd=res.cost_usd,
            ))

        state.art = ArtResult(
            character_references=char_refs,
            shot_images=shot_assets,
            consistency_note=(
                "每个角色锁定专属 seed + 参考图；分镜以首位出场角色为锚点复用其 seed 与参考图，"
                "配合 image_prompt 中的 fixed_visual_features 与 negative_prompt 中的 forbidden_changes，"
                "形成『视觉锚点 + 提示词约束』双重一致性保障。同 seed 在离线占位图中呈现相同主色调，可直观比对一致性。"
            ),
        )
