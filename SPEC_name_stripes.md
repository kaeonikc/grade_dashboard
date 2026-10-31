# grade_web: full student names and striped rows in the grids

Status: approved and built 2026-10-31 (as-built notes at the end). Branch: `section-folders`. Scope: `grade_dashboard/web/apps_script/`.
Builds on `SPEC_attendance_grid.md` and `SPEC_sections.md`.

## Context

The user sent a phone screenshot of Raw › attendance for Astronomy, Sec 51. They asked for two changes (translated
from Thai): "widen the column with the student's name and ID so the whole name shows; no text should be cut off", and
"a light background alternating between rows, in this section's colour (e.g. light blue), so I don't lose my place
while I focus on one student. Leave everything else as it is."

What the code does now:
- **Phone grid** (`.att-grid.compact`, below 960 px): the frozen Name column is fixed at 9rem, and the ID sits under
  the name. Names are cut with "…" after about 13 characters (`.tb .c-name`: `overflow: hidden; text-overflow:
  ellipsis`, `.tb td`: `white-space: nowrap`).
- **Wide table** (`.tb`, 960 px and up; scores, and the attendance grid on a computer): frozen Student ID (7.5rem) and
  Name (13rem), with the same "…".
- **Rows have no stripes.**
  - In All, a row is tinted only in its ID cell, and its name is in the section colour (`.sec-row`).
  - In Sec 51 or Sec 52 alone, and in a course with no sections, rows have no colour at all.
- **The roster:** Astro names are 15–33 characters (median 23), for example "นางสาว" + first name + surname.

## Decisions (from the interview)

| # | Question | Decision |
|---|---|---|
| D1 | How a full name fits on a phone | **Wrap inside the column.** The column grows from 9rem to 10.5rem, and the name wraps (surname on line 2, the ID under it). Rows get taller. |
| D2 | Where | **Phone attendance grid + wide table (computer).** The phone score-entry list, Summary, the student page and grade-tui stay as they are. |
| D3 | How a full name fits on a computer | **One line, as wide as the longest name.** The Name column fits its longest name and never cuts. It is still at least 13rem. Rows stay one line high. |
| D4 | What gets the stripe | **The whole row**: ID, name and every session or score cell. |
| D5 | Colour | **The section's colour.** Sec 51 uses `--sec-1` (blue) and Sec 52 uses `--sec-2` (amber). This follows the chip order, as `sectionSlot` already does. A course with no sections uses the app blue (`--accent`). |

## Behaviour

**N1. Phone grid names (`.att-grid.compact .c-name`).**
- The column is 10.5rem wide (width, min and max). That's 9rem + 1.5rem. The header "Name" cell matches it.
- The name wraps (`white-space: normal`) at the space between first name and surname. Thai line breaking applies,
  and `overflow-wrap: anywhere` is the last resort, so no part of a name is ever hidden. No ellipsis.
- The ID stays under the name in `.sub`, as now.
- A row is as tall as its name needs: 2 lines for a short name, usually 3. The minimum is the current 2.75rem.
- The session columns are unchanged. About 4 fit beside the name on a 390 px phone.
- `scrollPaddingLeft` is still measured from the Name cell after the build, so keyboard and focus scrolling stay
  clear of the wider frozen column.

**N2. Wide names (`.tb .c-name` on 960 px and up, both the scores table and the attendance grid).**
- The column is `max-content` wide with `min-width: 13rem`, with no `max-width` and no ellipsis. It stays on one line.
- It stays frozen at `left: 7.5rem`, beside the frozen ID.
- The header "Name" cell is as wide as the column.

**N3. Stripes.**
- Every second shown student row (2nd, 4th, …) gets the class `stripe`.
  - "Shown" means after Search, At risk only and the sort. A hidden row doesn't count, so the stripes stay
    alternate while you filter.
  - In All, the count restarts at each section heading. Each block starts with an unstriped row under its
    `Sec 51 · 28 students` heading.
