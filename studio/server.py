"""Chameleon Studio: a local demo UI around the real engine + official renderer.

    python -m studio.server            # then open http://127.0.0.1:8765

Standard library only. Nothing leaves your machine.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)  # engine + renderer resolve brand_kit/ relative to the repo root
sys.path.insert(0, str(ROOT))

from engine.chameleon import adapt  # noqa: E402
from engine.resize import stretch  # noqa: E402
from tools.checks import check  # noqa: E402
from tools.formats import FORMATS  # noqa: E402

ASSETS = ROOT / "brand_kit" / "assets"
INPUT = ROOT / "input"
MAX_BODY = 5_000_000
MAX_TARGETS = 20
MAX_ELEMENTS = 400
_render_lock = threading.Lock()

try:
    from renderer.converter.convert import render_design_to_png
    RENDERER = True
except Exception:  # pragma: no cover
    RENDERER = False


def render_b64(design: dict[str, Any], max_size: int = 720) -> str | None:
    if not RENDERER:
        return None
    with _render_lock, tempfile.NamedTemporaryFile(suffix=".png") as f:
        render_design_to_png(design, ASSETS, f.name, max_size=max_size)
        return base64.b64encode(Path(f.name).read_bytes()).decode()


def samples() -> list[dict[str, Any]]:
    out = []
    for p in sorted(INPUT.glob("*.json")):
        try:
            t = json.loads(p.read_text())
            out.append({"key": p.stem, "label": t.get("difficulty_label", p.stem),
                        "notes": t.get("notes", ""), "canvas": t["source"]["canvas"],
                        "elements": len(t["source"]["elements"]), "target": t.get("target_canvas")})
        except Exception:
            continue
    return out


def validate_source(src: Any) -> str | None:
    if not isinstance(src, dict):
        return "Expected a JSON object with 'canvas' and 'elements' (or a task with 'source')."
    c = src.get("canvas")
    if not isinstance(c, dict) or not all(isinstance(c.get(k), (int, float)) and c.get(k, 0) > 0 for k in ("width", "height")):
        return "Design needs a canvas with positive numeric width and height."
    els = src.get("elements")
    if not isinstance(els, list) or not els:
        return "Design has no elements."
    if len(els) > MAX_ELEMENTS:
        return f"Design has {len(els)} elements; the Studio accepts up to {MAX_ELEMENTS}."
    bad = [i for i, e in enumerate(els) if not isinstance(e, dict) or "id" not in e or e.get("type") not in ("text", "image", "shape")]
    if bad:
        return f"Element #{bad[0]} needs an 'id' and a type of text, image or shape."
    ids = [e["id"] for e in els]
    if len(set(ids)) != len(ids):
        return "Element ids must be unique."
    return None


def handle_adapt(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("sample"):
        p = INPUT / f"{Path(str(body['sample'])).name}.json"
        if not p.is_file():
            raise ValueError("Unknown sample.")
        src = json.loads(p.read_text())["source"]
    else:
        src = body.get("design")
        if isinstance(src, dict) and "source" in src:
            src = src["source"]
    err = validate_source(src)
    if err:
        raise ValueError(err)
    targets = body.get("targets") or []
    if not targets:
        raise ValueError("Pick at least one canvas size.")
    if len(targets) > MAX_TARGETS:
        raise ValueError(f"Pick at most {MAX_TARGETS} sizes at once.")
    allow_hide = bool(body.get("allow_hide", True))
    results = []
    for t in targets:
        w, h = int(t.get("width", 0)), int(t.get("height", 0))
        if not (16 <= w <= 8000 and 16 <= h <= 8000):
            raise ValueError(f"Canvas {w}x{h} is out of range (16 to 8000 px per side).")
        tc = {"width": w, "height": h}
        design, rep = adapt(src, tc, allow_hide=allow_hide)
        for c in rep["candidates"]:
            c["problems"] = check(src, c["design"])
        naive = stretch({"canvas": src["canvas"], "elements": [dict(e) for e in src["elements"]]}, tc)
        results.append({
            "name": t.get("name") or f"{w}x{h}", "width": w, "height": h,
            "design": design, "report": rep, "problems": check(src, design),
            "png": render_b64(design), "stretch_png": render_b64(naive),
        })
    return {"source": src, "source_png": render_b64(src), "results": results, "renderer": RENDERER}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("studio: " + fmt % args + "\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "studio" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/meta":
            self._json(200, {"samples": samples(), "formats": FORMATS, "renderer": RENDERER})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            self._json(413, {"error": "Upload is too large (5 MB max)."})
            return
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "That file isn't valid JSON."})
            return
        try:
            if self.path == "/api/adapt":
                self._json(200, handle_adapt(body))
            elif self.path == "/api/render":
                d = body.get("design")
                if not isinstance(d, dict) or validate_source(d):
                    raise ValueError("Invalid design.")
                self._json(200, {"png": render_b64(d)})
            else:
                self._json(404, {"error": "not found"})
        except ValueError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # pragma: no cover
            traceback.print_exc()
            self._json(500, {"error": f"Engine error: {e}"})


def main() -> None:
    port = int(os.environ.get("PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Chameleon Studio on http://127.0.0.1:{port}  (renderer: {'official' if RENDERER else 'unavailable'})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
