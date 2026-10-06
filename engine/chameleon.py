"""Orchestrates analyse -> candidate layouts -> score -> pick, and keeps an
explanation of every decision."""

from __future__ import annotations

import copy
import re
import math
import os
import time
from typing import Any

from .analyze import Analysis, analyze, num, rotated_aabb
from .layout import Ctx, Layout, candidates, emit_fit
from .score import WEIGHTS, score
from .textfit import BACKEND, fits


READABLE = 0.8


def _allow_hide() -> bool:
    return os.environ.get("CHAMELEON_ALLOW_HIDE", "1") not in ("0", "false", "no")


def _r(v: float) -> float:
    return round(float(v), 4)


def _clamp(el: dict[str, Any], W: float, H: float) -> None:
    """Keep the element's (rotated) bounds inside the canvas."""
    w, h = max(0.0, num(el.get("width"))), max(0.0, num(el.get("height")))
    rot = num(el.get("rotation"))
    aw, ah = rotated_aabb(w, h, rot)
    k = min(1.0, W / aw if aw > 0 else 1.0, H / ah if ah > 0 else 1.0)
    if k < 1.0:
        cx, cy = num(el.get("x")) + w / 2, num(el.get("y")) + h / 2
        w, h, aw, ah = w * k, h * k, aw * k, ah * k
        el["x"], el["y"] = cx - w / 2, cy - h / 2
        if el.get("type") == "text":
            el["font_size"] = max(1, int(num(el.get("font_size"), 1) * k))
    cx, cy = num(el.get("x")) + w / 2, num(el.get("y")) + h / 2
    cx = min(max(cx, aw / 2), W - aw / 2)
    cy = min(max(cy, ah / 2), H - ah / 2)
    x, y = cx - w / 2, cy - h / 2
    # The unrotated box must also be inside (that's what the self-check tests).
    x = min(max(x, 0.0), max(0.0, W - w))
    y = min(max(y, 0.0), max(0.0, H - h))
    el.update(x=_r(x), y=_r(y), width=_r(min(w, W)), height=_r(min(h, H)))
    if el.get("type") == "text":
        el["font_size"] = max(1, int(num(el.get("font_size"), 1)))


def _transparent(color: str) -> str:
    m = re.match(r"\s*rgba?\(([^)]*)\)", color)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")][:3]
        if len(parts) == 3:
            return f"rgba({parts[0]},{parts[1]},{parts[2]},0)"
    return "rgba(0,0,0,0)"


def _proportional(el: dict[str, Any], a: Analysis, W: float, H: float) -> dict[str, Any]:
    s = min(W / a.canvas[0], H / a.canvas[1])
    ox, oy = (W - a.canvas[0] * s) / 2, (H - a.canvas[1] * s) / 2
    n = dict(el)
    n.update(x=ox + num(el.get("x")) * s, y=oy + num(el.get("y")) * s,
             width=num(el.get("width")) * s, height=num(el.get("height")) * s)
    if el.get("type") == "text":
        n["font_size"] = max(1, int(num(el.get("font_size"), 12) * s))
    return n


def _box(n: dict[str, Any]) -> tuple[float, float, float, float]:
    x, y = num(n.get("x")), num(n.get("y"))
    return x, y, x + num(n.get("width")), y + num(n.get("height"))


