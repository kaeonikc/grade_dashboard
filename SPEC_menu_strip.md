# grade_web: categories under the sections, a frozen top area, and a phone score grid

Date: 2026-10-31. Status: approved and built (as-built notes at the end). Branch: `section-folders`.

## Context

The ☰ menu hides what it holds. On Raw it lists the categories, and on Summary and Analytics it lists a single entry
that does nothing useful. On a phone the top of the Raw page takes about 280 px, of which the student list scrolls
away with the page, and only 4 or 5 students fit on screen (rows are about 64 px).

The goal is that the categories are always visible, the top of the page stays still, and only the student data moves.

Facts from the real courses (read only): 5 or 6 categories (`attendance homework lab quiz midterm final`), up to
55 students, every name starts with `นาย` or `นางสาว` (115 of 115), and the longest name is 33 characters with its
title. The screenshot's phone is 374 px wide and 665 px tall.

## Decisions

| # | Decision |
|---|---|
| M1 | **The ☰ goes**, on phones and computers: the button, the drawer, the side column, its scrim, and the `s` key. |
| M2 | **Categories are a row under the sections**, on the Raw tab only. Tapping one opens it. The row is one line and slides sideways if it doesn't fit, with the chosen one scrolled into view. Labels are the full category names, as in the ☰ today. |
| M3 | **The section selector shrinks** to about 32 px tall (`All · 55`, `Sec 51 · 28`, `Sec 52 · 27`) and keeps its colours. The category row is the same height. |
| M4 | **The top area is a shaded panel** on `--bg2`, with a thin full-width line between its rows and a stronger line at its bottom edge. |
| M5 | **The top area freezes on every tab.** Only the content under it scrolls. On Raw that's the grid, on Summary the list, and on Analytics and Grading the page content. The bottom tab bar and Save stay frozen as they do now. |
| M6 | **Phone Raw is a grid for every category**, the same as the Attendance grid: the student column frozen on the left, the category's columns and its total sliding sideways. The Column picker row (`‹ hw1 ›`, `homework · max 7.5 · 0 of 55 entered`) goes. Each column's header shows `hw1`, `/7.5` and `0/55`. |
| M7 | *(Superseded in part by SPEC_fill_dismiss.md D2-D3: a tap outside the cell now only closes it, including a tap on another score cell.)* **Tap a score cell on a phone to type.** The keypad bar (ขส, Clear, Next ↓) works as it does today, and Next goes down the same column. Past the last student it closes the keypad and says `End of list · k of n entered`. Refused text stays in the cell with its message, and Next doesn't move. |
| M8 | **While typing, the top slides away.** Only the column headers stay, the grid fills the space above the keypad bar, and everything returns when the keypad closes. |
| M9 | **Smaller text in phone student lists:** name 13 px, ID 11 px under it, scores 14 px, rows about 40 px, so about 10 students fit. The column headers are 12 px. The student column is about 9.5rem wide. |
| M10 | **The title is hidden in phone student lists**: `นางสาวกาลัญญ น้อยทู่` shows as `กาลัญญ น้อยทู่`. Names are never cut off; a long one wraps between first name and surname. The title stays in the data, the student page, the Save sheet, screen-reader labels and search. |
| M11 | **The computer gets M1 to M5** with All columns as the first category and `· 15 pts` kept on the chips. Text size, names with titles and click-to-select in the table stay as they are. The table gets the 14rem back. The category row goes above the `[1] Summary …` strip. |

## Decisions I made that you can overrule

- **Tap size:** the section and category buttons are 32 px tall, under this app's usual 44 px. You asked for smaller
  ones. They keep a small gap so a tap doesn't land on the neighbour.
- **Points on a phone:** the chips show no points. The grid's last column already says `homework /15`.
- **All columns stays computer only.** It would add a seventh chip for a table few would use on a phone.
- **`was 5.0` under a changed score goes on a phone**, because a grid cell has no room for it. A changed cell keeps its
  amber background and `*`, above max keeps `▲` in red, and the old value is still on the Save sheet.
- **Fill** acts on the highlighted column. Tapping a header or a cell picks it, and the first column is picked when a
  category opens. This is how the computer already works.
