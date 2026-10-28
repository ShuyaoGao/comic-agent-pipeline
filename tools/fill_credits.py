# -*- coding: utf-8 -*-
"""Fill every double-brace placeholder (e.g. REPO_NAME) from credits.json (author, series, GitHub user, repo name ...)
and the numbers from results/result.json, then rebuild play/js/credits.js (and the release zip).

    python -m tools.fill_credits            # render tools/templates/*.tmpl -> repository root
    python -m tools.fill_credits --release  # ... and rebuild release/*.zip

Templates live in tools/templates/ (README.md.tmpl -> README.md, gitignore -> .gitignore, ...).
Re-running is safe: outputs are always regenerated from the templates. Finally it lists any
placeholder that is still unfilled anywhere in the repository.
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "tools" / "templates"
PH = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
TEXT_EXT = {".md", ".txt", ".cff", ".json", ".js", ".html", ".css", ".py", ".ini", ".yaml", ""}
RENAME = {"gitignore": ".gitignore", "nojekyll": ".nojekyll"}   # nojekyll: 空文件，GitHub Pages 不走 Jekyll


def numbers_from_results():
    vals = {}
    p = ROOT / "results" / "result.json"
    if p.exists():
        r = json.loads(p.read_text(encoding="utf-8"))
        d, g = r["demo"], r["demo"]["genlog"]
        money = lambda v: f"{v:.4f}".rstrip("0").rstrip(".") if v < 1 else f"{v:.2f}"  # noqa: E731
        vals.update({
            "BROWSER": {"msedge": "Microsoft Edge", "chrome": "Google Chrome"}.get(r["browser"]["name"], r["browser"]["name"]),
            "BROWSER_VERSION": r["browser"].get("version") or "",
            "DEMO_IDEA": d["idea"], "DEMO_SEED": str(d["seed"]), "DEMO_GENRE": d["genre"],
            "DEMO_CHARS": "、".join(d["characters"]), "DEMO_SHOTS": str(d["shots"]),
            "DEMO_DURATION": f"{d['total_duration_seconds']:g}", "DEMO_CONSISTENCY": f"{d['consistency_score']:.2f}",
            "DEMO_OVERALL": f"{d['overall_score']:g}",
            "GEN_TOTAL": str(g["total_generations"]), "GEN_LLM": str(g["llm_calls"]), "GEN_IMG": str(g["image_calls"]),
            "GEN_AUDIO": str(g["audio_calls"]), "GEN_VIDEO": str(g["video_calls"]),
            "TOK_IN": str(g["total_input_tokens"]), "TOK_OUT": str(g["total_output_tokens"]),
            "WARN_STATUS": r["warn_case"]["compliance"], "WARN_NOTE": r["warn_case"]["notes"][0],
            "IMPORT_CONSISTENCY": f"{r['import']['consistency_score']:.2f}",
        })
        for key, c in d["cost"].items():
            K = key.upper()
            vals[f"COST_{K}"] = money(c["estimated_real_cost_usd"])
            vals[f"REAL_{K}"] = str(c["real_video_shots"])
            vals[f"FULL_{K}"] = money(c["full_video_cost_usd"])
            vals[f"DISP_{K}"] = money(c["dispatched_video_cost_usd"])
    p = ROOT / "results" / "parity.json"
    if p.exists():
        r = json.loads(p.read_text(encoding="utf-8"))
        vals.update({"PARITY_CASES": str(r["cases"]), "PARITY_COMPARED": str(r["compared"]),
                     "PARITY_PYTHON": "Python " + r["python"], "PARITY_NODE": r["node"]})
    return vals


def render(values):
    written = []
    for tpl in sorted(TEMPLATES.iterdir()):
        if not tpl.is_file():
            continue
        name = tpl.name[:-len(".tmpl")] if tpl.name.endswith(".tmpl") else tpl.name
        out = ROOT / RENAME.get(name, name)
        text = tpl.read_text(encoding="utf-8")
        text = PH.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)
        out.write_text(text, encoding="utf-8", newline="\n")
        written.append(out)
    return written


def leftover_placeholders():
    left = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or ".git" in p.parts or "templates" in p.parts or p.suffix not in TEXT_EXT:
            continue
        if p.stat().st_size > 2_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in PH.finditer(text):
            left.append((p.relative_to(ROOT).as_posix(), m.group(0)))
    return left


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args(argv)
    if not TEMPLATES.is_dir():
        raise SystemExit("tools/templates/ not found (run this inside the published repository)")
    credits = json.loads((ROOT / "credits.json").read_text(encoding="utf-8"))
    values = {k: v for k, v in credits.items() if not k.startswith("_")}
    values.update(numbers_from_results())
    for p in render(values):
        print("wrote", p.relative_to(ROOT).as_posix())
    from tools import build
    build.main(["--release"] if args.release else [])
    left = leftover_placeholders()
    if left:
        print("UNFILLED placeholders:")
        for f, ph in left:
            print("  ", f, ph)
    else:
        print("no unfilled placeholders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
