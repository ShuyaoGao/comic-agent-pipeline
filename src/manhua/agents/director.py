"""
导演台 Agent（需求文档 第六章 3D 导演台与分镜控制系统）。

位置：分镜 → 【导演台预演】 → 美术（严格按 需求文档 第三章业务流程顺序）。
作用：为每镜做 2D 俯视预演，算出可控的镜头参数（机位/站位/灯光/构图），渲染俯视构图图，
     并把这些参数翻译进**精炼后的 image/video 提示词**，再交给美术 Agent 出图——
     让"镜头可控性"这一平台壁垒在 MVP 阶段就有可演示的内核。

不是 LLM 型 Agent：确定性几何 + 规则推导。它会就地增强分镜的 image_prompt/video_prompt
（仍保留角色固定特征，质检的一致性检测照常通过）。
"""
from __future__ import annotations

from ..director import compute_blocking, refine_prompts, render_blocking_diagram
from ..engine import ProjectState, RunContext
from ..schemas import ActorBlocking, DirectorBoard, DirectorShot


class DirectorAgent:
    key = "director"
    display_name = "导演台 Agent"

    def run(self, state: ProjectState, ctx: RunContext) -> None:
        assert state.storyboard is not None
        base_seed = ctx.config.seed
        diag_dir = ctx.out_dir / "assets" / "director"

        dshots: list[DirectorShot] = []
        for shot in state.storyboard.shots:
            blk = compute_blocking(shot, base_seed)
            diagram = diag_dir / f"{shot.shot_id}.png"
            render_blocking_diagram(shot.shot_id, blk, diagram, base_seed)

            img_p, vid_p = refine_prompts(shot, blk)
            # 就地增强分镜提示词（美术/合成据此出图，镜头语言更可控）
            shot.image_prompt = img_p
            shot.video_prompt = vid_p

            dshots.append(DirectorShot(
                shot_id=shot.shot_id, camera_x=blk["camera_x"], camera_y=blk["camera_y"],
                camera_height=blk["camera_height"], focal_hint=blk["focal_hint"],
                framing=blk["framing"], light_direction=blk["light_direction"],
                actors=[ActorBlocking(**a) for a in blk["actors"]],
                blocking_diagram=str(diagram),
                refined_image_prompt=img_p, refined_video_prompt=vid_p,
                notes="2D 俯视预演（确定性规则）；可拖拽 3D 导演台为第三阶段。",
            ))
            ctx.genlog.log_media("director/blocking", "diagram", "director-board-offline",
                                 prompt=f"{shot.shot_id} 机位:{blk['camera_height']} 构图:{blk['framing'][:20]}",
                                 params={"shot_id": shot.shot_id, "actors": len(blk["actors"])})

        state.director = DirectorBoard(
            shots=dshots,
            note=("导演台从分镜算出可控镜头参数（角色站位/机位高度/摄像机位置/灯光方位/三分法构图），"
                  "渲染俯视构图图，并把镜头语言翻译进精炼提示词后交美术出图。"
                  "俯视图角色配色与其分镜图主色调一致，把导演台与美术打通。"),
        )
