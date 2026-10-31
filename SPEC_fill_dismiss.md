# grade_web: Fill on the attendance grid, and tapping outside only closes

Status: built and committed on `section-folders`, not deployed yet. Date: 2026-11-01.

## Why

1. The Fill button shows on score categories but is hidden on the attendance grid
   (`.view-attgrid .fill-btn { display: none; }`). The only Fill for attendance is inside a one-session view.
2. A tap outside the P/L/A/X pop-up closes it, and then the same tap also lands on whatever is under it, which opens
   another student's pop-up, the student page or a menu. Typing a score on a phone does the same thing: tapping another
   cell opens that cell, on purpose (`keepsEditor`, `editOther`).

## Decisions

| # | Decision |
|---|---|
| F1 | **The attendance grid gets a `Fill…` button** on phones and computers, in the row with the search box. |
| F2 | **The Fill sheet on the grid has a Session menu**, above Cells. It lists every session, marks today's with `· today`, and starts on today's session. With no class today it starts on the latest held session, and with none held, on the first. Changing the session updates `→ n cells will change` at once. |
| F3 | **Tapping a session header still opens that session's big P/L/A/X list.** Headers don't pick a column for Fill on this grid. |
| F4 | **The rest of the sheet is the Fill sheet you already have:** Only empty cells (the default) or Whole column, a value of P L A X or Clear starting on P, the cell count, and `Includes n EA cells` when Whole column would overwrite EA. Filled cells are unsaved edits until you tap Save. |
| F5 | **In All, Fill works and says so:** `All sections: 55 students (Sec 51 · 28, Sec 52 · 27)`. This line appears on attendance only. |
| D1 | **Tapping outside the P/L/A/X pop-up only closes it**, on phones and computers. No other cell, pop-up, student page, chip, tab or button reacts to that tap. Nothing is marked. |
| D2 | **Tapping outside a score cell while typing on a phone only closes it.** This covers every score page (hw, midterm and the rest). The typed number stays as an unsaved edit and the keypad closes. Text that isn't a valid score is dropped, the old value comes back and the message says why, as it does now. |
| D3 | **Changes M7's tap-through:** tapping another score cell while typing no longer opens it (reverses the "keypad stays open" tap from SPEC_menu_strip.md). It closes the first cell, and a second tap opens the new one. **Next ↓, ขส and Clear don't change.** |
| D4 | **Typing on a computer doesn't change.** A click on another cell finishes the score and moves there, like a spreadsheet. Arrows, Enter, Esc, Tab and the P/L/A/X keys stay the same at both widths. |

## Decisions I made that you can overrule

- **Scrolling isn't a tap.** Dragging the grid with a pop-up open scrolls it, and the pop-up stays with its cell. It
  closes only on a tap.
- **The cell itself:** tapping the cell under an open pop-up closes it. Tapping inside the box you're typing in moves
  the caret as usual.
- **After a fill, the grid stays on the filled session.** It doesn't jump back to the latest held one.
- **The sheet says when Fill reaches hidden students.** With a search or `At risk` on, Fill still covers every student
  in the section, and a line says so. The search line exists already; `At risk` joins it.
- **A future session can be filled.** The menu lists every session, and the sheet shows which one you chose. Marks in a
  future dated session don't count towards Total until that date.
- **The button says `Fill…` with no session name on the grid**, because the sheet shows the session. This also leaves
  room on the phone row: search, `Fill…`, `Today ›`, `At risk`, `Roster`.
- **The one-session view keeps its Fill** with no Session menu, because its session is already chosen.

## Out of scope

- The student page's score boxes, which have no pop-up.
- The Fill, Save, Discard and ⋯ sheets. A tap outside a sheet already closes only that sheet.
- Moving to the next student after picking P/L/A/X.
- Fill across several sessions at once.
- Server, grader, grade-tui and Python changes. Fill only makes unsaved edits, as it does now.

## Interfaces and files

**`web/apps_script/client_state.html`**
- New pure `fillSession()`: today's session, else the latest held one, else the first, else null.
- New pure `fillScope()`: the `All sections: …` text in All on attendance, else null.

**`web/apps_script/client_views.html`**
- `refreshChrome()`: `cm.fill` on the grid is enabled when the course has sessions, and reads `Fill…`.
- `openFill()`: on the grid the column comes from `fillSession()` and can change through a new `<select>`. `update()`
  reads the current session, and the title follows it. Adds the F5 line and the `At risk` note. After filling, the grid
  scrolls to the filled session instead of the latest held one.
- New one document-level guard, `outsideTap`, which is the only place that knows the rule:
  - Armed on `pointerdown` (capture) when a tap starts outside the open pop-up, or outside the phone's open editor and
    keypad bar. A computer's score editor never arms it (D4).
  - Closes on `pointerup` if the pointer moved less than 10 px; `pointercancel` or a longer move disarms it (scrolling).
    `pointerup` is used because iOS Safari doesn't send `click` for taps on plain elements.
  - Swallows the `click` that follows, in capture, with `preventDefault` and `stopPropagation`.
  - On a computer, `focusout` still closes the pop-up on mouse down. The guard stays armed, so the click is still
    swallowed.
