# Grade order, boundary ranges, distribution and colours (web app + grade-tui)

Status: draft for approval (2026-10-19). Branch: `web-app`. Deploy: Claude runs clasp after every test passes.

## Problem

The web app's Grading tab lists letters in the order of the `grade_boundaries` object's keys ("stored order, never
re-sorted", web/SPEC.md §13), and the strictly-descending check walks that same order. Every config on the Mac is
stored as `A, B+, B, C+, C, D+, D`, but on the phone the tab showed **A, B, C, D, D+, C+, B+**. Key order is lost
somewhere between `grader web-push` and the browser (Drive JSON, `google.script.run` serialisation, or both). The
Node tests never go through Apps Script, so they didn't catch it. Two results follow:

1. The letters show in the wrong order.
2. Each plus grade is refused: `D+ 55 must be lower than D 50`, `C+ 65 must be lower than D+ 55`, `B+ 75 must be
   lower than C+ 65`, and Save boundaries stays disabled.

Grade **assignment** is not affected, because `letterGrade` sorts by value, as `calculators.assign_letter_grade`
does.

grade-tui has the same kind of bug in its Edit Boundaries dialog. `types.rs` holds `grade_boundaries` as a
`BTreeMap`, so `start_editing_boundaries` lists the letters alphabetically (`A, B, B+, C, C+, D, D+`).

## Decisions (from the interview)

| # | Decision |
|---|---|
| D1 | **Fixed scale order** everywhere a list of letters is shown or checked: `A, B+, B, C+, C, D+, D`, then `F`. A letter outside the scale (e.g. `A+`) is placed by its **saved** threshold among the others. No code ever relies on object key order again. |
| D2 | The check stays strict: thresholds must go strictly down along the D1 order. `B+ 69` under `B 70` is refused. |
| D3 | Each letter shows its **half-open interval**, written as grade-tui writes boundaries: `B 70 ≤ X < 75`, so 70.1 and 74.5 are both B. The top letter reads `X ≥ 80` and F reads `X < 50`. The text updates live as you type. |
| D4 | New **Grade distribution** on the Grading tab (grade-tui's "Letter Grade Distribution"): count and % per letter in D1 order. It is **live**: it uses the saved scores plus unsaved edits, and while a weights or boundaries form holds a changed, valid value it uses the typed values and shows a `(preview)` tag. |
| D5 | A student with no scores counts as `F`, as in grade-tui and the Python dashboard. |
| D6 | **Grade colours**: grade-tui's hue progression (A blue → B+ teal → B green → C+ lime → C yellow → D+ amber → D orange → F red), tuned for the web so each colour reaches ≥ 4.5:1 contrast as text in light and dark mode. Used in the wide-table Grade column, the student detail card, the Grading tab (letter labels + distribution) and the preview lines (`B → B+`). The distribution bars are filled from the palette tokens `--bar-*` instead (SPEC_bar_colours.md). |
| D7 | grade-tui's Edit Boundaries dialog uses the D1 order and the D2 check, with the same message wording. |
| D8 | Everything is committed on `web-app`. Claude runs `clasp push --force` and `clasp update-deployment <id>` only after every test passes. Commits stay local (the user pushes to GitHub). |

## Rules (exact)

### Order: `gradeOrder(saved)`

- Input: a `{letter: threshold}` map as saved (course.json / config). Output: the letters as an array.
- Known letters (`A, B+, B, C+, C, D+, D`) keep their scale rank. Each unknown letter goes just before the first
  letter (in the result built so far) whose saved threshold is lower than its own, or at the end. Ties among unknowns
  are broken by key text, so the result is deterministic.
- `F` is never a key. It is added only by callers that show an F row.
- Unknown letters are placed by the **saved** values, never the typed ones, so rows don't move while you type.

### Check: `configProblems('grade_boundaries', gradeOrder(saved), form)`

The existing check, given the D1 order instead of `Object.keys`. Each problem is `{field, reason: 'order', upper}`
for the lower letter, so the message keeps today's wording, e.g. `B 70 must be lower than B+ 69`. The number checks
(empty, comma, negative, not a number) are unchanged.

### Ranges: `gradeRanges(order, values)`

`values` must pass the check (otherwise every row shows `—`). X is the Final Score as it's compared with the
thresholds (`letterGrade`, `assign_letter_grade`). The rule is `t_i ≤ X < t_above`, so every value in the interval
gets the letter, decimals included (70.1 and 74.5 are both B). A score reaches B+ only when it is 75 or more. Today's
Final Score is already a whole number, because coursework, midterm and final are each rounded up before they're
added (CLAUDE.md "Grade calculation" step 4). The grade math is unchanged.

- Top letter: `X ≥ {t}`.
- Every other letter: `{t} ≤ X < {t_above}`.
- `F`: `X < {t_lowest}`.
- Thresholds print as numbers, without trailing zeros (`74.5`, `70`, not `70.0`). Use `≤`, `<` and `≥` with a space
  on each side.

| Saved boundaries | Shown |
|---|---|
| A 80, B+ 75, B 70, C+ 65, C 60, D+ 55, D 50 | A `X ≥ 80`, B+ `75 ≤ X < 80`, B `70 ≤ X < 75`, C+ `65 ≤ X < 70`, C `60 ≤ X < 65`, D+ `55 ≤ X < 60`, D `50 ≤ X < 55`, F `X < 50` |
| B+ 74.5 (rest default) | B+ `74.5 ≤ X < 80`, B `70 ≤ X < 74.5` |
| A only, 80 | A `X ≥ 80`, F `X < 80` |

### Distribution: `distribution(grades, order)`

`[{letter, count, pct}]` for `order + ['F']`. `pct = count / n × 100`, shown to one decimal (`15.0%`). With n = 0
the section reads `No students yet.` A letter that appears in `grades` but not in `order` can't happen (grades come
from the same boundaries) and needs no handling.

## Files

### Web (`web/apps_script/`)

| File | Change |
|---|---|
| `grades.js` | Add and export `GRADE_SCALE`, `gradeOrder`, `gradeRanges`, `distribution`, `gradeClass(letter)` (mirrors `grade_color_for`: `A*`→`a`, `B+`→`bp`, `B*`→`b`, `C+`→`cp`, `C*`→`c`, `D+`→`dp`, `D*`→`d`, else `f`). `letterGrade` is unchanged. |
| `save.js` | `planConfig` for `grade_boundaries`: check in `Grades.gradeOrder(current)` and build `next` in that order, so the course.json the server writes is in scale order. Weights are unchanged (they use `category_order`). |
| `client_state.html` | `configKeys`, `configProblems`, `configValues`: use `Grades.gradeOrder(course.grade_boundaries)` for boundaries. Add `gradeDistribution()`, which returns `{rows, preview}` from the forms (D4), reusing `gradeChanges`' recompute path. |
| `client_views.html` | Grading tab: a range text after each boundary input; the F row shows its range instead of `below 50`; a new `Grade distribution` section after the boundaries form (rows: coloured letter, bar, `6 (15.0%)`; the bars are `aria-hidden`, the text carries the numbers; a `(preview)` tag next to the heading while it previews). `configStale` lists boundaries in D1 order. Colour classes on the table Grade cell (`paintCell`, `s.key === 'grade'`), the detail card's Grade, the preview lines' letters and the Grading labels. |
| `style.html` | Tokens `--grade-a … --grade-f` in light and dark, plus `.g-a … .g-f` classes and the distribution bar styles. |

Colour tokens (contrast checked by a test against `--bg`):

| Letter | Light (on #ffffff) | Dark (on #121316) |
|---|---|---|
| A | `#0b5cad` | `#7ab8ff` |
| B+ | `#00777a` | `#4fd1d1` |
| B | `#2d7a12` | `#8fdc5a` |
| C+ | `#5a7000` | `#c6e04a` |
| C | `#806600` | `#f2e14a` |
| D+ | `#9a5b00` | `#ffc24d` |
| D | `#b34700` | `#ff9a4d` |
| F | `#b3261e` | `#ff8a80` |

(Starting values. If the contrast test fails for one, darken or lighten it in the same hue until it passes.)

### grade-tui (`rust_tui/src/`)

| File | Change |
|---|---|
| `grades.rs` (new, pure, unit-tested) | `grade_order(&BTreeMap<String, f64>) -> Vec<String>` (D1) and `boundary_problem(order, values) -> Option<String>`, returning the first message, e.g. `B 70 must be lower than B+ 69`. |
| `main.rs` | `mod grades;` |
| `app.rs` | `start_editing_boundaries` fills `settings_keys` from `grade_order`. `save_config` (boundaries) runs `boundary_problem` after parsing; on a problem it sets `self.error` and **keeps the dialog open** with the typed values. The message must be visible while the dialog is open (check in the running TUI). Saving still goes through `update-config`, which sorts by value: unchanged. |

### Docs

- `web/SPEC.md` §13 and the `config.test.js` row: "letters in stored order (never re-sorted)" → the D1 rule, plus the
  range text and the distribution section.
- `web/README.md` status line: mention the distribution.
- `rust_tui/CLAUDE.md` architecture list: add `grades.rs`.

## Tests

| Where | Test |
|---|---|
| `web/tests/grades.test.js` | `gradeOrder` on the screenshot order (`A, B, C, D, D+, C+, B+`) → `A, B+, B, C+, C, D+, D`; on alphabetical order → same; `A+ 85` lands before `A`; an unknown letter at 0 lands last; a single-letter map (`A 80`). `gradeRanges`: the three table rows above. `letterGrade` agrees with the intervals at their edges: 69.9 → C+, 70 → B, 70.1 → B, 74.5 → B, 74.99 → B, 75 → B+. `distribution`: F1 golden grades sum to n, order matches, n = 0. `gradeClass` table. |
| `web/tests/config.test.js` | `planConfig` with the boundaries map in the screenshot order and unchanged values → ok, no problem, `Object.keys(course.grade_boundaries)` in D1 order. Typed `B+ 69` with `B 70` → `INVALID`, field `B`, upper `B+`. The existing `ac10_4` tests are updated to the D1 rule (they asserted "never re-sorted"). |
| `web/tests/style.test.js` (new) | Parses the `--grade-*` and `--bg` tokens from `style.html` for light and dark and asserts each contrast ratio ≥ 4.5. |
| `rust_tui/src/grades.rs` | `#[cfg(test)]`: the order cases above and `boundary_problem` (default ok, `B+ 69`/`B 70` message, equal values refused). |
| Existing suites | `node --test 'web/tests/*.test.js'`, `pytest tests/`, `cargo test --manifest-path rust_tui/Cargo.toml`, `web/scripts/e2e.sh`: all green, no golden JSON changes (grade math is untouched). |

## Out of scope

- Grade math and letter assignment (already value-sorted and golden-checked), and the golden JSON.
- Finding exactly which hop scrambles the key order. The fix makes the web independent of it. The `course.json` the
  server writes is now in scale order, and `web-push` is unchanged.
- The Streamlit dashboard, `tui_api.py`, `calculators.py`, `webpush.py`, `webpull.py`.
- grade-tui's Analytics panels (Boundaries list, distribution bars). They already sort by value. No range text in
  the TUI.
- Adding, removing or renaming letters (S10.4 still fixes the key set). Configurable scales.
- Pushing to GitHub. Merging `web-app` into `main`.

## End-to-end verification

1. **Automated:** run from `grade_dashboard/`:
   `node --test 'web/tests/*.test.js' && python3 -m pytest tests/ -q && cargo test --manifest-path rust_tui/Cargo.toml && web/scripts/e2e.sh`.
   Every suite passes, and e2e ends with `E2E OK`.
2. **TUI:** `(cd rust_tui && cargo build --release)`. Run `grade-tui` on `courses/1_test_grading` (a test course, not
   `~/cmru/teachings`) and open Edit Boundaries. The fields read `A, B+, B, C+, C, D+, D`. Type `B+ 69`, then Save.
   The dialog stays open and shows `B 70 must be lower than B+ 69`. Restore `B+ 75`, then Esc without saving.
3. **Deploy:** `cd web && clasp push --force && clasp list-deployments`, then `clasp update-deployment <the
   @N grade_web id>`. The URL stays the same.
4. **Phone:** `python3 grader.py web-push courses/1_test_grading`. Open it in the web app, Grading tab:
   - The letters read `A X ≥ 80`, `B+ 75 ≤ X < 80`, `B 70 ≤ X < 75`, … `D 50 ≤ X < 55`, `F X < 50`, with no red
     messages, and Save boundaries is disabled (nothing changed).
   - Type `B+ 77`. B+ reads `77 ≤ X < 80` and B reads `70 ≤ X < 77`, Save is enabled, the preview lists the changed grades, and
     the distribution shows `(preview)` with the moved counts. Press Reset; the preview tag goes away.
   - Type `B+ 69`. The message `B 70 must be lower than B+ 69` shows, Save is disabled, and the ranges show `—`.
     Reset.
   - The Grade colours show in the Table, the student detail and the distribution, in both light and dark mode.
   - Open the real course from the screenshot (read only, nothing saved). The order is fixed and there are no red
     messages.
5. **Commit** on `web-app` (local only): `fix(web): grade letters in scale order with ranges, distribution, colours`
   and `fix(grade-tui): boundaries dialog in scale order with the descending check`.