def _hits(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _clear_text(a: Analysis, out: dict[str, dict[str, Any]], W: float, H: float) -> None:
    """Shrink decorations toward their corner so text never sits on them."""
    texts = [_box(n) for n in out.values() if n.get("type") == "text"]
    for b in a.decoration:
        for el in b.elements:
            n = out[el["id"]]
            x0, y0, x1, y1 = _box(n)
            ax = 0.0 if (x0 + x1) / 2 < W / 2 else W   # corner it shrinks toward
            ay = 0.0 if (y0 + y1) / 2 < H / 2 else H
            for k in (0.85, 0.7, 0.55, 0.4):
                if not any(_hits(_box(n), t) for t in texts):
                    break
                n.update(x=ax + (x0 - ax) * k, y=ay + (y0 - ay) * k,
                         width=(x1 - x0) * k, height=(y1 - y0) * k)


def build(a: Analysis, lay: Layout, W: float, H: float) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for b in a.background:
        for el in b.elements:
            n = dict(el)
            n.update(x=0, y=0, width=W, height=H)
            if el.get("type") == "image" and el.get("fit", "contain") != "cover":
                n["fit"] = "cover"  # full-bleed art crops instead of stretching
            out[el["id"]] = n
    s_d = math.sqrt(W * H / (a.canvas[0] * a.canvas[1]))
    for b in a.decoration:
        for el in b.elements:
            n = dict(el)
            w, h = num(el.get("width")) * s_d, num(el.get("height")) * s_d
            # Keep each decoration's distance to its nearest corner (scaled),
            # so corner ornaments stay in corners on any aspect ratio.
            sx = num(el.get("x")) + num(el.get("width")) / 2
            sy = num(el.get("y")) + num(el.get("height")) / 2
            W0, H0 = a.canvas
            cx = sx * s_d if sx < W0 / 2 else W - (W0 - sx) * s_d
            cy = sy * s_d if sy < H0 / 2 else H - (H0 - sy) * s_d
            n.update(x=cx - w / 2, y=cy - h / 2, width=w, height=h)
            out[el["id"]] = n
    for f in lay.fits:
        for n in emit_fit(f):
            out[n["id"]] = n
    _clear_text(a, out, W, H)
    for eid in lay.hidden:
        src = next(el for b in a.all_blocks() for el in b.elements if el["id"] == eid)
        n = _proportional(src, a, W, H)
        n["opacity"] = 0
        if n.get("type") == "text":
            # The official renderer ignores `opacity` on text (verified), so
            # also zero the colour's alpha; otherwise "hidden" text still draws.
            n["color"] = _transparent(str(n.get("color", "rgba(0,0,0,1)")))
            if n.get("style_runs"):
                n["style_runs"] = [{**r, "color": _transparent(str(r["color"]))} if "color" in r else r
                                   for r in n["style_runs"]]
        out[eid] = n
    for b in a.all_blocks():  # safety net: never lose an id
        for el in b.elements:
            out.setdefault(el["id"], _proportional(el, a, W, H))
    for n in out.values():
        _clamp(n, W, H)
        if n.get("type") == "text" and n["id"] not in lay.hidden:
            while n["font_size"] > 1 and not fits(n, n["font_size"], n["width"], n["height"] * 1.05):
                n["font_size"] -= 1
    return out


def adapt(source: dict[str, Any], target_canvas: dict[str, Any],
          allow_hide: bool | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (resized_design, report)."""
    t0 = time.perf_counter()
    W = max(1, int(num((target_canvas or {}).get("width"), 1)))
    H = max(1, int(num((target_canvas or {}).get("height"), 1)))
    elements = [e for e in (source or {}).get("elements") or [] if isinstance(e, dict) and "id" in e]
    order = [e["id"] for e in elements]
    allow_hide = _allow_hide() if allow_hide is None else allow_hide
    report: dict[str, Any] = {"target": {"width": W, "height": H}, "text_backend": BACKEND,
                              "allow_hide": allow_hide, "weights": WEIGHTS}
    if not elements:
        report.update(error="source has no usable elements", candidates=[], roles=[])
        return {"canvas": {"width": W, "height": H}, "elements": []}, report

    src = copy.deepcopy({"canvas": source.get("canvas") or {}, "elements": elements})
    a = analyze(src)
    ctx = Ctx(a, W, H, allow_hide)
    scored = []
    for lay in candidates(ctx):
        out = build(a, lay, W, H)
        total, parts = score(a, out, set(lay.hidden), W, H, lay.overflow)
        scored.append((total, lay, out, parts))
    scored.sort(key=lambda t: -t[0])
    # Dropping content is a last resort: allowed only when no layout that
    # keeps everything (missing assets aside) reaches good readability.
    def drops(lay: Layout) -> bool:
        return any("readable" in why for why in lay.hidden.values())
    full = [t for t in scored if not drops(t[1])]
    best_full_read = max((t[3]["readability"] for t in full), default=0.0)
    may_drop = best_full_read < READABLE
    eligible = scored if may_drop or not full else full
    best_total, best, best_out, _ = eligible[0]
    report["drop_rule"] = (f"best layout keeping everything reads at {best_full_read:.2f} "
                           f"({'below' if may_drop else 'at or above'} {READABLE}), so dropping is "
                           f"{'allowed' if may_drop else 'not needed'}")

    def design(out: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return {"canvas": {"width": W, "height": H}, "elements": [out[i] for i in order]}

    report["roles"] = [
        {"block": b.id, "role": b.role, "priority": b.priority, "reason": b.reason,
         "elements": [e["id"] for e in b.elements]}
        for b in a.background + a.flow + a.floating + a.decoration
    ]
    report["notes"] = a.notes
    report["candidates"] = [
        {"name": lay.name, "description": lay.description, "score": round(t, 4), "parts": parts,
         "hidden": lay.hidden, "overflow": lay.overflow, "design": design(out)}
        for t, lay, out, parts in eligible + [x for x in scored if x not in eligible]
    ]
    report["chosen"] = best.name
    report["hidden"] = best.hidden
    src_by_id = {e["id"]: e for e in elements}
    report["changes"] = [
        {"id": i, "before": {k: src_by_id[i].get(k) for k in ("x", "y", "width", "height", "font_size") if k in src_by_id[i]},
         "after": {k: best_out[i].get(k) for k in ("x", "y", "width", "height", "font_size") if k in best_out[i]}}
        for i in order
    ]
    report["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return design(best_out), report


def safe_fit(source: dict[str, Any], target_canvas: dict[str, Any]) -> dict[str, Any]:
    """Last-resort fallback: uniform contain-scale of the whole design,
    centred, with full-canvas backgrounds. Always valid."""
    W = max(1, int(num((target_canvas or {}).get("width"), 1)))
    H = max(1, int(num((target_canvas or {}).get("height"), 1)))
    canvas = (source or {}).get("canvas") or {}
    W0, H0 = num(canvas.get("width"), W) or W, num(canvas.get("height"), H) or H
    s = min(W / W0, H / H0)
    ox, oy = (W - W0 * s) / 2, (H - H0 * s) / 2
    out = []
    for el in (source or {}).get("elements") or []:
        if not isinstance(el, dict) or "id" not in el:
            continue
        n = dict(el)
        if num(el.get("width")) * num(el.get("height")) >= 0.85 * W0 * H0:
            n.update(x=0, y=0, width=W, height=H)
        else:
            n.update(x=ox + num(el.get("x")) * s, y=oy + num(el.get("y")) * s,
                     width=num(el.get("width")) * s, height=num(el.get("height")) * s)
            if el.get("type") == "text":
                n["font_size"] = max(1, int(num(el.get("font_size"), 12) * s))
        _clamp(n, W, H)
        out.append(n)
    return {"canvas": {"width": W, "height": H}, "elements": out}
