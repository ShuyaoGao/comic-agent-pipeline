"""
导演台核心（需求文档 第六章 3D 导演台与分镜控制系统）—— 离线 2D 俯视预演。

平台最差异化的功能是"像导演一样在虚拟空间摆角色/摄像机/灯光，输出更可控的镜头参数"。
完整可拖拽 3D 导演台(Three.js)是第三阶段；本模块先做出它的**内核**：
  用确定性规则，从分镜表算出每镜的【角色站位 / 机位高度 / 摄像机位置 / 灯光方位 / 构图(三分法)】，
  渲染一张**俯视构图图**（摄像机视锥 + 角色站位 + 灯光方向 + 三分法网格 + 竖屏安全框），
  并把这些镜头参数**翻译进精炼后的图像/视频提示词**（需求文档 第六章"输出数据：结构化镜头参数 + 提示词"）。

俯视图里角色圆点的颜色与该角色分镜图主色调一致（同一套 seed→调色板），把导演台和美术视觉打通。
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from PIL import Image, ImageDraw

from .image.placeholder import _load_font, _palette_from_seed


def _derive_seed(base: int, key: str) -> int:
    """与美术 Agent 完全一致的 seed 派生，保证俯视图配色 == 该角色分镜图主色调。"""
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
    return (base + h) % (2**31)


# 景别 -> 角色与镜头的纵深（0=贴近镜头, 1=最远）
_DEPTH = {"特写": 0.28, "大特写": 0.24, "近景": 0.38, "中近景": 0.46,
          "中景": 0.56, "中远景": 0.64, "远景": 0.74, "全景": 0.78}
# 多角色时的左右站位
_X_LAYOUT = {1: [0.5], 2: [0.36, 0.64], 3: [0.27, 0.5, 0.73], 4: [0.22, 0.41, 0.59, 0.78]}


def compute_blocking(shot, base_seed: int) -> dict:
    """从一个分镜镜头算出导演台参数（纯确定性）。返回可填入 DirectorShot 的 dict（不含 diagram/prompts）。"""
    ids = list(shot.characters)
    n = max(1, len(ids))
    depth = _DEPTH.get(shot.camera.shot_size, 0.52)
    xs = _X_LAYOUT.get(n, [0.18 + 0.64 * i / max(1, n - 1) for i in range(n)])
    facings = ["朝向镜头", "侧身对峙", "侧身", "背向镜头"]
    actors = []
    for i, cid in enumerate(ids):
        # 纵深按序轻微错落，避免完全重叠
        y = min(0.9, max(0.12, depth + (0.06 if i % 2 else -0.04) * (i // 2 + 1)))
        actors.append({"character_id": cid, "x": round(xs[i % len(xs)], 3),
                       "y": round(y, 3), "facing": facings[i] if i < len(facings) else "侧身"})

    # 机位高度（从机位角度推断）
    angle = shot.camera.angle
    if "低" in angle or "仰" in angle:
        cam_height, cam_y = "仰拍(低机位)", -0.12
    elif "俯" in angle or "高" in angle:
        cam_height, cam_y = "俯拍(高机位)", -0.05
    else:
        cam_height, cam_y = "平视", -0.08
    cam_x = 0.5
    if "侧后" in angle:
        cam_x, cam_height = 0.80, cam_height + "·侧后方"
    elif "侧" in angle:
        cam_x = 0.30

    # 焦段/景深（从景别推断）
    if shot.camera.shot_size in ("特写", "大特写", "近景"):
        focal = "长焦/大光圈，浅景深虚化背景，突出主体"
    elif shot.camera.shot_size in ("远景", "全景", "中远景"):
        focal = "广角、大景深，交代环境与空间关系"
    else:
        focal = "标准镜头，主体与环境兼顾"

    # 构图（三分法 + 竖屏安全框）
    if n == 1:
        third = "右三分线" if (int(shot.shot_id[1:] or 0) % 2 == 0) else "左三分线"
        framing = f"主体置于{third}，视线留白；竖屏 9:16，关键信息避开上下 10% 安全框"
    else:
        framing = "双主体分置左右三分线，视线于画面中部交汇；竖屏 9:16 安全框，避免角色压边"

    # 灯光方位（从主光描述推断方向）
    key = shot.lighting.key_light
    side = "顶部" if "顶" in key else ("右前方" if "右" in key else "左前方")
    light_dir = f"{side}{key}（主），{shot.lighting.rim_light}（轮廓），强度{shot.lighting.intensity}"

    return {
        "camera_x": cam_x, "camera_y": cam_y, "camera_height": cam_height,
        "focal_hint": focal, "framing": framing, "light_direction": light_dir,
        "actors": actors,
    }


def refine_prompts(shot, blk: dict) -> tuple[str, str]:
    """把导演台镜头参数翻译进精炼后的 image/video 提示词（保留原提示词里的角色固定特征）。"""
    clause = (
        f"；【导演台】机位:{blk['camera_height']}；构图:{blk['framing']}；"
        f"灯光:{blk['light_direction']}；镜头:{blk['focal_hint']}"
    )
    image_prompt = shot.image_prompt + clause
    video_prompt = shot.video_prompt + f"；机位{blk['camera_height']}，运镜{shot.camera.movement}，保持构图与灯光一致"
    return image_prompt, video_prompt


# ----------------------------------------------------------------------------
#  俯视构图图渲染
# ----------------------------------------------------------------------------
def render_blocking_diagram(shot_id: str, blk: dict, out_path: Path, base_seed: int,
                            *, size=(640, 430)) -> None:
    W, H = size
    img = Image.new("RGB", (W, H), (16, 20, 26))
    d = ImageDraw.Draw(img, "RGBA")
    f_title = _load_font(20)
    f_small = _load_font(15)

    # 舞台区域（俯视）：上=远景，下=近景；摄像机在更下方
    L, R, T, B = 40, W - 40, 56, H - 90
    # 舞台地面
    d.rectangle([L, T, R, B], fill=(26, 32, 40), outline=(70, 84, 98), width=2)
    sx = lambda x: L + x * (R - L)
    sy = lambda y: T + y * (B - T)

    # 三分法网格（需求文档 构图辅助）
    for k in (1, 2):
        d.line([sx(k / 3), T, sx(k / 3), B], fill=(70, 84, 98, 120), width=1)
        d.line([L, sy(k / 3), R, sy(k / 3)], fill=(70, 84, 98, 120), width=1)
    d.text((L + 4, T + 2), "远景 ↑", font=f_small, fill=(140, 160, 175))
    d.text((L + 4, B - 20), "近景 ↓", font=f_small, fill=(140, 160, 175))

    # 摄像机（在舞台前方下侧）+ 视锥
    cam = (sx(blk["camera_x"]), B + 46)
    cone = (200, 120, 90, 60)  # 半透明视锥
    d.polygon([cam, (sx(0.12), B), (sx(0.88), B)], fill=cone)
    d.polygon([(cam[0] - 13, cam[1] + 10), (cam[0] + 13, cam[1] + 10),
               (cam[0] + 8, cam[1] - 8), (cam[0] - 8, cam[1] - 8)],
              fill=(245, 210, 90), outline=(0, 0, 0))
    d.text((cam[0] + 16, cam[1] - 6), f"📷 {blk['camera_height']}", font=f_small, fill=(245, 210, 90))

    # 灯光方向箭头
    lx, ly = (sx(0.12), sy(0.12))
    if "右" in blk["light_direction"]:
        lx = sx(0.88)
    if "顶" in blk["light_direction"]:
        lx, ly = sx(0.5), T - 2
    d.line([lx, ly, sx(0.5), sy(0.5)], fill=(120, 170, 230), width=2)
    d.ellipse([lx - 9, ly - 9, lx + 9, ly + 9], fill=(150, 195, 240))
    d.text((lx - 8, ly + 10), "💡", font=f_small, fill=(150, 195, 240))

    # 角色站位（圆点颜色 = 该角色分镜图主色调）
    for a in blk["actors"]:
        dark, light = _palette_from_seed(_derive_seed(base_seed, a["character_id"]))
        px, py = sx(a["x"]), sy(a["y"])
        d.ellipse([px - 16, py - 16, px + 16, py + 16], fill=dark, outline=(255, 255, 255), width=2)
        # 朝向小箭头（默认朝下=朝镜头）
        dir_y = 22 if "朝向" in a["facing"] else (-22 if "背向" in a["facing"] else 0)
        dir_x = 22 if "侧" in a["facing"] and dir_y == 0 else 0
        if dir_x or dir_y:
            d.line([px, py, px + dir_x, py + dir_y], fill=(255, 255, 255), width=2)
        d.text((px - 14, py - 8), a["character_id"].replace("CHAR_", "C"), font=f_small, fill=(255, 255, 255))
        d.text((px - 18, py + 18), a["facing"], font=f_small, fill=(200, 210, 220))

    # 标题
    d.text((L, 16), f"导演台俯视 · {shot_id}", font=f_title, fill=(120, 200, 170))
    d.text((L, H - 36), f"构图：{blk['framing'][:34]}", font=f_small, fill=(160, 178, 192))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
