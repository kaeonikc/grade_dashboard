# SPEC — The score files follow your config.yaml edits

Status: **implemented** · 2026-10-14 · grade_dashboard (`src/columns.py`)

## Problem

You edit `config.yaml` by hand (remove, rename or re-point a column) and then run `grader update`. Before this
change:

- the CSV kept the old column as an "orphan" (kept whenever it held any value, even zeros);
- `grader sync` then took it for a column added to the CSV by hand and asked to add it **back to the config**.

It couldn't tell "removed from the config" from "added to the CSV". One real case: IndustPhys `hw1 (15pts)` and
`hw2 (15pts)` stayed after the config moved to `hw_motions/hw_heat/hw_fluid`.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Telling the sides apart | `grader mkdb/update/sync` remember the config's columns and points in `history/config_sync.json`. For a course from before this existed, the earlier configs in `history/*/course_info/*_config.yaml` and `course_info/*_config.yaml.bak` stand in. |
| 2 | Column removed from the config, empty | Deleted from the CSV, with a history entry. |
| 3 | Column removed from the config, with scores | `grader update` and `grader sync` ask: `[d]` delete / `[r]` rename it to a new config column of that category that is missing or empty (moves its scores) / `[k]` keep it (not counted, recorded under `kept`, never proposed again). Default and `--yes` = keep. |
| 4 | Column added to the CSV by hand (or by `exam submit scores`) | Unchanged: `grader sync` offers to add it to the config. |
| 5 | Points differ | If the header still has the remembered points, you changed the config, so the header follows without a question. If the config still has them, you changed the header: `grader update` keeps it and `grader sync` asks `[f]/[c]/[s]` as before. If it can't be told, it asks. |
| 6 | "Manual total score is determined as …" warning in `update`/`mkdb` | Only when `total_pts` is set explicitly. A weight is not a points total. |

## Files

- `src/columns.py`: `remembered`, `save_base`, `unmapped` (kinds `removed` / `kept` / `hand`), `rename_targets`,
  `points_side`, `settle_removed`.
- `src/sync.py`: `Changes.removed` and `Changes.follow_config`, plus their warnings.
- `grader.py`:
  - `update_course` keeps hand-edited header points, calls `settle_removed` (history entry `update-columns`) and
    saves the memory;
  - `sync_cmd` follows config points, settles removed columns and saves the memory;
  - `mkdb` saves the memory.
- Tests: `tests/test_config_columns.py`.

## Out of scope

- Renaming a whole category.
- Moving a column between categories.
