# grade_web: grade-tui tabs and a ☰ categories menu

Status: approved 2026-10-19. Branch: `web-app`. Scope: `grade_dashboard/web/`.

## Context

The web app's views (Table, Scores, Attendance, Grading) don't match grade-tui, the dashboard the user works in daily.
The user wants grade-tui's structure on the phone and in the browser: [1] Summary › Summary Scores, [2] Raw Details ›
one category at a time, [3] Analytics › Overview. A ☰ button shows and hides a Categories menu, so jumping between
categories is quick. Editing, saving, Fill, undo, attendance taking and the Grading editor keep working as they do
today. They move into the new structure.

## Decisions (from the interview)

| # | Decision |
|---|---|
| N1 | Tabs **[1] Summary · [2] Raw Details · [3] Analytics · [4] Grading**. Grading is today's weights/boundaries editor, unchanged. |
| N2 | **☰** (top-left of the course header) shows/hides a **Categories** menu for the current tab, like grade-tui's left panel (`s`). Wide screens: a left column next to the content. Phones: a slide-over drawer with a scrim. Picking an entry closes the drawer on phones, but not on wide screens. |
| N3 | Menu entries. [1]: `Summary Scores`. [2]: `All columns` (wide screens only) and then every category in `category_order` with its points (`homework  20 pts`), attendance included. [3]: `Overview`. [4]: no menu, and ☰ is disabled. |
| N4 | **Phones:** the bottom tab bar keeps its place and now holds 4 tabs. [2] › a score category opens today's **column mode limited to that category's columns** (◂ hw1 ▸ … Fill, ขส/Clear/Next bar). [2] › attendance opens today's attendance taking. |
| N5 | **Wide screens:** a top tab strip. [2] › a category shows **that category's table** (ID, Name, its columns, its total), with today's editing, Fill, keyboard and student-detail panel. [2] › All columns is today's full table. |
| N6 | **[1] Summary Scores.** Wide: a read-only table with ID, Name, each weighted category as `homework /20`, Coursework Total, Final Score and Grade (coloured). Clicking a row opens the student detail panel. Phone: a **compact list** (ID, name, Final Score, coloured Grade, ▸). Tapping a row **expands it in place** into that student's full Summary row (each category /pts, Coursework Total, Final Score, Grade) with a `Details ›` button that opens the editable student detail. Tapping again folds it. |
| N7 | **[3] Overview:** four panels, as in grade-tui. **Class statistics** (Enrolled, Mean, Median, Std. deviation, Pass rate with `(n/N passing)`; passing = grade ≠ F). **Grade distribution** (same bars as the Grading tab, current grades). **Histogram** (Final Score, 10 bins: `0-9 … 80-89, 90-100`). **Box plot** (min, Q1, median, Q3, max, mean, whiskers, outliers with names, skew note). |
| N8 | Grade distribution appears in **both** Overview (current grades) and Grading (live `(preview)` while typing). |
| N9 | Summary and Overview are **live**: they include unsaved edits, like today's table and detail. |
| N10 | **Remembered per device:** the menu's open/closed state (default open on wide screens, closed on phones), and per course the last tab + category (first visit: [1] Summary). Wide-screen keys, as in grade-tui: `1`–`4` switch tabs and `s` toggles the menu. These keys work only when focus is not in an input or the table grid, because the table's navigation mode uses digits to start an edit. |
| N11 | Out of the web app for now: Analytics' Progress, Item Analysis, Correlation and At-Risk, [4] Roundup, and Summary's For Submission. |

## Statistics: exact rules (parity with grade-tui)

These are ported from `src/tui_api.py::_compute_analytics` (overview, histogram, box_plot), over
`Grades.computeGrades` rows (all rows, so an empty row counts as Final 0 / F, as in grade-tui).

- `n` = number of rows. mean, median (pandas linear quantile), std (ddof = 1, 0 when n ≤ 1) and pass_rate are each
  rounded with **Python's `round(x, 2)`**: decimal round-half-even on the exact binary value. That is not numpy's
  `round2`. It needs a new `pyRound2` helper, tested on ties (0.125 → 0.12, 0.375 → 0.38, 2.675 → 2.67).
- Histogram: bin = `min(9, max(0, floor(score / 10)))`; labels `0-9`, …, `80-89`, `90-100`. It is empty when n = 0.
- Box plot: q1/median/q3 use linear interpolation (`pos = (n−1)·q`). Fences are `q1 ∓ 1.5·IQR`. Whiskers are the
  min/max of the non-outliers. mean is `pyRound2`. The skew label uses `(mean−median)/IQR`: |r| < 0.05 is "roughly
  symmetric", r > 0 is "right-skewed (mean > median)", otherwise "left-skewed (mean < median)". Outliers are sorted
  by score. n = 0 gives all zeros and "roughly symmetric".
- Parity is enforced by golden JSON: `web/tools/make_golden.py` also writes `analytics: {overview, histogram,
  box_plot}` from `get_course_data` for each fixture F1–F4 (without `raw_index`), and a node test compares the JS
  with `assert.deepStrictEqual`.

## Files

### Web (`web/apps_script/`)

