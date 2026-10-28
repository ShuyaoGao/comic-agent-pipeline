/* =====================================================================
 * app.js —— 页面外壳：三个模式、左栏作品画面、右栏流水线面板（流程图 / 共享状态 / 一致性矩阵 /
 * 成本与调度 / 生成日志）、练习清单、操作说明、大屏、退出、页脚、自检（?selftest=1）与截图状态（?shot=…）
 * ===================================================================== */
(function () {
  "use strict";
  const N = window.APP_NAMES, CR = window.CREDITS || {}, P = window.Pipeline, R = window.Render;
  const QS = new URLSearchParams(location.search);
  const AppAbort = new AbortController();
  const ON = { signal: AppAbort.signal };
  const el = id => document.getElementById(id);
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const errors = [];
  window.addEventListener("error", e => errors.push(String(e.message || e)), ON);
  window.addEventListener("unhandledrejection", e => errors.push("unhandled: " + String(e.reason && e.reason.message || e.reason)), ON);
  const origErr = console.error.bind(console);
  console.error = (...a) => { errors.push(a.map(String).join(" ")); origErr(...a); };

  const SAMPLES = [
    "一个程序员意外重生回到大学，要在毕业前阻止一场实验室事故",
    "末日里少女带着会说话的猫寻找信号源",
    "雨夜老公寓里的失踪案，真相藏在旧电梯里",
    "校园天台上的一封匿名情书",
    "古风权谋宫廷夺嫡步步惊心",
    "霓虹赛博城里，义体黑客偷走了自己的记忆",
    "契约联姻的豪门总裁其实是卧底",
    "照搬某部热门剧的同款剧情，翻拍成漫剧",
  ];
  const SPEEDS = [
    { key: "explain", name: "逐段讲解", delay: 2600, desc: "每个阶段停约 2.6 秒，适合边讲边看" },
    { key: "normal", name: "正常", delay: 1000, desc: "默认速度" },
    { key: "fast", name: "快速", delay: 260, desc: "快速过一遍" },
    { key: "instant", name: "瞬间", delay: 0, desc: "不等待，直接出结果" },
  ];
  const TASKS = [
    { key: "own", text: "用自己写的一句创意跑完 9 个阶段" },
    { key: "seed", text: "同一句创意换一个 seed 再跑，看角色名 / 外貌变没变" },
    { key: "matrix", text: "在「一致性矩阵」里点一个镜头，看它复用了谁的 seed" },
    { key: "warn", text: "写一句带“照搬 / 同款 / 翻拍”的创意，让审稿 Agent 亮黄牌" },
    { key: "cost", text: "跑完后把成本档切到「省钱档」和「全量真实视频」各看一次" },
    { key: "rerun", text: "选「分镜」或之后的阶段，点“重跑”" },
    { key: "import", text: "导入一份 3D 导演台导出的镜头 JSON（可用示例）" },
  ];
  const KIND = { idea: "llm", script: "llm", review: "llm", characters: "llm", storyboard: "llm",
                 director: "rule", art: "rule", compose: "rule", qc: "rule" };

  const S = {
    mode: null, speed: "normal", cost: "standard", state: null, run: null, cache: new R.AssetCache(),
    loop: null, paused: false, view: null, fresh: null, rtab: "state", openKeys: new Set(),
    runs: [], seenCost: new Set(), done: new Set(), matrixSel: null, stopped: false, reel: null, timers: new Set(),
  };
  const sleep = ms => new Promise(r => { const t = setTimeout(() => { S.timers.delete(t); r(); }, ms); S.timers.add(t); });
  function toast(msg, err) {
    const t = el("toast"); t.textContent = msg; t.className = err ? "show err" : "show";
    clearTimeout(toast._h); toast._h = setTimeout(() => (t.className = ""), 2600);
  }
  const speedDelay = () => SPEEDS.find(s => s.key === S.speed).delay;
  const stageName = k => P.STAGES.find(s => s[0] === k)[1];
  const stageIdx = k => P.STAGE_KEYS.indexOf(k);
  const nextStage = () => (S.state ? P.STAGE_KEYS.find(k => S.state[k] === null) : P.STAGE_KEYS[0]);
  const fmtUsd = v => "$" + (+v).toFixed(v < 1 ? 4 : 2);

  /* =====================================================================
   * 新建一次运行
   * ===================================================================== */
  function readSeed() {
    let s = parseInt(el("seed").value, 10);
    if (!Number.isFinite(s) || s < 0) s = 20260529;
    if (s > 2147483647) s = 2147483647;
    el("seed").value = s;
    return s;
  }
  function newRun() {
    const idea = el("idea").value.trim() ? el("idea").value : SAMPLES[0];
    const seed = readSeed();
    const config = applyCostPreset(P.defaultConfig(), S.cost);
    config.seed = seed;
    S.run = P.makeContext(config);
    S.state = P.newState(idea, "demo");
    S.cache.clear(); S.fresh = null; S.matrixSel = null;
    S.view = null;
    renderAll();
  }
  function ensureRun() {
    const idea = el("idea").value.trim() ? el("idea").value : SAMPLES[0];
    if (!S.state || S.state.idea_text !== idea || S.run.config.seed !== readSeed()) newRun();
  }

  /* 跑一个阶段并刷新界面 */
  function doStage() {
    const k = nextStage();
    if (!k) return null;
    P.runStage(S.state, S.run, k);
    if (k === "director" || k === "art") S.cache.clear();
    S.fresh = k; S.view = k;
    afterStage(k);
    return k;
  }
  function afterStage(k) {
    el("cap-title").textContent = `第 ${stageIdx(k) + 1} 步 · ${stageName(k)}`;
    el("cap-text").textContent = N.STAGE_HELP[k];
    if (k === "qc") onFinished();
    renderAll();
    if (k === "qc" && S.rtab === "state") setRTab("matrix");
  }
  function onFinished() {
    const st = S.state;
    S.runs.push({ idea: st.idea_text, seed: S.run.config.seed, names: st.characters.characters.map(c => c.name).join(",") });
    if (!SAMPLES.includes(st.idea_text) && S.mode !== "watch") tick("own");
    const same = S.runs.filter(r => r.idea === st.idea_text);
    if (new Set(same.map(r => r.seed)).size >= 2) tick("seed");
    if (st.review.compliance_status === "warn") tick("warn");
  }

  async function runLoop(ensure = true) {
    if (S.loop) return;
    if (ensure) { ensureRun(); if (!nextStage()) newRun(); }
    S.paused = false;
    const token = {};
    S.loopToken = token;
    const alive = () => !S.stopped && S.loopToken === token;
    let resolveLoop;
    S.loop = new Promise(r => { resolveLoop = r; });
    setButtons(true);
    let natural = false;
    try {
      while (true) {
        if (!alive()) break;
        if (!nextStage()) { natural = true; break; }
        while (S.paused && alive()) await sleep(80);
        if (!alive()) break;
        doStage();
        if (nextStage()) await sleep(speedDelay() || 0);
      }
    } finally {
      if (S.loopToken === token) { S.loopToken = null; S.loop = null; setButtons(false); renderFlow(); }
      resolveLoop();
    }
    if (natural && !S.stopped && S.state && S.state.qc) {
      S.view = "compose"; renderView(); renderViewTabs(); renderFlow();
      if (S.mode === "watch") el("cap-text").textContent += " —— 全部 9 个阶段完成：左边在播草样片；右栏看一致性矩阵与成本。可切到「我来编」换自己的创意。";
      if (S.reel && S.speed !== "instant") S.reel.play(false);
    }
  }
  /* 停止当前循环；返回一个在循环真正结束后 resolve 的 promise */
  function stopLoop() {
    S.paused = false;
    const l = S.loop;
    S.loopToken = null; S.loop = null;
    setButtons(false);
    return l;
  }
  function setButtons(running) {
    el("btn-pause").disabled = !running;
    el("btn-pause").textContent = S.paused ? "▶ 继续" : "⏸ 暂停";
    for (const id of ["btn-step", "btn-rerun", "btn-reset", "btn-import"]) el(id).disabled = running;
    el("btn-run").disabled = running;
  }
  function rerunFrom(key) {
    if (!S.state) return;
    if (S.state[key] === null) { toast("这个阶段还没跑过，直接点“一键跑完”或“单步”", true); return; }
    P.resetFrom(S.state, key);
    S.cache.clear();
    if (stageIdx(key) >= stageIdx("storyboard")) tick("rerun");
    el("cap-title").textContent = `从「${stageName(key)}」重跑`;
    el("cap-text").textContent = "已清空该阶段及之后的产物（前面的保留不动），这就是“检查点 + 单步重跑”。生成日志会继续追加，不会丢掉之前的记录。";
    renderAll();
    runLoop(false);
  }

  /* =====================================================================
   * 左栏：作品画面（按阶段）
   * ===================================================================== */
  function renderViewTabs() {
    const box = el("view-tabs");
    box.innerHTML = P.STAGES.map(([k, n], i) =>
      `<button data-v="${k}" ${S.state && S.state[k] ? "" : "disabled"} class="${S.view === k ? "on" : ""}" title="${n}">${i + 1} ${n.replace(" Agent", "").replace("与合规", "")}</button>`).join("");
    box.querySelectorAll("button").forEach(b => b.addEventListener("click", () => { S.view = b.dataset.v; renderView(); renderViewTabs(); renderFlow(); }));
  }
  function canvasThumb(path, cls) {
    return `<canvas class="thumb ${cls || ""}" data-asset="${esc(path)}" width="10" height="10"></canvas>`;
  }
  function paintCanvases(root) {
    root.querySelectorAll("canvas[data-asset]").forEach(c => {
      const src = S.cache.get(c.dataset.asset, S.run);
      if (!src) return;
      c.width = src.width; c.height = src.height;
      c.getContext("2d").drawImage(src, 0, 0);
    });
  }
  function scoreRow(name, score, note) {
    const known = score !== null && score !== undefined;
    return `<div class="score-row"><span>${esc(name)}</span><div class="bar ${known ? "" : "ghost"}"><i style="width:${known ? score * 10 : 100}%"></i></div>` +
           `<span class="num">${known ? score + " / 10" : "待后期"}</span></div>` + (note ? `<div class="note" style="margin:-2px 0 4px 98px">${esc(note)}</div>` : "");
  }
  const VIEWS = {
    idea(st) {
      const i = st.idea;
      return `<div class="blk"><div>${[i.genre, i.target_audience, i.emotional_tone].map(x => `<span class="chip">${esc(x)}</span>`).join("")}</div>
        <p style="margin:6px 0">${esc(i.premise)}</p>
        <div class="line"><b>核心冲突</b>：${esc(i.core_conflict)}</div><div class="line"><b>开头钩子</b>：${esc(i.opening_hook)}</div>
        <div class="line"><b>系列化</b>：${esc(i.series_potential)}</div></div>
        <div class="grid g3">${i.character_seeds.map(s => `<div class="blk"><h4>${esc(s.name)} <span class="chip">${esc(s.role)}</span></h4><div class="line">${esc(s.one_line)}</div></div>`).join("")}</div>
        <div class="blk"><h4>可选方向</h4>${i.candidate_directions.map(d => `<div class="line">· ${esc(d)}</div>`).join("")}
        <div class="note" style="margin-top:4px">${i.type_structure_notes.map(esc).join("；")}</div></div>`;
    },
    script(st) {
      const s = st.script, tag = { dialogue: "台词", narration: "旁白", action: "动作" };
      return `<div class="blk"><h4>${esc(s.title)}</h4><div class="line"><b>一句话</b>：${esc(s.logline)}</div>
        <div class="line"><b>平台 / 时长</b>：${esc(s.target_platform)} ｜ ${s.target_duration_seconds}s</div></div>` +
        s.scenes.map(sc => `<div class="blk"><h4>${esc(sc.scene_id)} · ${esc(sc.location)} <span class="sub">（${esc(sc.time_of_day)}）出场：${sc.on_stage.map(esc).join("、")}</span></h4>
          <div class="line">${esc(sc.summary)}</div>${sc.script_lines.map(l => `<div class="line"><span class="chip">${tag[l.kind]}</span><b>${esc(l.speaker)}</b>：${esc(l.content)}</div>`).join("")}</div>`).join("");
    },
    review(st) {
      const r = st.review, warn = r.compliance_status !== "pass";
      return `<div class="blk"><h4>合规判定：<span class="chip ${warn ? "warn" : "ok"}">${esc(r.compliance_status)}</span> 建议进入下一阶段：${r.overall_pass ? "是" : "否"}</h4>
        ${r.compliance_notes.map(n => `<div class="line">${esc(n)}</div>`).join("")}</div>
        <div class="blk"><h4>八维质量评分 <span class="chip warn">离线示意分，不是模型评出来的</span></h4>
        ${r.quality_scores.map(q => scoreRow(q.dimension, q.score, q.comment)).join("")}
        <div class="note">离线编造器里这 8 个分数是写死的常量；前期评不了的维度留空“待后期”。换成真实模型后才是模型给出的评分。</div></div>
        <div class="blk"><div class="line"><b>逻辑</b>：${r.logic_issues.map(esc).join("；")}</div><div class="line"><b>节奏</b>：${r.pacing_notes.map(esc).join("；")}</div>
        <div class="line"><b>连贯</b>：${r.continuity_notes.map(esc).join("；")}</div><div class="line"><b>建议</b>：${r.suggestions.map(esc).join("；")}</div></div>`;
    },
    characters(st) {
      const cs = st.characters;
      return `<div class="grid g3">${cs.characters.map(c => {
        const pal = c.reference_seed !== null ? R.palette(c.reference_seed) : null;
        return `<div class="blk">${c.reference_image ? canvasThumb(c.reference_image) : `<div class="placeholder">参考图在「美术」阶段生成</div>`}
          <h4 style="margin-top:6px">${esc(c.character_id)} ${esc(c.name)} <span class="sub">${c.age} 岁 · ${esc(c.identity)}</span></h4>
          <div>${c.fixed_visual_features.map(f => `<span class="chip">${esc(f)}</span>`).join("")}</div>
          <div class="note">不可变：${c.forbidden_changes.map(esc).join("、")}</div>
          <div class="line">音色：${esc(c.voice_profile)}${pal ? ` ｜ <span class="sw" style="background:${pal.darkCss}"></span>seed ${c.reference_seed}` : ""}</div></div>`;
      }).join("")}</div><div class="blk note">${esc(cs.consistency_strategy)}</div>`;
    },
    storyboard(st) {
      return tw(`<table class="t"><tr><th>镜号</th><th>场景</th><th>角色</th><th>景别 / 机位 / 运镜</th><th>情绪</th><th>对白</th></tr>${st.storyboard.shots.map(sh =>
        `<tr><td class="num">${esc(sh.shot_id)}</td><td>${esc(sh.scene)}</td><td>${sh.characters.map(esc).join("、")}</td>
         <td>${esc(sh.camera.shot_size)} / ${esc(sh.camera.angle)} / ${esc(sh.camera.movement)}</td><td>${esc(sh.emotion)}</td><td>${esc(sh.dialogue)}</td></tr>`).join("")}</table>`) +
        st.storyboard.shots.map(sh => `<details class="blk"><summary>${esc(sh.shot_id)} 的 image / video / negative 提示词</summary>
          <div class="prompt">🖼 ${esc(sh.image_prompt)}</div><div class="prompt">🎬 ${esc(sh.video_prompt)}</div><div class="prompt">🚫 ${esc(sh.negative_prompt)}</div></details>`).join("");
    },
    director(st) {
      return `<div class="grid g2">${st.director.shots.map(ds => `<div class="blk">${canvasThumb(ds.blocking_diagram)}
        <div class="line" style="margin-top:4px"><b>${esc(ds.shot_id)}</b> ｜ 📷 ${esc(ds.camera_height)} ｜ ${esc(ds.focal_hint)}</div>
        <div class="note">构图：${esc(ds.framing)}</div><div class="note">灯光：${esc(ds.light_direction)}</div>
        <div>${ds.actors.map(a => `<span class="chip">${esc(a.character_id.replace("CHAR_", "C"))} (${a.x}, ${a.y}) ${esc(a.facing)}</span>`).join("")}</div></div>`).join("")}</div>
        <div class="blk note">${esc(st.director.note)}</div>`;
    },
    art(st) {
      const a = st.art;
      const sel = S.matrixSel;
      return `<h4 style="margin-bottom:4px">角色参考图（每个角色锁一个 seed）</h4><div class="grid g3">${a.character_references.map(r =>
        `<div>${canvasThumb(r.image_path)}<div class="cap">${esc(r.ref_id)} · seed ${r.seed}</div></div>`).join("")}</div>
        <h4 style="margin:8px 0 4px">分镜图（复用首位出场角色的 seed + 参考图 → 同色）</h4><div class="grid g3">${a.shot_images.map(r =>
        `<div style="${sel === r.ref_id ? "outline:3px solid #ffd95c;border-radius:8px" : ""}">${canvasThumb(r.image_path)}
          <div class="cap">${esc(r.ref_id)} · seed ${r.seed} · 参考 ${esc(r.reference_image ? r.reference_image.split("/").pop() : "无")}</div></div>`).join("")}</div>
        <div class="blk note" style="margin-top:6px">${esc(a.consistency_note)}</div>`;
    },
    compose(st) {
      const c = st.compose, tl = c.timeline, colors = ["#7fb3ff", "#ffd27f", "#9ff3d4", "#ffaaa6", "#d1b3ff", "#b7e07f"];
      return `<div class="reelwrap"><div><canvas id="reel"></canvas>
          <div class="row" style="margin-top:4px"><button class="btn" id="reel-play">▶ 播放草样片</button>
          <label title="与 Python 版占位 .wav 同一公式：极低音量的提示音"><input type="checkbox" id="reel-sound"> 提示音</label></div></div>
        <div class="timeline"><h4>剪辑时间线 · ${esc(tl.aspect_ratio)} · ${tl.fps}fps · 总时长 ${tl.total_duration_seconds}s</h4>
          <div class="tl" id="tl">${tl.clips.map((cl, i) => `<span data-i="${i}" style="flex:${cl.duration_seconds};background:${colors[i % colors.length]}">${esc(cl.shot_id)}</span>`).join("")}</div>
          ${tw(`<table class="t"><tr><th>镜号</th><th>起始</th><th>时长</th><th>配音</th><th>字幕</th></tr>${tl.clips.map((cl, i) => {
            const au = c.audio_clips[i];
            return `<tr><td class="num">${esc(cl.shot_id)}</td><td class="num">${cl.start_seconds}s</td><td class="num">${cl.duration_seconds}s</td>
              <td class="num">${au ? au.duration_seconds + "s" : "—"}</td><td>${esc(cpShort(cl.subtitle, 30))}</td></tr>`;
          }).join("")}</table>`)}
          <div class="note">${esc(c.note)}</div>
          <div class="note">配音时长按“约 4.5 字 / 秒”估算、且不超过镜头时长；浏览器版草样片是 canvas 轮播（Python 版产出 GIF）。</div></div></div>`;
    },
    qc(st) {
      const q = st.qc, cls = q.passed ? "pass" : "warnc";
      return `<div class="blk"><span class="big ${cls}">${q.consistency_score.toFixed(2)}</span>
        <span class="sub"> 角色一致性（1.00 满分）｜ 综合 ${q.overall_score} / 10 ｜ <b class="${cls}">${q.passed ? "通过" : "需关注"}</b></span>
        ${q.metrics.map(m => scoreRow(m.dimension, m.score, m.detail)).join("")}</div>
        ${q.issues.length ? `<div class="blk"><h4>问题清单</h4>${q.issues.map(i => `<div class="line">· ${esc(i)}</div>`).join("")}</div>` : ""}
        <div class="blk note">${esc(q.note)}</div>`;
    },
  };
  const cpShort = (s, n) => { const a = Array.from(String(s)); return a.length > n ? a.slice(0, n).join("") + "…" : a.join(""); };
  /* 长表格放进横向滚动容器（手机上容器内滚动，整页不横向溢出；电脑上没有影响） */
  const tw = html => `<div class="tw">${html}</div>`;

  function renderView() {
    const v = el("view");
    if (S.reel) { S.reel.stop(); S.reel = null; }
    const k = S.view && S.state && S.state[S.view] ? S.view : null;
    if (!k) {
      el("view-title").textContent = "作品画面";
      v.innerHTML = `<div class="placeholder">还没有产物。点下方“▶ 一键跑完”或“⏭ 单步”，9 个 Agent 会依次把结果写进共享状态。</div>`;
      return;
    }
    el("view-title").textContent = `${stageIdx(k) + 1}. ${stageName(k)} 的产物`;
    v.innerHTML = VIEWS[k](S.state);
    paintCanvases(v);
    if (k === "compose") setupReel();
  }
  function setupReel() {
    const cv = el("reel");
    if (!cv) return;
    S.reel = new R.ReelPlayer(cv, i => {
      document.querySelectorAll("#tl span").forEach(s => s.classList.toggle("cur", +s.dataset.i === i));
    });
    S.reel.onEnd = () => { const b = el("reel-play"); if (b) b.textContent = "▶ 播放草样片"; };
    S.reel.load(S.run.reel, S.cache, S.run, S.run.audio);
    el("reel-play").addEventListener("click", () => {
      if (S.reel.playing) { S.reel.stop(); el("reel-play").textContent = "▶ 播放草样片"; }
      else { S.reel.play(el("reel-sound").checked); el("reel-play").textContent = "⏸ 暂停"; }
    });
  }

  /* =====================================================================
   * 右栏
   * ===================================================================== */
  function renderFlow() {
    const box = el("flow");
    const cur = S.loop ? nextStage() : null;
    box.innerHTML = P.STAGES.map(([k, n], i) => {
      const done = S.state && S.state[k] !== null;
      const st = done ? "已完成" : (k === cur ? "运行中" : "待运行");
      return `<div class="node kind-${KIND[k]} ${done ? "done" : ""} ${k === cur ? "run" : ""} ${S.view === k ? "sel" : ""}" data-k="${k}" title="${esc(N.STAGE_HELP[k])}">
        <span class="no">${i + 1}</span><span class="nm">${esc(n.replace(" Agent", ""))}</span><span class="st">${st}</span></div>`;
    }).join("");
    box.querySelectorAll(".node").forEach(nd => nd.addEventListener("click", () => {
      if (S.state && S.state[nd.dataset.k]) { S.view = nd.dataset.k; renderView(); renderViewTabs(); renderFlow(); }
    }));
    const n = S.state ? P.STAGE_KEYS.filter(k => S.state[k] !== null).length : 0;
    el("mob-explain").textContent = n ? `已完成 ${n} / ${P.STAGE_KEYS.length} 个阶段 · 流程图、共享状态 JSON、一致性矩阵、成本、生成日志`
                                      : "流程图 · 共享状态 JSON · 一致性矩阵 · 成本与调度 · 生成日志";
  }
  function renderStateTree() {
    const box = el("state-tree");
    if (!S.state) { box.innerHTML = ""; return; }
    const st = S.state;
    const head = `<div class="note" style="margin-bottom:4px">project_id: ${esc(st.project_id)} ｜ idea_text: ${esc(st.idea_text)} ｜ created_at: ${esc(st.created_at)}</div>`;
    box.innerHTML = head + P.STAGE_KEYS.map(k => {
      const v = st[k];
      const size = v === null ? "null（还没运行）" : `${JSON.stringify(v).length.toLocaleString()} 字符`;
      const open = v !== null && (S.openKeys.has(k) || S.fresh === k);
      return `<details class="sk ${v === null ? "null" : ""} ${S.fresh === k ? "fresh" : ""}" data-k="${k}" ${open ? "open" : ""}>
        <summary>"${k}" <span class="sz">${esc(stageName(k))} · ${size}</span></summary>${v === null ? "" : `<pre>${esc(JSON.stringify(v, null, 1))}</pre>`}</details>`;
    }).join("");
    box.querySelectorAll("details.sk").forEach(d => d.addEventListener("toggle", () => {
      if (d.open) S.openKeys.add(d.dataset.k); else S.openKeys.delete(d.dataset.k);
    }));
    const fresh = box.querySelector(".sk.fresh");
    if (fresh) fresh.scrollIntoView({ block: "nearest" });
  }
  function renderMatrix() {
    const box = el("matrix");
    if (!S.state || !S.state.qc) {
      box.innerHTML = `<div class="placeholder">质检 Agent 跑完后，这里列出每个镜头的 4 项一致性检查。</div>`;
      return;
    }
    const seedOf = {};
    for (const c of S.state.characters.characters) seedOf[c.character_id] = c.reference_seed;
    const assets = {};
    for (const a of S.state.art.shot_images) assets[a.ref_id] = a;
    const names = ["seed复用", "参考图复用", "固定特征入image_prompt", "负面词抑制漂移"];
    const label = { "seed复用": "seed 复用", "参考图复用": "参考图复用", "固定特征入image_prompt": "固定外貌写进提示词", "负面词抑制漂移": "负面词抑制漂移" };
    box.innerHTML = `<div class="note" style="margin-bottom:4px">角色一致性得分 = 所有镜头 4 项检查的通过比例的平均 = <b>${S.state.qc.consistency_score.toFixed(3)}</b>。点一行，左边高亮这一镜的分镜图。</div>
      ${tw(`<table class="t mx"><tr><th>镜号</th><th>锚点角色</th><th>本镜 seed</th>${names.map(n => `<th>${label[n]}</th>`).join("")}</tr>${S.run.qcMatrix.map(r => {
        const a = assets[r.shot_id], pal = a ? R.palette(a.seed) : null;
        return `<tr data-s="${esc(r.shot_id)}" class="${S.matrixSel === r.shot_id ? "sel" : ""}"><td class="num">${esc(r.shot_id)}</td>
          <td>${esc(r.anchor)}（锁定 seed ${seedOf[r.anchor] ?? "—"}）</td>
          <td class="num">${pal ? `<span class="sw" style="background:${pal.darkCss}"></span>` : ""}${a ? a.seed : "—"}</td>
          ${r.checks.map(c => `<td class="c ${c.ok ? "y" : "n"}">${c.ok ? "✔" : "✘"}</td>`).join("")}</tr>`;
      }).join("")}</table>`)}
      <div class="note" style="margin-top:6px">没有角色出场的镜头不参与一致性检查。想看检查失败的样子：导入一份引用了不存在角色的导演台 JSON。</div>`;
    box.querySelectorAll("tr[data-s]").forEach(tr => tr.addEventListener("click", () => {
      S.matrixSel = tr.dataset.s; tick("matrix");
      S.view = "art"; renderView(); renderViewTabs(); renderFlow(); renderMatrix();
    }));
  }
  function renderCost() {
    const box = el("costbox");
    if (!S.state || !S.state.storyboard) {
      box.innerHTML = `<div class="placeholder">分镜表出来后就能估算成本；跑完全部阶段后数字最完整。</div>`;
      return;
    }
    const cfg = S.run.config;
    const cost = P.estimateCost(S.state, S.run.genlog, cfg), plan = P.dispatchModels(S.state, cfg);
    const preset = COST_PRESETS.find(p => p.key === S.cost);
    if (S.state.qc) { S.seenCost.add(S.cost); if (S.seenCost.has("save") && S.seenCost.has("all_real")) tick("cost"); }
    box.innerHTML = `<div class="blk"><h4>当前成本档：${esc(preset.name)} <span class="sub">${esc(preset.desc)}</span></h4>
        <div class="line">本次离线实跑成本 <b>${fmtUsd(cost.actual_cost_usd)}</b> ｜ 若改用真实云端模型生产本片，估算约 <b class="warnc">${fmtUsd(cost.estimated_real_cost_usd)}</b></div>
        ${tw(`<table class="t"><tr><th>类别</th><th>计量</th><th>示意单价</th><th>估算</th></tr>${cost.lines.map(l =>
          `<tr><td>${esc(l.category)}</td><td>${esc(l.quantity)}${l.category.startsWith("文本") ? "（估算）" : ""}</td><td>${esc(l.unit_price)}</td><td class="num">${fmtUsd(l.estimated_usd)}</td></tr>`).join("")}</table>`)}
        <div class="note">token 数是按字数估算的（约 2 字 1 token），不是真实计费；所有单价都是教学示意值，不对应任何具体厂商报价。</div></div>
      <div class="blk"><h4>多模型调度：只给关键镜出真实视频</h4>
        <div class="line">视频成本：每镜都出真实视频 <b>${fmtUsd(plan.full_video_cost_usd)}</b> → 调度后 <b class="pass">${fmtUsd(plan.dispatched_video_cost_usd)}</b>
          （${plan.real_video_shots} 镜真实视频 + ${plan.placeholder_shots} 镜占位）</div>
        ${tw(`<table class="t"><tr><th>镜号</th><th>重要度</th><th>图像模型</th><th>视频方案</th><th>理由</th></tr>${plan.shots.map(d =>
          `<tr><td class="num">${esc(d.shot_id)}</td><td class="num">${d.importance}</td><td>${esc(N.label(d.image_model))}</td>
           <td>${d.real_video ? "✅ " : ""}${esc(N.label(d.video_model))}</td><td>${esc(d.reason)}</td></tr>`).join("")}</table>`)}
        <div class="note">重要度：特写 / 近景 +2，多角色同框 +1，高情绪 +1，首尾镜 +1；按重要度取前 ${cfg.dispatch.key_shot_max} 镜出真实视频，重要度 ≥ 2 的用强一致性图像模型。</div></div>
      <div class="blk"><h4>降本建议</h4>${cost.saving_tips.map(t => `<div class="line">· ${esc(t)}</div>`).join("")}</div>`;
  }
  function renderLog() {
    const box = el("logbox");
    if (!S.run || !S.run.genlog.records.length) { box.innerHTML = `<div class="placeholder">还没有生成记录。</div>`; return; }
    const sm = S.run.genlog.summary();
    box.innerHTML = `<div class="note" style="margin-bottom:4px">共 ${sm.total_generations} 条：文本 ${sm.llm_calls} · 图像 ${sm.image_calls} · 配音 ${sm.audio_calls} · 草样片 ${sm.video_calls} ·
      输入 / 输出 token（估算）${sm.total_input_tokens} / ${sm.total_output_tokens} · 实际花费 $${sm.total_cost_usd}</div>` +
      S.run.genlog.records.slice().reverse().map(r => `<div class="rec"><div class="h"><span class="id">${r.id}</span><span class="stg">${esc(r.stage)}</span>
        <span>${esc(r.gen_type)}</span><span class="sub">${esc(N.label(r.model))}</span>
        ${r.gen_type === "llm" ? `<span class="sub">token 估算 ${r.input_tokens} 入 / ${r.output_tokens} 出</span>` : ""}
        ${r.params && r.params.seed !== undefined ? `<span class="sub">seed ${r.params.seed}</span>` : ""}</div>
        <div class="p" title="${esc(r.prompt)}">${esc(r.prompt.split("\n").join(" ⏎ "))}</div></div>`).join("");
  }
  function setRTab(k) {
    S.rtab = k;
    document.querySelectorAll("[data-rtab]").forEach(b => b.classList.toggle("on", b.dataset.rtab === k));
    document.querySelectorAll(".rpane").forEach(p => p.classList.toggle("on", p.id === "rpane-" + k));
    el("rtab-hint").textContent = { state: "刚写入的阶段会高亮", matrix: "角色一致性 = 可复核的工程指标", cost: "示意单价，只影响估算", log: "最新的在最上面" }[k];
    if (k === "cost") renderCost();
  }
  function renderAll() {
    renderFlow(); renderViewTabs(); renderView(); renderStateTree(); renderMatrix(); renderLog();
    if (S.rtab === "cost") renderCost();
  }

  /* =====================================================================
   * 练习
   * ===================================================================== */
  function renderTasks() {
    const first = TASKS.findIndex(t => !S.done.has(t.key));
    el("tasks").innerHTML = TASKS.map((t, i) => `<li class="${S.done.has(t.key) ? "done" : i === first ? "next" : ""}">${esc(t.text)}</li>`).join("");
  }
  function tick(k) {
    if (S.mode !== "practice" || S.done.has(k)) return;
    S.done.add(k); renderTasks();
    if (S.done.size === TASKS.length) toast("练习全部完成！");
  }

  /* =====================================================================
   * 导入 / 导出
   * ===================================================================== */
  function importStoryboard(data, label) {
    if (!S.state || !S.state.characters) { toast("先至少跑到「角色设定」阶段：导入的镜头要复用项目里的角色 seed / 参考图", true); return false; }
    let sb;
    try { sb = P.loadStoryboard(data); } catch (e) { toast("导入失败：" + e.message, true); return false; }
    const known = new Set(S.state.characters.characters.map(c => c.character_id));
    const unknown = P.unknownCharacterIds(sb, known);
    stopLoop();
    S.state.storyboard = sb;
    P.resetFrom(S.state, "art");
    S.cache.clear();
    el("cap-title").textContent = `已导入 ${label}（${sb.shots.length} 镜）`;
    el("cap-text").textContent = "分镜被替换，接着重跑 美术 → 合成 → 质检（与 Python 版 --storyboard-from 相同：导演台阶段保留原样）。" +
      (unknown.length ? `注意：引用了项目里不存在的角色 ${unknown.join("、")}，这些镜无法复用角色 seed / 参考图，质检会扣分。` : "");
    tick("import");
    renderAll(); runLoop(false);
    return true;
  }
  function download(name, text, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function exportAll() {
    if (!S.state) return toast("还没有产物", true);
    const bundle = { state: S.state, cost_report: P.estimateCost(S.state, S.run.genlog, S.run.config),
                     model_dispatch: P.dispatchModels(S.state, S.run.config), asset_library: P.buildAssetLibrary(S.state) };
    download("comic_pipeline_state.json", JSON.stringify(bundle, null, 2), "application/json");
    download("generation_log.jsonl", S.run.genlog.records.map(r => JSON.stringify(r)).join("\n") + "\n", "application/jsonl");
  }

  /* =====================================================================
   * 模式
   * ===================================================================== */
  async function setMode(mode) {
    const l = stopLoop(); if (l) await l;
    S.mode = mode;
    for (const m of ["watch", "edit", "practice"]) document.body.classList.toggle("m-" + m, m === mode);
    if (S.sheet) S.sheet.close();
    document.querySelectorAll("#modes button").forEach(b => b.classList.toggle("on", b.dataset.mode === mode));
    el("tasks").hidden = mode !== "practice";
    el("idea").readOnly = mode === "watch";
    if (mode === "watch") {
      el("idea").value = SAMPLES[0]; el("seed").value = 20260529;
      newRun();
      el("cap-title").textContent = "观看：示例创意自动跑一遍";
      el("cap-text").textContent = "左边看每个阶段的产物，右栏看流程图走到哪一步、共享状态 JSON 怎么一段段长出来。";
      runLoop();
    } else if (mode === "edit") {
      el("cap-title").textContent = "我来编";
      el("cap-text").textContent = "改创意、seed 或成本档，再点“一键跑完”或“单步”。同一创意 + 同一 seed，结果永远一样（可复现）。";
      if (!S.state) newRun();
    } else {
      S.done = new Set(); renderTasks();
      el("cap-title").textContent = "练习";
      el("cap-text").textContent = "按清单一项项做，完成的自动打勾。";
      if (!S.state) newRun();
    }
  }

  /* =====================================================================
   * 说明 / 大屏 / 退出 / 页脚
   * ===================================================================== */
  const HELP_KEY = "comic-agent-pipeline.help-seen";
  function openHelp() {
    el("dlg-help").classList.add("show");
    if (S.loop && !S.paused) { S.paused = true; S.helpPaused = true; setButtons(true); }
  }
  function closeHelp() {
    el("dlg-help").classList.remove("show");
    if (S.helpPaused) { S.helpPaused = false; S.paused = false; setButtons(!!S.loop); }
    try { localStorage.setItem(HELP_KEY, "1"); } catch (e) { /* file:// 下可能不可用 */ }
  }
  function exitApp() {
    if (S.stopped) return;
    S.stopped = true; S.loop = null;
    for (const t of S.timers) clearTimeout(t);
    if (S.reel) S.reel.stop();
    if (S.sheet) S.sheet.close();
    R.closeAudio();
    AppAbort.abort();
    if (window.MobileUI) window.MobileUI.destroy();
    S.cache.clear(); S.state = null; S.run = null;
    document.querySelectorAll("canvas").forEach(c => { c.width = c.height = 0; });
    try { window.close(); } catch (e) { /* 浏览器不允许 */ }
    setTimeout(() => { el("layout").remove(); el("ended").classList.add("show"); document.title = "已停止运行"; }, 120);
  }
  function fillFooter() {   // 页脚只放纯文字署名 + 联系邮箱 + 许可证
    const parts = [];
    if (CR.AUTHOR) parts.push("作者 " + CR.AUTHOR + (CR.AUTHOR_EMAIL ? `（${CR.AUTHOR_EMAIL}）` : ""));
    if (CR.UNIVERSITY_EN) parts.push(CR.UNIVERSITY_EN);
    if (CR.UNIVERSITY_KO) parts.push(CR.UNIVERSITY_KO);
    parts.push("代码 MIT · 文档 CC BY 4.0");
    if (CR.SERIES_NAME_ZH) parts.push(`${CR.SERIES_NAME_ZH} · 系列教学演示`);
    parts.push("离线演示：文字为规则编造、图片为占位卡片，不是真实模型输出");
    el("footer").textContent = parts.join(" · ");
  }
  function buildSeg(id, list, cur, onPick) {
    const box = el(id);
    box.innerHTML = list.map(p => `<button data-k="${p.key}" title="${esc(p.desc)}">${esc(p.name)}</button>`).join("");
    const mark = k => box.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.k === k));
    box.querySelectorAll("button").forEach(b => b.addEventListener("click", () => { mark(b.dataset.k); onPick(b.dataset.k); }, ON));
    mark(cur);
    return mark;
  }

  /* =====================================================================
   * 手机 / 触屏：☰ 菜单、过程面板全屏展开、横屏提示、按下反馈、防误触（样式在 css/mobile.css）
   * ===================================================================== */
  function setupMobile() {
    const M = window.MobileUI;
    if (!M) return;
    S.sheet = M.sheets(el("panel-close"), cur => { if (cur === "panel") el("rightcol").scrollTop = 0; });
    M.detect({ onChange: st => { if (!st.touchp) S.sheet.close(); } });
    M.menu(el("menu-btn"), el("menu"));
    el("menu-help").addEventListener("click", openHelp, ON);
    el("menu-exit").addEventListener("click", exitApp, ON);
    el("panel-btn").addEventListener("click", () => S.sheet.open("panel"), ON);
    M.rotateHint(el("rotate-hint"), el("rotate-ok"));
    M.pressFeedback(document.body, ".btn, .seg button, #modes button, .tabs button, .node, .mbtn, #menu button, #menu a, .icon, .exit");
    M.guard(document.body, { onReset: () => {} });
  }

  /* =====================================================================
   * 自检（?selftest=1）与截图（?shot=…）
   * ===================================================================== */
  function layoutCheck(tag) {
    const de = document.documentElement, vw = innerWidth, vh = innerHeight, r = id => el(id).getBoundingClientRect();
    const L = r("leftcol"), Rr = r("rightcol"), F = r("footer"), V = r("view"), T = r("topbar");
    return { tag, vw, vh, hOverflow: de.scrollWidth - vw, leftBottom: Math.round(L.bottom), rightBottom: Math.round(Rr.bottom),
             viewH: Math.round(V.height), topbarOverflow: el("topbar").scrollWidth - Math.round(T.width),
             ok: de.scrollWidth <= vw && L.bottom <= vh + 1 && Rr.bottom <= vh + 1 && F.bottom <= vh + 1 && V.height >= 160 &&
                 el("topbar").scrollWidth <= Math.round(T.width) + 1 };
  }
  async function runInstant() { S.speed = "instant"; await runLoop(); }
  async function selftest() {
    const out = { ok: false, steps: {}, layout: [], errors };
    const t0 = performance.now();
    try {
      await setMode("edit");
      el("idea").value = SAMPLES[0]; el("seed").value = 20260529;
      for (const preset of ["standard"]) { S.cost = preset; }
      newRun(); await runInstant();
      const st = S.state, run = S.run;
      const cost = {};
      for (const p of COST_PRESETS) {
        const cfg = applyCostPreset(P.defaultConfig(), p.key); cfg.seed = run.config.seed;
        const c = P.estimateCost(st, run.genlog, cfg), d = P.dispatchModels(st, cfg);
        cost[p.key] = { name: p.name, estimated_real_cost_usd: c.estimated_real_cost_usd, real_video_shots: d.real_video_shots,
                        full_video_cost_usd: d.full_video_cost_usd, dispatched_video_cost_usd: d.dispatched_video_cost_usd };
      }
      out.steps.demo = {
        idea: st.idea_text, seed: run.config.seed, stages_done: P.STAGE_KEYS.filter(k => st[k] !== null).length,
        characters: st.characters.characters.map(c => `${c.character_id} ${c.name}`), shots: st.storyboard.shots.length,
        genre: st.idea.genre, compliance: st.review.compliance_status,
        consistency_score: st.qc.consistency_score, overall_score: st.qc.overall_score, qc_passed: st.qc.passed,
        total_duration_seconds: st.compose.timeline.total_duration_seconds, genlog: run.genlog.summary(), cost,
        canvases_painted: document.querySelectorAll("#view canvas").length,
      };
      // 合规红线：带“照搬 / 同款”的创意应得到 warn
      el("idea").value = SAMPLES[7]; newRun(); await runInstant();
      out.steps.warn_case = { compliance: S.state.review.compliance_status, notes: S.state.review.compliance_notes };
      // 导入 3D 导演台示例导出：替换分镜 → 重跑 美术 / 合成 / 质检
      el("idea").value = SAMPLES[3]; newRun(); await runInstant();
      const okImport = importStoryboard(window.SAMPLE_DIRECTOR_EXPORT, "示例导出"); if (S.loop) await S.loop;
      out.steps.import = { ok: okImport, shots: S.state.storyboard.shots.length, qc: !!S.state.qc,
                           consistency_score: S.state.qc && S.state.qc.consistency_score };
      // 草样片：每个镜头都能画出一帧
      S.view = "compose"; renderView();
      out.steps.reel = { shots: S.run.reel.shots.length, canvas: [el("reel").width, el("reel").height] };
      // 各视图、右栏标签、模式、说明、大屏
      for (const k of P.STAGE_KEYS) { S.view = k; renderView(); }
      for (const k of ["state", "matrix", "cost", "log"]) setRTab(k);
      await setMode("practice"); out.layout.push(layoutCheck("practice"));
      await setMode("edit"); out.layout.push(layoutCheck("edit"));
      openHelp(); out.steps.help_open = el("dlg-help").classList.contains("show"); closeHelp();
      el("bigscreen").click(); out.layout.push(layoutCheck("edit+big")); el("bigscreen").click();
      S.speed = "instant"; await setMode("watch"); if (S.loop) await S.loop;
      out.layout.push(layoutCheck("watch"));
      const d = out.steps.demo;
      out.ok = d.stages_done === 9 && d.qc_passed && d.consistency_score === 1 && out.steps.warn_case.compliance === "warn" &&
               out.steps.import.ok && out.steps.import.qc && out.steps.reel.shots > 0 && out.layout.every(l => l.ok);
    } catch (e) { errors.push("selftest exception: " + (e && e.stack || e)); }
    out.ms = Math.round(performance.now() - t0);
    out.ok = out.ok && errors.length === 0;
    el("selftest").textContent = JSON.stringify(out);
    document.title = out.ok ? "SELFTEST PASS" : "SELFTEST FAIL";
  }
  async function shot(kind) {
    await setMode("edit");
    el("idea").value = SAMPLES[0]; el("seed").value = 20260529; newRun();
    if (kind === "mid") {                     // 跑到分镜，停在中途：流程图半亮、共享状态正在长
      for (let i = 0; i < 5; i++) doStage();
      S.view = "storyboard"; S.openKeys = new Set(["storyboard"]); renderAll(); setRTab("state");
      return;
    }
    await runInstant();
    if (kind === "director") { S.view = "director"; renderAll(); setRTab("cost"); }
    else if (kind === "art") { S.matrixSel = "S03"; S.view = "art"; renderAll(); setRTab("matrix"); }
    else { S.view = "compose"; renderAll(); setRTab("matrix"); if (S.reel) S.reel.drawAt(7); }
  }

  /* =====================================================================
   * 启动
   * ===================================================================== */
  async function boot() {
    el("app-name").textContent = N.APP_NAME; el("app-tagline").textContent = N.TAGLINE; document.title = N.APP_NAME;
    fillFooter();
    el("idea-samples").innerHTML = `<option value="">示例创意…</option>` + SAMPLES.map((s, i) => `<option value="${i}">${esc(s)}</option>`).join("");
    el("idea-samples").addEventListener("change", e => { if (e.target.value !== "") { el("idea").value = SAMPLES[+e.target.value]; e.target.value = ""; } }, ON);
    el("idea").value = SAMPLES[0]; el("seed").value = 20260529;
    el("from-stage").innerHTML = P.STAGES.map(([k, n], i) => `<option value="${k}">${i + 1}. ${n}</option>`).join("");
    el("from-stage").value = "storyboard";
    buildSeg("speed-presets", SPEEDS, S.speed, k => { S.speed = k; });
    buildSeg("cost-presets", COST_PRESETS, S.cost, k => {
      S.cost = k;
      if (S.run) { const fresh = applyCostPreset(P.defaultConfig(), k); for (const sec of ["llm", "image", "cost", "dispatch"]) S.run.config[sec] = fresh[sec]; }
      setRTab("cost");
    });
    document.querySelectorAll("#modes button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode), ON));
    document.querySelectorAll("[data-rtab]").forEach(b => b.addEventListener("click", () => setRTab(b.dataset.rtab), ON));
    el("btn-run").addEventListener("click", () => { ensureRun(); if (!nextStage()) newRun(); runLoop(); }, ON);
    el("btn-step").addEventListener("click", () => { ensureRun(); if (!nextStage()) newRun(); doStage(); }, ON);
    el("btn-pause").addEventListener("click", () => { S.paused = !S.paused; setButtons(true); }, ON);
    el("btn-rerun").addEventListener("click", () => rerunFrom(el("from-stage").value), ON);
    el("btn-reset").addEventListener("click", () => { stopLoop(); newRun(); el("cap-title").textContent = "已清空"; el("cap-text").textContent = ""; }, ON);
    el("btn-export").addEventListener("click", exportAll, ON);
    el("btn-import").addEventListener("click", () => {
      if (confirm("从文件导入 3D 导演台导出的 JSON？\n选“取消”则使用内置的示例导出（tools/sample_director_export.json）。")) el("file-import").click();
      else importStoryboard(window.SAMPLE_DIRECTOR_EXPORT, "示例导出");
    }, ON);
    el("file-import").addEventListener("change", async e => {
      const f = e.target.files[0]; e.target.value = "";
      if (!f) return;
      try { importStoryboard(JSON.parse(await f.text()), f.name); } catch (err) { toast("不是有效的 JSON：" + err.message, true); }
    }, ON);
    el("help-btn").addEventListener("click", openHelp, ON);
    el("help-close").addEventListener("click", closeHelp, ON);
    el("exit-btn").addEventListener("click", exitApp, ON);
    el("bigscreen").addEventListener("change", e => document.body.classList.toggle("big", e.target.checked), ON);
    setupMobile();
    document.addEventListener("keydown", e => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) || e.ctrlKey || e.metaKey) return;
      if (e.code === "KeyH") { e.preventDefault(); el("dlg-help").classList.contains("show") ? closeHelp() : openHelp(); }
      if (e.code === "Escape") closeHelp();
    }, ON);

    // 验收脚本用的只读句柄（tools/mobile_check_cap.py、tools/browser_check.py）
    window.__cap = { S, setMode, ready: false };
    if (QS.has("selftest")) return selftest();
    if (QS.has("shot")) { await shot(QS.get("shot")); window.__cap.ready = true; return; }
    let seen = false;
    try { seen = localStorage.getItem(HELP_KEY) === "1"; } catch (e) { /* 忽略 */ }
    await setMode("watch");
    if (!seen && !QS.has("nohelp")) openHelp();
    window.__cap.ready = true;
  }
  boot();
})();
