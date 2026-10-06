"""Score a candidate layout on the qualities the brief says are rewarded
(PDF §2.5): no unwanted collisions, readable text, hierarchy kept, looks
intentional (consistent scale, balanced, uses the space), nothing lost.

These are our own measurable proxies, not Adobe's scorer.
"""

from __future__ import annotations

import math
from typing import Any

from .analyze import Analysis, num, rotated_aabb
from .textfit import fits

WEIGHTS = {
    "readability": 0.25,
    "hierarchy": 0.15,
    "space": 0.18,
    "consistency": 0.10,
    "collisions": 0.15,
    "completeness": 0.10,
    "fidelity": 0.04,
    "balance": 0.03,
}


def _aabb(el: dict[str, Any]) -> tuple[float, float, float, float]:
    w, h = num(el.get("width")), num(el.get("height"))
    aw, ah = rotated_aabb(w, h, num(el.get("rotation")))
    cx, cy = num(el.get("x")) + w / 2, num(el.get("y")) + h / 2
    return cx - aw / 2, cy - ah / 2, cx + aw / 2, cy + ah / 2


def _ov(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def score(a: Analysis, out: dict[str, dict[str, Any]], hidden: set[str],
          W: float, H: float, overflow: bool) -> tuple[float, dict[str, float]]:
    src = {el["id"]: el for b in a.all_blocks() for el in b.elements}
    block_of = {el["id"]: b for b in a.all_blocks() for el in b.elements}
    content = [b for b in a.flow + a.floating]
    visible = [b for b in content if not any(e["id"] in hidden for e in b.elements)]

    # Readability: every visible text at >= 12px scores 1, below 7px scores 0.
    rs, rw = 0.0, 0.0
    texts = [e for b in visible for e in b.elements if e.get("type") == "text"]
    for el in texts:
        f = num(out[el["id"]].get("font_size"), 1)
        wt = block_of[el["id"]].priority + 10
        rs += wt * max(0.0, min(1.0, (f - 7) / 5))
        rw += wt
    readability = rs / rw if rw else 1.0
    # Text that no longer fits its own box will be cut off or overflow.
    bad_fit = sum(1 for el in texts if not fits(out[el["id"]], int(num(out[el["id"]].get("font_size"), 1)),
                                                 num(out[el["id"]].get("width")), num(out[el["id"]].get("height")) * 1.05))
    if texts:
        readability *= 1 - 0.5 * bad_fit / len(texts)

    # Hierarchy: pairwise order of text sizes and image areas is preserved,
    # and the headline keeps its lead over the next-biggest text.
    pairs, kept = 0, 0
    flow_text = [b.elements[0] for b in visible if b.is_text]
    for i, p in enumerate(flow_text):
        for q in flow_text[i + 1:]:
            sp, sq = num(src[p["id"]].get("font_size")), num(src[q["id"]].get("font_size"))
            if abs(sp - sq) < 1:
                continue
            pairs += 1
            op, oq = num(out[p["id"]].get("font_size")), num(out[q["id"]].get("font_size"))
            kept += (op - oq) * (sp - sq) > 0 or op == oq
    order = kept / pairs if pairs else 1.0
    lead = 1.0
    head = next((b for b in visible if b.role == "headline"), None)
    others = [e for e in flow_text if head is None or e["id"] != head.id]
    if head is not None and others:
        sh = num(src[head.id].get("font_size"))
        so = max(num(src[e["id"]].get("font_size")) for e in others)
        oh = num(out[head.id].get("font_size"))
        oo = max(num(out[e["id"]].get("font_size")) for e in others)
        lead = min(1.0, (oh / max(1.0, oo)) / max(1e-6, sh / max(1.0, so)))
    hierarchy = 0.6 * order + 0.4 * lead

    # Space: how big the content is vs an area-preserving scale, and how much
    # of the canvas it spans in each direction.
    scales = []
    for b in visible:
        e = b.elements[0]
        o = out[e["id"]]
        if b.is_text:
            scales.append(num(o.get("font_size"), 1) / max(1.0, num(e.get("font_size"), 1)))
        else:
            scales.append(num(o.get("width")) / max(1e-6, num(e.get("width"))))
    s_area = math.sqrt(W * H / (a.canvas[0] * a.canvas[1]))
    med = sorted(scales)[len(scales) // 2] if scales else s_area
    size_term = min(1.0, med / s_area)
    boxes = [_aabb(out[e["id"]]) for b in visible for e in b.elements]
    if boxes:
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        cover = min(1.0, (x1 - x0) / (0.85 * W)) * min(1.0, (y1 - y0) / (0.8 * H))
        off = math.hypot((x0 + x1) / 2 - W / 2, (y0 + y1) / 2 - H / 2) / math.hypot(W / 2, H / 2)
    else:
        cover, off = 0.0, 1.0
    space = 0.5 * size_term + 0.5 * math.sqrt(cover)
    balance = max(0.0, 1 - 2 * off)

    # Consistency: blocks keep similar scale to each other ("same design").
    if len(scales) > 1:
        logs = [math.log(max(1e-6, s)) for s in scales]
        mu = sum(logs) / len(logs)
        sd = math.sqrt(sum((v - mu) ** 2 for v in logs) / len(logs))
        consistency = math.exp(-1.2 * sd)
    else:
        consistency = 1.0

    # Collisions between different visible content blocks.
    vis_boxes = [(b.id, _aabb(out[e["id"]])) for b in visible for e in b.elements]
    total = sum((bx[2] - bx[0]) * (bx[3] - bx[1]) for _, bx in vis_boxes) or 1.0
    ov = 0.0
    for i, (ia, ba) in enumerate(vis_boxes):
        for ib, bb in vis_boxes[i + 1:]:
            if ia != ib:
                ov += _ov(ba, bb)
    collisions = max(0.0, 1 - 6 * ov / total)

    # Completeness: priority-weighted share of content still visible.
    pr_all = sum(b.priority for b in content) or 1
    pr_hidden = sum(b.priority for b in content if b not in visible)
    completeness = 1 - pr_hidden / pr_all

    # Fidelity: content still reads in the original order (top-to-bottom
    # may become left-to-right), and floating pieces keep their corner.
    def centre(b):
        bx = [_aabb(out[e["id"]]) for e in b.elements]
        return (min(v[0] for v in bx) + max(v[2] for v in bx)) / 2, (min(v[1] for v in bx) + max(v[3] for v in bx)) / 2
    flow_vis = [b for b in visible if b in a.flow]
    fp, fk = 0, 0
    for i, p in enumerate(flow_vis):
        for q in flow_vis[i + 1:]:
            if abs(p.center[1] - q.center[1]) < 0.05 * a.canvas[1]:
                continue
            first, second = (p, q) if p.center[1] < q.center[1] else (q, p)
            (fx, fy), (sx, sy) = centre(first), centre(second)
            fp += 1
            fk += fy < sy - 1 or fx < sx - 1
    for b in visible:
        if b in a.floating:
            (ox, oy), (sx, sy) = centre(b), b.center
            fp += 1
            fk += (ox < W / 2) == (sx < a.canvas[0] / 2) and (oy < H / 2) == (sy < a.canvas[1] / 2)
    fidelity = fk / fp if fp else 1.0

    parts = {
        "readability": readability, "hierarchy": hierarchy, "space": space,
        "consistency": consistency, "collisions": collisions,
        "completeness": completeness, "fidelity": fidelity, "balance": balance,
    }
    total_score = sum(WEIGHTS[k] * v for k, v in parts.items())
    if overflow:
        total_score -= 0.3
    return total_score, {k: round(v, 3) for k, v in parts.items()}
