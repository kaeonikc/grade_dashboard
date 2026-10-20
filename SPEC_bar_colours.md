# Grade bar colours (web app)

Interview 2026-10-20. The grade distribution bars in grade_web get softer fill colours in grade-tui's hues. The
first round used the user's palette image; see B1. Only the bars change: the letters, the Grade column, the detail card and the attendance chips keep the
readable text shades from SPEC_grade_order.md D6.

## Decisions

| # | Decision |
|---|---|
| B1 | **Hues follow grade-tui** (follow-up the same day: "make it correspond to grade-tui"). The hues are from `rust_tui/src/style.rs` `MONOKAI_PRO`; `~/.config/grade_dashboard/theme.json` has no override. Lightness and chroma are softened in the spirit of the palette image (earlier rounds asked for "a bit darker, not too vivid", and for C and D+ to be more orange). Values are OKLCH (L, C, H), and neighbouring fills are at least 0.10 apart in OKLab. |

| Grade | grade-tui | Fill | OKLCH |
|---|---|---|---|
| A | `#0087ff` blue | `#2772c6` | 0.55, 0.15, 254 |
| B+ | `#00afaf` blue-green | `#2ca2a2` | 0.65, 0.10, 195 |
| B | `#5fd700` green | `#5aac47` | 0.67, 0.16, 140 |
| C+ | `#afd700` green-yellow | `#a4c34b` | 0.77, 0.15, 122 |
| C | `#ffff00` yellow | `#e4d457` | 0.86, 0.145, 102 |
| D+ | `#ffaf00` yellow-orange | `#e8a634` | 0.77, 0.145, 76 |
| D | `#ff8700` orange | `#de7b21` | 0.68, 0.155, 56 |
| F | `#d70000` red | `#bd3a2e` | 0.54, 0.17, 29 |

| # | Decision |
|---|---|
| B2 | **Bars only.** The fills are new tokens `--bar-a … --bar-f`. The `--grade-*` text tokens, the `.g-*` letter colours and the attendance chips (`.att-*`) are unchanged, and still reach 4.5:1 as text. |
| B3 | **Light mode: a 1px edge in the letter colour.** Each bar has an inset 1px edge in its `--grade-*` shade (so the yellow C bar gets a dark gold edge), which keeps the pale fills (the yellow C fill is about 1.4:1 on the grey track) visible. The edge is drawn with an inset `box-shadow`, so a bar with 0 students (width 0%) shows nothing. |
| B4 | **Dark mode: no edge.** The same fills are used in both modes. On the dark track (`--bg2` `#1c1d21`) every fill reaches at least 3:1 (F, the lowest, is 3.05:1), so the edge is turned off (`--bar-edge: 0`). |
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
