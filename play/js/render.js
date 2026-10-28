/* =====================================================================
 * render.js —— Pillow / wave 产物的浏览器版
 *   drawCard      ← image/placeholder.py（占位分镜卡：同 seed → 同主色调，演示角色一致性）
 *   drawDiagram   ← director.py 的 render_blocking_diagram（导演台俯视构图图）
 *   ReelPlayer    ← postprod.py 的 build_reel_gif（草样片：分镜图 + 轻缩放 + 字幕，按时间线轮播）
 *   playVoice     ← postprod.py 的 write_voice_wav（极低音量正弦 + 首尾淡入淡出，WebAudio 合成）
 * 颜色公式与 Python 相同（md5(str(seed)) → 色相 → colorsys.hsv_to_rgb）。文字用系统字体，不随包分发字体。
 * ===================================================================== */
(function (root) {
  "use strict";
  const FONT = '"Microsoft YaHei","PingFang SC","Hiragino Sans GB","Noto Sans CJK SC",sans-serif';

  /* colorsys.hsv_to_rgb */
  function hsvToRgb(h, s, v) {
    if (s === 0) return [v, v, v];
    let i = Math.trunc(h * 6.0);
    const f = h * 6.0 - i, p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
    i = i % 6;
    return [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i];
  }
  function palette(seed) {
    const h = parseInt(root.PyRT.md5Hex(String(seed)).slice(0, 8), 16);
    const hue = (h % 360) / 360.0;
    const dark = hsvToRgb(hue, 0.55, 0.45).map(c => Math.trunc(c * 255));
    const light = hsvToRgb(hue, 0.30, 0.92).map(c => Math.trunc(c * 255));
    return { dark, light, darkCss: `rgb(${dark})`, lightCss: `rgb(${light})` };
  }
  /* _wrap_cjk：按码点数硬换行 */
  function wrapCjk(text, maxChars) {
    const lines = [];
    for (let raw of String(text).split("\n")) {
      let a = Array.from(raw);
      while (a.length > maxChars) { lines.push(a.slice(0, maxChars).join("")); a = a.slice(maxChars); }
      lines.push(a.join(""));
    }
    return lines;
  }
  const baseName = p => (p ? String(p).split(/[\\/]/).pop() : "");

  /* ---------------- 占位分镜卡（768×1024，与 Pillow 版布局一致） ---------------- */
  function drawCard(canvas, info, size) {
    const [w, h] = size || [768, 1024];
    canvas.width = w; canvas.height = h;
    const g = canvas.getContext("2d");
    const pal = palette(info.seed);
    g.fillStyle = pal.lightCss; g.fillRect(0, 0, w, h);
    g.fillStyle = pal.darkCss; g.fillRect(0, 0, w, 91);
    g.textBaseline = "top";
    g.fillStyle = "#fff"; g.font = `40px ${FONT}`; g.fillText(info.label || "", 24, 24, w - 48);
    const cx = Math.floor(w / 2), cy = 300, r = 130;
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fillStyle = pal.darkCss; g.fill();
    g.lineWidth = 6; g.strokeStyle = "#fff"; g.stroke();
    const inner = info.seed % 5;
    g.fillStyle = pal.lightCss; g.fillRect(cx - 50, cy - 20 - inner * 8, 100, 60 + inner * 16);
    g.lineWidth = 4; g.strokeStyle = pal.darkCss; g.strokeRect(cx - 50, cy - 20 - inner * 8, 100, 60 + inner * 16);
    let y = 470;
    g.fillStyle = pal.darkCss; g.font = `22px ${FONT}`; g.fillText("image_prompt:", 24, y);
    y += 32;
    g.fillStyle = "rgb(40,40,40)"; g.font = `18px ${FONT}`;
    for (const line of wrapCjk(info.prompt || "", Math.max(10, Math.floor(w / 24))).slice(0, 9)) { g.fillText(line, 24, y); y += 26; }
    y = h - 200;
    g.strokeStyle = pal.darkCss; g.lineWidth = 2; g.beginPath(); g.moveTo(24, y - 12); g.lineTo(w - 24, y - 12); g.stroke();
    const meta = [`SEED（锁定）：${info.seed}`,
      `参考图（保身份）：${info.reference_image ? baseName(info.reference_image) : "无（首图/参考基准）"}`,
      `negative：${root.PyRT.cpSlice(info.negative_prompt || "", 0, 40)}`,
      "离线占位图 · 非真实绘画 · 同 seed → 同主色调，演示角色一致性"];
    g.fillStyle = "rgb(70,70,70)";
    for (const line of meta) for (const sub of wrapCjk(line, Math.max(10, Math.floor(w / 20)))) { g.fillText(sub, 24, y); y += 24; }
    return canvas;
  }

  /* ---------------- 导演台俯视构图图（640×430） ---------------- */
  function drawDiagram(canvas, shotId, blk, baseSeed) {
    const W = 640, H = 430;
    canvas.width = W; canvas.height = H;
    const d = canvas.getContext("2d");
    d.fillStyle = "rgb(16,20,26)"; d.fillRect(0, 0, W, H);
    const L = 40, R = W - 40, T = 56, B = H - 90;
    d.fillStyle = "rgb(26,32,40)"; d.fillRect(L, T, R - L, B - T);
    d.strokeStyle = "rgb(70,84,98)"; d.lineWidth = 2; d.strokeRect(L, T, R - L, B - T);
    const sx = x => L + x * (R - L), sy = y => T + y * (B - T);
    d.strokeStyle = "rgba(70,84,98,.47)"; d.lineWidth = 1;
    for (const k of [1, 2]) {
      d.beginPath(); d.moveTo(sx(k / 3), T); d.lineTo(sx(k / 3), B); d.stroke();
      d.beginPath(); d.moveTo(L, sy(k / 3)); d.lineTo(R, sy(k / 3)); d.stroke();
    }
    d.textBaseline = "top"; d.font = `15px ${FONT}`; d.fillStyle = "rgb(140,160,175)";
    d.fillText("远景 ↑", L + 4, T + 2); d.fillText("近景 ↓", L + 4, B - 20);
    const cam = [sx(blk.camera_x), B + 46];
    d.fillStyle = "rgba(200,120,90,.24)";
    d.beginPath(); d.moveTo(cam[0], cam[1]); d.lineTo(sx(0.12), B); d.lineTo(sx(0.88), B); d.closePath(); d.fill();
    d.fillStyle = "rgb(245,210,90)"; d.strokeStyle = "#000"; d.lineWidth = 1;
    d.beginPath(); d.moveTo(cam[0] - 13, cam[1] + 10); d.lineTo(cam[0] + 13, cam[1] + 10);
    d.lineTo(cam[0] + 8, cam[1] - 8); d.lineTo(cam[0] - 8, cam[1] - 8); d.closePath(); d.fill(); d.stroke();
    d.fillText(`📷 ${blk.camera_height}`, cam[0] + 16, cam[1] - 6);
    let lx = sx(0.12), ly = sy(0.12);
    if (blk.light_direction.includes("右")) lx = sx(0.88);
    if (blk.light_direction.includes("顶")) { lx = sx(0.5); ly = T - 2; }
    d.strokeStyle = "rgb(120,170,230)"; d.lineWidth = 2;
    d.beginPath(); d.moveTo(lx, ly); d.lineTo(sx(0.5), sy(0.5)); d.stroke();
    d.fillStyle = "rgb(150,195,240)"; d.beginPath(); d.arc(lx, ly, 9, 0, Math.PI * 2); d.fill();
    d.fillText("💡", lx - 8, ly + 10);
    for (const a of blk.actors) {
      const pal = palette(root.Pipeline.deriveSeed(baseSeed, a.character_id));
      const px = sx(a.x), py = sy(a.y);
      d.beginPath(); d.arc(px, py, 16, 0, Math.PI * 2); d.fillStyle = pal.darkCss; d.fill();
      d.strokeStyle = "#fff"; d.lineWidth = 2; d.stroke();
      const dirY = a.facing.includes("朝向") ? 22 : (a.facing.includes("背向") ? -22 : 0);
      const dirX = a.facing.includes("侧") && dirY === 0 ? 22 : 0;
      if (dirX || dirY) { d.beginPath(); d.moveTo(px, py); d.lineTo(px + dirX, py + dirY); d.stroke(); }
      d.fillStyle = "#fff"; d.fillText(a.character_id.replace("CHAR_", "C"), px - 14, py - 8);
      d.fillStyle = "rgb(200,210,220)"; d.fillText(a.facing, px - 18, py + 18);
    }
    d.font = `20px ${FONT}`; d.fillStyle = "rgb(120,200,170)"; d.fillText(`导演台俯视 · ${shotId}`, L, 16);
    d.font = `15px ${FONT}`; d.fillStyle = "rgb(160,178,192)";
    d.fillText(`构图：${root.PyRT.cpSlice(blk.framing, 0, 34)}`, L, H - 36);
    return canvas;
  }

  /* ---------------- 资产缓存：路径 → 离屏 canvas ---------------- */
  class AssetCache {
    constructor() { this.map = new Map(); }
    clear() { this.map.clear(); }
    get(path, ctx) {
      if (this.map.has(path)) return this.map.get(path);
      const info = ctx && ctx.images[path];
      if (!info) return null;
      const c = document.createElement("canvas");
      if (info.kind === "diagram") drawDiagram(c, info.shot_id, info.blk, info.base_seed);
      else drawCard(c, info, ctx.config.image.size);
      this.map.set(path, c);
      return c;
    }
  }

  /* ---------------- 草样片播放器（canvas 轮播，按每镜时长 + Ken Burns 轻缩放） ---------------- */
  class ReelPlayer {
    constructor(canvas, onShot) { this.canvas = canvas; this.onShot = onShot; this.raf = 0; this.playing = false; }
    load(reel, cache, ctx, audio) {
      this.stop();
      this.reel = reel; this.cache = cache; this.ctx = ctx; this.audioInfo = audio || {};
      const [cw, ch] = reel ? reel.canvas : [360, 640];
      this.canvas.width = cw; this.canvas.height = ch;
      this.total = reel ? reel.shots.reduce((a, s) => a + s.duration_seconds, 0) : 0;
      this.t = 0; this.lastIdx = -1;
      this.drawAt(0);
    }
    frame(shot, zoom) {
      const g = this.canvas.getContext("2d"), cw = this.canvas.width, ch = this.canvas.height;
      g.fillStyle = "rgb(8,10,14)"; g.fillRect(0, 0, cw, ch);
      const areaH = Math.trunc(ch * 0.74);
      const src = shot.image_path ? this.cache.get(shot.image_path, this.ctx) : null;
      if (src) {
        const scale = (cw / src.width) * zoom, nw = src.width * scale, nh = src.height * scale;
        g.drawImage(src, (cw - nw) / 2, (areaH - nh) / 2, nw, nh);
      }
      g.fillStyle = "#000"; g.fillRect(0, 0, cw, 40);
      g.fillStyle = "rgb(220,230,235)"; g.font = `20px ${FONT}`; g.textBaseline = "top";
      g.fillText(`${shot.shot_id} · ${shot.scene || ""}`, 12, 9, cw - 24);
      const subTop = ch - Math.trunc(ch * 0.20);
      g.fillStyle = "#000"; g.fillRect(0, subTop, cw, ch - subTop);
      g.font = `22px ${FONT}`; g.fillStyle = "rgb(245,245,245)"; g.textAlign = "center";
      let y = subTop + 12;
      for (const line of wrapCjk(shot.subtitle || "", Math.max(8, Math.floor(cw / 24))).slice(0, 3)) { g.fillText(line, cw / 2, y); y += 30; }
      g.textAlign = "left";
    }
    locate(t) {
      let acc = 0;
      for (let i = 0; i < this.reel.shots.length; i++) {
        const d = this.reel.shots[i].duration_seconds;
        if (t < acc + d || i === this.reel.shots.length - 1) return { i, local: Math.min(1, (t - acc) / d) };
        acc += d;
      }
      return { i: 0, local: 0 };
    }
    drawAt(t) {
      if (!this.reel || !this.reel.shots.length) {
        const g = this.canvas.getContext("2d");
        g.fillStyle = "#111"; g.fillRect(0, 0, this.canvas.width, this.canvas.height);
        return;
      }
      const { i, local } = this.locate(t);
      this.frame(this.reel.shots[i], 1.0 + 0.06 * local);
      if (i !== this.lastIdx) {
        this.lastIdx = i;
        if (this.onShot) this.onShot(i, this.reel.shots[i]);
        if (this.playing && this.sound) playVoice(this.audioInfo[`assets/audio/${this.reel.shots[i].shot_id}.wav`]);
      }
    }
    play(sound) {
      if (!this.reel || !this.reel.shots.length) return;
      this.stop(); this.playing = true; this.sound = !!sound; this.lastIdx = -1;
      const t0 = performance.now() - this.t * 1000;
      const loop = now => {
        if (!this.playing) return;
        this.t = (now - t0) / 1000;
        if (this.t >= this.total) { this.t = 0; this.playing = false; this.drawAt(this.total - 0.001); if (this.onEnd) this.onEnd(); return; }
        this.drawAt(this.t);
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
    }
    stop() { this.playing = false; cancelAnimationFrame(this.raf); stopVoice(); }
  }

  /* ---------------- 占位配音：与 write_voice_wav 同一公式（WebAudio 现场合成） ---------------- */
  let actx = null, voiceNode = null;
  function playVoice(info, amplitude = 0.06) {
    if (!info) return;
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      stopVoice();
      const rate = actx.sampleRate, n = Math.max(1, Math.trunc(info.seconds * rate)), fade = Math.max(1, Math.trunc(0.04 * rate));
      const buf = actx.createBuffer(1, n, rate), d = buf.getChannelData(0);
      for (let i = 0; i < n; i++)
        d[i] = amplitude * Math.min(1, i / fade) * Math.min(1, (n - i) / fade) * Math.sin(2 * Math.PI * info.pitch_hz * (i / rate));
      const src = actx.createBufferSource(); src.buffer = buf; src.connect(actx.destination); src.start();
      voiceNode = src;
    } catch (e) { /* 没有音频设备时静默 */ }
  }
  function stopVoice() { if (voiceNode) { try { voiceNode.stop(); } catch (e) { /* 已结束 */ } voiceNode = null; } }
  function closeAudio() { stopVoice(); if (actx) { try { actx.close(); } catch (e) { /* 忽略 */ } actx = null; } }

  root.Render = { palette, hsvToRgb, wrapCjk, drawCard, drawDiagram, AssetCache, ReelPlayer, playVoice, stopVoice, closeAudio };
})(typeof window !== "undefined" ? window : globalThis);
