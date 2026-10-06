# BUILD_PLAN — Chameleon engine + Studio demo

## Concept (one sentence)

A deterministic layout engine that reads a design's structure (roles, groups, reading order and hierarchy) and **rebuilds** it for any canvas. It tries several layout strategies, measures each one with the renderer's real font metrics, and keeps the best. Every decision is explained.

## Primary workflow

1. Pick a design (the 3 official samples, or upload a task or design JSON).
2. Pick one or more target formats from a catalogue of real platform sizes, or enter a custom size.
3. **Adapt.** The engine runs locally and the official renderer draws the result.
4. Compare the original, the naive stretch, and the Chameleon result side by side.
5. Open **Why**: the detected roles, the strategy chosen, the scored alternatives, and what happened to each element.
6. If you don't like the pick, choose another ranked candidate and download the JSON.

## The single best demo moment

One click turns one portrait poster into **every format at once**: story, square, YouTube thumbnail, 4:1 banner, 728×90 leaderboard and 160×600 skyscraper. The naive stretch for the same size sits next to each one. Then click into the 728×90 to show that the engine noticed the headline, logo and CTA must survive while the fine print can't be read at 90 px tall, and explains that choice.

## Smallest complete version

- `engine/resize.py` returns a valid, rearranged layout for every sample × catalogue size. No crashes on malformed or missing input.
- Tests cover the hard rules (ids, on-canvas, image proportions, family and content unchanged, text fits its box, no unwanted collisions).
- A local Studio web page (stdlib HTTP server, no new deps) that runs the real engine and the official renderer.

## Technical approach and why it fits

The input carries no semantic labels, and scoring rewards hierarchy, readability, alignment and no collisions. That calls for structure-aware layout, not scaling.

1. **Analyse** (`engine/analyze.py`)
   - Find the background (a cover image spanning the canvas) and decoration (translucent or ungrouped shapes with no text on them).
   - Build **blocks**: `group_id` groups, plus implicit groups where text sits on a shape.
   - Infer **roles** from geometry and type alone: headline (largest type), body, fine print (smallest, longest, near an edge), logo (a wide image near the top), hero (the largest contained image), CTA (the biggest button-like group), badges (repeated small groups in one row), sticker (a rotated group), and unavailable image (asset file missing).
   - Each role gets a priority.
2. **Measure** (`engine/textfit.py`)
   - Wrap text with the same greedy algorithm and Skia glyph widths as the renderer, using the brand fonts.
   - Find the largest whole-number font size that fits a box.
   - Falls back to a width heuristic if Skia or the fonts are unavailable.
3. **Layout candidates** (`engine/layout.py`)
   - *Stack*: one column in the source's reading order (portrait, square, tall).
   - *Split*: hero on one side, text stack on the other, in both mirror versions (landscape).
   - *Three columns*: hero | message | actions (wide banners).
   - *Strip*: one row of logo | hero | headline | CTA (leaderboards and extreme banners).
   - Each candidate shares space by role weight. It binary-searches a global scale so everything fits, then aligns on a margin grid. Groups move as rigid units.
   - Decoration and stickers re-anchor to their original corner.
4. **Score** (`engine/score.py`)
   - Readability (minimum font size relative to the canvas), hierarchy kept (rank order of text sizes and image areas), collisions, use of space, balance, scale consistency, and hidden-element penalties.
   - The best candidate wins. All scores are kept for the explanation.
5. **Explain** (`engine/report.py`): roles, the candidate table, and per-element before→after. The Studio uses this, and it is useful for the Adobe engineering session.

No LLM: the hard part is geometric and measurable, determinism makes it reproducible, and it runs in milliseconds offline.

## Risks and fallbacks

- **Role inference is wrong on unseen designs.** Roles only change weights and slots. Every candidate still respects the hard rules, and scoring picks the least bad. If analysis throws, `resize()` falls back to a safe "fit and centre" layout (uniform contain-scale of the whole composition, background stretched to cover), which is still valid.
- **The renderer wraps differently from our measurement.** We use the same algorithm and glyph widths, plus a small safety margin.
- **Extreme targets (728×90).** Low-priority text may be hidden (assumption A3 in the notes). `CHAMELEON_ALLOW_HIDE=0` disables this.
- **Docker is not installed on this machine.** The image is unverified locally. We add no new dependencies, so the starter Dockerfile should work unchanged.

**Cut order if time is tight:** Studio candidate picker → upload → three-column template → explanation detail. Never cut the tests or the hard-rule guarantees.

## Parallel task breakdown

| Track | Owner | Files |
|---|---|---|
| Engine analysis + roles | A | `engine/analyze.py` |
| Text measurement | A | `engine/textfit.py` |
| Layout templates + scoring | B | `engine/layout.py`, `engine/score.py` |
| Tests + batch evaluator + contact sheet | C | `tests/`, `tools/` |
| Studio UI + server | D | `studio/` |
| Docs, pitch, demo script | any | `README.md`, `SUBMISSION.md` |

## Status log

- [x] Brief + starter read, `CHALLENGE_NOTES.md` written
- [x] Engine: analyse / measure / layout / score / explain (`engine/`)
- [x] Tests: 114 passing (hard rules × samples × 19 sizes, 40 random designs, malformed input, no-hide mode)
- [x] Batch evaluator + contact sheets (`tools/evaluate.py`, copies in `docs/`)
- [x] Studio UI (`studio/`), checked in headless Chromium
- [x] README, `SUBMISSION.md` (description, demo script, criteria map, checklist)
- [ ] Docker build verified (needs Docker; not installed here)
- [ ] Organiser answers on hiding and the text-opacity renderer quirk

### Scope changes during the build

- Content dropping on strips is limited to canvases under 200 px tall. It was hiding badges on a 1584×396 banner where a column layout fits.
- Added a "fidelity" score term (reading order and corner anchors) so ties go to the more faithful layout.
- Decorations shrink toward their corner when they would sit under text.
- Finding: the renderer ignores `opacity` on text, so hidden text also gets a transparent colour.

- Optimisation pass: small canvases get text-first and drop-long-copy variants, but only when no full layout reaches readability 0.8. Mean proxy score went from 0.936 to 0.940, with the gains on Level 3 small formats (billboard 0.84 → 0.92, half page 0.81 → 0.84). Slowest resize went from 32 ms to 80 ms.

- Banner-height pass (canvases under 80 px tall). The scorer counts text under 5 px and images under 12 px as lost, because they are present in the JSON but invisible. Readability now has a gradient below 7 px, and the hierarchy check includes button labels. Strips shrink pictures before the CTA, keep the logo at least 45% of the strip height, try finer text-share splits, and may drop the product as a last resort. Small button labels can grow up to 1.3x to fill their box. Level 3 at 320x50 went from a 4 px headline with 1 px badges to an 8 px headline, a visible logo and a CTA.

### Next highest-value tasks

1. Run the Docker build and run once Docker is available.
2. Get the organisers' answer on hiding, then pick the default.
3. Build more test designs (two images of equal size, left-aligned editorial layouts, a bottom logo) to harden the role heuristics.
4. Finale: wrap the engine as an Express add-on. The Studio interactions map directly to it (pick canvases, compare, choose an alternative).
