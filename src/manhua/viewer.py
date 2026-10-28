"""
项目看板（自包含 HTML，零依赖，浏览器直接打开）。

把一次运行的全部结构化产物 + 图片 + 草样片 + 配音 + 质检 + 成本，渲染成一页可视化看板，
便于**不看 JSON 也能一眼浏览**整条流水线产出（对应 需求文档 第九章「前端看板」的零依赖最小实现）。
图片/音频用相对路径引用本项目目录下的资产，因此把 viewer.html 留在项目目录内打开即可。
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Optional

from .engine import ProjectState
from .schemas import CostReport

_CSS = """
* { box-sizing: border-box; }
body { margin:0; background:#0f1216; color:#e7edf3; font-family:"Microsoft YaHei",system-ui,sans-serif; line-height:1.6; }
a { color:#6cb6ff; }
.wrap { max-width:1080px; margin:0 auto; padding:24px; }
h1 { font-size:26px; margin:0 0 4px; }
h2 { font-size:20px; margin:32px 0 12px; border-left:4px solid #4f8cff; padding-left:10px; }
.sub { color:#9bb0c3; font-size:14px; }
.card { background:#171c22; border:1px solid #232b34; border-radius:10px; padding:14px 16px; margin:10px 0; }
.grid { display:grid; gap:14px; }
.g2 { grid-template-columns:repeat(2,1fr); }
.g3 { grid-template-columns:repeat(3,1fr); }
.chip { display:inline-block; background:#243140; color:#bfe0ff; border-radius:12px; padding:1px 9px; margin:2px 3px; font-size:12px; }
.chip.warn { background:#3a2c1a; color:#ffd699; }
.chip.bad { background:#3a1f1f; color:#ff9b9b; }
img.shot { width:100%; border-radius:8px; display:block; border:1px solid #2a333d; }
.shotcard .meta { font-size:12px; color:#9bb0c3; margin-top:6px; }
details { margin-top:6px; } summary { cursor:pointer; color:#9bb0c3; font-size:13px; }
.prompt { font-size:12px; color:#c7d2dc; white-space:pre-wrap; background:#10151a; padding:8px; border-radius:6px; margin-top:4px; }
audio { width:100%; margin-top:8px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th,td { text-align:left; padding:6px 8px; border-bottom:1px solid #232b34; }
.bar { height:10px; background:#243140; border-radius:6px; overflow:hidden; }
.bar > i { display:block; height:100%; background:linear-gradient(90deg,#4f8cff,#6cf0c2); }
.big { font-size:34px; font-weight:700; }
.pass { color:#6cf0c2; } .warnc { color:#ffd699; }
.foot { color:#6b7d8f; font-size:12px; margin-top:30px; border-top:1px solid #232b34; padding-top:12px; }
.line { color:#9bb0c3; font-size:13px; }
"""


def _esc(x) -> str:
    return html.escape(str(x))


def _scene_lines(scene) -> str:
    rows = []
    for ln in scene.script_lines:
        tag = {"dialogue": "台词", "narration": "旁白", "action": "动作"}.get(ln.kind, ln.kind)
        rows.append(f'<div class="line"><span class="chip">{_esc(tag)}</span> '
                    f'<b>{_esc(ln.speaker)}</b>：{_esc(ln.content)}</div>')
    return "".join(rows)


def build_viewer_html(state: ProjectState, genlog_summary: dict,
                      cost_report: Optional[CostReport] = None,
                      dispatch_plan=None) -> str:
    p: list[str] = []
    a = p.append
    title = state.script.title if state.script else state.project_id
    a(f'<!doctype html><html lang="zh"><head><meta charset="utf-8">'
      f'<meta name="viewport" content="width=device-width,initial-scale=1">'
      f'<title>{_esc(title)} · 漫剧看板</title><style>{_CSS}</style></head><body><div class="wrap">')

    # 头部
    a(f'<h1>{_esc(title)}</h1>')
    a(f'<div class="sub">项目 {_esc(state.project_id)} ｜ 创意：{_esc(state.idea_text)} ｜ 生成于 {_esc(state.created_at)}</div>')

    # 选题
    if state.idea:
        i = state.idea
        a('<h2>① 选题</h2><div class="card">')
        a(f'<div><span class="chip">{_esc(i.genre)}</span><span class="chip">{_esc(i.target_audience)}</span>'
          f'<span class="chip">{_esc(i.emotional_tone)}</span></div>')
        a(f'<p>{_esc(i.premise)}</p>')
        a(f'<div class="line"><b>核心冲突</b>：{_esc(i.core_conflict)}</div>')
        a(f'<div class="line"><b>开头钩子</b>：{_esc(i.opening_hook)}</div>')
        a('</div>')

    # 剧本
    if state.script:
        a('<h2>② 剧本</h2>')
        a(f'<div class="card"><div class="line"><b>Logline</b>：{_esc(state.script.logline)}</div>'
          f'<div class="line"><b>平台/时长</b>：{_esc(state.script.target_platform)} ｜ {state.script.target_duration_seconds}s</div></div>')
        for sc in state.script.scenes:
            a(f'<div class="card"><b>{_esc(sc.scene_id)} · {_esc(sc.location)}</b> '
              f'<span class="sub">（{_esc(sc.time_of_day)}）</span>'
              f'<div class="line">{_esc(sc.summary)}</div>{_scene_lines(sc)}</div>')

    # 角色
    if state.characters:
        a('<h2>③ 角色设定（需求文档 附录 12.1）</h2><div class="grid g3">')
        for c in state.characters.characters:
            ref = f"assets/characters/{c.character_id}_reference.png"
            fixed = "".join(f'<span class="chip">{_esc(f)}</span>' for f in c.fixed_visual_features)
            forb = "".join(f'<span class="chip warn">{_esc(f)}</span>' for f in c.forbidden_changes)
            a(f'<div class="card"><img class="shot" src="{ref}" alt="{_esc(c.name)}">'
              f'<div style="margin-top:8px"><b>{_esc(c.character_id)} {_esc(c.name)}</b> '
              f'<span class="sub">{c.age}岁 · {_esc(c.identity)}</span></div>'
              f'<div style="margin-top:6px">{fixed}</div>'
              f'<div style="margin-top:4px" class="sub">不可变：</div><div>{forb}</div>'
              f'<div class="line" style="margin-top:6px">🎙 {_esc(c.voice_profile)} ｜ seed {c.reference_seed}</div></div>')
        a('</div>')

    # 分镜
    if state.storyboard:
        a('<h2>④ 分镜表 + 分镜图（需求文档 附录 12.2）</h2><div class="grid g2">')
        for sh in state.storyboard.shots:
            img = f"assets/shots/{sh.shot_id}.png"
            wav = f"assets/audio/{sh.shot_id}.wav"
            a(f'<div class="card shotcard"><img class="shot" src="{img}" alt="{_esc(sh.shot_id)}">'
              f'<div class="meta"><b>{_esc(sh.shot_id)}</b> · {_esc(sh.scene)} ｜ '
              f'{_esc(sh.camera.shot_size)}/{_esc(sh.camera.angle)}/{_esc(sh.camera.movement)} ｜ {_esc(sh.duration)} ｜ '
              f'{_esc(sh.emotion)} ｜ 角色 {_esc("、".join(sh.characters))}</div>'
              f'<div class="line" style="margin-top:4px">{_esc(sh.action)}</div>'
              + (f'<div class="line">💬 {_esc(sh.dialogue)}</div>' if sh.dialogue else "")
              + f'<details><summary>image / video / negative 提示词</summary>'
              f'<div class="prompt">🖼 {_esc(sh.image_prompt)}</div>'
              f'<div class="prompt">🎬 {_esc(sh.video_prompt)}</div>'
              f'<div class="prompt">🚫 {_esc(sh.negative_prompt)}</div></details>'
              f'<audio controls preload="none" src="{wav}"></audio></div>')
        a('</div>')

    # 导演台预演（俯视构图图 + 可控镜头参数）
    if state.director:
        a('<h2>⑤ 导演台预演（需求文档 第六章：可控镜头参数 + 俯视构图图）</h2><div class="grid g2">')
        for ds in state.director.shots:
            diag = f"assets/director/{ds.shot_id}.png"
            pos = "".join(f'<span class="chip">{_esc(x.character_id.replace("CHAR_","C"))}·{_esc(x.facing)}</span>' for x in ds.actors)
            a(f'<div class="card"><img class="shot" src="{diag}" alt="{_esc(ds.shot_id)} 俯视">'
              f'<div class="meta" style="margin-top:6px"><b>{_esc(ds.shot_id)}</b> ｜ 📷 {_esc(ds.camera_height)} ｜ {_esc(ds.focal_hint)}</div>'
              f'<div class="line">构图：{_esc(ds.framing)}</div>'
              f'<div class="line">灯光：{_esc(ds.light_direction)}</div>'
              f'<div style="margin-top:4px">{pos}</div></div>')
        a('</div>')

    # 草样片 + 时间线
    if state.compose:
        a('<h2>⑥ 草样片 + 剪辑时间线（需求文档 4.7）</h2>')
        if state.compose.reel_path:
            a(f'<div class="card"><div class="sub">草样片预览（占位 GIF，主机直接可播）</div>'
              f'<img class="shot" style="max-width:360px;margin:8px auto" src="preview.gif" alt="preview"></div>')
        tl = state.compose.timeline
        rows = "".join(
            f'<tr><td>{_esc(c.shot_id)}</td><td>{_esc(c.scene)}</td><td>{c.start_seconds}s</td>'
            f'<td>{c.duration_seconds}s</td><td>{_esc(c.subtitle)[:30]}</td></tr>' for c in tl.clips)
        a(f'<div class="card"><div class="sub">时间线 {_esc(tl.aspect_ratio)} · {tl.fps}fps · 总时长 {tl.total_duration_seconds}s</div>'
          f'<table><tr><th>镜号</th><th>场景</th><th>起始</th><th>时长</th><th>字幕</th></tr>{rows}</table></div>')

    # 质检
    if state.qc:
        q = state.qc
        cls = "pass" if q.passed else "warnc"
        a('<h2>⑦ 质检（角色一致性命门 + 八维质量）</h2>')
        a(f'<div class="card"><span class="big {cls}">{q.consistency_score:.2f}</span> '
          f'<span class="sub">角色一致性（1.0 满分）｜ 综合 {q.overall_score}/10 ｜ '
          f'<b class="{cls}">{"通过" if q.passed else "需关注"}</b></span>')
        for m in q.metrics:
            pct = max(0, min(100, m.score * 10))
            a(f'<div style="margin-top:10px"><div class="line">{_esc(m.dimension)} · {m.score}/10 '
              f'<span class="sub">{_esc(m.detail)}</span></div>'
              f'<div class="bar"><i style="width:{pct}%"></i></div></div>')
        a('</div>')

    # 成本
    if cost_report:
        a('<h2>⑧ 成本估算（需求文档 成本控制）</h2>')
        rows = "".join(
            f'<tr><td>{_esc(l.category)}</td><td>{_esc(l.quantity)}</td><td>{_esc(l.unit_price)}</td>'
            f'<td>${l.estimated_usd}</td></tr>' for l in cost_report.lines)
        a(f'<div class="card"><div class="sub">本次实跑成本 <b>${cost_report.actual_cost_usd}</b>（mock 离线）｜ '
          f'若用真实云端模型估算 <b class="warnc">${cost_report.estimated_real_cost_usd}</b></div>'
          f'<table><tr><th>类别</th><th>计量</th><th>单价</th><th>估算</th></tr>{rows}</table>'
          f'<div class="sub" style="margin-top:8px">降本建议：</div>'
          + "".join(f'<div class="line">· {_esc(t)}</div>' for t in cost_report.saving_tips) + '</div>')

    # 多模型调度
    if dispatch_plan is not None:
        a('<h2>⑨ 多模型调度（需求文档 4.6：不绑死一个模型）</h2>')
        rows = "".join(
            f'<tr><td>{_esc(d.shot_id)}</td><td>{d.importance}</td><td>{_esc(d.image_model)}</td>'
            f'<td>{_esc(d.video_model)}</td><td>{"✅真实" if d.real_video else "占位"}</td></tr>'
            for d in dispatch_plan.shots)
        a(f'<div class="card"><div class="sub">关键镜真实视频 <b>{dispatch_plan.real_video_shots}</b> ｜ 占位 {dispatch_plan.placeholder_shots} ｜ '
          f'视频成本 ${dispatch_plan.full_video_cost_usd} → <b class="pass">${dispatch_plan.dispatched_video_cost_usd}</b></div>'
          f'<table><tr><th>镜号</th><th>重要度</th><th>图像模型</th><th>视频方案</th><th>真实视频</th></tr>{rows}</table>'
          f'<div class="line" style="margin-top:6px">{_esc(dispatch_plan.note)}</div></div>')

    # 日志汇总
    a('<h2>⑩ 生成日志汇总（需求文档 第七章）</h2><div class="card">')
    a("".join(f'<span class="chip">{_esc(k)}: {_esc(v)}</span>' for k, v in genlog_summary.items()))
    a('</div>')

    a('<div class="foot">离线 mock 看板：分镜图为 Pillow 占位图、配音为占位音轨、草样片为 GIF 故事板，'
      '均用于演示工程闭环与一致性机制；切到真实 API/模型后即为真实素材。本页内容均原创生成，符合 需求文档 第八章合规边界。</div>')
    a('</div></body></html>')
    return "".join(p)


def write_viewer(state: ProjectState, out_dir: Path, genlog_summary: dict,
                 cost_report: Optional[CostReport] = None, dispatch_plan=None) -> Path:
    path = out_dir / "viewer.html"
    path.write_text(build_viewer_html(state, genlog_summary, cost_report, dispatch_plan), encoding="utf-8")
    return path