- **Attendance on a phone:** `Take today ›`, `At risk only` and `Sort` join the search on one row, with shorter labels
  (`Today ›`, `At risk`, `Roster` or `Lowest %`) and their full wording kept for screen readers. Grid and session
  behaviour don't change, and a session's big P/L/A/X buttons keep their size.
- **The session view keeps its column row** (`‹ Grid`, `‹ session ›`), one line with the `Column` label hidden, because
  that is how you move between sessions.
- **Landscape phones keep today's rule:** the top scrolls away so the grid gets almost the whole screen
  (SPEC_landscape.md).
- **A draft banner or storage warning sits in the frozen area.** They are rare, and the banner can be dismissed.
- **Section headings in All** (`Sec 51 · 28 students`) scroll with their students.

## Interfaces and files

**`web/apps_script/grades.js`**
- New pure `plainName(name)`: removes one leading `นางสาว`, `นาย`, `นาง` or `น.ส.`. A name that would end up empty
  comes back unchanged.
- `modeOf`'s rule changes in `client_views.html` (below); `navFromMemory` stays, so an old remembered `scores` tab still
  opens Raw.

**`web/apps_script/client_views.html`**
- Remove `cm.menuBtn`, `cm.menu`, `cm.menuList`, `cm.scrim`, `menuEntries`, `renderMenu`, `toggleMenu`, `closeDrawer`,
  `pickMenu`, the `s` key, and the menu lines in the `WIDE` change handler. `catPoints` stays for M11.
- New `cm.catBar` (`role="group"`, `aria-label="Categories"`) after `cm.secBar`, drawn by a new `refreshCatBar()` from
  `renderView()`, hidden off the Raw tab. Its buttons call `setCategory`, and the chosen one has `aria-pressed="true"`.
- `modeOf()`: Raw is `table` at both widths for every category, except an open attendance session. The `'scores'` mode
  and the code only it used go. `renderColumn` stays for the session view.
- `tableColumns()`: no ID column on phones, as `attColumns()` does. `paintCell`: on phones the name is
  `plainName(row.name)` with the ID under it, for every table. `buildTable`: `compact` for every phone table.
- `headCell`: on a phone a score column's header also shows its max and entered count, refreshed by `refreshCounts`.
- `tableClick`: on a phone a score cell picks the column and calls `startEdit`.
- `keypad`, `barSet` and `move` work on the open grid editor as well as `cm.current`. A new `body.typing-grid` class
  drives M8, separate from `typing` so typing in the student page doesn't move the page behind it.
- Next keeps the iPhone keypad open by moving focus inside the tap. If removing the old input closes the keypad, the
  editor moves one input from cell to cell instead.
- `reveal()`, `placeBar()` and the `window.scrollTo` calls (recheck, open) work on the area that now scrolls. `placeBar`
  also sets the grid's height from `visualViewport` while typing.
- Summary, session and search lists use `plainName` on phones and wrap instead of `…`.

**`web/apps_script/client_state.html`**
- Remove `state.menu`, `menuPref` and `rememberMenu`. The old saved setting is ignored.

**`web/apps_script/style.html`**
- Remove the ☰ rules in section 14 (`.menu-btn`, `.cat-menu`, `.scrim`, `.menu-title`, `.menu-list`, `.cat-item`,
  `body.menu-open main`).
- Add the panel (M4), `.cat-bar`, and the compact section buttons.
- Phone course pages become a fixed-height column (`100dvh`) in which one area scrolls.
- Phone sizes for M9. Inputs and `.tb-input` stay at 16 px or more, because iOS Safari zooms the page when a smaller
  input takes focus; a cell shows 14 px and grows to 16 px only while being typed in.
- `@media (max-height: 500px)` stays the exception for landscape.

**Tests and docs**
- `web/tests/nav.test.js`, `style.test.js`, `page_scope.test.js`; new `web/tests/menu_strip.test.js`.
- `web/README.md` (the expected-screen step, any ☰ mention); a superseded note in `SPEC_web_tabs.md` for the ☰ and in
  `SPEC_name_stripes.md` for N1's name column size.

## Out of scope

- grade-tui, `grader`, Python, Apps Script server code and the course data format. This is page code and style only.
- The course list page, the student page, the ⋯ menu, dialogs and the Grading and Analytics content.
- The bottom tab bar, Save and Discard.
- Phone All columns. Sorting or freezing score columns other than the student column.
- Showing the title differently per course or as a setting.
- Stripes and section colours: unchanged, on the smaller rows.

