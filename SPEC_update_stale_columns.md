# SPEC: Stop `grader update` from stranding stale category columns

## Root cause (confirmed)

`grader update`'s `update_course()` in `grader.py` realigns each category's score
CSV (`data/<prefix>_<category>.csv`) to the current `config.yaml`
`data_mapping`. The **old** (committed) version matched an existing CSV column
to a config column by exact string equality of the cleaned column name. When a
category is restructured — e.g. `midterm: ["midterm_score"]` (30pts) becomes
`midterm: [{midterm_mcq: 35}, {midterm_showsol: 5}]` — the old column no
longer matches any new config entry, so the old code treated it as orphaned:
it prompted (`Confirm.ask`) to delete it if it held scores, and unconditionally
added two brand-new blank columns for the new names. Separately,
`update_database_totals()` in `src/dashboard.py` writes a `total (Npts)`
column into the same file, computed as the sum of the *current* mapped
columns' max scores (35 + 5 = 40) — this is the "net/สุทธิ" column the report
described; it is correct, expected behavior, not a symptom of the bug.

Confirmed on the user's real course
(`/Users/chakkritk/cmru/teachings/2569-1/2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51_grading`):
`data/..._midterm.csv` currently has `midterm_mcq (35pts)`,
`midterm_showsol (5pts)`, a stray `midterm_score (30pts)` (100% empty across
all 19 students — confirmed via direct read, zero data loss), and
`total (40pts)`. `weights.midterm: 0.20` in config.yaml is the "20 คะแนน"
referenced in the original report (the category's weight, not a raw-points
figure). `calculate_final_grades`/`validate_scores` in `src/calculators.py`
only operate on columns listed in the *current* `data_mapping`, so the orphan
column does not affect anyone's computed grade — confirmed by reading
`calculate_final_grades`'s `allowed_cols` filter.

There is **already an uncommitted WIP fix** for this in the working tree
(`git diff grader.py src/data_loader.py src/dashboard.py src/tui_api.py`),
started in an earlier session. It:
- Normalizes column-name matching (`normalize_col_key`: case/whitespace/
  underscore-insensitive) so cosmetic header differences don't cause a false
  "missing" detection.
- Changes the philosophy from "delete orphan columns after a confirm prompt"
  to "**never delete data automatically** — keep orphan columns/rows in the
  file, print an info line instead."
- Adds `backup_csv_before_write()` (`src/data_loader.py`) and wires it into
  every full-dataframe CSV overwrite path (`update_course`,
  `update_database_totals`, `update_student_score`, `update_column_score`) so
  every write is `.bak`-recoverable via `grader undo`.
- Skips rewriting a file when realignment produces no actual change
  (avoids meaningless `.bak` churn).

This spec covers finishing/verifying that WIP work, adding an explicit way to
purge truly-empty orphan columns, and cleaning up the specific stray column
on the user's live course.

## Files/interfaces involved

- `grader.py`
  - `normalize_col_key()`, `update_course()` (category-CSV realignment loop) — review/finish/verify the existing uncommitted diff.
  - New: an opt-in purge step at the end of `update_course()`'s per-category loop, gated by a new `--purge-empty-orphans` flag on the `update` subcommand (`parser_update.add_argument`, and the `args.command == "update"` dispatch).
- `src/data_loader.py` — `backup_csv_before_write()` (already added, uncommitted). No further change expected; read-only verification.
- `src/dashboard.py` — `update_database_totals()` (already wired to `backup_csv_before_write`, uncommitted). No further change expected.
- `src/tui_api.py` — `update_student_score()`, `update_column_score()` (already wired, uncommitted). No further change expected.
- `src/calculators.py` — read-only; confirmed orphan columns are excluded from `calculate_final_grades`/`validate_scores` via the `allowed_cols`/`data_mapping` filter. No change.
- Live data fix (one-off, not code): `/Users/chakkritk/cmru/teachings/2569-1/2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51_grading/data/2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51_midterm.csv` — drop the empty `midterm_score (30pts)` column.

### Constraint: do not touch this course's `config.yaml` programmatically

`course_info/2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51_config.yaml` is currently
open for editing in a live MacVim process (confirmed via `lsof`/`ps` — a
`.swp` file exists and the process is running). The data-file cleanup below
touches only the `data/*_midterm.csv` file, never the config, so it's safe to
do regardless of that open editor. No code path in this fix writes to
`config.yaml`.

## Design

### 1. Finish/verify the WIP realignment fix
No redesign — the uncommitted approach (normalized matching, never
auto-delete, skip no-op writes) is confirmed correct in principle. Work here
is verification only:
- Read through the full current diff once more for edge cases (header
  collisions, `total` column handling, orphan-student handling) — already
  done in this session, no defects found.
