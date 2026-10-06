"""Hard-rule checks on an engine output (our reading of RULES.md, not the
official scorer). Shared by the tests, the batch evaluator and the Studio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.analyze import num, rotated_aabb
from engine.textfit import fits

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "chameleon_design_schema_v0.9.json"


def _schema_errors(design: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return []
    schema = json.loads(SCHEMA_PATH.read_text())
    v = jsonschema.Draft202012Validator(schema)
    return [f"schema: {e.message[:120]}" for e in v.iter_errors(design)]


def check(source: dict[str, Any], out: dict[str, Any]) -> list[str]:
    problems = _schema_errors(out)
    W, H = out["canvas"]["width"], out["canvas"]["height"]
    src = {e["id"]: e for e in source["elements"]}
    ids = [e["id"] for e in out["elements"]]
    if sorted(ids) != sorted(src):
        problems.append(f"ids differ: {sorted(set(src) ^ set(ids))}")
    for e in out["elements"]:
        s = src.get(e["id"])
        if s is None:
            continue
        x, y, w, h = (num(e.get(k)) for k in ("x", "y", "width", "height"))
        if x < -0.5 or y < -0.5 or x + w > W + 0.5 or y + h > H + 0.5:
            problems.append(f"{e['id']}: off-canvas box")
        aw, ah = rotated_aabb(w, h, num(e.get("rotation")))
        cx, cy = x + w / 2, y + h / 2
        if cx - aw / 2 < -1 or cy - ah / 2 < -1 or cx + aw / 2 > W + 1 or cy + ah / 2 > H + 1:
            problems.append(f"{e['id']}: rotated bounds off-canvas")
        if e.get("type") == "image" and e.get("fit", "contain") != "cover":
            r0 = num(s.get("width")) / max(1e-6, num(s.get("height")))
            r1 = w / max(1e-6, h)
            if abs(r1 / r0 - 1) > 0.05:
                problems.append(f"{e['id']}: image aspect changed {r0:.3f} -> {r1:.3f}")
        if e.get("type") == "text":
            for k in ("content", "font_family", "font_weight", "font_style"):
                if e.get(k) != s.get(k):
                    problems.append(f"{e['id']}: {k} changed")
            visible = num(e.get("opacity"), 1) > 0
            if visible and not fits(e, int(num(e.get("font_size"), 1)), w, h * 1.05):
                problems.append(f"{e['id']}: text overflows its box at {e.get('font_size')}px")
        for k in ("asset_id", "shape_type", "fill_color", "z_index", "group_id", "rotation"):
            if e.get(k) != s.get(k):
                problems.append(f"{e['id']}: {k} changed")
    return problems