- A striped row's cells are washed with its colour, at about 8% over their own background (light and dark):
  - **Plain cells:** the colour over `--bg`.
  - **Computed cells** (Total, P/L/A/X/blank counts, `c-calc`): the same wash over their grey (`--bg2`), so they
    still read as computed.
  - **The frozen ID and Name cells:** the same wash. These stay opaque, because they are sticky and the cells
    scroll under them.
- **The colour:**
  - In All, each row uses its own section's colour (its `sN` class, as now).
  - In Sec 51 or Sec 52 alone, the table takes that section's `sN` class, so every row uses the section colour.
    The chip that's pressed shows the same colour.
  - In a course with no sections, there's no `sN` class and the wash falls back to `--accent`.
- **These keep priority over the stripe:**
  - an unsaved cell's amber (`.unsaved`);
  - the focus outline;
  - the red text of an over-max or invalid value;
  - the at-risk red;
  - the All-view ID cell, which keeps its section bar and tint (`.sec-row td.c-id`).
- The section headings, the header row and the Present footer are never striped.
- **Contrast:** text, grade colours and attendance chip colours on a striped cell still reach 4.5:1, in light and
  dark.

**N4. Nothing else changes.**
- Column mode (the phone list), Summary, Analytics, Grading and the student page keep their one-line names.
- The chips, the section headings and the All-view section marks are unchanged.
- Keyboard moves, Fill and saving are unchanged.

## Implementation

- **`web/apps_script/client_state.html`:**
  - `stripes(rows, shown)` is a pure function. It takes the rows in table order and a `shown(row)` test, and returns
    the set of student IDs to stripe. It counts only shown rows and restarts at each block of `sectionBlocks(rows)`
    when the view is All.
  - `tableSlot()` returns the `sN` slot of the section being viewed alone, or 0 for All and for a course with no
    sections. It sits next to `sectionSlot`.
- **`web/apps_script/client_views.html`:**
  - `searchTable()` already runs after every build, search, At-risk toggle and sort. It now also toggles `stripe` on
    each `rec.tr` from `stripes(...)`.
  - `buildTable()` adds `s<tableSlot()>` to the table's class when it's non-zero.
- **`web/apps_script/style.html`:**
  - §7 (wide table): N2.
  - §6 (attendance grid, `.att-grid.compact .c-name`): N1.
  - §16 (sections): a `--stripe` wash, `color-mix(in srgb, var(--sec, var(--accent)) 8%, transparent)`, laid as a
    `background-image` over each cell's own background colour. This is why the grey and amber cells and the All-view
    ID cell keep their look. The rule is `.tb tr.stripe td`.

## Out of scope
- **The phone score-entry list, Summary, Analytics, Grading, the student page, grade-tui and the Streamlit
  dashboard** keep their current names and rows (D2).
- **Name content.** The title (นาย / นางสาว) and the name text are not changed.
- **Column widths other than Name**, the colours of the chips or headings, and any server, Python or Drive change.

## Test plan (new tests only; no existing test edited)
- **`web/tests/stripes.test.js`** (node:vm over `client_state.html`, like `sections.test.js`):
  - **Sec 51 alone, 28 rows:** students 2, 4, … 28 are striped.
  - **Search** leaves 5 shown rows. The 2nd and 4th shown rows are striped, and the hidden ones aren't.
  - **All with 51 (28) and 52 (27):** each block restarts, so the first row under each heading is unstriped.
  - **At risk only** (3 shown): the 2nd is striped.
  - **Sort:** the stripes follow the sorted order, not the roster order.
  - **`tableSlot()`:** 1 for Sec 51 alone, 2 for Sec 52, 0 for All and for a course with no sections.