- Build a disposable synthetic repro under the repo's own `courses/` (via
  `python grader.py mock`, which exists for exactly this purpose) or a
  scratch course, reshape one category from 1 column to 2 in its
  `config.yaml` (mirroring the real bug shape), run `python grader.py update`,
  and confirm:
  - the two new columns are added with correct headers/points and blank
    scores,
  - the old column survives untouched (header + data unchanged) with an
    `ℹ️` info line printed, not deleted,
  - `total (Npts)` reflects only the two new columns,
  - a second consecutive `update` run makes no changes ("already up to
    date"),
  - a `.bak` is created only on the run that actually changed the file.
- Clean up the disposable test course afterward.

### 2. `--purge-empty-orphans` flag on `grader update`
Scope kept narrow: **only** removes an orphan column when every row's value
for it is null/blank (`pd.isna` or stripped-empty) — i.e. it is provably safe
because there is nothing to lose. An orphan column that holds any data at all
is left alone with the existing info message; this flag never prompts and
never deletes real values, in keeping with the "never silently discard
scores" rule already established in the WIP fix.
- Add `parser_update.add_argument("--purge-empty-orphans", action="store_true", ...)`.
- Thread a `purge_empty_orphans: bool = False` parameter through
  `update_course()`.
- After computing `orphan_headers` for a category's CSV: if the flag is set,
  check each orphan column's data in `student_rows`; drop columns that are
  100% empty from both `student_rows` and `final_headers`; keep the existing
  info-line behavior for any orphan that still holds data.
- This changes `needs_write` detection incidentally (dropping a column is a
  real change), which the existing no-op-skip logic already handles
  correctly.

### 3. One-off cleanup of the live course
Using a small pandas script (or manually via the flag above once built):
read `data/2026_S1_..._midterm.csv`, drop the `midterm_score (30pts)` column
(verified 100% empty), back it up first with the existing
`backup_csv_before_write` convention, write it back. This can equivalently be
done by running `python grader.py update` with the new
`--purge-empty-orphans` flag against that course once the flag exists, which
also exercises the flag as a real-world test.

## Out of scope

- Any change to `config.yaml` for the live course, or to its open-in-vim
  workflow.
- Purging orphan columns that hold any data — that remains a manual decision
  outside this fix (no auto-delete of real scores, ever).
- Changes to `src/calculators.py` — confirmed unaffected, no fix needed there.
- Changes to `rust_tui/` (its own uncommitted diff is unrelated to this
  column-matching bug — not investigated further here).
- Committing the working-tree changes to git (left for the user to review
  and commit separately, per this repo's "only commit when asked" rule).

## End-to-end verification

1. `python grader.py mock` (or a hand-built scratch course) to get a
   synthetic course with a multi-column category.
2. Edit that course's `config.yaml` to split one category's single column
   into two new differently-named columns (reproducing the real shape:
   1 column → 2 new columns, different names, different point totals).
3. Run `python grader.py update <path-to-that-config.yaml>`. Confirm via
   `pandas.read_csv` on the resulting category CSV:
   - both new columns exist with correct `(Npts)` headers and blank scores,
   - the original column is still present, unchanged, un-deleted,
   - `total (Npts)` equals the sum of the two new columns' points only,
   - console output shows an `ℹ️` line for the orphan, not a delete prompt.
4. Re-run `python grader.py update <same config>` — confirm it reports
   "already up to date" and does not touch/rewrite the CSV (check mtime) or
   `.bak` files.
5. Re-run `python grader.py update <same config> --purge-empty-orphans` —
   confirm the orphan column (which has zero data) is now removed, a fresh
   `.bak` reflecting the pre-purge state was written, and the students'
   real scores in the surviving columns are untouched.
6. Run `python grader.py dashboard` against that synthetic course, confirm
   the Streamlit UI loads without error and the midterm category's
   calculated percentage matches the two real columns only.
7. Delete the disposable synthetic course directory.
8. Against the real course
   (`/Users/chakkritk/cmru/teachings/2569-1/2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51_grading`):
   run `python grader.py update --purge-empty-orphans` pointed at its config,
   confirm `midterm_score (30pts)` is gone from
   `data/2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51_midterm.csv`, the 19 students'
   `midterm_mcq`/`midterm_showsol`/`total` values are byte-identical to
   before, and a `.bak` exists to restore from if needed. Confirm
   `course_info/*_config.yaml` in that directory was not modified (its mtime
   unchanged) since it's open in vim.
