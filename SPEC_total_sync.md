# SPEC — Totals that stay in sync, raw multi-part exam scores, hand-edit aware submit (contract 2)

Status: **confirmed and implemented** · 2026-10-12 · spans grade_dashboard and exam_projects
Previous specs: `SPEC_update_stale_columns.md`, `SPEC_copy_friendly_scores.md`. The rules both projects share are in
`INTEGRATION.md` (contract 2).

## Context

Score CSVs (`data/<prefix>_<category>.csv`) store a `total (Npts)` column. A CSV can't hold formulas, so the total
went stale whenever a score was edited by hand in Excel or Numbers, or a column was added. One real course had 50
students with a stored total of `0.0` next to scores like 11.2.

An earlier draft proposed dropping `total`. **Decided instead:** keep it, and recompute it everywhere.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Stored total | Kept. `total` = plain sum of the row's cells in the columns `data_mapping` lists for the category (empty/`ขส`/invalid = 0); header `total (Σpts)`. Category rules (drop lowest) never change it. |
| 2 | When it's refreshed | Automatically: grade-tui on open and after each edit, `grader mkdb/update`, `exam submit scores`. After a hand edit: `grader sync`. No background watcher. |
| 3 | Columns added by hand | Not counted until `grader sync` proposes them and you answer y. Points come from the header `(Npts)`, or it asks. |
| 4 | Header vs config points | `grader sync` shows the difference and asks which wins (`--yes` leaves it). |
| 5 | Attendance | Never touched: no total sync. |
| 6 | exam's role | Copies data only. Raw mcq/fill per column, no scaling. May add its own missing part columns and set their header points. Never writes `config.yaml`. |
| 7 | Hand edits before a submit | Detected against what the last submit sent (`sent.json`), and listed. Default: keep them (also with `--yes`). `[o]` / `--overwrite-edits` overwrites, `[p]` picks each. |
| 8 | Viewing totals | grade-tui Raw Details shows raw total · %; the Summary panel shows raw/max (%) per category; the export adds `<cat>_raw/_max/_pct`. |

## Implementation

**grade_dashboard**

- `src/sync.py` (new):
  - `total_for` / `apply_total`: the total rule;
  - `sync_file` / `sync_course`: write only when changed, with a history snapshot;
  - `find_changes` and `warnings_for`: unmapped columns, points conflicts, missing columns, columns without
    points, stale totals;
  - `set_category`: a line-level edit of one `data_mapping` category. Comments elsewhere are kept, and the result is
    verified by re-parsing.
- `src/dashboard.py`:
  - `update_database_totals` now calls `sync_course`, and the attendance branch is gone;
  - `category_totals` (new) feeds the export, which gains `<cat>_raw/_max/_pct`.
- `src/tui_api.py`: `get_course_data` adds the sync warnings and `category_totals`; cell and column edits call
  `sync_file`.
- `grader.py`: `grader sync [--course] [--yes]` (one history entry), and `mkdb`/`update` refresh totals at the end.
- `rust_tui`: `CatTotal`/`category_totals` (`#[serde(default)]`); Raw Details shows `total · %`, and the Summary
  panel shows raw/max (%).
- Tests: `tests/test_sync.py`.

**exam_projects**

- Metadata gets `grade_category:` and `grade_columns: {mcq, fill}` (or `{score}`). An old `grade_column: X` is read
  as `{score: X}`.
- `exam submit link` gets `--category/--mcq/--fill/--score` and guesses `*mcq*`/`*fill*` columns, otherwise naming
  `<category>_mcq/_fill`.
- `exam submit scores` loses `--column/--no-scale` and gains `--overwrite-edits`.
- `gradebook.py`:
  - `grade_map`, `exam_totals`, `columns_in`, `category_for`;
  - `total_for` (copy of the shared rule);
  - `write_changes` (cells + added columns + header points + total + `sent.json`);
  - `last_sent`.
- `scores.py` is rewritten around these; `status.py` shows the map and the unmarked fill count.
- Tests: `cli/tests/test_gradebook.py`, `test_cli.py`.

## Out of scope

- A background file watcher.
- xlsx files for scores, or a `grader view`.
- Sub-weights within a category.
- Changes to the grade formula or rounding.
- exam writing `config.yaml`.
- Changes to attendance files.

## Verification

1. `python3 -m pytest tests -q` (grade_dashboard) and `./setup.sh --test` (exam_projects).
2. On copies of the real 2569-1 courses:
   - grades are identical before and after;
   - `grader sync` refreshes a hand-edited total and leaves attendance byte-identical;
   - a hand-added `bonus (5pts)` is proposed and, on y, counts.
3. Synthetic midterm scans:
   - `exam submit link` → `exam submit scores --yes` writes raw MCQ and the total;
   - a cell edited by hand is listed under "changed by hand" and kept, and `--overwrite-edits` replaces it;
   - `grader undo` restores the files byte for byte.
