# -*- coding: utf-8 -*-
"""Phone-portrait and desktop acceptance for play/index.html (series rule "section 8", v2).

    python -m tools.mobile_check_cap                   # all sizes, screenshots to a temp dir
    python -m tools.mobile_check_cap --shots docs/img  # also copy the 390x844 shot to docs/img/mobile_390x844.png
    python -m tools.mobile_check_cap --out DIR         # keep every screenshot + mobile_check.json in DIR

Drives the locally installed Edge through Playwright (channel "msedge") and emulates the devices through the
DevTools protocol (viewport, DPR, mobile, touch) -- not through --window-size. Sizes: 390x844, 414x896,
360x780 (DPR 3), 768x1024 (DPR 2) with touch, a landscape phone 844x390 (rotate hint), plus desktop
1920x1080 and 1366x768. The driver (tools/mobile_check.py: machine-wide Edge lock, free-memory guard,
overflow and JS-error checks, screenshots) is part of this repository.

Scenario (phone sizes): body gets class touchp; the first-visit help overlay shows the touch illustration (no
keyboard hint) with the start button inside the viewport; the header is one row (title, mode tabs, menu);
in "watch" the process panel sits right under the artwork; tabs / buttons / inputs have >= 44 px touch targets
and labels >= 14 px; a tap on "step" produces the first stage's artwork and a tap on "run" finishes all 9
stages; the stage step bar scrolls horizontally; long tables sit in horizontally scrolling containers; the
process panel opens full screen from its button and closes with "back"; the menu opens the help; no
horizontal overflow at any point; no JS errors. Desktop sizes: no touch classes, both columns inline, the
same run-through with clicks. The 3D stage page is opened at 390x844 as well (WebGL on the software
renderer): no overflow, three.js loaded, form controls >= 44 px.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "play" / "index.html"
DIRECTOR = ROOT / "play" / "director.html"
READY = "window.__cap && window.__cap.ready"
SWIFTSHADER = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
LANDSCAPE = {"name": "l844x390", "kind": "mobile", "w": 844, "h": 390, "dpr": 3}


# ----------------------------------------------------------------------------- helpers (run inside the page)
def _targets(page, sel, min_h):
    """Visible elements matching sel whose height is below min_h, as 'sel#i h=..'."""
    return page.evaluate("""([sel, minH]) => {
      const out = [];
      document.querySelectorAll(sel).forEach((el, i) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        if (r.height < minH - 0.5) out.push(sel + '#' + i + ' h=' + r.height.toFixed(1));
      });
      return out; }""", [sel, min_h])


def _font_min(page, sel):
    return page.evaluate("""(sel) => {
      let m = 1e9;
      document.querySelectorAll(sel).forEach(el => {
        const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) return;
        m = Math.min(m, parseFloat(getComputedStyle(el).fontSize)); });
      return m; }""", sel)


def _overflow(page, w, tag=""):
    out = page.evaluate("""(w) => {
      const d = document.documentElement, out = [];
      if (d.scrollWidth > w + 1) out.push('document scrollWidth ' + d.scrollWidth + ' > ' + w);
      ['#topbar', '#layout', '#viewcard', '#view', '#dock', '#rightcol', '#tabcard', '#flowcard'].forEach(s => {
        const el = document.querySelector(s); if (!el) return;
        const cs = getComputedStyle(el); if (cs.display === 'none') return;
        if (el.scrollWidth > el.clientWidth + 1 && cs.overflowX !== 'auto' && cs.overflowX !== 'scroll')
          out.push(s + ' scrollWidth ' + el.scrollWidth + ' > ' + el.clientWidth);
        const r = el.getBoundingClientRect(); if (r.right > w + 1) out.push(s + ' right ' + r.right.toFixed(0) + ' > ' + w); });
      return out; }""", w)
    return [f"{tag}{o}" for o in out]


def _rect(page, sel):
    return page.evaluate("""(sel) => { const el = document.querySelector(sel); if (!el) return null;
      const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      return {x: r.x, y: r.y, w: r.width, h: r.height, top: r.top, bottom: r.bottom, right: r.right, display: cs.display, position: cs.position, ox: cs.overflowX}; }""", sel)


def _wait_mode(page, mode, timeout=8000):
    try:
        page.wait_for_function("window.__cap.S.mode === %r && !window.__cap.S.loop" % mode, timeout=timeout)
        page.wait_for_timeout(150)
        return True
    except Exception:
        return False


def _help_open(page):
    return page.evaluate("document.getElementById('dlg-help').classList.contains('show')")


def _tables_ok(page, w):
    return page.evaluate("""(w) => { const bad = [];
      document.querySelectorAll('.tw').forEach((t, i) => { const r = t.getBoundingClientRect(); if (r.width === 0) return;
        if (getComputedStyle(t).overflowX !== 'auto' || r.right > w + 1) bad.push('.tw#' + i + ' ox=' + getComputedStyle(t).overflowX + ' right=' + r.right.toFixed(0)); });
      return bad; }""", w)


def _run_pipeline(page, click, fails, tag):
    """Reset, one step, then run to the end; assert the artwork area changes each time."""
    click("#btn-reset")
    page.wait_for_timeout(200)
    t0 = page.evaluate("document.getElementById('view-title').textContent")
    if page.evaluate("window.__cap.S.state && window.__cap.S.state.idea !== null"):
        fails.append(f"{tag}: reset did not clear the state")
    click("#btn-step")
    page.wait_for_timeout(400)
    t1 = page.evaluate("document.getElementById('view-title').textContent")
    if not page.evaluate("window.__cap.S.state && window.__cap.S.state.idea !== null") or t0 == t1 or \
            page.evaluate("document.querySelectorAll('#view .blk').length") == 0:
        fails.append(f"{tag}: tap on step did not produce the first stage's artwork ({t0!r} -> {t1!r})")
    click("#speed-presets button[data-k=instant]")
    click("#btn-run")
    try:
        page.wait_for_function("window.__cap.S.state && window.__cap.S.state.qc !== null && !window.__cap.S.loop", timeout=60000)
    except Exception as e:
        fails.append(f"{tag}: run did not finish all 9 stages: {e!r}"[:200])
        return
    page.wait_for_timeout(300)
    if page.evaluate("document.querySelectorAll('#flow .node.done').length") != 9:
        fails.append(f"{tag}: flow chart does not show 9 done nodes")


# ----------------------------------------------------------------------------- scenario
def scenario(page, size):
    """Runs the checks for one size; a step that throws is recorded and the failures collected so far are kept."""
    fails = []
    try:
        _scenario(page, size, fails)
    except Exception as e:
        fails.append("step raised: %s" % str(e).splitlines()[0][:200])
    return fails


def _scenario(page, size, fails):
    mobile = size["kind"] == "mobile"
    w, h = size["w"], size["h"]
    page.wait_for_function(READY, timeout=120000)
    page.wait_for_timeout(200)
    tap = (lambda sel: page.tap(sel)) if mobile else (lambda sel: page.click(sel))

    if not mobile:
        if page.evaluate("document.body.classList.contains('touchp') || document.body.classList.contains('touchl')"):
            fails.append("desktop size got body.touchp / touchl (phone layout on a desktop size)")
        if _help_open(page):
            page.click("#help-close")
            page.wait_for_timeout(150)
        for sel in ("#menu-btn", "#mob-bar", "#rotate-hint", "#panel-close"):
            if page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).display") != "none":
                fails.append(f"{sel} visible on desktop")
        if (_rect(page, "#rightcol") or {"w": 0})["w"] < 300:
            fails.append("right panel not visible inline on desktop")
        page.click("#modes button[data-mode=edit]")
        if not _wait_mode(page, "edit"):
            fails.append("click on tab did not switch mode")
        _run_pipeline(page, page.click, fails, "desktop")
        page.click("#view-tabs button[data-v=storyboard]")
        page.wait_for_timeout(200)
        fails += _tables_ok(page, w)
        page.click("#view-tabs button[data-v=director]")
        page.wait_for_timeout(200)
        fails += _overflow(page, w, "desktop ")
        if page.evaluate("document.getElementById('footer').getBoundingClientRect().bottom") > h + 1:
            fails.append("desktop: footer below the viewport (page should fit one screen)")
        return

    # ---- landscape phone: same single-column layout plus the "portrait is better" hint
    if w > h:
        if not page.evaluate("document.body.classList.contains('touchl') && document.body.classList.contains('touchp')"):
            fails.append("landscape phone: body has no touchl + touchp")
            return
        if page.evaluate("getComputedStyle(document.getElementById('rotate-hint')).display") == "none":
            fails.append("landscape phone: rotate hint not shown")
        page.tap("#rotate-ok")
        page.wait_for_timeout(150)
        if page.evaluate("getComputedStyle(document.getElementById('rotate-hint')).display") != "none" or \
                not page.evaluate("document.body.classList.contains('rot-ok')"):
            fails.append("landscape phone: 'continue in landscape' did not hide the hint")
        if _help_open(page):
            page.tap("#help-close")
            page.wait_for_timeout(150)
        fails += _overflow(page, w, "landscape ")
        return

    # ---- phone / tablet portrait
    if not page.evaluate("document.body.classList.contains('touchp')"):
        fails.append("body has no class touchp")
        return
    if page.evaluate("document.body.classList.contains('touchl')"):
        fails.append("portrait phone got body.touchl")
    if page.evaluate("getComputedStyle(document.getElementById('rotate-hint')).display") != "none":
        fails.append("rotate hint shown in portrait")
    # first-visit help overlay: touch illustration, no keyboard hint, start button inside the viewport
    if not _help_open(page):
        fails.append("help overlay not shown on first visit")
    else:
        st = page.evaluate("""() => ({
          touch: getComputedStyle(document.querySelector('#dlg-help .touch-only')).display !== 'none',
          svg: !!document.querySelector('#dlg-help .touch-only svg') && document.querySelector('#dlg-help .touch-only svg').getBoundingClientRect().height > 40,
          kbd: getComputedStyle(document.querySelector('#dlg-help .kbd-only')).display === 'none',
          scroll: getComputedStyle(document.querySelector('#dlg-help .dlg-body')).overflowY === 'auto' })""")
        if not st["touch"] or not st["svg"]:
            fails.append("help: touch illustration hidden")
        if not st["kbd"]:
            fails.append("help: keyboard hint visible on touch device")
        if not st["scroll"]:
            fails.append("help: body not scrollable")
        bb = page.locator("#help-close").bounding_box()
        if not bb or bb["y"] + bb["height"] > h + 0.5 or bb["height"] < 44:
            fails.append("help: start button not fixed inside viewport / too small: %r" % (bb,))
        page.tap("#help-close")
        page.wait_for_timeout(150)
        if _help_open(page):
            fails.append("help: tap on start did not close it")
    # header: one row (brand, mode tabs, menu button share the same band), nothing wider than the screen
    hd = page.evaluate("""() => { const q = s => document.querySelector(s).getBoundingClientRect();
      const b = q('.brand'), t = q('#modes'), m = q('#menu-btn'), top = q('#topbar');
      return {b, t, m, top: {h: top.height, bottom: top.bottom, right: top.right}}; }""")
    for k in ("b", "t", "m"):
        r = hd[k]
        if r["height"] == 0 or r["bottom"] > hd["top"]["bottom"] + 0.5 or r["right"] > w + 0.5:
            fails.append("header element %s not in the single header row: %r" % (k, r))
    if hd["top"]["h"] > 64:
        fails.append("header taller than one row: %.0f px" % hd["top"]["h"])
    for sel in ("#director-link", "#big-wrap", "#help-btn", "#exit-btn"):
        if page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).display") != "none":
            fails.append(f"header: {sel} should be folded into the menu")
    # watch mode: the process panel sits right under the artwork (compact), the controls below it
    if page.evaluate("window.__cap.S.mode") != "watch":
        fails.append("first mode is not watch")
    vc, rc, dk = _rect(page, "#viewcard"), _rect(page, "#rightcol"), _rect(page, "#dock")
    if not rc or rc["w"] < w * 0.8 or rc["position"] != "static":
        fails.append("watch: process panel not inline under the artwork: %r" % (rc,))
    elif rc["top"] < vc["bottom"] - 1 or dk["top"] < rc["bottom"] - 1:
        fails.append("watch: order should be artwork -> panel -> controls (%r / %r / %r)" % (vc["bottom"], rc["top"], rc["bottom"]))
    if page.evaluate("getComputedStyle(document.getElementById('mob-bar')).display") != "none":
        fails.append("watch: panel button bar should be hidden (panel is inline)")
    fails += _overflow(page, w, "watch ")
    # touch targets and label sizes (everything currently visible)
    for sel, mh in (("#modes button", 40), ("#menu-btn", 44), ("#view-tabs button", 44), ("#cost-presets button", 44), ("#speed-presets button", 44),
                    ("#dock .btn", 44), (".tabs button", 44), ("#dock input", 44), ("#dock select", 44), ("#flow .node", 44)):
        bad = _targets(page, sel, mh)
        if bad:
            fails.append("touch target < %d px: %s" % (mh, ", ".join(bad[:4])))
    fm = _font_min(page, "#modes button, #dock .btn, .seg button, .row label, .lbl, #caption, .tabs button, .mbtn, #menu button, #menu a")
    if fm < 14:
        fails.append("label font-size %.1f px < 14 px" % fm)
    # edit mode: panel collapsed, button bar visible; one step then a full run through taps
    page.tap("#modes button[data-mode=edit]")
    if not _wait_mode(page, "edit") or not page.evaluate("document.body.classList.contains('m-edit')"):
        fails.append("tap on tab did not switch to edit")
    if (_rect(page, "#rightcol") or {"w": 1})["w"] != 0:
        fails.append("edit: process panel should be collapsed by default on phones")
    pb = page.locator("#panel-btn").bounding_box()
    if not pb or pb["height"] < 44:
        fails.append("edit: panel button missing / too small: %r" % (pb,))
    _run_pipeline(page, tap, fails, "phone")
    # stage step bar scrolls horizontally; long tables sit in horizontally scrolling containers
    vt = page.evaluate("""() => { const el = document.getElementById('view-tabs'); const cs = getComputedStyle(el);
      return {ox: cs.overflowX, sw: el.scrollWidth, cw: el.clientWidth, wrap: cs.flexWrap, right: el.getBoundingClientRect().right}; }""")
    if vt["ox"] != "auto" or vt["wrap"] != "nowrap" or vt["right"] > w + 1:
        fails.append("stage step bar is not a horizontal scroller: %r" % (vt,))
    page.tap("#view-tabs button[data-v=storyboard]")
    page.wait_for_timeout(250)
    if page.evaluate("document.querySelectorAll('#view .tw table').length") == 0:
        fails.append("storyboard table not wrapped in a scroll container")
    fails += _tables_ok(page, w)
    fails += _overflow(page, w, "storyboard ")
    page.tap("#view-tabs button[data-v=compose]")
    page.wait_for_timeout(250)
    fails += _tables_ok(page, w)
    fails += _overflow(page, w, "compose ")
    # process panel: open full screen, switch a tab, close with "back"
    page.evaluate("window.scrollTo(0, 0)")
    page.tap("#panel-btn")
    page.wait_for_timeout(300)
    rb = page.evaluate("""() => { const r = document.getElementById('rightcol').getBoundingClientRect();
      const c = document.getElementById('panel-close').getBoundingClientRect(); const pos = getComputedStyle(document.getElementById('rightcol')).position;
      return {sheet: document.body.classList.contains('sheet-panel'), pos, w: r.width, h: r.height, cy: c.bottom, ch: c.height,
              nodes: document.querySelectorAll('#flow .node').length}; }""")
    if not rb["sheet"] or rb["pos"] != "fixed" or rb["w"] < w - 1 or rb["h"] < h - 1 or rb["nodes"] != 9 or rb["cy"] > h + 0.5 or rb["ch"] < 44:
        fails.append("panel sheet did not open full screen: %r" % (rb,))
    page.tap(".tabs button[data-rtab=matrix]")
    page.wait_for_timeout(250)
    if not page.evaluate("document.getElementById('rpane-matrix').classList.contains('on') && document.querySelectorAll('#matrix .tw table tr').length > 1"):
        fails.append("panel: consistency matrix tab did not render")
    fails += _tables_ok(page, w)
    page.tap(".tabs button[data-rtab=cost]")
    page.wait_for_timeout(250)
    fails += _tables_ok(page, w)
    fails += _overflow(page, w, "sheet ")
    page.tap("#panel-close")
    page.wait_for_timeout(200)
    if page.evaluate("document.body.classList.contains('sheet-panel') || document.getElementById('rightcol').getBoundingClientRect().width !== 0"):
        fails.append("panel sheet did not close")
    # menu -> help -> close
    page.tap("#menu-btn")
    page.wait_for_timeout(150)
    if page.evaluate("document.getElementById('menu').hidden"):
        fails.append("menu did not open")
    bad = _targets(page, "#menu button, #menu a", 44)
    if bad:
        fails.append("menu items < 44 px: %s" % ", ".join(bad[:3]))
    page.tap("#menu-help")
    page.wait_for_timeout(150)
    if not _help_open(page) or not page.evaluate("document.getElementById('menu').hidden"):
        fails.append("menu -> help did not open help / close menu")
    page.tap("#help-close")
    page.wait_for_timeout(150)
    page.tap("#menu-btn")
    page.wait_for_timeout(120)
    page.tap("#menu-btn")
    page.wait_for_timeout(120)
    if not page.evaluate("document.getElementById('menu').hidden"):
        fails.append("menu did not toggle closed")
    # practice mode: task list in one column, readable
    page.tap("#modes button[data-mode=practice]")
    if not _wait_mode(page, "practice"):
        fails.append("tap on tab did not switch to practice")
    tk = page.evaluate("""() => { const li = document.querySelectorAll('#tasks li'); if (!li.length) return null;
      const r = li[0].getBoundingClientRect(); return {n: li.length, w: r.width, fs: parseFloat(getComputedStyle(li[0]).fontSize), hidden: document.getElementById('tasks').hidden}; }""")
    if not tk or tk["hidden"] or tk["n"] != 7 or tk["fs"] < 14 or tk["w"] < w * 0.7:
        fails.append("practice: task list not a readable single column: %r" % (tk,))
    fails += _overflow(page, w, "practice ")
    # leave the page in a presentable state for the screenshot (edit mode, finished run, director view)
    page.tap("#modes button[data-mode=edit]")
    _wait_mode(page, "edit")
    page.tap("#view-tabs button[data-v=director]")
    page.wait_for_timeout(200)
    page.evaluate("window.scrollTo(0, 0); document.getElementById('toast').className = ''")
    page.wait_for_timeout(400)
    fails += _overflow(page, w, "final ")
    return


# ----------------------------------------------------------------------------- 3D stage page on a phone
def director_check(out: Path, size):
    """play/director.html at a phone size: selftest passes (three.js on the software renderer), no overflow, controls >= 44 px."""
    from playwright.sync_api import sync_playwright
    from tools.mobile_check import EdgeLock

    fails, errors = [], []
    with EdgeLock(), sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=SWIFTSHADER)
        try:
            ctx = browser.new_context(viewport={"width": size["w"], "height": size["h"]}, device_scale_factor=size["dpr"],
                                      is_mobile=True, has_touch=True, locale="zh-CN")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
            page.on("console", lambda m: errors.append("console.error: %s" % m.text) if m.type == "error" else None)
            page.goto(DIRECTOR.as_uri() + "?selftest=1")
            try:
                page.wait_for_function("(() => { const e = document.getElementById('selftest'); return e && e.textContent.length > 0; })()", timeout=60000)
                r = json.loads(page.evaluate("document.getElementById('selftest').textContent"))
            except Exception as e:
                r = {"ok": False, "errors": [repr(e)[:200]]}
            if not r.get("ok"):
                fails.append("director selftest failed: %s" % json.dumps(r, ensure_ascii=False)[:300])
            dims = page.evaluate("({sw: document.documentElement.scrollWidth, iw: innerWidth, pw: document.getElementById('panel').getBoundingClientRect().width, st: document.getElementById('stage').getBoundingClientRect()})")
            if dims["sw"] > size["w"] + 1 or dims["iw"] > size["w"] + 1 or dims["pw"] > size["w"] + 1:
                fails.append("director: horizontal overflow %r" % (dims,))
            if dims["st"]["width"] < size["w"] - 1 or dims["st"]["height"] < 200:
                fails.append("director: stage not full width on a phone: %r" % (dims["st"],))
            bad = _targets(page, "#panel input, #panel select, #panel button", 40)
            if bad:
                fails.append("director: controls < 40 px: %s" % ", ".join(bad[:4]))
            fails += [e for e in errors if "favicon" not in e.lower()]
            page.screenshot(path=str(out / ("director_%s.png" % size["name"])), full_page=False)
            ctx.close()
        finally:
            browser.close()
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", help="copy the phone screenshot (390x844) into this directory as mobile_390x844.png")
    ap.add_argument("--out", help="directory for all screenshots + mobile_check.json (default: a temp dir)")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from tools.mobile_check import run, SIZES  # noqa: E402

    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="cap_mobile_"))
    sizes = SIZES[:4] + [LANDSCAPE] + SIZES[4:]
    rep = run(INDEX.as_uri(), out, scenario=scenario, sizes=sizes, settle_ms=800)
    for s in rep["sizes"]:
        print("%-11s %4dx%-4d dpr%d %s" % (s["name"], s["w"], s["h"], s["dpr"], "PASS" if not s["fails"] else "FAIL: " + " | ".join(s["fails"])))
    dfails = director_check(out, SIZES[0])
    print("%-11s %4dx%-4d dpr%d %s" % ("director", SIZES[0]["w"], SIZES[0]["h"], SIZES[0]["dpr"], "PASS" if not dfails else "FAIL: " + " | ".join(dfails)))
    rep["director"] = {"size": SIZES[0]["name"], "fails": dfails}
    rep["ok"] = rep["ok"] and not dfails
    (out / "mobile_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("screenshots:", out)
    if args.shots:
        d = Path(args.shots)
        if not d.is_absolute():
            d = ROOT / d
        d.mkdir(parents=True, exist_ok=True)
        src = out / "m390x844.png"
        if src.exists():
            shutil.copy2(src, d / "mobile_390x844.png")
            print("wrote", (d / "mobile_390x844.png").as_posix())
    print(json.dumps({"ok": rep["ok"], "sizes": [(s["name"], not s["fails"]) for s in rep["sizes"]] + [("director", not dfails)]}))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