| File | Change |
|---|---|
| `grades.js` | Add and export `pyRound2`, `quantile(sorted, q)` and `overview(grades, rows)` → `{stats, histogram, box}` (rules above; `rows` gives names for the outliers). Reuse `distribution`, `gradeOrder` and `gradeClass` from SPEC_grade_order. |
| `client_state.html` | `state.view` becomes `state.tab` ∈ `summary` / `raw` / `analytics` / `grading`, plus `state.category` (a category name, or `*` for All columns) and `state.menu` (bool). `uiMemory` keeps `v: 1` and adds `tab` and `category`. An old saved `tab` of `scores`/`attendance` maps to `raw` with the first score category or attendance. A new per-device key `gw:ui:menu` holds the menu state (try/catch, as today). Column mode and the wide table take a **category filter** (`columnsOf(category)` over `course.columns` by `.category`). Add `summaryRows()` (grades + names, live) and `overviewData()` (`Grades.overview` + `Grades.distribution` over `state.grades`). |
| `client_views.html` | Header: a ☰ button (`aria-expanded`, `aria-controls="cat-menu"`, label "Categories"). The wide tab strip replaces today's view switch, and the phone tab bar gets 4 tabs. `renderMenu()` builds the nav list (N3; current entry `aria-current="page"`). On a phone the drawer moves focus into the menu, closes on Esc or a scrim tap, and returns focus to ☰. `renderView()` dispatches on `state.tab` (`renderSummary`, raw → `renderTable(filter)` / `renderColumn(filter)` / attendance, `renderOverview`, `renderGrading`) and keeps today's clean-up of the other views. Keys from N10. `renderSummary`: the wide table, or the phone list with expandable rows (`aria-expanded` on each row button). `renderOverview`: the four panels. The histogram reuses the `.dist` bar markup. The box plot is an inline SVG on a 0–100 axis (`aria-hidden`) plus a text line with every value and the outlier names (the accessible version). |
| `style.html` | Layout grid for menu + content (wide), the drawer and scrim (phone), the tab strip, the 4-tab bottom bar, the summary table and list, overview panels, and box-plot strokes using existing tokens (no new colours, so `style.test.js` keeps passing). |

### Tools and tests

| File | Change |
|---|---|
| `web/tools/make_golden.py` | Add the `analytics` block to each fixture's golden and regenerate `web/tests/golden/*.json`. Grades are unchanged, so `tests/test_web_golden.py` stays green. |
| `web/tests/grades.test.js` | `analytics parity <fixture>` ×4 (deepStrictEqual against the golden). `pyRound2 ties`. `quantile linear` (1, 2 and 4 values). `overview n = 0 and n = 1`. `histogram 100 → 90-100`. `outliers sorted with names`. |
| `web/tests/state.test.js` (new, pure parts) | `columnsOf` per category (F2: homework → hw1..hw3; attendance → sessions). uiMemory migration (`tab: 'scores'` → raw + first score category; `attendance` → raw + attendance). |

### Docs
- `web/SPEC.md` Interface: a short pointer section to `SPEC_web_tabs.md` for navigation; the old view switch text is
  marked superseded.
- `web/README.md` status line.

## Edge cases
- A course with no weighted categories: the [1] table shows ID, Name, Final and Grade, and [2] lists only All columns.
- A category with no pushed columns (e.g. `final` mapped but its file isn't pushed): it is listed, and opening it
  shows "No columns pushed for final."
- Unsaved edits: the badge/Save button stays visible on every tab. Switching tabs never drops edits, and the draft
  works as today.
- An open student detail survives switching between [1] and [2], as it does today between views.
- n = 0 (roster only): Overview shows "No students yet." in each panel.
- A remembered category that no longer exists after a re-push: fall back to the first category.

## Out of scope
- grade-tui and every Python module except `web/tools/make_golden.py`.
- Analytics' Progress, Item Analysis, Correlation and At-Risk, [4] Roundup, and Summary's For Submission (N11).
- Server (`Code.js`, `save.js`, `drive.js`, `journal.js`) changes. The new views read data the client already has.
- New colours or theme changes.

## Verification (end to end)
1. **Automated** (from `grade_dashboard/`): `node --test 'web/tests/*.test.js' && python3 -m pytest tests/ -q &&
   cargo test --manifest-path rust_tui/Cargo.toml && web/scripts/e2e.sh`. All pass, and e2e ends `E2E OK`.
2. **Local render** with the scratchpad preview harness (real server code over a tmp Drive with fixtures F1–F3,
   headless Chrome). Take screenshots at 500px (phone) and 1200px (wide), light and dark:
   - Opening a course lands on [1] Summary. On wide screens the full table shows coloured grades. On the phone, the
     list rows expand to the full row and `Details ›` opens the student detail.
   - ☰ toggles the menu on both widths. On the phone the drawer closes after a pick, and the state persists across a
     reload.
   - [2] › homework shows hw1..hw3 + the homework total (wide) or column mode limited to hw1..hw3 (phone), and typing
     a score marks it unsaved. [2] › attendance opens attendance taking. [2] › All columns is today's table (wide).
   - [3] › Overview for F2 matches the golden numbers (mean, median, std, pass rate, histogram counts, box plot
     values and outlier names).
   - [4] Grading is unchanged and still shows the live preview distribution.
   - Keys `1`–`4` and `s` work in navigation, and digits typed in the table still edit cells.
3. **Deploy**: `cd web && clasp push --force`, then `clasp update-deployment <id> -V <N>` for **both** deployments
   ("grade_web" and "New grade_web_app"). `clasp list-deployments` shows the new numbers.
4. **Phone**: open the real course read-only. Check [1] (expand a row), ☰ → [2] › homework, [3] Overview, then
   leave without saving.
5. **Commit** locally on `web-app`: `feat(web): grade-tui tabs, ☰ categories menu, Summary and Overview`.
