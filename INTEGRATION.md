---
contract: 2
---

# grade_dashboard ↔ exam_projects

This file is the agreement between **grade_dashboard** (`grader`, `grade-tui`) and **exam_projects** (`exam`).
The same file is kept in both repos: change both copies together, and bump `contract` when a rule changes. The two
projects never import each other's code. They meet only through the files described here.

Contract 2 (2026-10-12) adds three things:

- every score file's `total` column is kept in step with its cells;
- exams are sent as raw scores, part by part;
- `exam submit scores` detects your hand edits.

## Who owns what

| Thing | Owner | exam may |
|---|---|---|
| Course folder `<term>_<name>[_SEC_<n>]_grading/` | grade_dashboard (`grader init`) | read it |
| Roster `course_info/<prefix>_student_info.csv` (`Student ID,Name,Class Group`) | grade_dashboard (`grader init/update -i repclasslist.xls`) | read it; never write it |
| Config `course_info/<prefix>_config.yaml` (`data_mapping`, `weights`, …) | grade_dashboard (you, `grader sync`) | read it; **never write it** |
| Score files `data/<prefix>_<category>.csv` | grade_dashboard (`grader mkdb/update`) | change the cells of its mapped columns; **add** its own missing part columns; fix their header points; recompute that file's `total` |
| Attendance `data/<prefix>_attendance.xlsx/.csv` | grade_dashboard (`grader sync` keeps the two in step; the score-total rule doesn't apply) | never touch them |
| Exam folder, `grading/results.csv` | exam_projects | — (grade_dashboard doesn't read them) |

exam never adds or removes rows, never changes columns other than its own, and never writes `ขส` over a score.
A roster student without a row in the data CSV is reported ("run `grader update`") and skipped.

## Finding the course from an exam

`exam submit link` (and `exam submit scores` without `--to`) looks for `*/course_info/*_config.yaml` in the folders
up to three levels above the exam folder, plus every folder in `$EXAM_GRADEBOOK_ROOTS` (`:`-separated). A course
matches when:

- its `term` equals the exam's `semester` converted (`1/2569` → `2026_S1`), and
- its `course_id` appears in the exam's `course:` (e.g. `PHYS1120 ฟิสิกส์สำหรับอุตสาหกรรม`). When the exam has no
  course code, its `course_name` must equal the exam's course name instead (spaces and `_` ignored).

## Where an exam's scores go

`exam submit link` writes the following into `<exam>_metadata.yaml`:

```yaml
grading_dir: ../../2026_S1_…_SEC_51_grading      # or a list, for several sections
grade_category: final                             # the data_mapping category
grade_columns: {mcq: final_mcq, fill: final_fill} # raw MCQ and raw fill, each into its own column
# or:   grade_columns: {score: final_exam}        # MCQ + fill in one column
```

An old `grade_column: X` (contract 1) is read as `{score: X}`.

**Raw scores, no scaling.** A part's full marks come from the answer key (`mcq_total`, `fill_total`). The column's
header points are set to them (`final_mcq (35pts)`). grade_dashboard turns raw scores into percentages and weights.

A blank `fill` in results.csv means **not marked yet**: the cell is left as it is, and a blank never erases a value.

## Score files

```
Student ID,Name,final_mcq (35pts),final_fill (10pts),bonus (2pts),total (45pts)
69143302,นาย …,28,7,1,35
```

- **Points.** A column's points are in its header and, for the columns that count, in `config.yaml` `data_mapping`.
  `grader sync` reports any disagreement and asks which one wins.
- **Columns that count** are the ones `data_mapping` lists for the category. A column that is only in the file
  (added by hand, or added by `exam submit scores`) doesn't count until `grader sync` adds it to the config, which
  it does only after asking you.

### The total rule

`total` = the plain sum of the row's cells **in the columns that count** (empty, `ขส` and invalid count 0), like a
spreadsheet `SUM`. Its header is `total (Σ points of those columns)`. Rules such as `drop_lowest_homework` affect
only the dashboard's grade, never this stored total.

Every writer recomputes it after changing a file: grade-tui on opening a course and after each edit, `grader
sync/update/mkdb`, and `exam submit scores`. A writer changes only the total cells, and writes nothing when they
already match (a stored `40.0` matches `40`).

Implementations: `grade_dashboard/src/sync.py:total_for` and `exam_projects/cli/exam_cli/gradebook.py:total_for`.
Both test this table (mapped columns `a (35pts)` and `b (5pts)`, an unmapped `extra (9pts)` = 9, header `total (40pts)`):

| a | b | total |
|---|---|---|
| `30` | `5` | `35` |
| `12.5` | (empty) | `12.5` |
| `ขส` | `ขส` | `0` |
| `abs` | `3` | `3` |
| (empty) | (empty) | `0` |

## What a score cell can hold

| Cell text | Meaning | Counts as |
|---|---|---|
| a number (`12`, `12.5`) | the score | that number |
| empty | not entered yet | 0 |
| `ขส` | absent from the exam (ขาดสอบ) | 0, and shown as absent in grade-tui and in `reports/*_final_grades.csv` |
| anything else (`abs`, `ข ส`, `12a`) | invalid | 0, with a warning |

Surrounding spaces are ignored. `exam submit scores` writes `ขส` only into **empty** cells of roster students who
have no answer sheet, in every mapped column. Attendance columns use their own codes (P/A/L/X/EA).

Implementations: `grade_dashboard/src/cells.py` and `exam_projects/cli/exam_cli/gradebook.py`. Both test this table:

| input | kind |
|---|---|
| `12` | num 12 |
| ` 12.5 ` | num 12.5 |
| `0` | num 0 |
| `` (empty), `  `, `nan` | empty |
| `ขส`, ` ขส ` | absent |
| `abs`, `ข ส`, `12a` | invalid |

## Hand edits

Each `exam submit scores` keeps what it sent next to its history snapshot:
`<course>/history/<id>/sent.json`, holding `{column: {student id: text}}`. The next submit compares the file with it:

- **A cell that now differs from what was sent was changed by hand.** The preview lists it as "sent → now → exam".
  You then choose to keep your edits (the default, also with `--yes`), overwrite them (`--overwrite-edits`), or pick
  each one.
- **Columns that are neither in `data_mapping` nor exam's own** are columns you added by hand. They are listed and
  never touched.

## Writing a file in a course folder

Every tool that changes a file in a course folder does three things:

1. It copies the current file to `<course>/history/<YYYYMMDD-HHMMSS>_<tool>_<action>/<path relative to course>`.
2. It appends one JSON line to `<course>/history/log.jsonl`:
   `{"id", "ts", "tool", "action", "files": [relative paths], "cells", "note", …}`.
3. It writes the new file atomically (a temp file in the same folder, then `os.replace`). The BOM (if any) and the
   line endings are kept, and every cell it didn't mean to change stays byte-identical.

`exam submit scores` also checks, just before writing, that the file is unchanged since it showed the preview (same
SHA-256). If it changed, it stops and asks you to run it again.

`grader history` lists the entries. `grader undo [ID]` restores one: by default the newest change that isn't an
automatic total refresh and hasn't been undone. It saves the current version first, so the undo can be undone.
