"""Build the landing page (site/index.html) from current engine renders.

    python -m tools.evaluate --render
    python -m tools.evaluate --input samples/extra --render
    python -m tools.build_site

Embeds the stretch/result renders as WebP data URIs into site/template.html,
so the page is one static file plus site/studio.gif (deployable anywhere).
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image

from renderer.converter.convert import render_design_to_png

DESIGNS = [
    ("advanced", "chameleon_sample_level3_advanced", "input/chameleon_sample_level3_advanced.json",
     "Level 3 · Advanced", "17 elements, run-on headline, rotated ribbon, missing asset"),
    ("core", "chameleon_sample_level2_core", "input/chameleon_sample_level2_core.json",
     "Level 2 · Core", "11 elements, groups, translucent shapes"),
    ("event", "c_event_poster", "samples/extra/c_event_poster.json",
     "Event poster", "Our own test design: text only, left aligned, no image"),
]
FORMATS = [("ig_story", "Instagram Story", 1080, 1920), ("ig_post", "Instagram Post", 1080, 1080),
           ("yt_thumb", "YouTube Thumbnail", 1280, 720), ("li_banner", "LinkedIn Banner", 1584, 396),
           ("billboard", "Billboard Ad", 970, 250), ("leaderboard", "Leaderboard Ad", 728, 90),
           ("mobile_banner", "Mobile Banner", 320, 50), ("skyscraper", "Wide Skyscraper", 160, 600)]
HEAD = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="description" content="Chameleon rebuilds a finished design for any canvas size instead of stretching it.">\n')


def enc(path: str | Path, maxw: int = 1280, maxh: int = 1100) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((maxw, maxh), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=80)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


ROLE_COLORS = {"logo": (90, 160, 255), "hero": (90, 210, 130), "headline": (255, 200, 60), "body": (235, 235, 235),
               "badges": (190, 140, 255), "badge": (190, 140, 255), "cta": (255, 130, 70), "sticker": (255, 90, 160),
               "tag": (255, 90, 160), "fineprint": (170, 170, 170), "unavailable": (120, 120, 120)}
ROLE_NAMES = {"logo": "Logo", "hero": "Product", "headline": "Headline", "body": "Body text", "badges": "Badge row",
              "badge": "Badge", "cta": "Button", "sticker": "Sticker", "tag": "Tag", "fineprint": "Fine print",
              "unavailable": "Missing asset"}


def pipeline(tmp: str) -> dict:
    """One real resize, stage by stage, for the How it works section: the
    original, the roles the engine found, one candidate per layout family
    with its score, the winner's score breakdown and the result."""
    from PIL import ImageDraw
    from engine.chameleon import adapt
    task = json.loads(Path("input/chameleon_sample_level3_advanced.json").read_text())
    src = task["source"]
    W, H = 1584, 396
    design, rep = adapt(src, {"width": W, "height": H})
    orig = Path(tmp) / "pipe_orig.png"
    render_design_to_png(src, "brand_kit/assets", str(orig), max_size=1200)
    im = Image.open(orig).convert("RGB")
    k = im.width / src["canvas"]["width"]
    d = ImageDraw.Draw(im)
    els = {e["id"]: e for e in src["elements"]}
    found = []
    for r in rep["roles"]:
        col = ROLE_COLORS.get(r["role"])
        if not col:
            continue
        boxes = [els[i] for i in r["elements"] if i in els]
        x0 = min(e["x"] for e in boxes) * k; y0 = min(e["y"] for e in boxes) * k
        x1 = max(e["x"] + e["width"] for e in boxes) * k; y1 = max(e["y"] + e["height"] for e in boxes) * k
        d.rectangle([x0, y0, x1, y1], outline=col, width=max(3, int(4 * k * 2)))
        name = ROLE_NAMES.get(r["role"], r["role"])
        if name not in [f["name"] for f in found]:
            found.append({"name": name, "color": "#%02x%02x%02x" % col})
    roles_png = Path(tmp) / "pipe_roles.png"
    im.save(roles_png)
    best: dict = {}
    for c in rep["candidates"]:
        fam = c["name"].split("-")[0].split("·")[0]
        best.setdefault(fam, c)
    fam_names = {"columns": "Three columns", "split": "Image beside text", "strip": "One row", "stack": "One column",
                 "focus": "Headline-first row", "proportional": "Scaled as is"}
    cands = []
    for fam, c in list(best.items())[:4]:
        p = Path(tmp) / f"pipe_{fam}.png"
        render_design_to_png(c["design"], "brand_kit/assets", str(p))
        cands.append({"name": fam_names.get(fam, fam), "score": round(c["score"] * 100, 1),
                      "win": c["name"] == rep["chosen"], "img": enc(p, 1000, 300)})
    win = next(c for c in rep["candidates"] if c["name"] == rep["chosen"])
    part_names = {"readability": "Readability", "hierarchy": "Hierarchy", "space": "Use of space",
                  "consistency": "Consistency", "collisions": "No collisions", "completeness": "Completeness",
                  "fidelity": "Reading order", "balance": "Balance"}
    out = Path(tmp) / "pipe_out.png"
    render_design_to_png(design, "brand_kit/assets", str(out))
    return {"w": W, "h": H, "n": len(src["elements"]), "ms": round(rep["ms"]), "tried": len(rep["candidates"]),
            "orig": enc(orig, 600, 750), "roles": enc(roles_png, 600, 750), "found": found, "cands": cands,
            "parts": [{"name": part_names.get(k2, k2), "v": round(v * 100)} for k2, v in win["parts"].items()],
            "score": round(win["score"] * 100, 1), "out": enc(out, 1584, 396)}


def main() -> None:
    data = {"designs": [], "formats": [{"key": k, "name": n, "w": w, "h": h} for k, n, w, h in FORMATS]}
    with tempfile.TemporaryDirectory() as tmp:
        for key, stem, src, label, desc in DESIGNS:
            task = json.loads(Path(src).read_text())
            orig = Path(tmp) / f"{key}.png"
            render_design_to_png(task["source"], "brand_kit/assets", str(orig), max_size=1200)
            data["designs"].append({
                "key": key, "label": label, "desc": desc, "canvas": task["source"]["canvas"],
                "n": len(task["source"]["elements"]), "original": enc(orig, 600, 600),
                "pairs": {k: {"stretch": enc(f"output/eval/{stem}__{k}__stretch.png"),
                              "result": enc(f"output/eval/{stem}__{k}.png")} for k, *_ in FORMATS},
            })
        data["pipe"] = pipeline(tmp)
    body = Path("site/template.html").read_text().replace("__CSS__", "\n" + Path("site/style.css").read_text().split("\n", 1)[1])
    body = body.replace("__DATA__", json.dumps(data))
    body = body.replace("__CARD__", enc("docs/how-it-works.png", 1600, 900))
    logo = "data:image/svg+xml;base64," + base64.b64encode(Path("docs/logo.svg").read_bytes()).decode()
    body = body.replace("__LOGO__", logo)
    body = body.replace("__I18N__", Path("site/i18n.json").read_text())
    shutil.copyfile("docs/studio.gif", "site/studio.gif")
    title_end = body.index("</style>") + len("</style>")
    page = HEAD + body[:title_end] + "\n</head>\n<body>\n" + body[title_end:] + "\n</body>\n</html>\n"
    Path("site/index.html").write_text(page)
    print(f"site/index.html: {len(page) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
