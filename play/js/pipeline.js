/* =====================================================================
 * pipeline.js —— 9 个 Agent 的工作流引擎 + 非 LLM 阶段的逐行 JS 移植
 *   engine.py（共享 State / 检查点 / 单步重跑）、director.py（导演台几何）、agents/art.py、
 *   agents/compose.py + postprod.py（非绘图部分）、agents/qc.py、genlog.py、costing.py、
 *   dispatch.py、assets.py（资产库索引）、director_import.py（导入 3D 导演台导出的镜头）
 *
 * 与 Python 的约定：文件路径一律写成“项目目录内的相对路径”（assets/shots/S01.png），
 * Python 侧比对时把绝对路径前缀去掉、反斜杠换成 / 后应逐字段相同。时间戳不比对。
 * 图片、俯视图、草样片、配音在浏览器里由 render.js 用 canvas / WebAudio 现场画出来。
 * ===================================================================== */
(function (root) {
  "use strict";
  const { md5Hex, pyRound, pyFixed, pyFloat, pyMod, cpLen, cpSlice, pyIsSpace, pyFirstNumber } = root.PyRT;

  /* ------------------------------------------------------------------ 配置（与 config.py 的 dataclass 默认值一致） */
  function defaultConfig() {
    return {
      mode: "mock", seed: 20260529,
      llm: { model: "text-llm-example", price_input_per_mtok_usd: 0.14, price_input_cached_per_mtok_usd: 0.0028,
             price_output_per_mtok_usd: 0.28 },
      image: { size: [768, 1024], model: "image-cheap-example", price_per_image_usd: 0.1 },
      compose: { aspect_ratio: "9:16", fps: 25, reel_max_shots: 8, reel_width: 360,
                 bgm_note: "MVP 占位：阶段二接入情绪匹配 BGM（需求文档 4.7）" },
      cost: { video_per_second_usd: 0.10, tts_per_1k_chars_usd: 0.15 },
      dispatch: { image_model_strong: "image-strong-example", image_model_cheap: "image-cheap-example",
                  video_model_real: "video-real-example", video_placeholder: "storyboard-image", key_shot_max: 2 },
    };
  }

  const STAGES = [
    ["idea", "选题 Agent"], ["script", "编剧 Agent"], ["review", "审稿与合规 Agent"],
    ["characters", "角色设定 Agent"], ["storyboard", "分镜 Agent"], ["director", "导演台 Agent"],
    ["art", "美术 Agent"], ["compose", "合成/后期 Agent"], ["qc", "质检 Agent"],
  ];
  const STAGE_KEYS = STAGES.map(s => s[0]);
  const deriveSeed = (base, key) => pyMod(base + parseInt(md5Hex(key).slice(0, 8), 16), 2 ** 31);

  function nowIso() {
    const d = new Date(), p = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  /* ------------------------------------------------------------------ 共享状态 */
  function newState(ideaText, projectId, createdAt) {
    const st = { project_id: projectId, idea_text: ideaText, created_at: createdAt || nowIso() };
    for (const k of STAGE_KEYS) st[k] = null;
    return st;
  }
  function resetFrom(state, key) {
    const i = STAGE_KEYS.indexOf(key);
    if (i < 0) throw new Error(`未知阶段 ${key}`);
    for (const k of STAGE_KEYS.slice(i)) state[k] = null;
  }
  const clone = o => JSON.parse(JSON.stringify(o));

  /* ------------------------------------------------------------------ 生成日志（genlog.py） */
  class GenerationLog {
    constructor() { this.records = []; this._counter = 0; }
    _nextId() { this._counter++; return `GEN_${String(this._counter).padStart(4, "0")}`; }
    _rec(o) {
      return Object.assign({ id: this._nextId(), stage: "", gen_type: "", model: "", timestamp: nowIso(),
        prompt: "", reference_images: [], params: {}, input_tokens: 0, output_tokens: 0, cost_usd: 0.0,
        score: null, adopted: true, failure_reason: "", modification_reason: "" }, o);
    }
    logLlm(stage, r) {
      this.records.push(this._rec({ stage, gen_type: "llm", model: r.model, prompt: r.prompt, params: r.params,
        input_tokens: r.input_tokens, output_tokens: r.output_tokens, cost_usd: r.cost_usd }));
    }
    logImage(stage, r) {
      this.records.push(this._rec({ stage, gen_type: "image", model: r.model, prompt: r.prompt,
        reference_images: r.reference_image ? [r.reference_image] : [],
        params: { seed: r.seed, negative_prompt: r.negative_prompt }, cost_usd: r.cost_usd }));
    }
    logMedia(stage, genType, model, { prompt = "", params = null, cost_usd = 0.0 } = {}) {
      this.records.push(this._rec({ stage, gen_type: genType, model, prompt, params: params || {}, cost_usd }));
    }
    summary() {
      const R = this.records, cnt = t => R.filter(r => r.gen_type === t).length;
      return {
        total_generations: R.length, llm_calls: cnt("llm"), image_calls: cnt("image"), audio_calls: cnt("audio"),
        video_calls: cnt("video"),
        total_input_tokens: R.reduce((a, r) => a + r.input_tokens, 0),
        total_output_tokens: R.reduce((a, r) => a + r.output_tokens, 0),
        total_cost_usd: pyRound(R.reduce((a, r) => a + r.cost_usd, 0), 6),
        failures: R.filter(r => r.failure_reason).length,
      };
    }
  }

  /* ------------------------------------------------------------------ 占位图生成器（只记“生成了什么”，画图在 render.js） */
  const PLACEHOLDER_MODEL = "placeholder-offline";
  function placeholderGenerate({ prompt, negative_prompt, seed, reference_image, out_path, label }, ctx) {
    ctx.images[out_path] = { prompt, negative_prompt, seed, reference_image, label, kind: "card" };
    return { image_path: out_path, seed, prompt, negative_prompt, reference_image, model: PLACEHOLDER_MODEL, cost_usd: 0.0 };
  }

  /* ------------------------------------------------------------------ 导演台（director.py） */
  const DEPTH = { "特写": 0.28, "大特写": 0.24, "近景": 0.38, "中近景": 0.46, "中景": 0.56, "中远景": 0.64,
                  "远景": 0.74, "全景": 0.78 };
  const X_LAYOUT = { 1: [0.5], 2: [0.36, 0.64], 3: [0.27, 0.5, 0.73], 4: [0.22, 0.41, 0.59, 0.78] };

  function computeBlocking(shot) {
    const ids = shot.characters.slice();
    const n = Math.max(1, ids.length);
    const depth = Object.prototype.hasOwnProperty.call(DEPTH, shot.camera.shot_size) ? DEPTH[shot.camera.shot_size] : 0.52;
    const xs = X_LAYOUT[n] || Array.from({ length: n }, (_, i) => 0.18 + 0.64 * i / Math.max(1, n - 1));
    const facings = ["朝向镜头", "侧身对峙", "侧身", "背向镜头"];
    const actors = ids.map((cid, i) => {
      const y = Math.min(0.9, Math.max(0.12, depth + (i % 2 ? 0.06 : -0.04) * (Math.floor(i / 2) + 1)));
      return { character_id: cid, x: pyRound(xs[i % xs.length], 3), y: pyRound(y, 3),
               facing: i < facings.length ? facings[i] : "侧身" };
    });
    const angle = shot.camera.angle;
    let camHeight, camY;
    if (angle.includes("低") || angle.includes("仰")) { camHeight = "仰拍(低机位)"; camY = -0.12; }
    else if (angle.includes("俯") || angle.includes("高")) { camHeight = "俯拍(高机位)"; camY = -0.05; }
    else { camHeight = "平视"; camY = -0.08; }
    let camX = 0.5;
    if (angle.includes("侧后")) { camX = 0.80; camHeight = camHeight + "·侧后方"; }
    else if (angle.includes("侧")) camX = 0.30;
    const ss = shot.camera.shot_size;
    let focal;
    if (["特写", "大特写", "近景"].includes(ss)) focal = "长焦/大光圈，浅景深虚化背景，突出主体";
    else if (["远景", "全景", "中远景"].includes(ss)) focal = "广角、大景深，交代环境与空间关系";
    else focal = "标准镜头，主体与环境兼顾";
    let framing;
    if (n === 1) {
      const num = parseInt(shot.shot_id.slice(1) || "0", 10);
      const third = (num % 2 === 0) ? "右三分线" : "左三分线";
      framing = `主体置于${third}，视线留白；竖屏 9:16，关键信息避开上下 10% 安全框`;
    } else framing = "双主体分置左右三分线，视线于画面中部交汇；竖屏 9:16 安全框，避免角色压边";
    const key = shot.lighting.key_light;
    const side = key.includes("顶") ? "顶部" : (key.includes("右") ? "右前方" : "左前方");
    const lightDir = `${side}${key}（主），${shot.lighting.rim_light}（轮廓），强度${shot.lighting.intensity}`;
    return { camera_x: camX, camera_y: camY, camera_height: camHeight, focal_hint: focal, framing,
             light_direction: lightDir, actors };
  }
  function refinePrompts(shot, blk) {
    const clause = `；【导演台】机位:${blk.camera_height}；构图:${blk.framing}；` +
                   `灯光:${blk.light_direction}；镜头:${blk.focal_hint}`;
    return [shot.image_prompt + clause,
            shot.video_prompt + `；机位${blk.camera_height}，运镜${shot.camera.movement}，保持构图与灯光一致`];
  }

  /* ------------------------------------------------------------------ 后期（postprod.py 的非绘图部分） */
  function estimateSpeechSeconds(text, maxSeconds = 8.0) {
    const n = Array.from(text).filter(c => !pyIsSpace(c)).length;
    return Math.max(0.6, Math.min(maxSeconds, pyRound(n / 4.5 + 0.4, 2)));
  }
  /* write_voice_wav 只算时长；声音由 render.js 用 WebAudio 按同一公式合成 */
  function voiceSeconds(seconds, rate = 16000) {
    const n = Math.max(1, Math.trunc(seconds * rate));
    return pyRound(n / rate, 3);
  }
  const pitchFor = speaker => 150.0 + (parseInt(md5Hex(speaker).slice(0, 6), 16) % 70);

  /* ------------------------------------------------------------------ 9 个阶段 */
  const QC_ANTI_DRIFT = ["漂移", "发色", "瞳色", "服装", "一致", "畸形"];

  const RUNNERS = {
    _llm(stageKey, state, ctx) {
      const ag = root.LLM_AGENTS[stageKey];
      const [system, user, context] = ag.prompt(state);
      const res = ctx.llm.generate({ task: ag.task, system, user, context: clone(context) });
      ctx.genlog.logLlm(stageKey, res);
      state[stageKey] = res.output;
      return res;
    },
    idea: (s, c) => RUNNERS._llm("idea", s, c),
    script: (s, c) => RUNNERS._llm("script", s, c),
    review: (s, c) => RUNNERS._llm("review", s, c),
    characters: (s, c) => RUNNERS._llm("characters", s, c),
    storyboard: (s, c) => RUNNERS._llm("storyboard", s, c),

    director(state, ctx) {
      const dshots = [];
      for (const shot of state.storyboard.shots) {
        const blk = computeBlocking(shot);
        const diagram = `assets/director/${shot.shot_id}.png`;
        ctx.images[diagram] = { kind: "diagram", shot_id: shot.shot_id, blk, base_seed: ctx.config.seed };
        const [imgP, vidP] = refinePrompts(shot, blk);
        shot.image_prompt = imgP;           // 就地增强分镜提示词
        shot.video_prompt = vidP;
        dshots.push({
          shot_id: shot.shot_id, camera_x: blk.camera_x, camera_y: blk.camera_y, camera_height: blk.camera_height,
          focal_hint: blk.focal_hint, framing: blk.framing, light_direction: blk.light_direction,
          actors: blk.actors, blocking_diagram: diagram, refined_image_prompt: imgP, refined_video_prompt: vidP,
          notes: "2D 俯视预演（确定性规则）；可拖拽 3D 导演台为第三阶段。",
        });
        ctx.genlog.logMedia("director/blocking", "diagram", "director-board-offline", {
          prompt: `${shot.shot_id} 机位:${blk.camera_height} 构图:${cpSlice(blk.framing, 0, 20)}`,
          params: { shot_id: shot.shot_id, actors: blk.actors.length } });
      }
      state.director = {
        shots: dshots,
        note: "导演台从分镜算出可控镜头参数（角色站位/机位高度/摄像机位置/灯光方位/三分法构图），" +
              "渲染俯视构图图，并把镜头语言翻译进精炼提示词后交美术出图。" +
              "俯视图角色配色与其分镜图主色调一致，把导演台与美术打通。",
      };
    },

    art(state, ctx) {
      const base = ctx.config.seed;
      const seedMap = {}, refMap = {}, charRefs = [];
      for (const c of state.characters.characters) {
        const seed = deriveSeed(base, c.character_id);
        seedMap[c.character_id] = seed;
        const prompt = `角色三视图参考图：${c.name}，${c.age}岁，${c.identity}；` +
          `固定外貌：${c.fixed_visual_features.join("、")}；漫剧风格，正面/侧面/背面，中性表情，纯色背景`;
        const neg = c.forbidden_changes.join("、") + ",不要多人,不要文字水印";
        const res = placeholderGenerate({ prompt, negative_prompt: neg, seed, reference_image: null,
          out_path: `assets/characters/${c.character_id}_reference.png`, label: `${c.character_id} ${c.name} · 参考图` }, ctx);
        c.reference_image = res.image_path;
        c.reference_seed = seed;
        refMap[c.character_id] = res.image_path;
        ctx.genlog.logImage("art/character_reference", res);
        charRefs.push({ asset_type: "character_reference", ref_id: c.character_id, image_path: res.image_path,
          seed, reference_image: null, prompt, negative_prompt: neg, model: res.model, cost_usd: res.cost_usd });
      }
      const shotAssets = [];
      for (const shot of state.storyboard.shots) {
        let seed, refImg;
        if (shot.characters.length) {
          const anchor = shot.characters[0];
          seed = Object.prototype.hasOwnProperty.call(seedMap, anchor) ? seedMap[anchor] : deriveSeed(base, shot.shot_id);
          refImg = Object.prototype.hasOwnProperty.call(refMap, anchor) ? refMap[anchor] : null;
        } else { seed = deriveSeed(base, shot.shot_id); refImg = null; }
        const res = placeholderGenerate({ prompt: shot.image_prompt, negative_prompt: shot.negative_prompt, seed,
          reference_image: refImg, out_path: `assets/shots/${shot.shot_id}.png`, label: `${shot.shot_id} · ${shot.scene}` }, ctx);
        ctx.genlog.logImage("art/shot", res);
        shotAssets.push({ asset_type: "shot", ref_id: shot.shot_id, image_path: res.image_path, seed,
          reference_image: refImg, prompt: shot.image_prompt, negative_prompt: shot.negative_prompt,
          model: res.model, cost_usd: res.cost_usd });
      }
      state.art = {
        character_references: charRefs, shot_images: shotAssets,
        consistency_note: "每个角色锁定专属 seed + 参考图；分镜以首位出场角色为锚点复用其 seed 与参考图，" +
          "配合 image_prompt 中的 fixed_visual_features 与 negative_prompt 中的 forbidden_changes，" +
          "形成『视觉锚点 + 提示词约束』双重一致性保障。同 seed 在离线占位图中呈现相同主色调，可直观比对一致性。",
      };
    },

    compose(state, ctx) {
      const cc = ctx.config.compose;
      const voiceByName = {}, voiceById = {};
      for (const c of state.characters.characters) { voiceByName[c.name] = c.voice_profile; voiceById[c.character_id] = c.voice_profile; }
      const shotImg = {};
      if (state.art) for (const a of state.art.shot_images) shotImg[a.ref_id] = a.image_path;
      const audioClips = [], videoClips = [], reelInputs = [];
      let cursor = 0.0;
      for (const sh of state.storyboard.shots) {
        const dur = pyFirstNumber(sh.duration, 5.0);
        let speaker, text;
        if (sh.dialogue && sh.dialogue.includes("：")) {
          const i = sh.dialogue.indexOf("：");
          speaker = sh.dialogue.slice(0, i); text = sh.dialogue.slice(i + 1);
        } else if (sh.dialogue) { speaker = "旁白"; text = sh.dialogue; }
        else { speaker = "旁白"; text = sh.action || sh.scene; }
        const get = (o, k) => (Object.prototype.hasOwnProperty.call(o, k) ? o[k] : null);
        const voice = get(voiceByName, speaker) || (sh.characters.length ? get(voiceById, sh.characters[0]) : null) || "中性解说、语速中等";
        const spoken = Math.min(estimateSpeechSeconds(text), dur);
        const wav = `assets/audio/${sh.shot_id}.wav`;
        const real = voiceSeconds(spoken);
        ctx.audio[wav] = { seconds: real, pitch_hz: pitchFor(speaker), speaker, text };
        audioClips.push({ shot_id: sh.shot_id, speaker, text, voice_profile: voice, audio_path: wav,
                          duration_seconds: real, model: "mock-tts-offline" });
        ctx.genlog.logMedia("compose/voice", "audio", "mock-tts-offline",
          { prompt: `${speaker}（${voice}）：${text}`, params: { shot_id: sh.shot_id, seconds: real } });
        const subtitle = sh.dialogue || sh.action;
        const img = Object.prototype.hasOwnProperty.call(shotImg, sh.shot_id) ? shotImg[sh.shot_id] : null;
        videoClips.push({ shot_id: sh.shot_id, scene: sh.scene, image_path: img, audio_path: wav, subtitle,
                          start_seconds: pyRound(cursor, 2), duration_seconds: dur, transition: "硬切" });
        reelInputs.push({ shot_id: sh.shot_id, scene: sh.scene, image_path: img, subtitle, duration_seconds: dur });
        cursor += dur;
      }
      const total = pyRound(cursor, 2);
      const timeline = { aspect_ratio: cc.aspect_ratio, fps: cc.fps, bgm: cc.bgm_note,
                         total_duration_seconds: total, clips: videoClips };
      const reelShots = reelInputs.slice(0, cc.reel_max_shots);
      const truncated = reelInputs.length - reelShots.length;
      const ok = reelShots.length > 0;      // 浏览器里草样片是 canvas 轮播，有镜头就能播
      ctx.reel = { shots: reelShots, canvas: [cc.reel_width, Math.round(cc.reel_width * 16 / 9)] };
      if (ok) ctx.genlog.logMedia("compose/reel", "video", "pillow-gif-offline",
        { prompt: "草样片故事板卷（占位）", params: { shots: reelShots.length, seconds: total } });
      const note = `离线合成：${audioClips.length} 段占位配音 + 草样片 GIF（${reelShots.length} 镜）` +
        (truncated ? `，已截断 ${truncated} 镜` : "") + "；" +
        "并产出剪辑时间线与 FFmpeg 成片脚本。真实视频/配音在阶段二替换占位实现。";
      state.compose = { timeline, audio_clips: audioClips, reel_path: ok ? "preview.gif" : null,
        assemble_script: "assemble.ps1", shots_total: reelInputs.length, shots_in_reel: reelShots.length,
        note, model: "offline-postprod" };
    },

    qc(state, ctx) {
      const chars = state.characters ? state.characters.characters : [];
      const shots = state.storyboard ? state.storyboard.shots : [];
      const seedById = {}, refById = {}, fixedById = {};
      for (const c of chars) { seedById[c.character_id] = c.reference_seed; refById[c.character_id] = c.reference_image;
                               fixedById[c.character_id] = c.fixed_visual_features; }
      const validIds = new Set(Object.keys(seedById));
      const shotAsset = {};
      if (state.art) for (const a of state.art.shot_images) shotAsset[a.ref_id] = a;
      const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
      let issues = [];
      const metrics = [];
      const matrix = [];                    // 页面用：每镜 4 项检查（Python 不输出这个）

      // 1) 角色一致性
      const ratios = [], consIssues = [];
      for (const sh of shots) {
        if (!sh.characters.length) continue;
        const anchor = sh.characters[0];
        const asset = has(shotAsset, sh.shot_id) ? shotAsset[sh.shot_id] : null;
        const checks = [
          ["seed复用", !!(asset && asset.seed === (has(seedById, anchor) ? seedById[anchor] : null))],
          ["参考图复用", !!(asset && asset.reference_image === (has(refById, anchor) ? refById[anchor] : null))],
          ["固定特征入image_prompt", (has(fixedById, anchor) ? fixedById[anchor] : []).some(f => (sh.image_prompt || "").includes(f))],
          ["负面词抑制漂移", !!sh.negative_prompt && QC_ANTI_DRIFT.some(k => sh.negative_prompt.includes(k))],
        ];
        const passed = checks.filter(c => c[1]).length;
        ratios.push(passed / checks.length);
        matrix.push({ shot_id: sh.shot_id, anchor, checks: checks.map(([n, v]) => ({ name: n, ok: v })) });
        for (const [name, okk] of checks) if (!okk) consIssues.push(`${sh.shot_id}: 未满足『${name}』`);
      }
      const consistency = ratios.length ? pyRound(ratios.reduce((a, b) => a + b, 0) / ratios.length, 3) : 1.0;
      metrics.push({ dimension: "人物一致性", score: pyRound(consistency * 10, 1),
        detail: `对 ${ratios.length} 个有角色的镜头做 4 项一致性检查（seed/参考图复用 + 提示词双侧约束）`,
        issues: consIssues.slice(0, 12) });
      issues = issues.concat(consIssues.slice(0, 6));

      // 2) 结构完整性
      const structChecks = [], structIssues = [];
      for (const sh of shots) for (const cid of sh.characters) {
        const ok = validIds.has(cid);
        structChecks.push(ok);
        if (!ok) structIssues.push(`${sh.shot_id}: 引用了不存在的 character_id ${cid}`);
      }
      const appeared = new Set(shots.flatMap(sh => sh.characters));
      for (const c of chars) {
        const ok = appeared.has(c.character_id);
        structChecks.push(ok);
        if (!ok) structIssues.push(`角色 ${c.character_id} ${c.name} 未出现在任何镜头`);
      }
      for (const sh of shots) {
        const asset = has(shotAsset, sh.shot_id) ? shotAsset[sh.shot_id] : null;
        const ok = !!(asset && has(ctx.images, asset.image_path));     // Python：Path(...).exists()
        structChecks.push(ok);
        if (!ok) structIssues.push(`${sh.shot_id}: 缺少分镜图文件`);
      }
      const structScore = structChecks.length ? 10.0 * (structChecks.filter(Boolean).length / structChecks.length) : 10.0;
      metrics.push({ dimension: "结构完整性", score: pyRound(structScore, 1),
        detail: "校验 character_id 引用合法、角色均有出镜、每镜分镜图已落盘", issues: structIssues.slice(0, 12) });
      issues = issues.concat(structIssues.slice(0, 6));

      // 3) 镜头连贯性
      const contIssues = [];
      if (!shots.every((sh, i) => sh.shot_id === `S${String(i + 1).padStart(2, "0")}`)) contIssues.push("镜头编号非连续 S01..SNN");
      const emptyScene = shots.filter(sh => !sh.scene).map(sh => sh.shot_id);
      if (emptyScene.length) contIssues.push(`以下镜头缺少场景：${root.PyRT.pyReprList(emptyScene)}`);
      metrics.push({ dimension: "镜头连贯性", score: pyRound(Math.max(0.0, 10.0 - 2.0 * contIssues.length), 1),
        detail: "检查镜号连续性与场景完整性（成片级连贯性需视频阶段再评）", issues: contIssues });

      // 4) 音画同步
      if (state.compose) {
        const clips = state.compose.timeline.clips;
        const audioByShot = {};
        for (const a of state.compose.audio_clips) audioByShot[a.shot_id] = a;
        let fit = 0;
        const syncIssues = [];
        for (const cl of clips) {
          const a = audioByShot[cl.shot_id];
          if (a && a.duration_seconds <= cl.duration_seconds + 0.01) fit++;
          else syncIssues.push(`${cl.shot_id}: 配音时长超出镜头时长或缺失`);
        }
        const syncScore = clips.length ? 10.0 * (fit / clips.length) : 0.0;
        metrics.push({ dimension: "音画同步", score: pyRound(syncScore, 1),
          detail: `${fit}/${clips.length} 镜配音时长落在镜头时长内（占位音轨，真实口型对齐待阶段二）`,
          issues: syncIssues.slice(0, 8) });
      } else metrics.push({ dimension: "音画同步", score: 0.0, detail: "未运行合成阶段", issues: ["缺少 compose 产出"] });

      // 5) 成片可用率
      const target = state.script ? state.script.target_duration_seconds : 45;
      const total = state.compose ? state.compose.timeline.total_duration_seconds : 0.0;
      const ratio = target ? total / target : 0.0;
      const durScore = Math.max(0.0, 10.0 - Math.abs(1.0 - ratio) * 12.0);
      const durIssues = (ratio >= 0.7 && ratio <= 1.3) ? [] :
        [`成片时长 ${pyFloat(total)}s 与目标 ${target}s 偏差较大（${pyFixed(ratio, 2)}x）`];
      metrics.push({ dimension: "成片可用率", score: pyRound(Math.min(10.0, durScore), 1),
        detail: `草样片总时长 ${pyFloat(total)}s vs 目标 ${target}s`, issues: durIssues });

      // 6) 平台适配度
      const aspect = state.compose ? state.compose.timeline.aspect_ratio : "?";
      const platOk = aspect === "9:16" && total <= 90;
      metrics.push({ dimension: "平台适配度", score: platOk ? 10.0 : 6.0,
        detail: `画幅 ${aspect}，时长 ${pyFloat(total)}s（竖屏短视频偏好 9:16 且 ≤90s）`,
        issues: platOk ? [] : ["画幅或时长不完全契合竖屏短视频"] });

      const overall = pyRound(metrics.reduce((a, m) => a + m.score, 0) / metrics.length, 2);
      const passed = consistency >= 0.8 && !structIssues.length;
      state.qc = { consistency_score: consistency, metrics, overall_score: overall, passed, issues: issues.slice(0, 12),
        note: "确定性质检（非 LLM）：角色一致性=每镜 seed/参考图复用 + 提示词双侧约束的达成率；" +
              "另含结构完整性/镜头连贯性/音画同步/时长与平台适配。真实画面级一致性(人脸相似度)待阶段二接检测模型。" };
      ctx.qcMatrix = matrix;
    },
  };

  /* ------------------------------------------------------------------ 工作流 */
  function makeContext(config) {
    return { config, llm: new root.MockLLM(config.seed), genlog: new GenerationLog(), images: {}, audio: {},
             reel: null, qcMatrix: [] };
  }
  /* 跑一个阶段（已完成的跳过），返回是否真的执行了 */
  function runStage(state, ctx, key) {
    if (state[key] !== null) return false;
    RUNNERS[key](state, ctx);
    if (state[key] === null) throw new Error(`节点 ${key} 运行后未写入产物`);
    return true;
  }
  function runAll(state, ctx, startFrom) {
    if (startFrom) resetFrom(state, startFrom);
    for (const k of STAGE_KEYS) runStage(state, ctx, k);
    return state;
  }

  /* ------------------------------------------------------------------ 成本（costing.py） */
  function estimateCost(state, genlog, config) {
    const llm = config.llm, f = pyFloat;
    const inTok = genlog.records.reduce((a, r) => a + r.input_tokens, 0);
    const outTok = genlog.records.reduce((a, r) => a + r.output_tokens, 0);
    const llmUsd = inTok / 1000000 * llm.price_input_per_mtok_usd + outTok / 1000000 * llm.price_output_per_mtok_usd;
    const nImg = state.art ? state.art.character_references.length + state.art.shot_images.length : 0;
    const imgUsd = nImg * config.image.price_per_image_usd;
    let totalSec = 0.0, nShots = 0;
    if (state.storyboard) {
      nShots = state.storyboard.shots.length;
      totalSec = state.storyboard.shots.reduce((a, s) => a + pyFirstNumber(s.duration, 5.0), 0);
    }
    const videoUsd = totalSec * config.cost.video_per_second_usd;
    let nChars = 0;
    if (state.compose) nChars = state.compose.audio_clips.reduce((a, c) => a + cpLen(c.text), 0);
    else if (state.storyboard) nChars = state.storyboard.shots.reduce((a, s) => a + cpLen(s.dialogue), 0);
    const ttsUsd = nChars / 1000 * config.cost.tts_per_1k_chars_usd;
    const lines = [
      { category: "文本生成(LLM)", quantity: `${inTok}+${outTok} tokens`,
        unit_price: `$${f(llm.price_input_per_mtok_usd)}/${f(llm.price_output_per_mtok_usd)} 每百万(入/出)`,
        estimated_usd: pyRound(llmUsd, 6), note: "命中缓存可再降一个量级；可用更便宜模型做初稿、强模型只做审稿" },
      { category: "图像生成(分镜图+参考图)", quantity: `${nImg} 张`, unit_price: `$${f(config.image.price_per_image_usd)}/张`,
        estimated_usd: pyRound(imgUsd, 6), note: "先低分辨率出草图、定稿再高清；批量复用角色参考图" },
      { category: "视频生成", quantity: `${nShots} 镜 / 约 ${pyFixed(totalSec, 0)}s`,
        unit_price: `$${f(config.cost.video_per_second_usd)}/秒`, estimated_usd: pyRound(videoUsd, 6),
        note: "视频最贵；可只对关键镜出真实视频，其余用分镜图+轻动效（先低分辨率出片再转码，可进一步降本）" },
      { category: "配音(TTS)", quantity: `约 ${nChars} 字`, unit_price: `$${f(config.cost.tts_per_1k_chars_usd)}/千字`,
        estimated_usd: pyRound(ttsUsd, 6), note: "本地开源 TTS 可做到 ~0 成本" },
    ];
    return {
      actual_cost_usd: pyRound(genlog.records.reduce((a, r) => a + r.cost_usd, 0), 6),
      estimated_real_cost_usd: pyRound(llmUsd + imgUsd + videoUsd + ttsUsd, 4),
      lines,
      assumptions: [
        `LLM 单价取自 config.llm（${llm.model}）：入 $${f(llm.price_input_per_mtok_usd)}/出 $${f(llm.price_output_per_mtok_usd)} 每百万 token`,
        `图像 $${f(config.image.price_per_image_usd)}/张、视频 $${f(config.cost.video_per_second_usd)}/秒、TTS $${f(config.cost.tts_per_1k_chars_usd)}/千字（均为 2026-05 示意值）`,
        "以上为『若用真实云端模型生产本片』的估算；当前 mock 实跑成本为 $0。务必上线前核对各家真实定价。",
      ],
      saving_tips: [
        "视频是大头：只对关键镜生成真实视频，其余镜用分镜图 + 轻动效（草样片即此思路）。",
        "图像先低分辨率出草、定稿再高清；角色参考图跨镜复用，减少重复出图。",
        "LLM 善用 prompt 缓存与便宜模型分工（初稿便宜、审稿强模型），可显著降本。",
        "配音优先本地开源 TTS，接近零成本。",
      ],
    };
  }

  /* ------------------------------------------------------------------ 多模型调度（dispatch.py） */
  const HIGH_EMOTION = ["紧张", "对峙", "决", "高潮", "冲突", "危", "震撼", "爆发"];
  const CLOSE_SHOTS = ["特写", "近景"];
  function importance(shot, idx, total) {
    let s = 0;
    if (CLOSE_SHOTS.includes(shot.camera.shot_size)) s += 2;
    if (shot.characters.length >= 2) s += 1;
    if (HIGH_EMOTION.some(k => (shot.emotion || "").includes(k))) s += 1;
    if (idx === 0 || idx === total - 1) s += 1;
    return s;
  }
  function dispatchModels(state, config) {
    const dc = config.dispatch;
    const shots = state.storyboard ? state.storyboard.shots : [];
    const total = shots.length;
    const scored = shots.map((sh, i) => [i, sh, importance(sh, i, total)]);
    const order = scored.slice().sort((a, b) => (b[2] - a[2]) || (a[0] - b[0]));
    const realIds = new Set(order.slice(0, Math.max(0, dc.key_shot_max)).map(t => t[1].shot_id));
    const dshots = scored.map(([i, sh, imp]) => {
      const strong = imp >= 2, isReal = realIds.has(sh.shot_id);
      const reasons = [];
      if (CLOSE_SHOTS.includes(sh.camera.shot_size)) reasons.push("特写/近景需强一致性");
      if (sh.characters.length >= 2) reasons.push("多角色同框");
      if (HIGH_EMOTION.some(k => (sh.emotion || "").includes(k))) reasons.push("高情绪关键镜");
      if (i === 0 || i === total - 1) reasons.push("首/尾镜");
      if (!reasons.length) reasons.push("常规镜，走性价比方案");
      return { shot_id: sh.shot_id, importance: imp, image_model: strong ? dc.image_model_strong : dc.image_model_cheap,
               video_model: isReal ? dc.video_model_real : dc.video_placeholder, real_video: isReal,
               reason: reasons.join("；") + (isReal ? "｜真实视频" : "｜占位/图生视频") };
    });
    const price = config.cost.video_per_second_usd;
    const full = pyRound(shots.reduce((a, s) => a + pyFirstNumber(s.duration, 5.0), 0) * price, 4);
    const dispatched = pyRound(shots.filter(s => realIds.has(s.shot_id)).reduce((a, s) => a + pyFirstNumber(s.duration, 5.0), 0) * price, 4);
    return {
      shots: dshots, real_video_shots: realIds.size, placeholder_shots: total - realIds.size,
      full_video_cost_usd: full, dispatched_video_cost_usd: dispatched,
      note: `按规则把 ${total} 镜分流：${realIds.size} 个关键镜用真实视频(${dc.video_model_real})，` +
            `其余 ${total - realIds.size} 镜用占位/图生视频(${dc.video_placeholder})；` +
            `图像按重要度在 ${dc.image_model_strong}/${dc.image_model_cheap} 间择优。` +
            `视频成本由全量 $${pyFloat(full)} 降到 $${pyFloat(dispatched)}（省 $${pyFloat(pyRound(full - dispatched, 4))}）。` +
            "模型名均取自 config.dispatch，可随生态更新（需求文档 4.6：不绑死单一模型）。",
    };
  }

  /* ------------------------------------------------------------------ 资产库（assets.py 的 build_asset_library） */
  function buildAssetLibrary(state) {
    const lib = {
      project_id: state.project_id, created_at: state.created_at,
      character_assets: [], scene_assets: [],
      prop_assets: { items: [], note: "MVP 未生成；阶段二由分镜/资产管理补充" },
      storyboard_assets: [], director_assets: [],
      video_assets: { items: [], note: "草样片(GIF)与剪辑时间线已生成；真实视频(云端或本地视频模型)阶段二替换占位" },
      audio_assets: { items: [], note: "占位配音(.wav)已生成；真实配音(开源或云端 TTS)阶段二替换" },
      prompt_assets: [],
    };
    if (state.director) for (const ds of state.director.shots)
      lib.director_assets.push({ shot_id: ds.shot_id, blocking_diagram: ds.blocking_diagram,
        camera_height: ds.camera_height, framing: ds.framing, light_direction: ds.light_direction });
    if (state.compose) {
      if (state.compose.reel_path) lib.video_assets.items.push({ type: "reel_preview", path: state.compose.reel_path,
        total_duration_seconds: state.compose.timeline.total_duration_seconds, aspect_ratio: state.compose.timeline.aspect_ratio });
      for (const cl of state.compose.timeline.clips) lib.video_assets.items.push({ type: "clip", shot_id: cl.shot_id,
        image_path: cl.image_path, start: cl.start_seconds, duration: cl.duration_seconds });
      for (const a of state.compose.audio_clips) lib.audio_assets.items.push({ shot_id: a.shot_id, speaker: a.speaker,
        voice_profile: a.voice_profile, audio_path: a.audio_path, duration_seconds: a.duration_seconds });
    }
    if (state.characters) for (const c of state.characters.characters)
      lib.character_assets.push({ character_id: c.character_id, name: c.name, reference_image: c.reference_image,
        reference_seed: c.reference_seed, voice_profile: c.voice_profile, fixed_visual_features: c.fixed_visual_features,
        forbidden_changes: c.forbidden_changes });
    if (state.script) {
      const seen = new Set();
      for (const sc of state.script.scenes) if (!seen.has(sc.location)) {
        seen.add(sc.location); lib.scene_assets.push({ location: sc.location, first_seen_scene: sc.scene_id });
      }
    }
    const shotImg = {};
    if (state.art) for (const a of state.art.shot_images) shotImg[a.ref_id] = a.image_path;
    if (state.storyboard) for (const sh of state.storyboard.shots) {
      lib.storyboard_assets.push({ shot_id: sh.shot_id, scene: sh.scene, characters: sh.characters,
        image_path: Object.prototype.hasOwnProperty.call(shotImg, sh.shot_id) ? shotImg[sh.shot_id] : null, duration: sh.duration });
      lib.prompt_assets.push({ shot_id: sh.shot_id, image_prompt: sh.image_prompt, video_prompt: sh.video_prompt,
        negative_prompt: sh.negative_prompt });
    }
    return lib;
  }

  /* ------------------------------------------------------------------ 3D 导演台导出 → 分镜（director_import.py，按 Shot 结构严格校验） */
  const STR = v => typeof v === "string";
  function validateShot(s, i) {
    const where = `第 ${i + 1} 个镜头不符合 Shot 结构：`;
    if (!s || typeof s !== "object" || Array.isArray(s)) throw new Error(where + "不是对象");
    for (const k of ["shot_id", "scene", "action", "duration", "negative_prompt", "emotion", "image_prompt", "video_prompt"])
      if (!STR(s[k])) throw new Error(where + `字段 ${k} 缺失或不是字符串`);
    if (s.dialogue !== undefined && !STR(s.dialogue)) throw new Error(where + "字段 dialogue 不是字符串");
    if (!Array.isArray(s.characters) || !s.characters.every(STR)) throw new Error(where + "字段 characters 应为字符串列表");
    for (const [k, sub] of [["camera", ["shot_size", "angle", "movement"]], ["lighting", ["key_light", "rim_light", "intensity"]]]) {
      if (!s[k] || typeof s[k] !== "object") throw new Error(where + `字段 ${k} 缺失`);
      for (const kk of sub) if (!STR(s[k][kk])) throw new Error(where + `字段 ${k}.${kk} 缺失或不是字符串`);
    }
    return {
      shot_id: s.shot_id, scene: s.scene, characters: s.characters.slice(),
      camera: { shot_size: s.camera.shot_size, angle: s.camera.angle, movement: s.camera.movement },
      lighting: { key_light: s.lighting.key_light, rim_light: s.lighting.rim_light, intensity: s.lighting.intensity },
      action: s.action, duration: s.duration, negative_prompt: s.negative_prompt, emotion: s.emotion,
      dialogue: s.dialogue === undefined ? "" : s.dialogue, image_prompt: s.image_prompt, video_prompt: s.video_prompt,
    };
  }
  function loadStoryboard(data) {
    let raw;
    if (data && !Array.isArray(data) && typeof data === "object" && "shots" in data) raw = data.shots;
    else if (Array.isArray(data)) raw = data;
    else if (data && typeof data === "object") raw = [data];
    else throw new Error('无法识别的导出格式：应为 {"shots":[...]} / [shot,...] / 单个 shot 对象');
    if (!Array.isArray(raw) || !raw.length) throw new Error("导出文件中没有任何镜头");
    return { shots: raw.map(validateShot) };
  }
  function unknownCharacterIds(storyboard, knownIds) {
    const used = new Set(storyboard.shots.flatMap(sh => sh.characters));
    return [...used].filter(id => !knownIds.has(id)).sort();
  }

  root.Pipeline = { defaultConfig, STAGES, STAGE_KEYS, newState, resetFrom, makeContext, runStage, runAll,
    GenerationLog, computeBlocking, refinePrompts, estimateSpeechSeconds, voiceSeconds, pitchFor, deriveSeed,
    estimateCost, dispatchModels, buildAssetLibrary, loadStoryboard, unknownCharacterIds, importance };
})(typeof window !== "undefined" ? window : globalThis);