- **`web/tests/style.test.js`** (new tests appended in the file's style):
  - `.att-grid.compact .c-name` has `white-space: normal` and no `text-overflow: ellipsis`, and is 10.5rem.
  - The wide `.tb .c-name` has no `max-width` and no ellipsis.
  - `--text` and every `--grade-*` colour on each stripe colour (8% of `--sec-1…4` and `--accent` over `--bg` and
    `--bg2`) reach 4.5:1, in light and dark.
- **`web/tests/page_scope.test.js`** keeps passing, so the new names don't clash across the page scripts.

## Delivery
1. Write the tests above first and see them fail.
2. Implement until they pass.
3. Run all suites (Verification 1).
4. Run the WebKit check (Verification 2).
5. Commit locally on `section-folders`: `grade_web: full student names and striped rows in the grids`. Not pushed.
6. Deploy with `web/scripts/deploy.sh`, both deployments. **This waits for your OK at the time.**

## End-to-end verification
1. **Automated** (from `grade_dashboard/`): `node --test 'web/tests/*.test.js' && python3 -m pytest tests/ -q &&
   web/scripts/e2e.sh`. Everything passes (web 185 + new), and e2e ends `E2E OK`.
2. **WebKit check** (scratchpad Playwright WebKit plus a preview page that runs the real `Index.html` over a
   scratchpad copy of the real Drive `2026_S2_Astro`, read-only):
   - **iPhone 13 portrait (390×664), Raw › attendance, Sec 51:**
     - every name cell's `scrollWidth ≤ clientWidth`, and none is cut (checked in script for all 28);
     - the longest name is fully visible on 2–3 lines with its ID below;
     - rows 2, 4, … are light blue.
   - **Sec 52:** the same with amber stripes, for all 27.
   - **All:**
     - two blocks, each restarting its stripes under its heading;
     - in each row, the ID cell still has its section bar.
   - **Search "68161" and At risk only:** the shown rows still alternate.
   - **Horizontal scroll:** the frozen Name column stays put and opaque, with session cells passing under it.
   - **Edit a cell to A:** it shows unsaved amber inside a striped row.
   - **Dark mode:** the stripes are visible and the text is readable.
   - **Computer width (1280×800), Raw › attendance and Raw › a score column:**
     - names on one line, none cut (the same `scrollWidth` check for all 55);
     - the Name column is as wide as the longest name;
     - the grey Total/count columns are striped over grey.
   - **A course with no sections** (the e2e fixture course): blue stripes.
   - **The screens that must not change** (phone score list, Summary): they look as before.
   - Screenshots of each go in the scratchpad, and I look at them.
3. **Phone** (you, after the deploy): close and reopen the grade_web tab, then open Astronomy › Raw › attendance.
   - Sec 51: full names and light-blue alternate rows.
   - Sec 52: amber.
   - All: both blocks.

## As built (2026-10-31)
- **Thai word breaking split surnames** ("น้อย / ทู่") in the first browser check. The name cell now holds each
  space-separated part in its own `span.np` (`nameParts`). On the phone these are `inline-block`, so a line breaks
  only between first name and surname. A part longer than the column still wraps (`overflow-wrap: anywhere`).
- **Computed cells get a lighter wash.** At 8%, teal B+ text (`--grade-bp`) on a blue stripe over grey was 4.39:1.
  Computed cells (`c-calc`, `c-att`) use `--stripe-grey` at 5%, and plain cells keep `--stripe` at 8%.
- **The wide Summary table** shares `.tb .c-name`. `.tb.sum-table .c-name` keeps its old 13rem cut, because Summary
  is out of scope (D2).
- **The All-view ID cell** keeps its own section bar and 14% tint and isn't washed on top.
- **Checked in Chromium** (Playwright with iPhone emulation, 390×664, and 1280×800; the installed WebKit build didn't
  match the Playwright package). Results:
  - All 55 names are whole, and none is split mid-word. Phone rows are at most 64 px, and the wide Name column is
    225 px.
  - The stripes alternate in Sec 51, Sec 52 and All, and under search and At risk only.
  - The no-section fixture course has blue stripes.
  - An unsaved cell stays plain amber.
  - The frozen column is opaque.
- **Suites:** web 195/195, Python 266, `E2E OK`.
