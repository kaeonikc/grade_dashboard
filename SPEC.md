# SPEC — Attendance xlsx, csv and dashboard kept in sync by `grader sync`

Status: **confirmed and implemented** · 2026-10-14 · grade_dashboard only (exam_projects gets the identical `INTEGRATION.md` text)
Previous specs: `SPEC_total_sync.md` (score totals, contract 2), `SPEC_update_stale_columns.md`,
`SPEC_copy_friendly_scores.md`.

## Context

`grader init` creates `data/<prefix>_attendance.xlsx` and a `.csv` copy with 15 session columns from the schedule. A
term normally records 12–13 sessions, so at the end of term you delete the empty columns: usually in the xlsx,
sometimes in the csv. Before this change:

- **Hidden one-way copy.** `data_loader.check_and_sync_attendance` overwrote the csv from the xlsx whenever the xlsx
  was newer. That happened on every course open, with no history snapshot, and a csv-only edit was lost.
- **`grader update` brought deleted sessions back** by rebuilding the sheet with all 15 dates.
- **The total was wrong** after a deletion. The xlsx header kept `total (15pts)`, one csv said `total (1500pts)`, and
  the csv total cells were empty.
- The dashboard counts every session column in the csv as the attendance maximum, so once both files agree, the
  grade follows: 13 sessions → /13.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Who wins | **Three-way compare with the last sync** (baseline). A change made in only one file (cell, Name, column added or removed, row) is copied to the other. The same thing changed differently in both files is a conflict: both values are shown and you choose `[x]`lsx / `[c]`sv / `[s]`kip. `--yes` skips conflicts. |
| 2 | Empty sessions | `grader sync` offers to remove sessions that nobody has a mark in ("Remove 22 Sep 2026, 29 Sep 2026? [y/N]"). Deleting by hand still works and is mirrored. |
| 3 | Which empty ones | Only columns whose header date is **before today**. Future dates and headers that aren't dates are never offered. Default N; `--yes` never removes. |
| 4 | `grader update` | Keeps your session columns. It only adds roster students (empty cells) and drops a row that left the roster only when the row is empty. The schedule's dates are made only by `grader init`, or when no attendance file exists. |
| 5 | Writing the xlsx | **In place** (openpyxl): only differing cells; columns deleted or inserted; total header `total (Npts)` and each row's COUNTIF range rewritten; column widths, the P/A/L/X dropdown and the colour-rule ranges follow. Other formatting, notes and sheets stay. |
| 6 | Opening a course | **Safe auto-sync.** It applies only when nothing needs a question: a baseline exists, there are no conflicts, and no column with marks would be removed. It never offers empty sessions. Otherwise it warns "attendance: … run `grader sync`". |
| 7 | First sync (no baseline) | A column in only one file counts as deleted in the other. For a differing cell, the newer file's value is proposed. Everything is listed and applied only after y/N (`--yes` applies it). |
| 8 | Removing a column with marks | Always asked, showing the number of marks. Default N, and `--yes` keeps the column. On N, the column is restored in the file it was deleted from. Removing an empty column is mirrored (and shown in the preview). |

**Also:**

- **Rows** are matched by Student ID. A roster student missing from one file is added to it. A row that isn't on the
  roster is reported and never removed by the sync.
- **csv total**:
  - P = 1, L = 0.8, X = 1, EA = 1, A = 0 (as in the xlsx formula and the grade);
  - its header is `total (<sessions>pts)`;
  - totals are derived, so they are never compared.
- **The xlsx being open in Excel:** when `~$<name>.xlsx` is present, the xlsx isn't written ("close it in Excel
  first").
- **A renamed header** is one column removed and one added, so decision 8 applies.
- **History:** everything `grader sync` writes is one history entry, and it includes the baseline. So `grader undo`
  restores both files *and* what the next sync compares with.
- **grade-tui edits** go through the csv, which then updates the xlsx. The xlsx is never edited on its own, and
  the csv total and baseline are refreshed straight after.

## Implementation

- `src/attendance.py` (new):
  - `Sheet`, `read_csv_sheet` and `read_xlsx_sheet`;
  - baseline `<course>/history/attendance_sync.json`;
  - `plan(course, today)` → `AttPlan`;
  - `apply(...)` (csv through `csvio`; xlsx in place, atomic);
  - `auto_sync(course)`;
  - `align_rows(course, roster)`;
  - `att_total`.
- `src/data_loader.py`: `auto_sync` replaces `check_and_sync_attendance`/`sync_attendance_xlsx_to_csv`.
- `grader.py`:
  - `grader sync` gains the attendance part (preview, questions, the same history entry);
  - `init` saves the first baseline;
  - both update paths call `align_rows` and no longer rebuild the sheet.
- `src/tui_api.py`: the auto-sync warnings go into `warnings`, and attendance edits refresh the csv total.
- Docs: `MANUAL.md`, and `INTEGRATION.md` (both copies; contract stays 2).
- Tests: `tests/test_attendance.py`.

## Out of scope

- Attendance codes or weights.
- Attendance from exam_projects.
- xlsx copies of score files.
- A background watcher.
- Workbooks with several sheets (only the first sheet is read and written).
- Generating make-up dates (a column added by hand is mirrored).

## Verification

1. Run the suites:
   - `python3 -m pytest tests -q`;
   - `cd rust_tui && cargo build --release`;
   - exam_projects `./setup.sh --test`.
2. On a copy of ฟิสิกส์ทั่วไป 2 (13 of 15 sessions used), run `grader sync`:
   - the first run proposes the newer file and offers 22 Sep and 29 Sep;
   - answering y leaves 13 sessions in both files, with `total (13pts)`, COUNTIF `C2:O2`, the dropdown and colour
     ranges ending at column O, and the csv totals filled;
   - the dashboard's attendance maximum is 13.
3. On that copy:
   - an xlsx edit auto-syncs when the course is opened;
   - a csv edit reaches the xlsx with `grader sync --yes`;
   - a conflicting edit is asked about;
   - deleting a marked column is asked about, and N restores it.
4. `grader update` keeps 13 sessions, and a new roster student gets an empty row in both files.
5. `grader undo` restores both files byte for byte, and opening the course twice changes no mtime.
