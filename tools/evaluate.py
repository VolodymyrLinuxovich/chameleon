"""Batch evaluation: every task in input/ x every catalogue format.

    python -m tools.evaluate            # summary table + hard-rule checks
    python -m tools.evaluate --render   # also contact sheets in output/eval/

Contact sheets show, per format, the naive stretch (top) against the
Chameleon result (bottom), rendered by the official renderer.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from engine.chameleon import adapt
from engine.resize import stretch
from tools.checks import check
from tools.formats import FORMATS

ASSETS = Path("brand_kit/assets")


def render(design: dict, path: Path) -> None:
    from renderer.converter.convert import render_design_to_png
    render_design_to_png(design, ASSETS, str(path))


def sheet(rows: list[tuple[str, list[Path]]], labels: list[str], out: Path, cell: int = 260) -> None:
    from PIL import Image, ImageDraw
    pad, lab = 12, 22
    W = pad + len(labels) * (cell + pad) + 90
    H = pad + lab + len(rows) * (cell + pad)
    img = Image.new("RGB", (W, H), (246, 242, 236))
    d = ImageDraw.Draw(img)
    for j, t in enumerate(labels):
        d.text((90 + pad + j * (cell + pad), pad), t, fill=(40, 30, 40))
    for i, (name, paths) in enumerate(rows):
        y = pad + lab + i * (cell + pad)
        d.text((pad, y + cell // 2), name, fill=(40, 30, 40))
        for j, p in enumerate(paths):
            im = Image.open(p).convert("RGB")
            im.thumbnail((cell, cell))
            x = 90 + pad + j * (cell + pad)
            img.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
    img.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--input", default="input")
    args = ap.parse_args()
    outdir = Path("output/eval")
    outdir.mkdir(parents=True, exist_ok=True)
    total_problems = 0
    summary = []
    for task_path in sorted(Path(args.input).glob("*.json")):
        task = json.loads(task_path.read_text())
        src = task["source"]
        targets = [dict(task["target_canvas"], key="task", name="Task target")] + FORMATS
        rows_s, rows_c = [], []
        print(f"\n{task_path.name}  ({src['canvas']['width']}x{src['canvas']['height']}, {len(src['elements'])} elements)")
        for t in targets:
            tc = {"width": t["width"], "height": t["height"]}
            t0 = time.perf_counter()
            design, rep = adapt(src, tc)
            ms = (time.perf_counter() - t0) * 1000
            probs = check(src, design)
            total_problems += len(probs)
            best = rep["candidates"][0]
            print(f"  {t['name']:<20} {t['width']:>5}x{t['height']:<5} {rep['chosen']:<44} "
                  f"score {best['score']:.3f}  hidden {len(rep['hidden']):>2}  {ms:6.1f}ms  "
                  f"{'OK' if not probs else probs}")
            summary.append({"task": task_path.stem, "format": t["key"], "chosen": rep["chosen"],
                            "score": best["score"], "parts": best["parts"], "hidden": list(rep["hidden"]),
                            "problems": probs, "ms": round(ms, 1)})
            if args.render:
                pc = outdir / f"{task_path.stem}__{t['key']}.png"
                ps = outdir / f"{task_path.stem}__{t['key']}__stretch.png"
                render(design, pc)
                render(stretch(src, tc), ps)
                rows_c.append(pc)
                rows_s.append(ps)
        if args.render:
            sheet([("stretch", rows_s), ("chameleon", rows_c)],
                  [f"{t['name']} {t['width']}x{t['height']}" for t in targets],
                  outdir / f"{task_path.stem}__sheet.png")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    n = len(summary)
    print(f"\n{n} runs, {total_problems} hard-rule problems, mean score "
          f"{sum(s['score'] for s in summary) / max(1, n):.3f}, max {max(s['ms'] for s in summary):.0f}ms")
    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main())
