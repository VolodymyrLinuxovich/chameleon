"""Build the landing page (site/index.html) from current engine renders.

    python -m tools.evaluate --render
    python -m tools.evaluate --input samples/extra --render
    python -m tools.build_site

Embeds the stretch/result renders as WebP data URIs into site/template.html,
so the page is one static file plus site/resize.gif (deployable anywhere).
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
    body = Path("site/template.html").read_text().replace("__DATA__", json.dumps(data))
    body = body.replace("__CARD__", enc("docs/how-it-works.png", 1600, 900))
    logo = "data:image/svg+xml;base64," + base64.b64encode(Path("docs/logo.svg").read_bytes()).decode()
    body = body.replace("__LOGO__", logo)
    shutil.copyfile("docs/resize.gif", "site/resize.gif")
    title_end = body.index("</style>") + len("</style>")
    page = HEAD + body[:title_end] + "\n</head>\n<body>\n" + body[title_end:] + "\n</body>\n</html>\n"
    Path("site/index.html").write_text(page)
    print(f"site/index.html: {len(page) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
