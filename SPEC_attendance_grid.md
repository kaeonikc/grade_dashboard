# grade_web: attendance overview grid (grade-tui style)

Status: approved 2026-10-19. Branch: `web-app`. Scope: `grade_dashboard/web/`. Builds on
`SPEC_web_tabs.md` ([2] Raw Details › attendance) and `SPEC_grade_order.md` (colour tokens).

## Context

grade-tui's Raw Details › attendance is a grid: one row per student, one numbered column per session, a coloured mark
per cell, and a Total. The web app shows one session at a time on phones and a plain text table on wide screens, so
there's no overview of how each student is attending. Real courses have 6–14 sessions and up to 57 students.

## Decisions (from the interview)

| # | Decision |
|---|---|
| A1 | Raw Details › attendance opens the **grid** on phones and wide screens. Tapping a **session header** opens the one-session view (today's attendance taking, big P/L/A/X buttons) for that session, with a `‹ Grid` button back. A **`Take today ›`** button opens today's session; it's disabled with "No session today" when none is dated today. |
| A2 | Cells are **coloured letter chips**: P green, L amber, A red, X/EA blue, using the grade colour tokens (P `--grade-b`, L `--grade-dp`, A `--grade-f`, X/EA `--grade-a`), which already pass 4.5:1 on `--bg` and `--bg2`. |
| A3 | Session headers show the **number over a short date** (`1` / `16/6`, day/month). Today's session is highlighted, and a held session that still has blanks shows a `•`. The full date and that session's counts go in the header button's accessible name. |
| A4 | **Phones:** the name column is frozen on the left, with the ID small under the name. Sessions and the summary columns scroll sideways, and the grid opens scrolled so the latest held session and Total are in view. **Wide:** the frozen ID and Name columns, as in today's table. |
| A5 | Summary columns after the sessions: **Total** = `9.6 / 10 · 96%`, then **P, L, A, X** counts (EA counted with X, as grade-tui does; A red when > 0), then **blank**. |
| A6 | **Held so far:** Total and % count only sessions held so far. A session is held when its header date is today or earlier. An undated header (e.g. `a1`) counts as held once any student has a code there. Points: P/X/EA = 1, L = 0.8, A/blank/invalid = 0 (grade-tui's `CODE_VALUE`). The term-wide `attendance /10` stays in Summary. |
| A7 | **At risk:** the Total turns red with ⚠ when % < 80 (exact value). The shown % is rounded **down** (`79.6` shows `79%`), so a flagged row never reads 80%. Nothing is flagged before the first held session. |
| A8 | **Blanks** in a held session are "not entered yet": an empty dashed chip, counted as 0, and counted in the blank column. A blank in a future session is just empty. |
| A9 | **Editing in the grid:** tapping or clicking a cell opens today's picker (P / L / A / X / Clear), and on wide screens the existing keyboard works (arrows, P/L/A/X, Delete). Changes are ordinary unsaved edits (badge, Save, draft). The row's Total, counts, flag and the footer update at once. |
| A10 | **Footer row:** each session's present count (P+L+X+EA), with the full `P n · L n · A n · X n · blank n` in its title and accessible name. |
| A11 | **Finding students:** the existing search box filters the grid. Two toggle buttons: **At risk only**, and **Sort: Roster ⇄ Lowest %** (lowest % first; ties keep roster order; rows with no held session last). The order is applied when toggled or when the grid opens, never while editing (rows don't jump). Both toggles reset when the course is reopened. |

## Rules (pure, in `grades.js`)

`attendanceStats(rows, sessions, textOf, today)`:
- `sessions`: the attendance columns in course order. `textOf(row, column)` gives the saved text with any unsaved
  edit applied. `today` is `YYYY-MM-DD`.
- `held(session)`: `sessionDate(header) <= today`. For an undated header: any row has a non-blank code.
- Per student: `{held, total, pct, counts: {P, L, A, X, blank}, atRisk}`.
  - `held` is the number of held sessions, and `total` is the sum of `CODE_VALUE` over held sessions (unknown codes
    count 0).
  - `pct = held ? total / held * 100 : null`, `atRisk = pct !== null && pct < 80`.
  - `counts` cover held sessions only. EA counts as X. `blank` is a blank cell in a held session. An invalid code
    counts in none of P/L/A/X and isn't blank (the cell already shows it as invalid).
- Per session: `{held, present, counts: {P, L, A, X, blank}}` over all rows.
- Display helpers: `fmtAttTotal(s)` gives `9.6 / 10 · 96%` (total to 1 decimal, held as an integer, `Math.floor(pct)`),
  or `—` when `held = 0`. `shortDate(header)` gives `16/6`, or the header as written when it's undated.

## Files

| File | Change |
|---|---|
| `web/apps_script/grades.js` | `attendanceStats`, `fmtAttTotal` and `shortDate` (rules above), exported. |
| `web/apps_script/client_state.html` | `state.attSession` (bool: the one-session view is open), `state.attRisk` and `state.attSort` (toggles, not remembered). `attStats()` runs `attendanceStats` over `state.rows`, `sessions()`, `cellValue` and `today()`. |
| `web/apps_script/client_views.html` | `modeOf()`: raw › attendance is `'attendance'` (one-session view) when `state.attSession`, else `'table'` on both widths. A grid toolbar above the table holds `Take today ›`, `At risk only` and `Sort`. `tableColumns()`: for the attendance category, `code` specs plus `att` calc specs (`total`, `P`, `L`, `A`, `X`, `blank`). On phones a combined frozen `who` column (name + ID) replaces ID + Name. `headCell` for a session: a header button (number, short date, today/blank marks) that opens the one-session view. `paintCell`: code cells as chips (`att-chip att-P/L/A/X`, dashed when blank in a held session). The `att` cells show stats from `attStats()`, and an at-risk row gets `.at-risk`. A footer `tfoot` row with present counts. `searchTable()` also applies At risk only, and the sort reorders `tb.recs`/rows on toggle or render. `changed(row)` repaints that row and the footer. The one-session view gets a `‹ Grid` button (in the picker row) that clears `state.attSession`. In All columns (wide), sessions also show as chips, without the summary columns or footer. |
| `web/apps_script/style.html` | Chip styles (`.att-chip` with grade tokens, dashed blank), the header button layout, `.today` and the `•`, `.at-risk` (Total in `--danger` with ⚠), the footer row, the grid toolbar, and a phone table layout (frozen `who` column about 9rem wide, sessions about 2.25rem). No new colour tokens. |
| `web/tests/attendance.test.js` (new) | See Tests. |
| `web/SPEC.md`, `web/README.md` | A short pointer to this file. |

## Tests

`web/tests/attendance.test.js`, all over fixture F2 (sessions `13 Jan 2027`, `20 Jan 2027`, `27 Jan 2027`):
- With today = `2027-01-21`, two sessions are held. Per-student `held`, `total`, `pct`, counts and `atRisk` match
  values written out by hand in the test from the fixture rows. The invalid `p` cell is in neither P/L/A/X nor blank.
- With today = `2027-01-12` nothing is held: `pct` is null, `atRisk` false, and `fmtAttTotal` gives `—`.
- With today = `2027-02-01` all three are held.
- An unsaved edit (an overlay through `textOf`) changes the total and counts.
- Undated sessions `a1..a3`: a1 has codes and a2 is all blank, so only a1 is held.
- The 80% boundary: exactly 80 is not at risk, 79.99 is, and `fmtAttTotal` floors (79.99 gives `79%`).
- `shortDate('16 Jun 2026')` gives `16/6`, and `shortDate('a3')` gives `a3`.

The existing suites stay green: `node --test 'web/tests/*.test.js'`, `pytest tests/`, `cargo test`, `web/scripts/e2e.sh`.

## Edge cases
- No attendance sessions: today's message ("This course has no attendance sessions…").
- No held session yet: Total `—`, no flags, the footer shows counts (all blank), and `Take today` works if a session is
  dated today.
- At risk only with nobody at risk: "Nobody is under 80% so far." in the table's empty row (`tb.none`).
- Search plus At risk only: both filters apply.
- A large course: the existing `Building the table…` path is unchanged.
- An edit made while sorted by % doesn't move the row until the next toggle or render.

## Out of scope
- grade-tui and every Python module. The attendance scoring itself (`CODE_VALUE`, the term-wide attendance points).
- Remembering the toggles, exporting the grid, editing session dates, and the student detail's attendance section.
- Other categories' tables: they're unchanged.

## Verification (end to end)
1. **Automated** (from `grade_dashboard/`): `node --test 'web/tests/*.test.js' && python3 -m pytest tests/ -q &&
   cargo test --manifest-path rust_tui/Cargo.toml && web/scripts/e2e.sh`. All pass, and e2e ends `E2E OK`.
2. **Local render** with the scratchpad preview harness (real server code over a tmp Drive with F2, the browser date
   fixed to 2027-01-21 by a harness stub). Take screenshots at 500px and 1280px, light and dark:
   - Raw › attendance shows the grid with coloured chips, headers `1 13/1`, `2 20/1`, `3 27/1` (with the browser date
     on 2027-01-20, 20/1 is marked today), Total `x / 2 · y%` with ⚠ on at-risk rows, P/L/A/X/blank, and the footer present counts.
   - Tapping a cell opens the picker. Picking A turns the chip red, marks it unsaved, and updates that row's Total,
     counts and flag plus the footer.
   - At risk only and Sort: Lowest % behave as specified, and search filters too.
   - Tapping header 2 opens the one-session view for 20 Jan 2027, and `‹ Grid` returns. On 2027-01-20, `Take today ›`
     opens that session.
3. **Deploy:** `cd web && clasp push --force` (no BigInt literals), `clasp create-version`, then
   `clasp update-deployment <id> -V <N>` for both deployments. Check with `clasp list-deployments`.
4. **Phone:** open the real course read-only and check the grid against the TUI's Raw Details › attendance for the
   same course (same marks per student, same totals over held sessions). Leave without saving.
5. **Commit** locally on `web-app`: `feat(web): attendance overview grid like grade-tui`.
