# SPEC: Batch score editing, save-on-quit prompt, targeted Fill Column

Status: **confirmed and implemented** · 2026-10-17 · grade_dashboard only (rust_tui + `src/tui_api.py`)
Branch: `batch-edit`, cut from `panel-toggle`.
Previous specs: `SPEC.md` (attendance sync), `SPEC_total_sync.md`, `SPEC_config_columns.md`.

## Problem

In grade-tui, each score needs Enter → popup → type → Enter, and every Enter writes the file at once with its own
`history/` snapshot. Entering one assignment for 40 students means 40 round trips, 40 writes and 40 undo steps.
Fill Column can only set one value for **every** student. Quitting never warns.

## Decisions (from the interview)

| # | Decision |
|---|---|
| 1 | **Spreadsheet-style editing.** Type into the cell under the cursor. Changes collect as *unsaved edits* and `Ctrl+S` writes them all at once. |
| 2 | **Typing keys.** On score cells, `0-9` or `.` starts an edit and `Enter` edits the current value. `Backspace`/`Delete` blanks the cell and `-` marks ขส (absent). On attendance cells, `P` `L` `A` `X` set the code and move down, so `l` means Late there; arrows still move. Every other letter keeps its current command. |
| 3 | **Validation.** Non-numbers (other than blank/ขส) and negatives are refused: the cell stays in edit and a red message shows. Values above the column max are accepted, drawn red, and counted in the save prompt (bonus points). |
| 4 | **Scope.** Unsaved edits last for the whole course visit: they survive category, tab and student-popup changes. A prompt appears on `q`, `Ctrl+C`, and `Esc` back to the course list. Totals, grades, Summary and Analytics show *saved* values until you save. A header badge `● N unsaved` shows the count. |
| 5 | **Conflicts.** Each edit stores the value it started from. At save time, a cell whose file value no longer matches is skipped, listed, and kept unsaved. Every other cell is written. |
| 6 | **Fill → unsaved edits.** Fill adds its cells to the unsaved edits; it doesn't write the file. `u` undoes a whole fill in one step. |
| 7 | **Fill targets.** You choose students by marked rows, typed row range, or Class Group. "Only empty cells" filters any of them. |
| 8 | **Marks** belong to students, not cells. They stay while you move between columns and categories. They clear on `m` (clear marks), after a successful save, and when you leave the course. A fill keeps them. |
| 9 | **No draft file.** Unsaved edits are lost if the terminal is killed. The badge and the prompt are the only protection. |

## Interface

