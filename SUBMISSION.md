# Submission pack

## Project description (paste-ready)

Chameleon resizes a finished design for any canvas by rearranging it instead of stretching it. It reads the design the way a designer would. It finds the headline, the logo, the product, the call to action and the fine print from geometry alone. Then it builds several real layouts for the new shape and measures each one with the renderer's own font metrics. It keeps the layout that stays readable, keeps the hierarchy and avoids collisions. Images keep their proportions. Copy and fonts never change. Every element comes back. The engine is deterministic, runs offline in milliseconds, and explains every decision it makes.

## 75 second demo script

**0:00 Problem.** Open the Studio with the Level 3 poster selected. "This is one finished poster. Marketing needs it as a story, a square, a YouTube thumbnail, a LinkedIn banner and a 728 by 90 leaderboard. Resize tools stretch or crop it, and the logo and the button fall off."

**0:12 One click.** Press Adapt design. Seven canvases appear in about a second. "Every one of these was laid out by the engine. Nobody touched them."

**0:22 The contrast.** Hold the stretch button on the leaderboard card. "This is the naive stretch. Unreadable." Release it. "This is Chameleon. Logo, product, headline and button in one readable row."

**0:35 Why.** Open Why on the LinkedIn banner and tick Show what the engine saw. "There are no labels in the input. The engine worked out which piece is the headline, the logo, the product and the button. It kept the three badges together as one row, and the rotated ribbon as one sticker."

**0:50 The technical differentiator.** Point at Layouts considered. "It tried a column, a split and three columns. It scored each one on readability, hierarchy, collisions and use of space, with text measured exactly the way the official renderer draws it. The winner is not a guess. If I prefer another layout, I click Use."

**1:05 Trust.** Point at the Hard-rule checks line. "Every id is kept, nothing is off canvas, images keep their proportions, fonts and copy never change. 113 automated tests check this across 15 formats and 40 random designs. It runs offline in under 100 milliseconds."

**1:15 Close.** "Same design. Every canvas."

## How the implementation addresses each criterion in the brief

The brief lists the qualities the scoring rewards (PDF §2.5), plus "speed and reliability" (`RULES.md`). No weights were published.

| Brief criterion | What we built | Evidence |
|---|---|---|
| Rearrange, don't stretch (§2) | Five layout strategies that re-place blocks; text reflows; rigid blocks scale uniformly | `engine/layout.py`; `docs/sheet_*.png` |
| No unwanted collisions | Stacks and strips can't overlap by construction. Stickers and tags look for a free corner. Decorations shrink away from text. The collision term is scored | `test_no_collisions_between_visible_content` |
| Everything readable, nothing cut off | Text is measured with the renderer's own fonts and wrap. Integer sizes match the renderer. Readability is scored; unreadable low-priority items may drop away on tight canvases only | `engine/textfit.py`; overflow check in `tools/checks.py` |
| On brand | Font family, copy, colours (except hidden text, see README), assets, z-order and groups are unchanged. Logo keeps its proportions | `tools/checks.py` field checks |
| Looks intentional | Shared margins and gaps. Source reading order and top/bottom anchors kept. The headline keeps its lead. Consistent scale across blocks | hierarchy, consistency and fidelity terms in `engine/score.py` |
| Holds up everywhere | Only generic rules, never keyed to a size or design. Tested on 3 samples × 19 sizes and 40 random designs, with malformed input | `tests/test_engine.py` (113 passing) |
| JSON valid and honest | Same ids, required fields, schema validation, on-canvas boxes including rotated bounds | `tools/checks.py`; `main.py` self-check shows 0 warnings |
| Speed and reliability | Deterministic, about 1–80 ms per resize, no model or network, a `safe_fit` fallback if anything throws | `python -m tools.evaluate` timing column |
| Finale: product thinking (§3.3) | Studio: many canvases at once, stretch comparison, role overlay, ranked alternatives you can pick, JSON download | `studio/` |

## Final checklist

**Works and verified on this machine (macOS, Python 3.11 venv)**

- [x] `python -m engine.main` on the 3 official samples: 0 self-check warnings, real renders
- [x] `python -m pytest -q`: 113 passed
- [x] `python -m tools.evaluate`: 48 runs, 0 hard-rule problems, max 80 ms
- [x] Studio: adapt, hold-to-compare, explanation dialog, role overlay and candidate switching. Checked in headless Chromium with no console errors and no horizontal scroll at 390 px width
- [x] Error paths: invalid JSON, a design without a canvas, no targets, out-of-range sizes

**Unverified**

- [ ] `docker build` / `docker run --network none` (Docker isn't installed here). Run it before submitting
- [ ] Behaviour on the hidden scorer and AI evaluator
- [ ] Whether `opacity: 0` hiding is acceptable (ask the organisers; `CHAMELEON_ALLOW_HIDE=0` turns it off)
- [ ] Linux/amd64 font metrics vs macOS (same fonts and Skia, so we expect identical results, but this is untested)
- [ ] Adobe Express add-on (finale deliverable, not started)

**If the live demo fails**

1. Show `docs/sheet_level3_advanced.png` and `docs/sheet_level2_core.png`: stretch vs Chameleon across 16 sizes, rendered by the official renderer.
2. Show `docs/studio_results.png` and `docs/studio_explain.png` for the UI and the explanation.
3. Run `python -m engine.main` in a terminal and open `output/*_output.png`. It needs no server or browser.

## Questions to send the organisers

1. Is setting `opacity: 0` on an unreadable low-priority element acceptable, given every id is still returned?
2. The official renderer ignores `opacity` on text elements. Is that known? Will it be fixed before scoring?
3. FAQ Q5 mentions a "required (but not scored) viewer add-on" for stage one, but the PDF lists the add-on for the finale only. Which is right?
4. Does the off-canvas check use the unrotated box or the rotated bounds? (We satisfy both.)
