"""Layout strategies: rebuild the analysed design on the target canvas.

Every strategy places *blocks* (rigid groups, reflowable text, rows of
badges) into regions of the target canvas. Rigid blocks scale uniformly so
images and buttons keep their proportions; text blocks reflow, i.e. keep
their font family and content but get a new box width and an integer font
size measured with the renderer's own glyph widths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from .analyze import Analysis, Block, num, rotated_aabb
from .textfit import fit_font, fits, measure


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float


@dataclass
class Fit:
    """A block sized for some region; position is filled in later."""
    block: Block
    w: float
    h: float
    scale: float = 1.0
    font: int | None = None          # text blocks
    per_line: int = 0                # rows: children per line
    x: float = 0.0
    y: float = 0.0


@dataclass
class Layout:
    name: str
    description: str
    fits: list[Fit] = field(default_factory=list)          # flow + floating, positioned
    hidden: dict[str, str] = field(default_factory=dict)   # element id -> reason
    overflow: bool = False


# ----------------------------------------------------------------------------
# Context shared by all strategies for one (source, target) pair
# ----------------------------------------------------------------------------

@dataclass
class Ctx:
    a: Analysis
    W: float
    H: float
    allow_hide: bool

    @property
    def W0(self) -> float:
        return self.a.canvas[0]

    @property
    def H0(self) -> float:
        return self.a.canvas[1]

    @property
    def s_area(self) -> float:
        return math.sqrt(self.W * self.H / (self.W0 * self.H0))

    @property
    def s_cap(self) -> float:
        return 1.15 * self.s_area

    @property
    def margin(self) -> float:
        return max(4.0, min(80.0, 0.06 * min(self.W, self.H)))

    @property
    def src_gap(self) -> float:
        flow = sorted(self.a.flow, key=lambda b: b.bbox[1])
        gaps = [b.bbox[1] - p.bbox[3] for p, b in zip(flow, flow[1:]) if b.bbox[1] - p.bbox[3] > 0]
        g = sorted(gaps)[len(gaps) // 2] if gaps else 0.03 * self.H0
        return max(0.015 * self.H0, min(0.04 * self.H0, g))

    def text_cap(self, el: dict[str, Any]) -> int:
        fs = num(el.get("font_size"), 12)
        return max(1, int(max(fs * self.s_cap, min(fs, 0.4 * self.H))))


# ----------------------------------------------------------------------------
# Sizing primitives
# ----------------------------------------------------------------------------

def _row_gap(b: Block) -> float:
    kids = b.children
    gaps = [k.bbox[0] - p.bbox[2] for p, k in zip(kids, kids[1:])]
    return max(0.15 * min(k.h for k in kids), sum(gaps) / len(gaps)) if gaps else 0.0


def _row_dims(b: Block, s: float, per_line: int) -> tuple[float, float]:
    kids, gap = b.children, _row_gap(b) * s
    lines = [kids[i:i + per_line] for i in range(0, len(kids), per_line)]
    w = max(sum(k.w * s for k in ln) + gap * (len(ln) - 1) for ln in lines)
    h = sum(max(k.h for k in ln) * s for ln in lines) + gap * (len(lines) - 1)
    return w, h


def size_rigid(b: Block, s: float, max_w: float, max_h: float = math.inf) -> Fit:
    if b.children:
        best: Fit | None = None
        for k in range(len(b.children), 0, -1):
            w1, h1 = _row_dims(b, 1.0, k)
            se = min(s, max_w / w1, max_h / h1)
            if best is None or se > best.scale * 1.02:
                best = Fit(b, w1 * se, h1 * se, se, per_line=k)
        assert best is not None
        return best
    se = min(s, max_w / b.w, max_h / b.h)
    return Fit(b, b.w * se, b.h * se, se)


def size_text(b: Block, s: float, max_w: float, cap: int) -> Fit:
    el = b.elements[0]
    font = max(1, min(cap, int(num(el.get("font_size"), 12) * s)))
    width = max(1.0, min(max_w, b.w * s * 1.25))
    n, widest, h = measure(el, font, width)
    while widest > width + 0.5 and font > 1:  # one very long word
        font -= 1
        n, widest, h = measure(el, font, width)
    return Fit(b, width, h, s, font=font)


def size_block(ctx: Ctx, b: Block, s: float, max_w: float) -> Fit:
    if b.is_text:
        return size_text(b, s, max_w, ctx.text_cap(b.elements[0]))
    return size_rigid(b, s, max_w)


def _anchor(ctx: Ctx, b: Block) -> str:
    f = b.center[0] / ctx.W0
    return "center" if 0.4 <= f <= 0.6 else ("left" if f < 0.4 else "right")


# ----------------------------------------------------------------------------
# Vertical stack: the workhorse for portrait, square and column regions
# ----------------------------------------------------------------------------

def stack(ctx: Ctx, blocks: list[Block], box: Box, s_cap: float | None = None,
          anchor_edges: bool = True, h_align: str | None = None) -> tuple[list[Fit], bool]:
    """Place `blocks` top-to-bottom in `box`, finding the largest common
    scale that fits. Returns (fits, overflow)."""
    if not blocks:
        return [], False
    s_cap = s_cap or ctx.s_cap

    def attempt(s: float) -> tuple[list[Fit], float, float]:
        fs = [size_block(ctx, b, s, box.w) for b in blocks]
        gap = ctx.src_gap * s
        return fs, sum(f.h for f in fs) + gap * (len(fs) - 1), gap

    fs, total, gap = attempt(s_cap)
    overflow = False
    if total > box.h:
        lo, hi = 1e-3, s_cap
        fs_lo, total_lo, gap_lo = attempt(lo)
        if total_lo > box.h:
            fs, total, gap, overflow = fs_lo, total_lo, gap_lo, True
        else:
            for _ in range(28):
                mid = (lo + hi) / 2
                if attempt(mid)[1] <= box.h:
                    lo = mid
                else:
                    hi = mid
            fs, total, gap = attempt(lo)

    # Vertical distribution: keep top/bottom anchoring from the source.
    n = len(fs)
    top_n = 0
    bot_n = 0
    if anchor_edges and n >= 3:
        while top_n < n - 1 and fs[top_n].block.center[1] < 0.2 * ctx.H0:
            top_n += 1
        while bot_n < n - 1 - top_n and fs[n - 1 - bot_n].block.center[1] > 0.86 * ctx.H0:
            bot_n += 1
    top, mid, bot = fs[:top_n], fs[top_n:n - bot_n], fs[n - bot_n:]

    def run(group: list[Fit], y: float, g: float) -> float:
        for f in group:
            f.y = y
            y += f.h + g
        return y - g if group else y

    leftover = max(0.0, box.h - total)
    if top or bot:
        y_end = run(top, box.y, gap)
        bot_h = sum(f.h for f in bot) + gap * max(0, len(bot) - 1)
        run(bot, box.y + box.h - bot_h, gap)
        region_top = y_end + (gap if top else 0)
        region_bot = box.y + box.h - bot_h - (gap if bot else 0)
        mid_h = sum(f.h for f in mid)
        space = region_bot - region_top - mid_h
        g = gap if len(mid) < 2 else max(gap, min(gap * 1.5, space / (len(mid) + 1)))
        mid_total = mid_h + g * max(0, len(mid) - 1)
        run(mid, region_top + (space - (mid_total - mid_h)) / 2, g)
    else:
        g = gap + min(gap * 0.5, leftover / (n + 1)) if n > 1 else gap
        tot = sum(f.h for f in fs) + g * (n - 1)
        run(fs, box.y + (box.h - tot) / 2, g)

    for f in fs:
        al = h_align or _anchor(ctx, f.block)
        f.x = box.x + {"left": 0.0, "center": (box.w - f.w) / 2, "right": box.w - f.w}[al]
    return fs, overflow


# ----------------------------------------------------------------------------
# Horizontal strip: leaderboards and extreme banners
# ----------------------------------------------------------------------------

STRIP_H_CAP = {"logo": 0.7, "hero": 0.95, "cta": 0.75, "badges": 0.7, "badge": 0.7,
               "tag": 0.7, "sticker": 0.85, "image": 0.8}
TEXT_WEIGHT = {"headline": 3.0, "body": 2.0, "fineprint": 1.2}


def _readable_floor(b: Block) -> float:
    """Smallest scale at which a rigid block still reads (label >= 11px, logo >= 36px tall)."""
    fonts = [num(e.get("font_size"), 12) for e in b.elements if e.get("type") == "text"]
    if fonts:
        return 11.0 / max(1.0, min(fonts))
    if b.role == "logo":
        return 36.0 / b.h
    return 0.0


def strip(ctx: Ctx, blocks: list[Block], box: Box, text_share: float) -> tuple[list[Fit], bool]:
    rigid = [b for b in blocks if not b.is_text]
    texts = [b for b in blocks if b.is_text]
    fits_: dict[str, Fit] = {}
    for b in rigid:
        cap_h = STRIP_H_CAP.get(b.role, 0.8) * box.h
        s = min(cap_h / b.h, max(ctx.s_cap, _readable_floor(b)))
        fits_[b.id] = size_rigid(b, s, math.inf, cap_h)
    gap_min = max(4.0, 0.25 * ctx.margin)
    rigid_w = sum(fits_[b.id].w for b in rigid)
    budget = box.w - gap_min * (len(blocks) - 1)
    max_rigid = budget * (1 - text_share) if texts else budget
    if rigid_w > max_rigid > 0:
        k = max_rigid / rigid_w
        for b in rigid:
            fits_[b.id] = size_rigid(b, fits_[b.id].scale * k, math.inf, box.h)
        rigid_w = sum(fits_[b.id].w for b in rigid)
    text_budget = max(1.0, budget - rigid_w)
    wsum = sum(TEXT_WEIGHT.get(b.role, 1.5) for b in texts) or 1.0
    overflow = False
    for b in texts:
        el = b.elements[0]
        alloc = text_budget * TEXT_WEIGHT.get(b.role, 1.5) / wsum
        font = fit_font(el, alloc, box.h * 0.92, ctx.text_cap(el))
        if font is None:
            font, overflow = 1, True
        _, widest, h = measure(el, font, alloc)
        fits_[b.id] = Fit(b, min(alloc, widest + 2), h, font=font)

    ordered = [fits_[b.id] for b in blocks]
    used = sum(f.w for f in ordered)
    n = len(ordered)
    gap = (box.w - used) / (n - 1) if n > 1 else 0.0
    gap = max(gap_min, min(gap, 0.08 * ctx.W))
    total = used + gap * (n - 1)
    x = box.x + max(0.0, (box.w - total) / 2)
    for f in ordered:
        f.x, f.y = x, box.y + (box.h - f.h) / 2
        x += f.w + gap
    return ordered, overflow or total > box.w + 1


# ----------------------------------------------------------------------------
# Floating elements (stickers, corner tags) and hidden elements
# ----------------------------------------------------------------------------

def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def fit_box(f: Fit) -> tuple[float, float, float, float]:
    return f.x, f.y, f.x + f.w, f.y + f.h


def place_floating(ctx: Ctx, lay: Layout, b: Block, base_scale: float) -> None:
    if b.role == "unavailable" and ctx.allow_hide:
        lay.hidden[b.elements[0]["id"]] = "asset file is missing, so it is skipped (allowed by the brief)"
        return
    m = 0.5 * ctx.margin
    cx, cy = b.center
    pref = ("l" if cx < ctx.W0 / 2 else "r", "t" if cy < ctx.H0 / 2 else "b")
    corners = [pref, (pref[0], "b" if pref[1] == "t" else "t"),
               ("r" if pref[0] == "l" else "l", pref[1]),
               ("r" if pref[0] == "l" else "l", "b" if pref[1] == "t" else "t")]
    s0 = min(max(base_scale, _readable_floor(b)), 0.4 * ctx.W / b.w, 0.4 * ctx.H / b.h)
    occupied = [fit_box(f) for f in lay.fits]
    best: tuple[float, Fit] | None = None
    for corner in corners:
        for k in (1.0, 0.85, 0.7):
            f = size_rigid(b, s0 * k, math.inf)
            f.x = m if corner[0] == "l" else ctx.W - m - f.w
            f.y = m if corner[1] == "t" else ctx.H - m - f.h
            ov = sum(_overlap(fit_box(f), o) for o in occupied)
            if best is None or ov < best[0] - 1e-6:
                best = (ov, f)
            if ov == 0:
                break
        if best and best[0] == 0:
            break
    assert best is not None
    if best[0] > 0 and ctx.allow_hide and b.priority <= PRIORITY_HIDEABLE:
        for el in b.elements:
            lay.hidden[el["id"]] = "no free corner without covering content"
        return
    lay.fits.append(best[1])


PRIORITY_HIDEABLE = 45


# ----------------------------------------------------------------------------
# Strategies
# ----------------------------------------------------------------------------

def _content_box(ctx: Ctx) -> Box:
    m = ctx.margin
    return Box(m, m, ctx.W - 2 * m, ctx.H - 2 * m)


def _median_scale(fs: list[Fit]) -> float:
    sc = sorted(f.scale for f in fs if not f.block.is_text) or [1.0]
    return sc[len(sc) // 2]


def _finish(ctx: Ctx, lay: Layout, floating: list[Block]) -> Layout:
    base = _median_scale(lay.fits) if lay.fits else ctx.s_area
    for b in floating:
        place_floating(ctx, lay, b, base)
    return lay


def strat_stack(ctx: Ctx) -> Layout:
    lay = Layout("stack", "Single column in the original reading order; top and bottom anchors kept.")
    lay.fits, lay.overflow = stack(ctx, ctx.a.flow, _content_box(ctx))
    return _finish(ctx, lay, ctx.a.floating)


def strat_proportional(ctx: Ctx) -> Layout:
    lay = Layout("proportional", "Whole composition scaled uniformly and centred (keeps every relative position).")
    s = min(ctx.W / ctx.W0, ctx.H / ctx.H0)
    ox, oy = (ctx.W - ctx.W0 * s) / 2, (ctx.H - ctx.H0 * s) / 2
    for b in ctx.a.flow + ctx.a.floating:
        if b.role == "unavailable" and ctx.allow_hide:
            lay.hidden[b.id] = "asset file is missing, so it is skipped (allowed by the brief)"
            continue
        if b.is_text:
            el = b.elements[0]
            f = Fit(b, b.w * s, b.h * s, s, font=max(1, int(num(el.get("font_size"), 12) * s)))
        else:
            f = Fit(b, b.w * s, b.h * s, s, per_line=len(b.children))
        f.x, f.y = ox + b.bbox[0] * s, oy + b.bbox[1] * s
        lay.fits.append(f)
    return lay


def strat_split(ctx: Ctx, hero_side: str, frac: float) -> Layout | None:
    hero = next((b for b in ctx.a.flow if b.role == "hero"), None)
    if hero is None:
        return None
    lay = Layout(f"split-{hero_side}-{int(frac * 100)}",
                 f"Hero image on the {hero_side} ({int(frac * 100)}% of the width), message stacked beside it.")
    cb = _content_box(ctx)
    gap = ctx.margin
    hw = (cb.w - gap) * frac
    hf = size_rigid(hero, 1.6 * ctx.s_cap, hw, cb.h)
    rest_w = cb.w - gap - hf.w
    if hero_side == "left":
        hf.x, rx = cb.x, cb.x + hf.w + gap
    else:
        hf.x, rx = cb.x + cb.w - hf.w, cb.x
    hf.y = cb.y + (cb.h - hf.h) / 2
    rest = [b for b in ctx.a.flow if b is not hero]
    fs, lay.overflow = stack(ctx, rest, Box(rx, cb.y, rest_w, cb.h), h_align="center")
    lay.fits = [hf] + fs
    return _finish(ctx, lay, ctx.a.floating)


def strat_columns(ctx: Ctx) -> Layout | None:
    """hero | message | actions — for wide banners."""
    flow = ctx.a.flow
    hero = next((b for b in flow if b.role == "hero"), None)
    actions = [b for b in flow if b.role in ("cta", "badge", "badges")]
    message = [b for b in flow if b is not hero and b not in actions]
    if not actions or not message:
        return None
    lay = Layout("columns", "Three columns: hero, message, actions (reads left to right like the original read top to bottom).")
    cb = _content_box(ctx)
    gap = ctx.margin
    x = cb.x
    fits_: list[Fit] = []
    if hero is not None:
        hf = size_rigid(hero, 1.6 * ctx.s_cap, (cb.w - 2 * gap) * 0.3, cb.h)
        hf.x, hf.y = x, cb.y + (cb.h - hf.h) / 2
        fits_.append(hf)
        x += hf.w + gap
    rem = cb.x + cb.w - x
    mw = (rem - gap) * 0.6
    fm, o1 = stack(ctx, message, Box(x, cb.y, mw, cb.h), anchor_edges=False, h_align="center")
    fa, o2 = stack(ctx, actions, Box(x + mw + gap, cb.y, rem - mw - gap, cb.h),
                   anchor_edges=False, h_align="center")
    lay.fits, lay.overflow = fits_ + fm + fa, o1 or o2
    return _finish(ctx, lay, ctx.a.floating)


def strat_strip(ctx: Ctx, drop: tuple[str, ...], text_share: float) -> Layout:
    tag = "+".join(drop) if drop else "all"
    lay = Layout(f"strip-{tag}-{int(text_share * 100)}",
                 "One row, left to right in the original reading order" +
                 (f"; {', '.join(drop)} dropped to keep the rest readable" if drop else "") + ".")
    blocks: list[Block] = []
    for b in sorted(ctx.a.flow + [f for f in ctx.a.floating if f.role != "unavailable"],
                    key=lambda b: (b.center[1], b.center[0])):
        if b.role in drop:
            for el in b.elements:
                lay.hidden[el["id"]] = f"{b.role} can't be shown at a readable size in a {ctx.W:.0f}x{ctx.H:.0f} strip"
        else:
            blocks.append(b)
    # Stickers and tags go last so the row ends with an accent, logo first.
    blocks.sort(key=lambda b: (b.role in ("sticker", "tag"), b.role != "logo"))
    m = max(4.0, 0.12 * ctx.H) if ctx.H < 200 else ctx.margin
    box = Box(m * 1.5, m, ctx.W - 3 * m, ctx.H - 2 * m)
    lay.fits, lay.overflow = strip(ctx, blocks, box, text_share)
    rest = [b for b in ctx.a.floating if b.role == "unavailable"]
    return _finish(ctx, lay, rest)


def candidates(ctx: Ctx) -> list[Layout]:
    r = ctx.W / ctx.H
    out: list[Layout | None] = [strat_stack(ctx), strat_proportional(ctx)]
    if r >= 1.15:
        for side in ("left", "right"):
            for frac in (0.4, 0.5):
                out.append(strat_split(ctx, side, frac))
    if r >= 2.2:
        out.append(strat_columns(ctx))
    if r >= 3.0:
        roles = {b.role for b in ctx.a.flow + ctx.a.floating}
        drops: list[tuple[str, ...]] = [()]
        if ctx.allow_hide and ctx.H < 200:  # only drop content when the canvas is truly tight
            opts = [d for d in ("fineprint", "body", "badges", "badge", "tag", "sticker") if d in roles]
            acc: list[str] = []
            for d in opts:
                acc.append(d)
                drops.append(tuple(acc))
        for d in drops:
            for share in (0.45, 0.6):
                out.append(strat_strip(ctx, d, share))
    return [c for c in out if c is not None]


# ----------------------------------------------------------------------------
# Emit schema elements
# ----------------------------------------------------------------------------

def emit_rigid(b: Block, x: float, y: float, s: float) -> list[dict[str, Any]]:
    bx0, by0 = b.bbox[0], b.bbox[1]
    out = []
    for el in b.elements:
        n = dict(el)
        w, h = num(el.get("width")) * s, num(el.get("height")) * s
        cx = x + (num(el.get("x")) + num(el.get("width")) / 2 - bx0) * s
        cy = y + (num(el.get("y")) + num(el.get("height")) / 2 - by0) * s
        n.update(x=cx - w / 2, y=cy - h / 2, width=w, height=h)
        if el.get("type") == "text":
            fs = num(el.get("font_size"), 12)
            font = max(1, int(fs * s))
            src_fits = fits(el, int(fs), num(el.get("width")), num(el.get("height")))
            while src_fits and font > 1 and not fits(n, font, w, h):
                font -= 1
            n["font_size"] = font
        out.append(n)
    return out


def emit_fit(f: Fit) -> list[dict[str, Any]]:
    b = f.block
    if b.is_text and f.font is not None:
        n = dict(b.elements[0])
        n.update(x=f.x, y=f.y, width=f.w, height=f.h, font_size=f.font or 1)
        return [n]
    if b.children:
        out: list[dict[str, Any]] = []
        k = f.per_line or len(b.children)
        gap = _row_gap(b) * f.scale
        lines = [b.children[i:i + k] for i in range(0, len(b.children), k)]
        y = f.y
        for ln in lines:
            lw = sum(c.w * f.scale for c in ln) + gap * (len(ln) - 1)
            lh = max(c.h for c in ln) * f.scale
            x = f.x + (f.w - lw) / 2
            for c in ln:
                out += emit_rigid(c, x, y + (lh - c.h * f.scale) / 2, f.scale)
                x += c.w * f.scale + gap
            y += lh + gap
        return out
    return emit_rigid(b, f.x, f.y, f.scale)
