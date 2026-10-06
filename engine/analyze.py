"""Read a design's structure from geometry alone.

The input has no semantic labels (FAQ Q1), only ids, types, geometry,
z-order and group_ids. This module turns that into *blocks* (units that
move together) with an inferred *role* and *priority*, plus a short human
readable reason for every decision so the result can be explained.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ASSETS_DIR = Path(os.environ.get("CHAMELEON_ASSETS_DIR", "brand_kit/assets"))

PRIORITY = {
    "headline": 100, "logo": 90, "cta": 85, "hero": 80, "body": 60,
    "image": 50, "badge": 45, "badges": 45, "sticker": 40, "tag": 40,
    "fineprint": 20, "unavailable": 5, "decoration": 0, "background": 0,
}

# Roles that are laid out in the main flow (everything else floats or fills).
FLOW_ROLES = {"headline", "logo", "cta", "hero", "body", "image", "badge", "badges", "fineprint"}


def num(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def rotated_aabb(w: float, h: float, deg: float) -> tuple[float, float]:
    r = math.radians(deg or 0.0)
    c, s = abs(math.cos(r)), abs(math.sin(r))
    return w * c + h * s, w * s + h * c


@dataclass
class Block:
    id: str
    role: str
    elements: list[dict[str, Any]]
    reason: str
    children: list["Block"] = field(default_factory=list)  # for rows

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.role, 30)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Union of element boxes, expanded for rotation (source px)."""
        xs0, ys0, xs1, ys1 = [], [], [], []
        for el in self.elements:
            w, h = num(el.get("width")), num(el.get("height"))
            aw, ah = rotated_aabb(w, h, num(el.get("rotation")))
            cx, cy = num(el.get("x")) + w / 2, num(el.get("y")) + h / 2
            xs0.append(cx - aw / 2); xs1.append(cx + aw / 2)
            ys0.append(cy - ah / 2); ys1.append(cy + ah / 2)
        return min(xs0), min(ys0), max(xs1), max(ys1)

    @property
    def w(self) -> float:
        b = self.bbox
        return max(1.0, b[2] - b[0])

    @property
    def h(self) -> float:
        b = self.bbox
        return max(1.0, b[3] - b[1])

    @property
    def center(self) -> tuple[float, float]:
        b = self.bbox
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    @property
    def is_text(self) -> bool:
        return len(self.elements) == 1 and self.elements[0].get("type") == "text"

    @property
    def text_el(self) -> dict[str, Any] | None:
        texts = [e for e in self.elements if e.get("type") == "text"]
        return max(texts, key=lambda e: num(e.get("font_size"), 1)) if texts else None


@dataclass
class Analysis:
    canvas: tuple[float, float]
    background: list[Block]
    decoration: list[Block]
    flow: list[Block]        # reading order (top-to-bottom, left-to-right)
    floating: list[Block]    # stickers / corner tags, re-anchored after layout
    notes: list[str]

    def all_blocks(self) -> list[Block]:
        return self.background + self.decoration + self.flow + self.floating


def _area(el: dict[str, Any]) -> float:
    return max(0.0, num(el.get("width"))) * max(0.0, num(el.get("height")))


def _contains_point(el: dict[str, Any], px: float, py: float) -> bool:
    x, y = num(el.get("x")), num(el.get("y"))
    return x <= px <= x + num(el.get("width")) and y <= py <= y + num(el.get("height"))


def _asset_missing(el: dict[str, Any]) -> bool:
    if not ASSETS_DIR.is_dir():
        return False  # can't tell; don't penalise
    aid = el.get("asset_id")
    return not aid or not (ASSETS_DIR / str(aid)).is_file()


