import json
import random
from pathlib import Path

import pytest

from engine.chameleon import adapt, safe_fit
from engine.resize import resize
from engine.score import _aabb, _ov
from tools.checks import check
from tools.formats import FORMATS

TASKS = sorted(Path("input").glob("*.json")) + sorted(Path("samples/extra").glob("*.json"))
TARGETS = [(f["width"], f["height"]) for f in FORMATS] + [(1600, 400), (728, 90), (1, 1), (5000, 200)]


def load(p):
    return json.loads(Path(p).read_text())


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.stem)
@pytest.mark.parametrize("wh", TARGETS, ids=lambda t: f"{t[0]}x{t[1]}")
def test_hard_rules(task, wh):
    src = load(task)["source"]
    out = resize(src, {"width": wh[0], "height": wh[1]})
    assert out["canvas"] == {"width": wh[0], "height": wh[1]}
    probs = check(src, out)
    if wh == (1, 1):  # nothing can be legible on a 1px canvas; only structure matters
        probs = [p for p in probs if "overflows" not in p]
    assert probs == []


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.stem)
def test_no_collisions_between_visible_content(task):
    t = load(task)
    design, rep = adapt(t["source"], t["target_canvas"])
    roles = {e: r["role"] for r in rep["roles"] for e in r["elements"]}
    block = {e: r["block"] for r in rep["roles"] for e in r["elements"]}
    vis = [e for e in design["elements"] if e.get("opacity", 1) > 0
           and roles[e["id"]] not in ("background", "decoration")]
    for i, a in enumerate(vis):
        for b in vis[i + 1:]:
            if block[a["id"]] != block[b["id"]]:
                assert _ov(_aabb(a), _aabb(b)) < 1.0, (a["id"], b["id"])


def test_banner_rearranges_instead_of_stretching():
    t = load("input/chameleon_sample_level2_core.json")
    design, rep = adapt(t["source"], t["target_canvas"])
    el = {e["id"]: e for e in design["elements"]}
    assert rep["chosen"] != "proportional"
    # product sits beside the headline, not above it as in the square source
    assert el["product"]["x"] + el["product"]["width"] <= el["headline"]["x"] + 1
    # headline stays the biggest text
    assert el["headline"]["font_size"] > max(el["subhead"]["font_size"], el["cta_label"]["font_size"])


def test_leaderboard_keeps_primary_message_readable():
    t = load("input/chameleon_sample_level3_advanced.json")
    design, rep = adapt(t["source"], t["target_canvas"])
    el = {e["id"]: e for e in design["elements"]}
    for key in ("headline", "logo", "cta_bg", "cta_label", "product"):
        assert el[key].get("opacity", 1) > 0, key
    assert el["headline"]["font_size"] >= 9
    assert "holiday_watermark" in rep["hidden"]  # missing asset is skipped, not drawn


def test_hide_can_be_disabled():
    t = load("input/chameleon_sample_level3_advanced.json")
    design, rep = adapt(t["source"], t["target_canvas"], allow_hide=False)
    assert rep["hidden"] == {}
    assert all(e.get("opacity", 1) > 0 for e in design["elements"])
    assert check(t["source"], design) == [] or all("overflows" in p for p in check(t["source"], design))


def test_deterministic():
    t = load("input/chameleon_sample_level2_core.json")
    assert resize(t["source"], t["target_canvas"]) == resize(t["source"], t["target_canvas"])


def test_does_not_mutate_input():
    t = load("input/chameleon_sample_level2_core.json")
    before = json.dumps(t, sort_keys=True)
    resize(t["source"], t["target_canvas"])
    assert json.dumps(t, sort_keys=True) == before


@pytest.mark.parametrize("bad", [
    {"canvas": {"width": 100, "height": 100}, "elements": []},
    {"elements": [{"id": "a", "type": "text", "x": 0, "y": 0, "width": 50, "height": 20,
                   "content": "hi", "font_family": "Solstice Sans", "font_size": 12, "color": "rgba(0,0,0,1)"}]},
    {"canvas": {"width": 100, "height": 100}, "elements": [
        {"id": "z", "type": "image", "x": 10, "y": 10, "width": 0, "height": 0, "asset_id": "nope.png"}]},
    {"canvas": {"width": 100, "height": 100}, "elements": [
        {"id": "w", "type": "widget", "x": "bad", "y": None, "width": 40, "height": 40}]},
])
def test_malformed_inputs_do_not_crash(bad):
    out = resize(bad, {"width": 300, "height": 250})
    assert {e["id"] for e in out["elements"]} == {e["id"] for e in bad["elements"]}


