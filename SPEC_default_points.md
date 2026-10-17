# SPEC — Default points per category; lab headers without "(10pts)"

Status: **confirmed and implemented** · 2026-10-18 · grade_dashboard + exam_projects (both copies of `INTEGRATION.md`, now contract 3)
Previous specs: `SPEC_config_columns.md` (config ↔ header points), `SPEC_total_sync.md` (total rule),
`SPEC_batch_editing.md` (grade-tui editing).

## Problem

A lab category normally has 10 labs at 10 points each. Each header carries its points (`1 (10pts)` … `10 (10pts)`),
which wastes space in two places:

- **grade-tui**: in the Raw Details table every score column is at least 12 cells wide (`rust_tui/src/ui.rs`, the
  `sub_col_widths` line), and the second header line repeats `(10 pts)` ten times.
- **the CSV opened in a spreadsheet**: `4 (10pts)` makes the column wider than the scores it holds.

You can't just drop the suffix. `data_loader.py` takes a column's max from its header, and with no header points it
falls back to the config, then to 100 (`grader`) or to `weight × 100 / n` (`tui_api._fill_default_max_scores`, which
would make each lab worth 3 pts). Both tools' `total_for` add `config pts or header pts`, so a bare header with a bare
config entry counts as 0. The fix moves where a column's points come from. It also changes the label.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Which columns go bare | Any category can have a **default points** value. A column whose points equal its category's default gets a bare header (`4`). A column with other points keeps `name (Npts)`. A category with no default changes nothing; `hw1 (100pts)` stays. |
| 2 | Config syntax | `pts_each` in the dict form that already holds `total_pts`: `lab: {pts_each: 10, columns: [1, …, 10]}`. Entries may be bare (`1`) or explicit (`5: 20`). |
| 3 | Built-in default | A category named exactly `lab` has default 10 when `pts_each` is absent. `lab_attend` and the others have none. Your current configs (`- 1: 10 … - 10: 10`) need no edit. |
| 4 | A column's points | First its explicit config value (`- 5: 20`), then `pts_each`, then the built-in lab 10. With none of these, today's behaviour applies (header points, else 100 / weight-derived). One resolver, used everywhere. |
| 5 | Total column | Unchanged: `total (Σpts)`, e.g. `total (100pts)`. The CSV gets no "10 each" note; the config holds it. |
| 6 | grade-tui | The Raw Details title gets `· 10 pts each` for a category with a default. A column at the default shows only its name, and its width shrinks to `max(len(name), 4) + 2` (6 for labs `1`–`10`). Columns off the default keep `name` / `(N pts)` and the current width. The Total header is unchanged. |
| 7 | Existing courses | `grader update` and `grader sync` rename `4 (10pts)` → `4` when 10 is the column's resolved points (config side). Scores are not touched. Files are snapshotted to `history/` first (`grader undo` restores them), and one line is printed per file. |
| 8 | Changing `pts_each` after scores exist | `history/config_sync.json` remembers each column's points. If a bare column's remembered points differ from the new default and the column has a non-empty cell, `grader update`/`sync` ask: `lab: 10 → 20 pts each; 42 students' scores now count out of 20. [y] keep 20 / [n] put 10 back in config.yaml`. `--yes` = `y`. grade-tui doesn't ask. It just follows the config. |
| 9 | Header ≠ config (existing rule, `SPEC_config_columns.md` #5) | A bare header is treated as "header points = category default". So a hand-written `5 (20pts)` in a `pts_each: 10` lab is a header change → `grader sync` asks `[f]/[c]/[s]`. `[f]` writes `- 5: 20` into the `columns:` list. A config change to `- 5: 20` makes the header follow (`5 (20pts)`). |
| 10 | Column added by hand | A bare column in the CSV of a category with a default counts as the default when `grader sync` offers to add it, and is added as a bare entry. One with `(Npts)` ≠ default is added as `- name: N`. |
| 11 | exam_projects | Both repos learn the same rule. `gradebook.mapping()` returns resolved points (pts_each, built-in lab). `exam submit scores` writes the canonical header (bare when its part's points equal the category default) and treats a bare header at the default as correct, so the two tools don't undo each other. `INTEGRATION.md` gets the rule and a header table that both test suites check, like the total table. |

### Canonical header (both repos, table in INTEGRATION.md)

| column | resolved points | category default | header |
|---|---|---|---|
| `4` | 10 | 10 | `4` |
| `5` | 20 | 10 | `5 (20pts)` |
| `hw1` | 15 | (none) | `hw1 (15pts)` |
| `final_mcq` | 35 | 35 | `final_mcq` |
| `final_mcq` | 35 | (none) | `final_mcq (35pts)` |

## Files

### grade_dashboard (new branch `default-points` off `batch-edit`)

- `src/sync.py` (shared helpers):
  - `category_default(config, category) -> float | None` (pts_each, else `lab` → 10, else None);
  - `column_points(config, category, entry)` (decision 4);
  - `header_for(name, pts, default)` (canonical header table);
  - `total_for` callers pass resolved points.
- `grader.py`:
  - `parse_category_mapping` returns `pts_each` too;
  - `create_empty_category_csv` and `update_course` build headers with `header_for` (bare-header match uses the
    resolved points, not `default_max`) and do the migration (decision 7);
  - `sync_cmd`'s `set_points` / `add_column` write into the `columns:` list of the dict form, bare when equal to the
    default (decision 10);
  - the "Manual total score" warning must not fire for a dict that has only `pts_each`.
- `src/columns.py`: `points_side` and `remembered`/`save_base` read a bare header as the default, and the
  `pts_each` change check (decision 8).
- `src/data_loader.py`:
  - `load_config` keeps `pts_each` (today a dict without `total_pts` stores `total_pts = 0.0`; make it store nothing);
  - `load_course_data` seeds `max_scores` with `column_points`, so a bare header keeps the config value.
- `src/tui_api.py`:
  - `_fill_default_max_scores` normalises the dict form (it iterates the dict's keys today) and never overrides a
    resolved value;
  - `get_course_data` adds `default_pts: {category: pts}` to its reply.
- `src/calculators.py`: check that every `data_mapping` loop goes through the cleaned config (no change expected).
- `rust_tui/src/types.rs`: `default_pts: HashMap<String, f64>` with `#[serde(default)]`.
- `rust_tui/src/ui.rs`: Raw Details title, bare header and narrow width (decision 6), in both score-table renderers
  (the Raw Details table and the popup table further down).
- `INTEGRATION.md`: "Points" bullet and the canonical-header table.
- `MANUAL.md`: `pts_each`, the lab built-in, and the update/sync messages.
- Tests: `tests/test_default_points.py` (new), plus updates in `test_config_columns.py` and `test_sync.py`; an
  `edits.rs`/`ui` unit test for column width.

### exam_projects (new branch `default-points` off `total-sync`)

- `cli/exam_cli/gradebook.py`: `mapping()` resolves points; `header_for` (same table); `total_for` gets resolved
  points.
- `cli/exam_cli/scores.py`: `plan_course` builds `want` with `header_for` and accepts a bare header at the default.
- `INTEGRATION.md`: identical copy (`test_gradebook.py` checks it).
- Tests in `cli/tests/test_gradebook.py` for the header table and for a no-op submit into a bare-header column.

## Implementation notes (beyond the decisions above)

- `INTEGRATION.md` is **contract 3** (a new rule); `gradebook.CONTRACT = 3`.
- `grader update` gets `-y/--yes` (decision 8's question).
- `grader update` now reads score CSVs as text. Before, a column with blanks came back as floats and any rewrite
  turned `9` into `9.0`. The reshape rewrites files that used to be left alone, so this had to be fixed to keep
  the cells byte-identical.
- `exam submit scores` also reshapes an old header with the same points (`final_mcq (35pts)` → `final_mcq` at a
  35 default), and its preview says "same points" for that case instead of "the exam's points".
- Putting `pts_each` back ([n]) rewrites that one category of `config.yaml` in block style (`columns:` as a `- n`
  list); every other line stays byte-identical (`set_category`).
- `grader sync` writes a config key back as a number when it was one (`- 5: 20`, `- 11`), not `'5'`.

## Out of scope

- The Streamlit dashboard's display. Its numbers come out right through `load_course_data`, but its layout isn't
  changed.
- Built-in defaults for categories other than `lab`, and the count shorthand (`lab: 10`).
- Attendance files (xlsx/csv) and their `total (Npts)` header.
- The `grader init` config template (`pts_each` is documented in MANUAL.md instead).
- Column-name clashes between categories (e.g. a `1` in both lab and quiz). This is an existing limitation.
- Writing anything in `~/cmru/teachings`. All testing uses copies.

## Verification (end to end, on a copy)

1. `cp -R ~/cmru/teachings/2569-1/2026_S1_ฟิสิกส์ทั่วไป_2_SEC_51_grading <scratchpad>/c` (config has `lab: - 1: 10 …
   - 10: 10`, no `pts_each`). On the **old** code, run `grader mkdb` (or `update`) in the copy. Fill lab scores for a
   few students (one at 9.5, one `ขส`), then save `tui_api.py get-course-data <copy>` as `before.json`.
2. Switch to `default-points` and run `grader update` in the copy:
   - `data/*_lab.csv` header is `Student ID,Name,1,2,…,10,total (100pts)`;
   - every score cell is byte-identical to before;
   - a `history/` snapshot exists;
   - `grader undo` brings back the old headers, and running `grader update` again re-applies the change.
3. `tui_api.py get-course-data <copy>` → `after.json`: `max_scores["1"] … ["10"] == 10`, `default_pts.lab == 10`,
   and every student's final grade and lab percentage are equal to `before.json`.
4. Change the config to `lab: {pts_each: 20, columns: [1..10]}` and run `grader update`: it asks (decision 8);
   answering `n` puts `pts_each: 10` back. Set `- 5: 20` → the header becomes `5 (20pts)` and the total becomes
   `total (110pts)`.
5. grade-tui on the copy (in tmux, `capture-pane`): the lab title reads `Raw Details › lab · 10 pts each`, the lab
   columns are 6 cells wide, `5` shows `(20 pts)` at normal width, Total shows `(110 pts)`. Typing `11` in column
   `1` is flagged as above the max (10) (`edits.rs::is_over_max`), proving the TUI got 10, not 100 or 3.
6. exam side: in a copy with `final: {pts_each: 45, columns: [final_exam]}`, the `exam submit scores` preview proposes
   no header rename for a bare `final_exam`, and a following `grader update` changes nothing.
7. Suites: `pytest` (grade_dashboard), `cargo test` (rust_tui), `./setup.sh --test` (exam_projects, including the
   identical-INTEGRATION.md test).
