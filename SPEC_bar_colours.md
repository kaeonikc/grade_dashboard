# Grade bar colours from the palette (web app)

Interview 2026-10-20. The grade distribution bars in grade_web take their fill colours from the user's palette
image. Only the bars change: the letters, the Grade column, the detail card and the attendance chips keep the
readable text shades from SPEC_grade_order.md D6.

## Decisions

| # | Decision |
|---|---|
| B1 | **Hue order stays blue → red**, the same order as today and as grade-tui. Fills are the palette swatches, sampled from the image, then toned down (follow-up the same day: "a bit darker, not too vivid"). Each swatch is converted to OKLCH, with lightness × 0.88 and chroma × 0.78, and the hue is kept. The image has no darker yellow, peach or sky, so a single rule is used for A, B+, B and F. Follow-up: "C and D+ more orange, and the nearby colours to match". C+ to D are set by hand on a warm ramp toward F's brick red. In OKLCH (L, C, H) they are C+ (0.80, 0.125, 92) mustard, C (0.735, 0.145, 70) amber orange, D+ (0.665, 0.155, 55) orange, and D (0.605, 0.15, 39) red orange. That makes each neighbour about 0.07–0.09 apart in OKLab. |

Swatch → fill:

| Grade | Swatch | Fill |
|---|---|---|
| A | `#327df6` blue | `#336ac5` |
| B+ | `#5ed0fa` sky | `#5caece` |
| B | `#5fce3d` green | `#5aab43` |
| C+ | `#fae14c` yellow | `#dbbb56` (ramp) |
| C | `#f2a983` peach | `#e2972c` (ramp) |
| D+ | `#ee7e31` orange | `#da751d` (ramp) |
| D | `#ec6b71` coral | `#ca5c36` (ramp) |
| F | `#ea332b` red | `#bd382f` |

| # | Decision |
|---|---|
| B2 | **Bars only.** The fills are new tokens `--bar-a … --bar-f`. The `--grade-*` text tokens, the `.g-*` letter colours and the attendance chips (`.att-*`) are unchanged, and still reach 4.5:1 as text. |
| B3 | **Light mode: a 1px edge in the letter colour.** Each bar has an inset 1px edge in its `--grade-*` shade (so a yellow C+ bar gets a dark olive edge), which keeps the pale fills (the yellow C+ fill is about 1.7:1 on the grey track) visible. The edge is drawn with an inset `box-shadow`, so a bar with 0 students (width 0%) shows nothing. |
| B4 | **Dark mode: no edge.** The same fills are used in both modes. On the dark track (`--bg2` `#1c1d21`) every fill reaches at least 3:1 (F, the lowest, is 3.0:1), so the edge is turned off (`--bar-edge: 0`). |
| B5 | **Where:** every `.dist` bar coloured by a grade: the Grading tab's "Grade distribution" (including its `(preview)` state while boundaries are being edited) and Analytics › Overview's "Grade distribution". Unknown letters fall into F through `Grades.gradeClass`, as today, and get the F fill. |

## Files

- `web/apps_script/style.html`
  - `:root` (defined once and shared by both modes): `--bar-a … --bar-f` from the B1 table, then `--bar-edge: 1px;`
  - Dark `:root` inside `@media (prefers-color-scheme: dark)`: `--bar-edge: 0;`
  - `.dist .bar span` takes `background: var(--bar-fill, currentColor); box-shadow: inset 0 0 0 var(--bar-edge)
    currentColor;`. `currentColor` is the span's `.g-*` letter colour, so the edge matches the letter.
  - The span already carries `.g-*`. A grade colour class inside a bar also sets its fill, for example
    `.dist .bar .g-a { --bar-fill: var(--bar-a); }`, one line per letter.
  - The histogram's `.plain` bars keep `var(--accent)` with no edge: `.dist .bar span.plain { box-shadow: none; }`.
- `web/apps_script/client_views.html`: no change, because `barItems` already puts `g-<x>` on the bar span.
- `web/tests/style.test.js` gets new tests:
  - Each `--bar-<x>` exists in the first `:root` with the exact hex from B1.
  - In dark mode, each fill reaches at least 3:1 on `--bg2` (WCAG 1.4.11, non-text contrast).
  - In light mode, each bar's edge colour (`--grade-<x>`) reaches at least 3:1 on `--bg2`, and `--bar-edge` is
    `1px`.
  - In dark mode, `--bar-edge` is `0`.
  - The rule `.dist .bar span` uses `var(--bar-fill` and `inset`.
  - The `--grade-*` values are unchanged (the existing 4.5:1 tests still pass as they are).
- Docs: `web/SPEC.md` (the Accessibility tokens paragraph names the bar tokens and B3/B4) and
  `SPEC_grade_order.md` D6 (one line: the bars use `--bar-*`, see SPEC_bar_colours.md).

## Out of scope

- The letter, Grade column, detail card and preview-line colours (`--grade-*`).
- The attendance chips, and the P/L/A/X code buttons.
- The Final Score histogram, which keeps the accent blue. It counts score bins, not grades.
- grade-tui (Rust) and the Streamlit dashboard.
- A light/dark switch inside the app (`data-theme`). The app follows the system setting, as today.

## Edge cases

- A letter with 0 students: the bar has width 0% and shows nothing, with no edge sliver (inset shadow).
- A letter with very few students (for example 1 out of 40 next to a top count of 20): the bar is a few pixels
  wide, and the edge still marks it.
- A boundary preview with custom letters: `gradeClass` maps them as today (for example `A-` → a). Anything else
  falls into F and gets the red fill.
- Windows high contrast / `forced-colors`: browsers drop backgrounds and shadows, and the count text still gives
  the number. No change is needed.

## Verification

1. Test first: the new `style.test.js` tests fail before the CSS change and pass after. Full suites:
   `node --test 'web/tests/*.test.js'` (163 + new), `pytest` (177, untouched), `web/scripts/e2e.sh` → `E2E OK`.
2. WebKit, iPhone 13 emulation, through the scratchpad preview harness. Open a test course with grades spread over
   all eight letters plus one letter at 0, then screenshot:
   - the Grading tab and Analytics › Overview in light mode, at 390 and 844 widths;
   - the same views in dark mode (`colorScheme: 'dark'`).

   Check by eye:
   - the eight bars show the B1 colours in order;
   - the yellow, sky and peach bars are clearly outlined in light mode;
   - there is no outline in dark mode;
   - the 0-count row shows an empty track;
   - the letters and the histogram look exactly as before.

   Read the computed `background-color` of each bar span with `getComputedStyle`, and check that it equals the B1
   hex.
3. Commit on `web-app` (local only). After every test passes, `clasp push --force`, `clasp create-version`, then
   `update-deployment` on both deployments to the new version (v14). On the phone, the user opens a **test copy**
   course's Grading tab and checks the colours in light and dark mode.
