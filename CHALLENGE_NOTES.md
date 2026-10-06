# CHALLENGE_NOTES — Project CHAMELEON

Sources read, in priority order:

1. `~/Desktop/Final%20Chameleon%20Challenge.pdf` (14 pages; every page's text and images checked)
2. The starter repo the PDF points to, `github.com/jhaaj08/chameleon` (cloned here): `README.md`, `RULES.md`, `FAQ.md`, `chameleon_design_schema_v0.9.json`, `engine/main.py`, `engine/resize.py`, `renderer/`, `brand_kit/`, and the 3 sample tasks in `input/`

The public summary ("adapt an existing design to a new canvas size while keeping its intent") matches the PDF. The PDF adds a lot of detail. I found no conflict between public info and the PDF.

## 1. The problem in plain language

A designer finishes one design, for example a 1080×1350 portrait poster. Then they need it as a square post, a tall story, a wide banner, a leaderboard ad and more. Today they rebuild it by hand for each size. Adobe Express's Resize tool scales or crops it, and the PDF shows that cutting off the logo and CTA (p.3: "no sane marketing team would use this feature").

Build an **engine** that takes a design and a target canvas size. It returns the same design **re-laid-out** for the new shape, with no human help. "Move the furniture, don't stretch the photo" (p.5).

## 2. User and core need

- **Final user:** a designer or marketer on a brand team who needs one design in many formats.
- **Most important need:** the resized version still looks like *the same design, made by a designer*. Brand, content and hierarchy stay the same. Positions, stacking, type size and cropping change (p.4).
- **Stage one "user":** an automated scorer. The engine is a headless service with no screen (p.5, §2.1).

## 3. Input → transformation → output

- **Input:** one JSON task `{ "source": {canvas, elements[]}, "target_canvas": {width, height} }`. The samples also include `task_id`, `difficulty`, and `notes`.
  - Each element has `id`, `type` (`text` | `image` | `shape`), `x, y, width, height` in pixels. It may also have `rotation` (degrees), `opacity`, `z_index`, and `group_id`.
  - Text fields: `content, font_family, font_size, font_weight, font_style, color, text_align, line_height, letter_spacing, max_lines, style_runs`.
  - Image fields: `asset_id`, `fit` (`contain` | `cover` | `fill`).
  - Shape fields: `shape_type` (`rectangle` | `ellipse` | `line`), `fill_color, stroke_color, stroke_width, corner_radius`.
  - **There are no semantic labels.** The engine does not know which element is the headline or the logo (FAQ Q1). `group_id` only says that pieces "travel together".
- **Transformation:** `engine/resize.py::resize(source, target_canvas) -> design`. This is the only file the starter expects us to edit.
- **Output:** the same structure with `canvas = target_canvas` and the same elements, with updated position and size. For text, `font_size` may also change. `main.py` writes `<task>_output.json` and renders `<task>_output.png` with the official renderer (cr-renderer through the vendored converter).

## 4. Requirements, constraints and deliverables

Hard requirements (from `RULES.md`, `resize.py` docstring, PDF §4 and §7):

- Return every source element `id` exactly once. Do not add or remove elements.
- **Nothing off-canvas.**
- Non-background images keep their aspect ratio within about 5%. A full-bleed `fit: cover` image may crop.
- `font_size` may change. `font_family` and text `content` must **not** change for stage one.
- **Disqualifying:** regenerating, redrawing or replacing any asset's pixels, including with generative AI.
- No hand-tailoring to specific designs or sizes. Hidden tests use unseen designs and targets.
- Stage one runs **offline** (`docker run --network none`) in the starter Docker image. Everything must install at build time. A local model is allowed under a size limit and an approved-model list, but the exact limits are not yet published.
- A fine-tuned or LoRA model must have publicly hosted weights.
- Reference hardware is Apple M5 Pro (exact limits TBD). There is no hard time limit, and "speed and reliability" is a rubric row.
- The engine must not crash on a missing asset (the Level 3 `holiday_watermark` is missing on purpose).
- Allowed "fixed materials": the brand colours, fonts and logo, and the catalogue of common canvas sizes. Targets will be real platform formats.

Deliverables:

- **Stage one:** the engine (code + Dockerfile) and a short README that explains the approach and how to run it.
- **Finale (top 6–7 teams, in person):** a full Adobe Express add-on running on the engine, a short pitch, and a brief demo video.
- FAQ Q5 also mentions a "required (but not scored) viewer add-on" for stage one. That conflicts with the PDF (see §7).

## 5. Judging criteria

**Stage one is automated.** Hidden designs × hidden target sizes across 3 difficulty levels. Two artifacts are checked:

1. **Output JSON, checked structurally:** same ids, required fields, nothing off-canvas, images in proportion, "and so on".
2. **Rendered PNG, scored by an "AI evaluator" against a rubric.** A good JSON that renders badly gets no credit. A good-looking PNG from a broken or dishonest JSON also gets no credit.

Qualities named in PDF §2.5 ("the same ones our scoring rewards"):

- **No unwanted collisions.** Intentional layering is fine, but text must never sit on a busy image.
- **Everything readable.** Text is big enough, has enough contrast, and nothing is cut off.
- **On brand.** Colours, fonts and logo stay intact and in proportion.
- **Looks intentional.** Things line up, spacing is even, the most important element still stands out, and pictures keep their proportions.
- **Holds up everywhere.** Good across many designs and shapes, not one lucky example.
- "Speed and reliability" is also a rubric row (`RULES.md`). A faster engine is preferred when all else is equal.

**No weights are shown anywhere.** The full rubric document is not in the materials.

**Finale:** a cross-functional jury (research, product, design, engineering). It is open-ended. "A judge may well prefer a delightful experience with a slightly weaker engine… over a strong engine with a flat experience." Suggested directions, none required: several options to choose from, letting a user lock or steer parts, letting less-important elements drop away when space is tight, adaptive copy and typography.

## 6. What judges need to see in a live demo

- One real design adapting to several very different canvases (the p.4 "one design, four canvases" image), with the original visible next to it.
- That it **rearranges** rather than stretches. A side-by-side with the naive stretch baseline makes this obvious.
- That hierarchy survives: headline still dominant, logo intact, CTA still a button, nothing overlapping or cut off.
- That it holds up on the hard cases: Level 2 (square → 4:1 banner) and Level 3 (portrait → 728×90 leaderboard with run-on text, a rotated ribbon and a missing asset).
- For the Adobe engineering session: the decisions and trade-offs behind the engine.

## 7. Unknowns and contradictions

1. **The rubric text and weights are not provided.** Only the qualities in §2.5 are known.
2. **The response schema is "being defined"** (p.5). We assume the output follows the same `chameleon_design_schema_v0.9.json` as the input. The schema title says "provisional, pending sign-off".
3. **Hiding elements.** Every id must be returned, but the brief also suggests "letting less-important elements gracefully drop away" (finale idea). We do not know whether `opacity: 0` on a fine-print element counts as legitimate or as "dishonest JSON". This affects extreme targets like 728×90. *(See assumption A3.)*
4. **Viewer add-on in stage one.** FAQ Q5 says stage one needs a "required (but not scored) viewer add-on". The PDF says the add-on is a finale deliverable. Ask the organisers.
5. **FAQ Q3 is stale.** It mentions a `/transformer-convertor` app at port 5050, but the repo now vendors the renderer under `renderer/` and `main.py` already renders. The PDF's version of Q3 matches the repo.
6. **Model limits, container details and the reference machine spec** are TBD. Our engine uses no model, so these do not affect it.
7. **Off-canvas definition.** `main.py` checks the unrotated box (±0.5 px). We do not know whether the official check uses the rotated bounds. We keep both inside the canvas.
8. **The target catalogue is not shipped.** We know only that targets are "common real-world formats".
9. **Self-check vs source.** The Level 2 source already bleeds a decorative circle off-canvas. The README calls that warning "expected", but `RULES.md` says nothing off-canvas. We clamp everything inside.

## 8. Assumptions (ours, not Adobe's)

- **A1.** The output schema is the v0.9 design schema. Extra keys are kept as they arrive (`_note` fields are passed through).
- **A2.** The hidden scorer's "AI evaluator" judges by eye on the qualities in §2.5, so we optimise those directly with deterministic, measurable proxies.
- **A3.** Every element stays visible by default. On extreme targets an element is set to `opacity: 0` only when it cannot be shown at a readable size without colliding. This happens only for low-priority roles (fine print, unavailable image). It is reported in the engine's explanation and can be turned off (`CHAMELEON_ALLOW_HIDE=0`). We should ask the organisers about this.
- **A4.** The target catalogue looks like standard platform sizes (Instagram post/portrait/story, YouTube thumbnail, LinkedIn/Facebook/Twitter banners, IAB ad units such as 728×90, 300×250, 160×600). We use such a list only for testing and the demo, never to special-case logic.
- **A5.** The brand kit (`brand_kit/fonts`) is present at run time. The Dockerfile copies it, and it is a permitted "fixed material". We use it to measure text with the same Skia font metrics as the renderer, with a heuristic fallback if it is missing.
- **A6.** No LLM or vision model is needed for stage one. A deterministic layout engine is more reliable, faster, reproducible, and allowed.

## 9. Findings during the build

- **The official renderer ignores `opacity` on text elements** (verified: a text element with `opacity: 0` still draws). Images and shapes honour it. Hidden text therefore also needs a transparent colour alpha. This is worth raising with the organisers.
- The renderer truncates `font_size` to an integer and draws text top-aligned at `i * font_size * line_height`. The engine follows both rules when measuring.
- Brand assets have transparent padding (the logo's visible mark is about 40% of its image width), so "contain" boxes look smaller than their geometry.