### Raw Details table (category view, right panel focused)
| Key | Action |
|---|---|
| `0-9` `.` | Start an inline edit in the cell, replacing its value with the typed character |
| `Enter` | No edit open: edit the current value inline. Edit open: keep the value and move **down** to the next student, same column |
| `Esc` (while editing) | Cancel this cell's edit |
| `↑` `↓` (while editing) | Keep the value and move up or down (like Enter) |
| `Backspace` / `Delete` | Not editing: set the cell to blank (unsaved). Editing: delete a character |
| `-` | Set the cell to `ขส` (unsaved) and move down |
| `P` `L` `A` `X` | Attendance cells only: set the code (unsaved) and move down. `X` is stored as today (EA mapping unchanged) |
| `Space` | Mark or unmark the student on this row |
| `Shift+↑/↓`, `K`/`J` | Extend the marks up or down (`K`/`J` work in terminals that don't send Shift+arrows) |
| `m` | Clear all marks |
| `u` | Undo the last unsaved change (one typed cell, or one whole fill) |
| `Ctrl+S` | Save all unsaved edits |
| `f` | Fill Column dialog (below) |

The **student popup** (L2, opened with Enter on the ID/Name column) uses the same keys, but `Enter` moves
**right** to the next item for that student. The popup opened from Analytics → At-Risk stays read-only.

The old Enter → modal score popup (`draw_edit_overlay`) is replaced by inline editing. The attendance picker
(`draw_attendance_picker`) still opens on `Enter` over an attendance cell, and its choice becomes an unsaved edit.

### What you see
- An unsaved cell is drawn with a distinct style (theme `warning` foreground + underline), and an over-max value
  is drawn in `grade_f` red. A marked row shows `▸` before the `#` number, with a subtle background.
- Header: `● 14 unsaved` (warning colour), shown only when there's at least one.
- Footer, while there are unsaved edits: `[Ctrl+S] Save 14  [u] Undo`. With marks: `[m] Clear 5 marks`.
- The editing cell shows the text and cursor inside the table cell itself (not a popup).

### Fill Column dialog (`f` on a score or attendance column)
```
╭ Fill hw1 (10pts) ─────────────────────────────────────────╮
│ Students:  ( ) All 42   (•) Marked 5   ( ) Rows [        ] │
│            ( ) Group  [x] SEC.1  [ ] SEC.2                 │
│ [x] Only empty cells                → 3 cells will change  │
│ Value: [0       ]          (attendance: P L A X Clear)     │
│ [Tab] next field  [Space] choose  [Enter] Fill  [Esc] Cancel│
╰───────────────────────────────────────────────────────────╯
```
- The four student choices are exclusive. The default is **Marked** when marks exist, otherwise **All**.
- **Rows** accepts the numbers in the `#` column: `1-10, 15, 20-25`. Spaces are ignored. Bad syntax or out-of-range
  numbers show red and block Enter.
- **Group** appears only when the roster's `Class Group` column has 2 or more distinct values. It allows several groups.
- **Only empty cells** skips students whose cell is non-empty, counting unsaved values: a cell typed in this
  session counts as filled.
- `→ N cells will change` updates live. Enter with N = 0 does nothing. Value follows the same validation as
  decision 3, and an empty Value is still treated as Cancel (as today).

### Save
- `Ctrl+S` while there are unsaved edits shows a loading overlay ("Saving 14 cells…"). The edits go to Python in **one**
  call, which writes **one** history entry covering every file touched, so a single `grader undo` reverts the whole
  save.
- On success, the info line reads `Saved 14 cells (3 files).` The course reloads with navigation kept
  (`preserve_nav_on_reload`), and the unsaved list and marks clear.
- *(Added after use.)* The `apply-edits` reply carries the reloaded course (`course_data`), so a save is one python
  start, not two, and the edits settle in the same step the new data arrives: no flash of the old values. While saving,
  the footer shows `⏳ Saving N cells…` instead of an overlay; score edits wait until it finishes.
- On conflicts, the info line reads `Saved 12 cells · 2 changed on disk, not saved: 69200003 hw1, 69200017 hw2`.
  Those 2 stay unsaved, and their "started from" value updates to the current file value, so a second Ctrl+S writes
  them on purpose.
- If the save fails completely (Python error), nothing is cleared and the error shows in the footer.

### Unsaved-changes prompt
This prompt appears on `q`, `Ctrl+C` and `Esc`→course list when there are unsaved edits (not while a cell is being edited):
```
╭ Unsaved changes ─────────────────────────────╮
│ 14 unsaved scores (2 above max).             │
│                                              │
│  [S] Save and quit   [D] Discard and quit    │
│  [Esc] Keep editing                          │
╰──────────────────────────────────────────────╯
```
("quit" reads "leave course" for Esc.) If a save from the prompt runs into conflicts, the app doesn't quit. It
shows the conflicts and keeps them unsaved.

`w` (weights), `b` (boundaries) and `e` (export) still work while there are unsaved edits. `e` adds a warning to
its info line: "exported saved scores; 14 edits unsaved".

## Implementation

### Rust (`rust_tui/src/`)
- **`app.rs`**
  - New state: `pending: Vec<PendingChange>`, an ordered undo stack where each change is either a single cell or
    a whole fill with a list of cells. There's also a lookup `HashMap<(student_id, column), PendingCell>`, where
    `PendingCell { value, original }`. Plus `marks: BTreeSet<String>` (student IDs), `mark_anchor: Option<usize>`,
    `inline_edit: Option<TextArea>`, `confirm_leave: Option<LeaveAction>` (`Quit` | `CourseSelect`), and the
    fill-dialog fields (`fill_target`, `fill_rows_text`, `fill_groups`, `fill_only_empty`, `fill_focus`).
  - Helpers: `cell_value(row, col)` (unsaved value if any, otherwise loaded), `set_pending(sid, col, value)`
    (setting a cell back to its original value removes the pending entry), `undo_pending()`,
    `parse_row_ranges(&str, n) -> Result<Vec<usize>, String>`, `fill_targets() -> Vec<usize>`,
    `validate_score(&str, max) -> Result<Validity, String>`, `save_pending()`.
  - `start_editing_cell` / `save_edited_score` / `save_attendance_score` / `start_bulk_fill` / `dispatch_bulk_fill`
    now produce pending edits and no longer call the bridge.
  - New `AppEvent::EditsSaved(Result<SaveReport, String>)`.
  - Leaving: the course-list `Esc` paths and a new `wants_quit()` go through `confirm_leave` when `pending` is
    non-empty.
- **`main.rs`**: the `q` / `Ctrl+C` break checks `app.wants_quit()`, which returns true only after the prompt
  resolves, or straight away when nothing is pending.
- **`bridge.rs`**: add `apply_edits(course_path, edits_json) -> Result<SaveReport, String>`, which sends the JSON on
  **stdin** (Thai names and many cells, so no argv size or quoting issues). `update_score` and `bulk_update_score`
  stay but the TUI stops using them.
- **`types.rs`**: add `SaveReport { saved: usize, files: Vec<String>, conflicts: Vec<Conflict>, message }`,
  `Conflict { student_id, column, disk_value }`. Add `class_group` to the raw-score rows (from the `Class Group`
  key, when present).
- **`ui.rs`**: inline edit rendering inside `draw_sub_column_view` and `draw_student_popup`. Unsaved, over-max and
  marked styles. Header badge. Footer entries. `draw_bulk_fill_overlay` / `draw_bulk_fill_attendance_picker` are
  rewritten as the new Fill dialog. New `draw_confirm_leave`. `draw_edit_overlay` is removed.

### Python (`src/tui_api.py`)
- New subcommand `apply-edits <course_path>`, which reads `{"edits": [{"student_id", "column", "value",
  "original"}...]}` from stdin.
  - It groups edits by target file, using the existing column → file lookup, factored out of
    `update_student_score` into `_find_column_file`.
  - For each file it reads the text once with `read_csv_text`, compares each target cell with `original`, and
    sets the matches using `fmt_value`. The comparison is *normalized*: numbers compare numerically (`8` == `8.0`),
    and blank == blank.
  - Before writing anything, it takes **one** `history.snapshot(course, all_files, tool="grade-tui",
    action="edit", note="N cells", cells=N)`. Then it writes each file, runs `_sync_total` per file, and keeps
    attendance csv↔xlsx in step using the existing `_update_xlsx_attendance` + `_sync_attendance` path.
  - `.xlsx` score files are handled through the existing openpyxl branch, one workbook load per file.
  - It returns `{"status": "success", "saved": n, "files": [...], "conflicts": [...], "message"}`.
- `get_course_data`: include `"Class Group"` in each `raw_scores` record when the merged frame has it.
- `update-score` and `bulk-update-score` stay for compatibility.

## Out of scope
- Live recomputation of totals and grades from unsaved edits (decision 4).
- Draft or crash recovery (decision 9).
- Copy/paste of ranges, multi-cell rectangular selection, and editing on the Summary/Analytics/Roundup tabs.
- Changing the Streamlit/Rich `dashboard.py` or the `grader` CLI.
- Undoing *saved* edits inside the TUI (that stays `grader undo`).

## Tests
- **Python** (`tests/test_apply_edits.py`, on fixture course copies in `tmp_path`, as in the existing tests):
  - a batch across 2 csv files writes all cells and creates exactly one history entry, and `grader undo` restores both files
  - an `original` mismatch → that cell is skipped and reported, and the others are written
  - `8` vs `8.0` counts as a match
  - an attendance edit updates the csv and the xlsx companion
  - totals are re-synced
  - `ขส` and blank values round-trip
  - `get_course_data` exposes `Class Group`
- **Rust** (`app.rs` / `ui.rs` unit tests, no Python):
  - typing `8` `.` `5` Enter creates one pending cell and moves the cursor down
  - typing back the original value removes the pending entry
  - `abc` / `-3` are refused, and `12` over a max of 10 is accepted and flagged
  - `u` reverses a single edit, and reverses a fill as one step
  - `P` on an attendance cell sets `P` and moves down
  - `parse_row_ranges`: `"1-3, 5"` → `[0,1,2,4]`, bad input → Err
  - fill targets for All / Marked / Rows / Group, with and without "only empty" (unsaved values counted)
  - Space / Shift+↓ / `J` marking, and `m` clears it
  - `q` with pending edits opens the prompt and doesn't quit, `D` quits, `Esc` keeps editing
  - `wants_quit()` is true straight away when nothing is pending
  - a `TestBackend` render shows the `● N unsaved` badge and the unsaved-cell style

## End-to-end verification
1. `cd rust_tui && cargo test && cargo build --release`, then `cd .. && python3 -m pytest tests/ -q`. All green.
2. Copy the mock course: `cp -R "courses/0_ฟิสิกส์ทั่วไป_(ข้อมูลจำลอง)_grading" /tmp/gt/courses/`, then run
   `cd /tmp/gt && grade-tui`. Never use `~/cmru/teachings`.
3. In Raw Details → homework → hw1: type `9` Enter `8.5` Enter `12` Enter. You should see 3 unsaved cells (`12` red),
   the header showing `● 3 unsaved`, and the file unchanged on disk (`git diff`/`cat` of the copy).
4. Mark rows 5–7 with Space + `J`, press `f`, choose **Marked**, tick **Only empty**, enter `0`, then Enter. Only
   blank cells among rows 5–7 become unsaved. Press `u` and the fill disappears in one step. Fill again.
5. Switch to midterm and type one score. Press `q`. The prompt reads "N unsaved scores (1 above max)". Press `Esc`
   (still running), then `Ctrl+S`. Expect "Saved N cells (2 files)". Totals update, and `grader history` in the copy
   shows **one** new grade-tui entry. `grader undo` restores both files.
6. Conflict check: type a score, edit the same cell in the csv with a text editor, then press `Ctrl+S`. That cell is
   reported and still unsaved. A second `Ctrl+S` writes it.
7. Type a score, press `q`, then `D`. The app exits, and the file on disk is unchanged.