def analyze(source: dict[str, Any]) -> Analysis:
    canvas = source.get("canvas") or {}
    elements = [e for e in source.get("elements") or [] if isinstance(e, dict) and "id" in e]
    W0 = num(canvas.get("width")) or max((num(e.get("x")) + num(e.get("width")) for e in elements), default=1)
    H0 = num(canvas.get("height")) or max((num(e.get("y")) + num(e.get("height")) for e in elements), default=1)
    canvas_area = W0 * H0
    notes: list[str] = []

    background: list[Block] = []
    remaining: list[dict[str, Any]] = []
    for el in sorted(elements, key=lambda e: num(e.get("z_index"))):
        t = el.get("type")
        covers = _area(el) >= 0.85 * canvas_area
        if t in ("image", "shape") and covers and not el.get("group_id") and (
            t == "image" or num(el.get("opacity"), 1) >= 0.9
        ):
            background.append(Block(el["id"], "background", [el],
                                    f"{t} covering {100 * _area(el) / canvas_area:.0f}% of the canvas"))
        else:
            remaining.append(el)

    # Explicit groups, then implicit "text sitting on a shape" groups.
    groups: dict[str, list[dict[str, Any]]] = {}
    singles: list[dict[str, Any]] = []
    for el in remaining:
        gid = el.get("group_id")
        if gid:
            groups.setdefault(str(gid), []).append(el)
        else:
            singles.append(el)

    shapes = [e for e in singles if e.get("type") == "shape"]
    for txt in [e for e in singles if e.get("type") == "text"]:
        cx = num(txt.get("x")) + num(txt.get("width")) / 2
        cy = num(txt.get("y")) + num(txt.get("height")) / 2
        hosts = [s for s in shapes if _contains_point(s, cx, cy)
                 and num(s.get("opacity"), 1) >= 0.5 and _area(s) < 0.25 * canvas_area
                 and _area(s) <= 6 * max(1.0, _area(txt))]
        if hosts:
            host = min(hosts, key=_area)
            key = f"_implicit_{host['id']}"
            groups.setdefault(key, [host]).append(txt)
            singles.remove(txt)
            if host in singles:
                singles.remove(host)
            shapes.remove(host)
            notes.append(f"'{txt['id']}' sits on shape '{host['id']}', so they move as one unit")

    decoration: list[Block] = []
    flow: list[Block] = []
    floating: list[Block] = []

    for gid, els in groups.items():
        types = {e.get("type") for e in els}
        b = Block(gid, "group", els, "")
        rotated = any(abs(num(e.get("rotation"))) > 3 for e in els)
        if types == {"shape"}:
            b.role, b.reason = "decoration", "shape-only group"
            decoration.append(b)
        elif rotated:
            b.role, b.reason = "sticker", f"rotated group ({num(els[0].get('rotation')):.0f}°)"
            floating.append(b)
        elif "text" in types and "shape" in types:
            b.role, b.reason = "badge", "text on a filled shape (button-like)"
            flow.append(b)
        else:
            b.role, b.reason = "image", "mixed group kept rigid"
            flow.append(b)

    for el in singles:
        t = el.get("type")
        b = Block(el["id"], "", [el], "")
        if abs(num(el.get("rotation"))) > 3 and t != "shape":
            b.role, b.reason = "sticker", f"rotated {t}"
            floating.append(b)
        elif t == "shape":
            why = "translucent shape" if num(el.get("opacity"), 1) < 0.6 else "free-standing shape"
            b.role, b.reason = "decoration", why
            decoration.append(b)
        elif t == "text":
            b.role = "text"
            flow.append(b)
        elif t == "image":
            if _asset_missing(el):
                b.role, b.reason = "unavailable", f"asset '{el.get('asset_id')}' is not in the brand kit"
            else:
                b.role = "img"
            flow.append(b)
        else:
            b.role, b.reason = "image", f"unknown type '{t}', kept rigid"
            flow.append(b)

    _assign_text_roles([b for b in flow if b.role == "text"], H0, notes, min(W0, H0))
    _assign_image_roles([b for b in flow if b.role == "img"], W0, H0, canvas_area)
    _assign_action_roles([b for b in flow if b.role == "badge"])

    # Unavailable images float: they can't be shown meaningfully anyway.
    for b in [b for b in flow if b.role == "unavailable"]:
        flow.remove(b)
        floating.append(b)

    # Small badges hugging a corner stay corner-anchored ("tags").
    for b in [b for b in flow if b.role == "badge"]:
        x0, y0, x1, y1 = b.bbox
        near_x = x0 < 0.12 * W0 or x1 > 0.88 * W0
        near_y = y0 < 0.12 * H0 or y1 > 0.88 * H0
        if near_x and near_y and b.w * b.h < 0.06 * canvas_area:
            b.role, b.reason = "tag", b.reason + "; hugs a corner, so it stays corner-anchored"
            flow.remove(b)
            floating.append(b)

    flow = _merge_rows(flow)
    flow.sort(key=lambda b: (round(b.center[1] / max(1.0, 0.04 * H0)), b.center[0]))
    return Analysis((W0, H0), background, decoration, flow, floating, notes)


