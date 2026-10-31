# grade_web: one useful status line instead of the speed numbers

Status: built 2026-10-31. Branch: `section-folders`. Scope: `grade_dashboard/web/apps_script/`.
Changes where the `?timing=1` line shows (SPEC_discard_and_speed.md D2).

## Context

The user circled the header area on the course list and on a course page, and asked for more useful information
there, in less space, on all pages. The phone link ends in `?timing=1`, so three lines of speed numbers sat under
each header.

## Behaviour

- **Course line** (`headSummary()`, under the course name on Summary, Raw, Analytics and Grading), for example
  `ศ. 08:30-12:30 · 3 at risk · 11 edits not pulled · Pushed 9 h ago`:
  - **Class time:** of the one section shown, from `course.sections`. All and courses without sections have none.
  - **At risk:** students under 80% attendance among those shown, unsaved edits included. Left out when 0.
  - **Not pulled:** left out when 0.
  - **Pushed:** the age, always, last. "Saving…" and "Checking Drive…" still replace the line while they apply.
  - With all four facts it can wrap to a second line on a phone.
- **List line** (`listSummary()`, under `grade_web`): `3 courses · 62 edits not pulled`. The edits part appears only
  when not 0. Until the list is known, the header is only the title.
- **Speed numbers:** with `?timing=1` they sit at the bottom of a course's ⋯ sheet, not in a header. The list page has
  no ⋯ menu, so it shows none. Without `?timing=1`, nothing shows.
- **Full push date:** in the ⋯ sheet's title.
- **Attendance in All:** `attStats()` counts each student over their own section's sessions. Before, a session only
  sec 51 had held counted as an absence for all of sec 52, so All showed 28 at risk when only 1 was (Astro,
  2026-10-31). The grid's At risk only, Total and Sort in All use the same stats and now agree with each section's
  own view. `sessions` in the reply (the Present row, the held marks) still cover everyone shown.

## Out of scope
The chips, search box, attendance toolbar, course cards, student page, server, grader and grade-tui.

## Tests
- `web/tests/head_line.test.js`: both lines, what is left out, the order, and All counting each section by itself.
- `web/tests/style.test.js`: `.head-line`.
- A browser check on the scratch Astro copy (Chromium, phone and computer sizes, light and dark): the course header
  is 79 px on every tab, the line follows the chips and an unsaved edit, and the ⋯ sheet shows the numbers only with
  `?timing=1`.
