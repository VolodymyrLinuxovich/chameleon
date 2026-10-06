"""Text measurement that matches the official renderer.

The renderer wraps text greedily at real Skia glyph widths using the brand
fonts, then draws line i at y = i * font_size * line_height (top aligned),
with font_size truncated to an int. We reuse the renderer's own font loader
and wrap function when they are importable, so "fits" here means "fits"
in the rendered PNG. If they are not importable (no skia, no brand kit) we
fall back to a conservative average-glyph-width estimate.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

FONTS_DIR = Path(os.environ.get("CHAMELEON_FONTS_DIR", "brand_kit/fonts"))

try:  # same code path the renderer uses
    from renderer.converter.brand_fonts import load_brand_font_manager
    from renderer.converter.wrap import char_widths as _char_widths
    from renderer.converter.wrap import wrap_text as _wrap_text

    _FONT_MANAGER = load_brand_font_manager(str(FONTS_DIR))
    BACKEND = "skia"
except Exception:  # pragma: no cover - exercised only without the renderer
    _FONT_MANAGER = None
    BACKEND = "estimate"

    def _wrap_text(text: str, widths: list[float], max_width: float) -> str:
        chars, line_w, last_space = list(text), 0.0, None
        for i, c in enumerate(chars):
            if c == "\n":
                line_w, last_space = 0.0, None
                continue
            w = widths[i]
            if line_w + w > max_width and last_space is not None:
                chars[last_space] = "\n"
                line_w = sum(widths[j] for j in range(last_space + 1, i + 1))
                last_space = None
            else:
                line_w += w
            if c == " ":
                last_space = i
        return "".join(chars)


def _style(el: dict[str, Any]) -> tuple[str, str]:
    bold = str(el.get("font_weight", "regular")).lower() == "bold"
    italic = str(el.get("font_style", "normal")).lower() == "italic"
    weight = "bold" if bold else "regular"
    if bold and italic:
        return weight, "bolditalic"
    if bold:
        return weight, "bold"
    return weight, "italic" if italic else "regular"


@lru_cache(maxsize=20000)
def _widths(family: str, weight: str, style: str, size: int, text: str) -> tuple[float, ...]:
    if _FONT_MANAGER is not None:
        try:
            return tuple(_char_widths(_FONT_MANAGER, family, weight, style, float(size), text))
        except Exception:
            pass
    k = 0.62 if weight == "bold" else 0.56  # generous average advance / em
    return tuple((0.3 if c == " " else k) * size for c in text)


@lru_cache(maxsize=50000)
def _measure(family: str, weight: str, style: str, size: int, text: str,
             box_w: float, line_height: float, letter_spacing: float) -> tuple[int, float, float]:
    widths = _widths(family, weight, style, size, text)
    wrapped = _wrap_text(text, list(widths), box_w) if text else ""
    lines, idx = [], 0
    for line in wrapped.split("\n"):
        w = sum(widths[idx + j] for j in range(len(line))) + letter_spacing * max(0, len(line) - 1)
        lines.append(w)
        idx += len(line) + 1
    n = max(1, len(lines))
    lh = line_height or 1.2
    height = (n - 1) * size * lh + size * max(lh, 1.25)
    return n, max(lines) if lines else 0.0, height


def measure(el: dict[str, Any], size: int, box_w: float) -> tuple[int, float, float]:
    """(line_count, widest_line_px, block_height_px) for `el` rendered at
    `size` px wrapped into `box_w` px."""
    weight, style = _style(el)
    return _measure(str(el.get("font_family", "")), weight, style, int(size),
                    str(el.get("content", "")), float(box_w),
                    float(el.get("line_height", 1.2) or 1.2),
                    float(el.get("letter_spacing", 0) or 0))


def fits(el: dict[str, Any], size: int, box_w: float, box_h: float) -> bool:
    n, widest, h = measure(el, size, box_w)
    max_lines = el.get("max_lines")
    if isinstance(max_lines, int) and max_lines > 0 and n > max_lines:
        return False
    return widest <= box_w + 0.5 and h <= box_h + 0.5


def fit_font(el: dict[str, Any], box_w: float, box_h: float, max_size: int, min_size: int = 1) -> int | None:
    """Largest integer font size in [min_size, max_size] whose wrapped text
    fits box_w x box_h, or None if even min_size doesn't fit."""
    max_size = max(min_size, int(max_size))
    if fits(el, max_size, box_w, box_h):
        return max_size
    if not fits(el, min_size, box_w, box_h):
        return None
    lo, hi = min_size, max_size  # lo fits, hi doesn't
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fits(el, mid, box_w, box_h):
            lo = mid
        else:
            hi = mid
    return lo
