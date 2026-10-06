"""Stress test: realistic random designs x catalogue formats.

    python -m tools.stress --n 150 --render 8

Generates designs from varied but plausible structures (eyebrow, headline,
body, 0-2 images, logo top/bottom/corner, left or centred alignment, CTA,
badge rows, stickers), runs every format, and reports the worst cases by
the engine's own score plus a few hard visual red flags. With --render it
writes stretch/result pairs for the worst N to output/stress/.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from engine.chameleon import adapt
from tools.checks import check
from tools.formats import FORMATS

WORDS = ("golden hour botanical sparkling summer light chase limited batch crafted fresh citrus wild "
         "honey market night festival tickets launch collection season sunset garden evening").split()
SOURCES = [(1080, 1080), (1080, 1350), (1080, 1920), (1920, 1080), (1200, 628), (1000, 1500)]


def phrase(rng: random.Random, lo: int, hi: int, title: bool = False) -> str:
    words = [rng.choice(WORDS) for _ in range(rng.randint(lo, hi))]
    s = " ".join(w.capitalize() if title else w for w in words)
    return s if title else s.capitalize() + "."


def design(rng: random.Random) -> dict:
    W, H = rng.choice(SOURCES)
    u = min(W, H) / 1080
    left = rng.random() < 0.4
    align = "left" if left else "center"
    m = 80 * u
    colw = (W * (0.55 if W > H * 1.3 else 1.0)) - 2 * m
    x = m
    els = [{"id": "bg", "type": "image", "x": 0, "y": 0, "width": W, "height": H, "z_index": 0,
            "asset_id": "solstice_bg_gradient.png", "fit": "cover"}]
    y = m
    logo_pos = rng.choice(["top", "top", "bottom", "corner"])
    lw, lh = 300 * u, 100 * u
    if logo_pos == "top":
        els.append({"id": "logo", "type": "image", "x": x if left else (W - lw) / 2, "y": y, "width": lw,
                    "height": lh, "z_index": 3, "asset_id": "solstice_logo_lockup.png", "fit": "contain"})
        y += lh + 40 * u
    if rng.random() < 0.5:
        els.append({"id": "eyebrow", "type": "text", "x": x, "y": y, "width": colw, "height": 40 * u, "z_index": 3,
                    "content": phrase(rng, 2, 4, True).upper(), "font_family": "Solstice Sans",
                    "font_size": round(26 * u), "font_weight": "bold", "color": "rgba(240,178,66,1)",
                    "text_align": align})
        y += 56 * u
    hl = phrase(rng, *rng.choice([(2, 4), (4, 8), (10, 22)]), title=True)
    hfs = round(rng.choice([56, 72, 96]) * u)
    hh = hfs * 1.2 * max(1, min(4, len(hl) * hfs * 0.5 / colw + 1))
    els.append({"id": "headline", "type": "text", "x": x, "y": y, "width": colw, "height": hh, "z_index": 3,
                "content": hl, "font_family": "Solstice Serif", "font_size": hfs, "font_weight": "bold",
                "color": "rgba(255,255,255,1)", "text_align": align})
    y += hh + 30 * u
    hero_side = W > H * 1.3
    if rng.random() < 0.8:
        s = min(W, H) * rng.uniform(0.3, 0.5)
        if hero_side:
            els.append({"id": "product", "type": "image", "x": W - m - s, "y": (H - s) / 2, "width": s, "height": s,
                        "z_index": 2, "asset_id": "solstice_bottle.png", "fit": "contain"})
        else:
            els.append({"id": "product", "type": "image", "x": (W - s) / 2 if not left else x, "y": y, "width": s,
                        "height": s, "z_index": 2, "asset_id": "solstice_bottle.png", "fit": "contain"})
            y += s + 30 * u
        if rng.random() < 0.25:
            s2 = s * 0.5
            els.append({"id": "product2", "type": "image", "x": W - m - s2, "y": max(m, y - s2 - 30 * u),
                        "width": s2, "height": s2, "z_index": 2, "asset_id": "solstice_bottle.png", "fit": "contain"})
    if rng.random() < 0.7:
        bfs = round(rng.choice([24, 28, 32]) * u)
        body = phrase(rng, 6, 28)
        bh = bfs * 1.3 * max(1, min(5, len(body) * bfs * 0.5 / colw + 1))
        els.append({"id": "body", "type": "text", "x": x, "y": y, "width": colw, "height": bh, "z_index": 3,
                    "content": body, "font_family": "Solstice Sans", "font_size": bfs,
                    "color": "rgba(255,255,255,0.85)", "text_align": align})
        y += bh + 30 * u
    if rng.random() < 0.3:
        n = rng.randint(2, 3)
        bw, gap = 220 * u, 20 * u
        x0 = x if left else (W - (n * bw + (n - 1) * gap)) / 2
        for i in range(n):
            els.append({"id": f"b{i}_bg", "type": "shape", "x": x0 + i * (bw + gap), "y": y, "width": bw,
                        "height": 48 * u, "z_index": 3, "shape_type": "rectangle", "group_id": f"b{i}",
                        "fill_color": "rgba(43,27,46,1)", "corner_radius": 24 * u})
            els.append({"id": f"b{i}_label", "type": "text", "x": x0 + i * (bw + gap), "y": y + 12 * u, "width": bw,
                        "height": 26 * u, "z_index": 4, "content": phrase(rng, 1, 2, True).upper(),
                        "group_id": f"b{i}", "font_family": "Solstice Sans", "font_size": round(15 * u),
                        "font_weight": "bold", "color": "rgba(255,255,255,1)", "text_align": "center"})
        y += 70 * u
    if rng.random() < 0.85:
        cw, ch = 380 * u, 88 * u
        els.append({"id": "cta_bg", "type": "shape", "x": x if left else (W - cw) / 2, "y": y, "width": cw,
                    "height": ch, "z_index": 3, "shape_type": "rectangle", "group_id": "cta",
                    "fill_color": "rgba(232,106,58,1)", "corner_radius": ch / 2})
        els.append({"id": "cta_label", "type": "text", "x": x if left else (W - cw) / 2, "y": y + 22 * u,
                    "width": cw, "height": 44 * u, "z_index": 4, "content": phrase(rng, 2, 4, True),
                    "group_id": "cta", "font_family": "Solstice Sans", "font_size": round(26 * u),
                    "font_weight": "bold", "color": "rgba(255,255,255,1)", "text_align": "center"})
        y += ch + 30 * u
    if logo_pos in ("bottom", "corner"):
        ly = H - m - lh
        lx = (W - lw) / 2 if logo_pos == "bottom" else W - m - lw
        els.append({"id": "logo", "type": "image", "x": lx, "y": ly, "width": lw, "height": lh, "z_index": 3,
                    "asset_id": "solstice_logo_lockup.png", "fit": "contain"})
    if rng.random() < 0.25:
        els.append({"id": "rib_bg", "type": "shape", "x": W - 320 * u, "y": 40 * u, "width": 280 * u,
                    "height": 50 * u, "rotation": -10, "z_index": 5, "shape_type": "rectangle",
                    "group_id": "rib", "fill_color": "rgba(220,60,50,1)"})
        els.append({"id": "rib_label", "type": "text", "x": W - 320 * u, "y": 50 * u, "width": 280 * u,
                    "height": 30 * u, "rotation": -10, "z_index": 6, "content": phrase(rng, 1, 2, True).upper(),
                    "group_id": "rib", "font_family": "Solstice Sans", "font_size": round(20 * u),
                    "font_weight": "bold", "color": "rgba(255,255,255,1)", "text_align": "center"})
    if rng.random() < 0.4:
        s = min(W, H) * 0.45
        els.append({"id": "deco", "type": "shape", "x": rng.choice([-s / 3, W - s * 2 / 3]), "y": rng.choice([-s / 3, H - s * 2 / 3]),
                    "width": s, "height": s, "z_index": 1, "shape_type": "ellipse",
                    "fill_color": "rgba(255,255,255,1)", "opacity": 0.12})
    # keep the design itself on its canvas so results are comparable
    if y > H - m:
        k = (H - m) / y
        for e in els[1:]:
            if e["id"] != "deco" and not (logo_pos in ("bottom", "corner") and e["id"] == "logo"):
                e["y"] *= k
                e["height"] *= k
                if e["type"] == "text":
                    e["font_size"] = max(8, round(e["font_size"] * k))
                if e["type"] == "image":
                    e["width"] *= k
    return {"canvas": {"width": W, "height": H}, "elements": els}


def red_flags(src: dict, out: dict, rep: dict) -> list[str]:
    el = {e["id"]: e for e in out["elements"]}
    flags = []
    vis = lambda i: i in el and el[i].get("opacity", 1) > 0
    if vis("headline"):
        texts = [e for e in out["elements"] if e["type"] == "text" and e.get("opacity", 1) > 0]
        if any(t["font_size"] > el["headline"]["font_size"] for t in texts if t["id"] != "headline"):
            flags.append("headline not the biggest text")
        if el["headline"]["font_size"] < 9:
            flags.append(f"headline {el['headline']['font_size']}px")
    for i in ("logo", "cta_label"):
        if i in el and not vis(i):
            flags.append(f"{i} hidden")
    if vis("logo") and el["logo"]["height"] < 14:
        flags.append("logo speck")
    return flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--render", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    rows = []
    for i in range(args.n):
        src = design(rng)
        for f in FORMATS:
            tc = {"width": f["width"], "height": f["height"]}
            out, rep = adapt(src, tc)
            rows.append({"i": i, "fmt": f["key"], "score": rep["candidates"][0]["score"], "chosen": rep["chosen"],
                         "problems": check(src, out), "flags": red_flags(src, out, rep), "src": src, "tc": tc,
                         "out": out, "ms": rep["ms"]})
    probs = [r for r in rows if [p for p in r["problems"] if "overflows" not in p]]
    flagged = [r for r in rows if r["flags"]]
    from collections import Counter
    c = Counter(f.split(" ")[0] + " " + " ".join(f.split(" ")[1:3]) if "px" not in f else "headline <9px"
                for r in flagged for f in r["flags"])
    print(f"{len(rows)} runs, {len(probs)} with structural problems, {len(flagged)} flagged, "
          f"mean score {sum(r['score'] for r in rows) / len(rows):.3f}, max {max(r['ms'] for r in rows):.0f}ms")
    for k, v in c.most_common():
        print(f"  {v:4}  {k}")
    by_fmt = Counter(r["fmt"] for r in flagged)
    print("  flagged by format:", dict(by_fmt.most_common()))
    worst = sorted(rows, key=lambda r: (-len(r["flags"]), r["score"]))[:max(args.render, 10)]
    for r in worst[:10]:
        print(f"  design {r['i']:3} {r['fmt']:13} {r['score']:.3f} {r['chosen']:40} {r['flags']}")
    if args.render:
        from engine.resize import stretch
        from renderer.converter.convert import render_design_to_png
        d = Path("output/stress")
        d.mkdir(parents=True, exist_ok=True)
        for r in worst[:args.render]:
            stem = d / f"d{r['i']:03}_{r['fmt']}"
            render_design_to_png(r["out"], "brand_kit/assets", f"{stem}.png")
            render_design_to_png(r["src"], "brand_kit/assets", f"{stem}_src.png")
            Path(f"{stem}.json").write_text(json.dumps({"source": r["src"], "target_canvas": r["tc"]}))
    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