- Removes `keepsEditor`, `editOther` and their branches in `tableClick` and the table's `mousedown`.

**`web/apps_script/style.html`**
- Removes `.view-attgrid .fill-btn { display: none; }`.
- Adds the sheet's session row. The select stays at 16 px so iOS doesn't zoom.

**Docs:** `web/README.md`, and a superseded note in `SPEC_menu_strip.md` (M7's tap-through).

## Tests (written first)

**`web/tests/fill_dismiss.test.js`** (new, `node:vm` over `client_state.html`, like `menu_strip.test.js`)
- `fillSession()`: today's session; no class today gives the latest held one; none held gives the first; no sessions
  gives null. Undated sessions use the "held once any student has a code" rule.
- `fillScope()`: text with both counts in All; null with a section chosen, on a course without sections, and on a score
  category.
- `fillPlan` for a chosen session: Only empty skips marked cells; Whole column includes EA; unsaved edits count as
  filled; Clear on an already blank column changes nothing.
- The page no longer has `keepsEditor` or `editOther`.

**`web/tests/style.test.js`:** no rule hides `.fill-btn` on `.view-attgrid`, and the session select has no font size
under 16 px.

**`web/tests/page_scope.test.js`** guards the new names.

**Regression:** `web/tests/*.test.js`, `pytest tests/` and `web/scripts/e2e.sh` all pass.

## End-to-end verification

1. **Browser check** in Chromium, on the preview server with the scratch copy of the Astro course, at 375×665 with touch
   and at 1280×800. A new script, `scratchpad/preview/dismiss.js`, checks:
   - **Fill, Sec 51:** tap `Fill…`. The sheet starts on the expected session. Choose another session and see the count
     change. Fill P on Only empty, and only that session's blanks turn amber. Marked cells don't change, the grid stays
     on that session, and `Save n` shows.
   - **Fill, All:** the sheet shows `All sections: 55 students (Sec 51 · 28, Sec 52 · 27)`.
   - **Whole column:** a session with an EA shows `Includes 1 EA cell`.
   - **Phone row:** search, `Fill…`, `Today ›`, `At risk` and `Roster` stay on one line at 375 and 320 px.
   - **Pop-up:** open it for student 1 and tap, in turn, student 2's cell, a name, a section chip, a category chip, the
     bottom tab bar and a header. After each tap the pop-up is gone, no other pop-up or student page opens, the view is
     the same and no value changed.
   - **Pop-up, scrolling:** dragging the grid with the pop-up open scrolls it and the pop-up stays.
   - **Pop-up, picking:** P inside the pop-up still marks the cell.
   - **Typing (phone):** in hw1 type `5` and tap another student's cell. `5` is unsaved, the keypad bar is gone and no
     editor is open. A second tap opens that cell. `abc` and a tap outside puts the old value back with the message.
     Next ↓, ขส and Clear behave as before.
   - **Computer:** after typing a score, a click on another cell moves there. After a pop-up, a click on another
     attendance cell only closes it. Keyboard entry still works.
2. **Commit** locally on `section-folders`, with no git push. `web/.app/log.jsonl` is left alone.
3. **Deploy** with `web/scripts/deploy.sh`, once you say yes. `clasp list-deployments` shows both on the new version.
4. **You, on the iPhone:** close and reopen the grade_web tab. Tap outside a P/L/A/X pop-up, then outside a homework cell,
   and open Fill on the attendance grid. Use a scratch value and Discard afterwards. Only a real iPhone can prove the
   tap handling, because `pointerup` and `click` behave differently in iOS Safari than in Chromium.

## As built

- **Session dates:** `a1, a2…` in Astro and SciTech come from an empty `term_start_date` in their configs. No code
  change is needed: set it, then run `grader update` and `grader web-push`. The Session menu lists whatever the headers
  say, so it shows dates once the columns have them.
- **Phone row:** adding `Fill…` showed that the search box was too narrow (`Sea` at 375 px, over `Fill…` at 320 px).
  - The × now stays hidden until something is typed. It was showing on an empty box until the first search.
  - A phone hides the disabled `No session` button; `Today ›` shows on class days.
  - The search box keeps at least 4.5rem, and a block for phones under 360 px tightens the buttons, so the row fits at
    320 px on a class day with the sort on `Lowest %`.
- **`mousedown` too:** the guard also cancels the press outside, so a tap on the search box doesn't open the keyboard.
- **Browser check:** the end-to-end list ran in Chromium with touch at 375×665 and 320×568, and with a mouse at 1280×800:
  ALL OK. The real iPhone check is still to do.