def random_design(rng):
    W, H = rng.choice([(1080, 1080), (1080, 1350), (1920, 1080), (1080, 1920)])
    els = [{"id": "bg", "type": "image", "x": 0, "y": 0, "width": W, "height": H, "z_index": 0,
            "asset_id": "solstice_bg_gradient.png", "fit": "cover"}]
    words = "golden hour botanical sparkling summer light chase limited batch crafted fresh".split()
    for i in range(rng.randint(1, 14)):
        kind = rng.choice(["text", "text", "image", "shape", "button"])
        w, h = rng.uniform(60, W * 0.8), rng.uniform(30, H * 0.3)
        x, y = rng.uniform(-50, W - w + 50), rng.uniform(-50, H - h + 50)
        base = {"x": x, "y": y, "width": w, "height": h, "z_index": rng.randint(1, 6)}
        if rng.random() < 0.15:
            base["rotation"] = rng.uniform(-20, 20)
        if kind == "text":
            els.append({**base, "id": f"t{i}", "type": "text",
                        "content": " ".join(rng.choice(words) for _ in range(rng.randint(1, 30))),
                        "font_family": rng.choice(["Solstice Serif", "Solstice Sans"]),
                        "font_size": rng.randint(10, 90), "color": "rgba(255,255,255,1)",
                        "font_weight": rng.choice(["regular", "bold"]),
                        "text_align": rng.choice(["left", "center", "right"])})
        elif kind == "image":
            els.append({**base, "id": f"i{i}", "type": "image", "fit": "contain",
                        "asset_id": rng.choice(["solstice_bottle.png", "solstice_logo_lockup.png", "missing.png"])})
        elif kind == "shape":
            els.append({**base, "id": f"s{i}", "type": "shape", "shape_type": "ellipse",
                        "fill_color": "rgba(255,255,255,1)", "opacity": rng.uniform(0.1, 1)})
        else:
            els.append({**base, "id": f"b{i}", "type": "shape", "shape_type": "rectangle",
                        "fill_color": "rgba(232,106,58,1)", "group_id": f"g{i}"})
            els.append({**base, "id": f"bl{i}", "type": "text", "content": "SHOP NOW", "group_id": f"g{i}",
                        "font_family": "Solstice Sans", "font_size": max(8, int(h * 0.4)),
                        "color": "rgba(255,255,255,1)", "text_align": "center"})
    return {"canvas": {"width": W, "height": H}, "elements": els}


@pytest.mark.parametrize("seed", range(40))
def test_random_designs(seed):
    rng = random.Random(seed)
    src = random_design(rng)
    f = FORMATS[seed % len(FORMATS)]
    out = resize(src, {"width": f["width"], "height": f["height"]})
    # Random designs can have text that's illegible at any size in tiny ads;
    # the structural rules must still hold.
    assert [p for p in check(src, out) if "overflows" not in p] == []


def test_safe_fit_is_valid():
    t = load("input/chameleon_sample_level3_advanced.json")
    out = safe_fit(t["source"], {"width": 728, "height": 90})
    assert [p for p in check(t["source"], out) if "overflows" not in p] == []


def test_short_text_cta_is_never_dropped():
    t = load("input/chameleon_sample_level1_warmup.json")
    for w, h in [(300, 250), (160, 600), (320, 50)]:
        design, rep = adapt(t["source"], {"width": w, "height": h})
        assert "cta" not in rep["hidden"], (w, h)


def test_no_drops_when_full_design_is_readable():
    t = load("input/chameleon_sample_level3_advanced.json")
    design, rep = adapt(t["source"], {"width": 1584, "height": 396})
    assert not [i for i, why in rep["hidden"].items() if "readable" in why]


def test_small_canvas_drops_long_copy_to_keep_headline_readable():
    t = load("input/chameleon_sample_level3_advanced.json")
    design, rep = adapt(t["source"], {"width": 300, "height": 600})
    el = {e["id"]: e for e in design["elements"]}
    assert "subhead" in rep["hidden"] and el["headline"]["font_size"] >= 10
    assert el["cta_label"].get("opacity", 1) > 0 and el["product"].get("opacity", 1) > 0


def test_mobile_banner_keeps_message_readable():
    t = load("input/chameleon_sample_level3_advanced.json")
    design, rep = adapt(t["source"], {"width": 320, "height": 50})
    el = {e["id"]: e for e in design["elements"]}
    assert el["headline"]["font_size"] >= 8
    assert el["logo"]["height"] >= 15 and el["logo"].get("opacity", 1) > 0
    assert el["cta_label"].get("opacity", 1) > 0
    assert el["headline"]["font_size"] >= el["cta_label"]["font_size"]  # hierarchy kept
