/* =====================================================================
 * mobile.js —— 手机 / 触屏通用工具（不含任何流水线逻辑，可整份复制到别的流程 / 参数类项目）
 *
 *   MobileUI.detect(opts)               触屏 + 宽度 ≤ 980px → body.touchp（竖屏为主；横屏手机也走同一套单列布局）；
 *                                       触屏横屏且宽度 ≤ 980px → 再加 body.touchl（用来显示“竖屏体验更佳”）；
 *                                       任何触屏 → body.touch。窗口尺寸 / 方向变化时自动更新，变化后调 opts.onChange(state)。
 *   MobileUI.menu(btn, box)             ☰ 菜单：点按钮开关，点菜单项 / 点外面 / Esc 关闭。
 *   MobileUI.sheets(closeBtn, onChange) 全屏面板控制器：open('panel') 给 body 加 sheet-panel，close() 去掉；
 *                                       共用一个「返回」按钮；返回 {open, close, toggle, current}。
 *   MobileUI.rotateHint(el, okBtn)      横屏提示：点「仍然横屏继续」给 body 加 rot-ok；转回竖屏时自动清掉。
 *   MobileUI.pressFeedback(root, sel)   按下时给元素加 .pressed 并轻微振动（navigator.vibrate，失败静默）；
 *                                       抬起 / 取消 / 窗口失焦时全部清掉。
 *   MobileUI.guard(root, opts)          防误触：触屏下禁止长按菜单、iOS 捏合手势；窗口失焦、页面隐藏、
 *                                       所有手指离开时调 opts.onReset()。
 *   MobileUI.destroy()                  退出时解绑全部监听。
 *
 * 所有样式挂在 css/mobile.css 的 body.touchp / body.touchl / body.sheet-* 下面。
 * ===================================================================== */
(function (root) {
  "use strict";
  var doc = root.document;
  var state = { touch: false, touchp: false, touchl: false, maxWidth: 980 };
  var bound = [];
  var changeCbs = [];

  function on(el, ev, fn, opt) { el.addEventListener(ev, fn, opt); bound.push([el, ev, fn, opt]); }
  function vibrate(ms) { try { if (root.navigator && root.navigator.vibrate) root.navigator.vibrate(ms); } catch (e) { /* 不支持时静默 */ } }
  function isTouchDevice() {
    var n = root.navigator || {};
    if (n.maxTouchPoints > 0) return true;
    if ("ontouchstart" in root) return true;
    try { return !!(root.matchMedia && root.matchMedia("(pointer: coarse)").matches); } catch (e) { return false; }
  }

  function classify() {
    var w = root.innerWidth, h = root.innerHeight, touch = isTouchDevice(), portrait = h >= w;
    var narrow = touch && w <= state.maxWidth;
    var next = { touch: touch, touchp: narrow, touchl: narrow && !portrait };
    var changed = next.touch !== state.touch || next.touchp !== state.touchp || next.touchl !== state.touchl;
    state.touch = next.touch; state.touchp = next.touchp; state.touchl = next.touchl;
    var b = doc.body;
    b.classList.toggle("touch", state.touch);
    b.classList.toggle("touchp", state.touchp);
    b.classList.toggle("touchl", state.touchl);
    if (!state.touchl) b.classList.remove("rot-ok");
    return changed;
  }

  function detect(opts) {
    opts = opts || {};
    if (opts.maxWidth) state.maxWidth = opts.maxWidth;
    if (opts.onChange) changeCbs.push(opts.onChange);
    classify();
    var t = null;
    var relayout = function () {
      clearTimeout(t);
      t = setTimeout(function () { if (classify()) changeCbs.forEach(function (cb) { cb(state); }); }, 80);
    };
    on(root, "resize", relayout);
    on(root, "orientationchange", relayout);
    return state;
  }

  function menu(btn, box) {
    if (!btn || !box) return null;
    function set(open) { box.hidden = !open; btn.setAttribute("aria-expanded", open ? "true" : "false"); }
    on(btn, "click", function (e) { e.stopPropagation(); set(box.hidden); });
    on(box, "click", function (e) { if (e.target.closest("button, a")) set(false); });
    on(doc, "click", function (e) { if (!box.hidden && !box.contains(e.target) && e.target !== btn) set(false); });
    on(doc, "keydown", function (e) { if (e.code === "Escape" && !box.hidden) set(false); });
    return { open: function () { set(true); }, close: function () { set(false); }, isOpen: function () { return !box.hidden; } };
  }

  function sheets(closeBtn, onChange) {
    var cur = null;
    function apply(name) {
      if (cur) doc.body.classList.remove("sheet-" + cur);
      cur = name || null;
      if (cur) doc.body.classList.add("sheet-" + cur);
      if (closeBtn) closeBtn.hidden = !cur;
      if (onChange) onChange(cur);
    }
    if (closeBtn) on(closeBtn, "click", function () { apply(null); });
    on(doc, "keydown", function (e) { if (e.code === "Escape" && cur) apply(null); });
    return {
      open: function (name) { apply(name); },
      close: function () { if (cur) apply(null); },
      toggle: function (name) { apply(cur === name ? null : name); },
      current: function () { return cur; }
    };
  }

  function rotateHint(el, okBtn) {
    if (!el) return;
    if (okBtn) on(okBtn, "click", function () { doc.body.classList.add("rot-ok"); });
  }

  function clearPressed() {
    var list = doc.querySelectorAll(".pressed");
    for (var i = 0; i < list.length; i++) list[i].classList.remove("pressed");
  }

  function pressFeedback(rootEl, selector) {
    on(rootEl, "pointerdown", function (e) {
      var t = e.target.closest ? e.target.closest(selector) : null;
      if (!t || t.disabled) return;
      t.classList.add("pressed");
      if (e.pointerType === "touch") vibrate(8);
    });
    on(rootEl, "pointerup", clearPressed);
    on(rootEl, "pointercancel", clearPressed);
    on(root, "blur", clearPressed);
  }

  function guard(rootEl, opts) {
    opts = opts || {};
    var reset = function () { clearPressed(); if (opts.onReset) opts.onReset(); };
    on(rootEl, "contextmenu", function (e) { if (state.touch) e.preventDefault(); });
    on(doc, "gesturestart", function (e) { e.preventDefault(); });
    on(rootEl, "touchend", function (e) { if (!e.touches || e.touches.length === 0) clearPressed(); });
    on(rootEl, "touchcancel", reset);
    on(root, "blur", reset);
    on(doc, "visibilitychange", function () { if (doc.hidden) reset(); });
  }

  function destroy() {
    bound.forEach(function (b) { b[0].removeEventListener(b[1], b[2], b[3]); });
    bound = []; changeCbs = [];
  }

  root.MobileUI = {
    detect: detect, menu: menu, sheets: sheets, rotateHint: rotateHint,
    pressFeedback: pressFeedback, guard: guard, vibrate: vibrate, destroy: destroy,
    state: function () { return state; }
  };
})(window);
