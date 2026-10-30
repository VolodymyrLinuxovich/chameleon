"""Build docs/resize.gif: one design swept through many canvas sizes.

Each frame is a real engine result rendered by the official renderer, next to
the naive stretch of the same canvas. Run: python -m tools.make_gif
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from engine.chameleon import adapt
from renderer.converter.convert import render_design_to_png
from tools.evaluate import stretch

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "brand_kit" / "assets"
FONT = str(ROOT / "brand_kit" / "fonts" / "SolsticeSans-Regular.ttf")
FONT_B = str(ROOT / "brand_kit" / "fonts" / "SolsticeSans-Bold.ttf")

# Keyframes: (name, width, height). The sweep passes through every size between them.
KEYS = [
    ("Source square", 1080, 1080),
    ("Instagram story", 1080, 1920),
    ("Wide skyscraper", 160, 600),
    ("Instagram post", 1080, 1080),
    ("YouTube thumbnail", 1280, 720),
    ("LinkedIn banner", 1200, 628),
    ("Leaderboard", 728, 90),
    ("Mobile banner", 320, 50),
    ("Source square", 1080, 1080),
]
STEPS = 8          # in-between frames per leg
HOLD_MS, STEP_MS = 1500, 70  # time on each named size, and per in-between frame
W, H = 1000, 540   # GIF size
PANEL = (440, 380) # max box for each canvas
# Paper, ink and the darker brand orange, to match the light landing page.
BG, INK, MUTED, ACCENT, LINE = (251, 250, 247), (24, 22, 27), (110, 103, 116), (194, 70, 31), (220, 213, 202)


def sizes():
    out = []
    for (n0, w0, h0), (n1, w1, h1) in zip(KEYS, KEYS[1:]):
        out.append((n0, w0, h0))
        for i in range(1, STEPS + 1):
            t = i / (STEPS + 1)
            t = t * t * (3 - 2 * t)  # ease in and out
            w = round(w0 * (w1 / w0) ** t)
            h = round(h0 * (h1 / h0) ** t)
            out.append((None, w, h))
    return out


FAMILY = [("focus", "headline-first row"), ("strip", "one row"), ("columns", "three columns"),
          ("split", "image beside text"), ("stack", "one column"), ("proportional", "scaled as is")]


def plain(chosen: str) -> str:
    """Turn an internal candidate id like strip-all-61-cta7 into a readable name."""
    for key, name in FAMILY:
        if chosen.startswith(key):
            return name
    return chosen


def fit(img: Image.Image) -> Image.Image:
    s = min(PANEL[0] / img.width, PANEL[1] / img.height)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def main() -> None:
    src = json.load(open(ROOT / "input" / "chameleon_sample_level2_core.json"))["source"]
    f_title, f_lab, f_small = ImageFont.truetype(FONT_B, 26), ImageFont.truetype(FONT_B, 18), ImageFont.truetype(FONT, 16)
    frames, durs, cache = [], [], {}
    tmp = Path(tempfile.mkdtemp())
    for name, w, h in sizes():
        if (w, h) not in cache:
            tc = {"width": w, "height": h}
            design, rep = adapt(src, tc)
            a, b = tmp / "a.png", tmp / "b.png"
            render_design_to_png(stretch(src, tc), ASSETS, str(a))
            render_design_to_png(design, ASSETS, str(b))
            cache[(w, h)] = (fit(Image.open(a).convert("RGB")), fit(Image.open(b).convert("RGB")),
                             str(rep.get("chosen", "")), rep.get("ms", 0))
        sa, sb, chosen, ms = cache[(w, h)]
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.text((40, 30), "Chameleon", font=f_title, fill=INK)
        d.text((40 + d.textlength("Chameleon", font=f_title) + 14, 37), "Same design. Every canvas.", font=f_small, fill=MUTED)
        size_txt = f"{w} × {h}" + (f"   {name}" if name else "")
        d.text((W - 40 - d.textlength(size_txt, font=f_lab), 34), size_txt, font=f_lab, fill=ACCENT if name else INK)
        for i, (img, lab, sub) in enumerate([(sa, "Stretch", "what resize tools do"),
                                             (sb, "Chameleon", f"layout: {plain(chosen)}")]):
            cx = 40 + i * 480 + 220
            top = 90 + (PANEL[1] - img.height) // 2
            x0 = cx - img.width // 2
            d.rectangle([x0 - 1, top - 1, x0 + img.width, top + img.height], outline=LINE)
            im.paste(img, (x0, top))
            d.text((cx - d.textlength(lab, font=f_lab) / 2, 490), lab, font=f_lab, fill=ACCENT if i else MUTED)
            d.text((cx - d.textlength(sub, font=f_small) / 2, 512), sub, font=f_small, fill=MUTED)
        frames.append(im)
        durs.append(HOLD_MS if name else STEP_MS)
    out = ROOT / "docs" / "resize.gif"
    pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=durs, loop=0, optimize=True)
    print(out, len(frames), "frames", round(out.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