## Tests (new, written first)

- `plainName`: `นางสาว…`, `นาย…`, `นาง…`, `น.ส.…`; no title; English names; a title alone is unchanged; only one title
  comes off (`นางสาวนายิกา …` keeps `นายิกา`).
- `modeOf`: every Raw category is `table` on a phone, and an open session is `attendance`. Computer unchanged.
- Category entries: phone has no All columns, computer has it first; no points on a phone.
- `tableColumns`: no ID column on a phone, and the ID sits under the name.
- Style: the ☰ rules are gone; `.tb-input` and score inputs are at least 16 px on phones; `.cat-bar` and the panel exist.
- `page_scope.test.js` guards the new names, and no page script mentions the removed names.
- All existing suites pass: `node --test 'web/tests/*.test.js'`, `pytest tests/`, `web/scripts/e2e.sh`.

## End-to-end verification

1. **Browser check** on the preview harness with a scratch copy of the Astro course (never the real course or Drive),
   Chromium at 375×665 and 1280×800, light and dark:
   - No ☰ on any tab or width, and `s` does nothing.
   - Raw on a phone: chips are visible under the sections, tapping each category opens its grid, and at least 9 students
     show on screen (measured).
   - Scrolling the grid down moves only rows: the top area and headers keep the same pixel position. Scrolling sideways
     moves only data: the student column keeps its position. Summary, Analytics and Grading keep their top area too.
   - On a phone every name shows with no title and no `…`, and search still finds a student by full name with its title
     and by ID.
   - Typing: tap hw1 for the first student, type a score, tap Next, and the next student's cell is open. The value is an
     unsaved edit, the `0/55` count moves, the grade preview updates, and Save writes it to the scratch Drive.
   - ขส, Clear, a refused value and End of list behave as in M7. Fill acts on the highlighted column.
   - With a shrunken viewport standing in for the keypad, the top area hides and the row being typed stays visible.
   - Sec 51, Sec 52 and All each show the right students and colours in the grid. A course without sections shows no
     section row and still shows the categories.
   - Attendance grid and session view still work; a landscape phone (844×390) keeps today's behaviour.
   - Computer: categories sit under the sections, All columns is first with points on the chips, the table uses the full
     width, and text size is unchanged.
2. **Commit** locally on `section-folders`, with no git push. `web/.app/log.jsonl` stays alone.
3. **Deploy** with `web/scripts/deploy.sh`, only after you say so. `clasp list-deployments` shows both on the new version.
4. **You, on the iPhone:** Chromium can't show the iPhone keypad, so only this step proves M7 and M8. Close and reopen the
   grade_web tab, open a homework column, type three scores in a row with Next, and check that the keypad stays open, the
   page doesn't zoom, and the row you're on stays above the keypad bar.

## As built (2026-10-31)

- **Space on a 375×665 phone:** the top area is 189 px on Raw in Sec 51, the column headers 50 px and the dock 66 px,
  which leaves 9 whole rows of 40 px. With all four facts on the status line it wraps, and 8 rows fit. A status message
  in the dock costs one row for its 4 seconds.
- **Category row:** six categories fit on a 375 px phone without sliding (the panel's side padding is 0.5rem on phones).
- **Column names on a phone:** headers and `Fill…` use the short column name (`hw1`), because real headers already
  carry `(7.5pts)` and the max would show twice.
- **Keypad:** Next opens the next editor before the old input leaves the page, so focus moves from input to input. The
  single moving input described as a fallback wasn't needed in Chromium; only the iPhone can confirm that.
- **Tapping another score cell while typing** goes straight there, with the keypad kept open.
- **While typing,** the page's height and top come from `visualViewport` (`--typing-h`, `--typing-top`, `--bar-h`).
- **Moved to `client_state.html`** so they can be tested without a page: `modeOf`, `catEntries`, `catPoints`,
  `tableColumns(wide)`, `attColumns(wide)`.
- **Fixed on the way:**
  - `No columns pushed for lab.` was hidden by the `.view-table .empty` rule, on computers too.
  - The grid's frozen header showed through the student page. `.table-wrap` now has `isolation: isolate`.
  - The search hint on the phone Attendance row is `Search`, because the row is shared with three buttons.