def _text_weight(el: dict[str, Any]) -> float:
    return num(el.get("font_size"), 1) * (1.12 if str(el.get("font_weight")) == "bold" else 1.0)


def _assign_text_roles(blocks: list[Block], H0: float, notes: list[str], short_side: float = 1080.0) -> None:
    if not blocks:
        return
    ranked = sorted(blocks, key=lambda b: (_text_weight(b.elements[0]), b.w * b.h), reverse=True)
    top = ranked[0]
    top_size = num(top.elements[0].get("font_size"), 1)
    top.role, top.reason = "headline", f"largest type ({top_size:.0f}px)"
    for b in ranked[1:]:
        el = b.elements[0]
        fs = num(el.get("font_size"), 1)
        ratio = fs / max(1.0, top_size)
        near_edge = b.center[1] > 0.88 * H0 or b.center[1] < 0.06 * H0
        tiny = fs <= 0.016 * short_side  # legal-size type relative to the canvas
        if ratio <= 0.2 or (ratio <= 0.35 and tiny and (near_edge or len(str(el.get("content", ""))) > 80)):
            b.role, b.reason = "fineprint", f"{fs:.0f}px is {ratio:.0%} of the headline size"
        else:
            b.role, b.reason = "body", f"{fs:.0f}px supporting text"


def _assign_image_roles(blocks: list[Block], W0: float, H0: float, canvas_area: float) -> None:
    if not blocks:
        return
    largest = max(blocks, key=lambda b: b.w * b.h)
    for b in blocks:
        aspect = b.w / b.h
        frac = b.w * b.h / canvas_area
        top = b.center[1] < 0.3 * H0
        if aspect >= 1.6 and frac <= 0.12 and (top or b is not largest or frac < 0.04):
            b.role, b.reason = "logo", f"wide ({aspect:.1f}:1), small, {'near the top' if top else 'secondary'}"
        elif b is largest and frac >= 0.04:
            b.role, b.reason = "hero", f"largest image ({frac:.0%} of the canvas)"
        else:
            b.role, b.reason = "image", "secondary image"
    logos = [b for b in blocks if b.role == "logo"]
    for extra in sorted(logos, key=lambda b: b.center[1])[1:]:
        extra.role, extra.reason = "image", "wide image below the main logo"


def _assign_action_roles(blocks: list[Block]) -> None:
    if not blocks:
        return
    def size(b: Block) -> float:
        te = b.text_el
        return b.w * b.h * (1 + 0.02 * num(te.get("font_size"), 1) if te else 1)
    cta = max(blocks, key=size)
    others = [b for b in blocks if b is not cta]
    if not others or size(cta) >= 1.4 * max(size(o) for o in others):
        cta.role, cta.reason = "cta", "largest button-like group"


def _merge_rows(flow: list[Block]) -> list[Block]:
    """Badges that share a horizontal band become one row block."""
    badges = sorted([b for b in flow if b.role == "badge"], key=lambda b: b.center[1])
    used: set[int] = set()
    rows: list[Block] = []
    for i, b in enumerate(badges):
        if i in used:
            continue
        members = [b]
        for j in range(i + 1, len(badges)):
            o = badges[j]
            ov = min(b.bbox[3], o.bbox[3]) - max(b.bbox[1], o.bbox[1])
            if j not in used and ov >= 0.5 * min(b.h, o.h):
                members.append(o)
                used.add(j)
        if len(members) > 1:
            members.sort(key=lambda m: m.center[0])
            row = Block("row:" + "+".join(m.id for m in members), "badges",
                        [e for m in members for e in m.elements],
                        f"{len(members)} badges in one row", children=members)
            rows.append(row)
            for m in members:
                flow.remove(m)
    return flow + rows
