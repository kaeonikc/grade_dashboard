# ADR 003: web-push writes a resolved course.json, and the JS never parses YAML or points rules

Date: 2026-10-18 · Status: accepted

## Context
The browser has to compute exactly what grade-tui shows (S12). That depends on the YAML config (weights,
`data_mapping` in three syntaxes, `pts_each`, built-in `lab` = 10, `total_pts`, `rules`), on header points
(`hw1 (10pts)` overriding config, bare headers at the category default), on auto-detected attendance columns, and on
the weight-derived default for columns with no points (`_fill_default_max_scores`). A JS copy of all of that is a
second implementation of `src/points.py` and `load_config`, plus a YAML parser (a library, against the 0-library
budget).

## Decision
- `grader web-push` builds **`course.json`** in Python by running grade-tui's real loaders (`load_config`,
  `load_course_data`) on a temporary staging copy of the pushed files. It holds the cleaned `data_mapping`
  (attendance auto-detect applied), `weights`, `grade_boundaries`, `rules`, `total_pts`, and **`max_scores` as
  grade-tui has them before `_fill_default_max_scores`** (config points, `pts_each`/lab defaults, header
  overrides). It also holds a `columns` list mapping each counted column's clean name to its header and Drive file.
- The JS ports only what can change on the web: `cells.classify`, `_fill_default_max_scores` (it depends on the
  weights, which the web may edit), `calculate_final_grades`, `assign_letter_grade`, and the attendance code values.
- **No YAML on Drive.** `course.json` *is* the Drive config. A web weights/boundaries save rewrites its `weights` or
  `grade_boundaries` and journals a `config` line. web-pull applies that line to the Mac YAML through
  `update_course_config`. A YAML copy on Drive would go stale after the first web config save and give two answers
  to "what are the weights on Drive".
- Parity is proven end to end: `web/tools/make_golden.py` writes each fixture's `course.json` with the same builder
  web-push uses, and the expected values from `tui_api.get_course_data` (what grade-tui shows) on a temp copy of
  the fixture. `node --test` runs the JS on the fixture CSVs + that `course.json` and must match every student (S12.1).
  `tests/test_web_golden.py` regenerates and fails on drift, so a later change to grade-tui's math shows up.

## Alternatives considered
| Option | Why not |
|---|---|
| Copy the YAML to Drive and parse it in JS | Needs a YAML library (or a hand-written partial parser), plus a JS port of `points.py` and the loader's header and attendance rules: two implementations to keep in step |
| Golden values from `calculators.py` alone | It misses the loader's defaults (header override, `pts_each`, attendance auto-detect, weight-derived max), which is where the web would drift (S12.2) |
| Resolve everything in Python, including the weight-derived max | Wrong after a web weights edit: grade-tui would recompute those maxima from the new weights and the web wouldn't |
| Keep a reference `config.yaml` beside `course.json` | Stale after a web config save, and comments would be the only thing it adds |

## Consequences
- The JS stays small: classify, fill default max, the calculator, letters, about 200 lines. Points rules live only
  in Python.
- If grade_dashboard changes how points are resolved, only the builder output changes. The golden test flags drift
  and a re-push carries the fix.
- S1.1's "the course config" on Drive is `course.json`. A Drive course without `course.json` shows as unavailable
  (S2.3).
- Known divergence, kept out of fixtures: pandas reads a Student ID like `0012` as the number 12, while the web keeps
  the text. Fixtures use 10-digit IDs starting `99`, where the two agree.
