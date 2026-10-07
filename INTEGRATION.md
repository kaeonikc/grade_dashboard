---
contract: 1
---

# grade_dashboard ↔ exam_projects

This file is the agreement between **grade_dashboard** (`grader`, `grade-tui`) and **exam_projects** (`exam`).
The same file is kept in both repos; change both copies together and bump `contract` when a rule changes.
The two projects never import each other's code. They meet only through the files described here.

## Who owns what

| Thing | Owner | The other project may |
|---|---|---|
| Course folder `<term>_<name>[_SEC_<n>]_grading/` | grade_dashboard (`grader init`) | read it |
| Roster `course_info/<prefix>_student_info.csv` (`Student ID,Name,Class Group`) | grade_dashboard (`grader init/update -i repclasslist.xls`) | read it; never write it |
| Config `course_info/<prefix>_config.yaml` (`data_mapping`, `weights`, …) | grade_dashboard | read it; never write it |
| Score files `data/<prefix>_<category>.csv` | grade_dashboard (`grader mkdb/update`) | `exam scores` changes **existing score cells only** |
| `total (Npts)` column | grade_dashboard (recomputed by grade-tui) | never write it |
| Exam folder, `grading/results.csv` | exam_projects | grade_dashboard doesn't read them |

`exam scores` never adds or removes rows or columns. A student on the roster without a row in the data CSV is
reported ("run `grader update`") and skipped.

## Finding the course from an exam

`exam link` (and `exam scores` without `--to`) looks for `*/course_info/*_config.yaml` in the folders up to three levels
above the exam folder, plus every folder in `$EXAM_GRADEBOOK_ROOTS` (`:`-separated). A course matches when

- its `term` equals the exam's `semester` converted (`1/2569` → `2026_S1`), and
- its `course_id` appears in the exam's `course:` (e.g. `PHYS1120 ฟิสิกส์สำหรับอุตสาหกรรม`), or, when the exam
  has no course code, its `course_name` equals the exam's course name (spaces and `_` ignored).

The choice is written into `<exam>_metadata.yaml` as `grading_dir:` (a path, or a list of paths for several
sections, relative to the exam folder) and `grade_column:`.

## Score columns

`grade_column` names a column from `data_mapping` (`midterm_mcq`) or a category that has exactly one column
(`final`). The CSV header for it is `<column> (Npts)`; the points `N` come from the header, as in
`src/data_loader.py:parse_pts`.

## What a score cell can hold

| Cell text | Meaning | Counts as |
|---|---|---|
| a number (`12`, `12.5`) | the score | that number |
| empty | not entered yet | 0 |
| `ขส` | absent from the exam (ขาดสอบ) | 0, and shown as absent in grade-tui and `reports/*_final_grades.csv` |
| anything else (`abs`, `ข ส`, `12a`) | invalid | 0, with a warning |

Surrounding spaces are ignored. `exam scores` writes `ขส` only into **empty** cells of roster students who have no
answer sheet; it never replaces an existing score with `ขส`. Attendance columns use their own codes (P/A/L/X/EA).

Implementations: `grade_dashboard/src/cells.py` and `exam_projects/cli/exam_cli/gradebook.py`. Both test this table:

| input | kind |
|---|---|
| `12` | num 12 |
| ` 12.5 ` | num 12.5 |
| `0` | num 0 |
| `` (empty), `  `, `nan` | empty |
| `ขส`, ` ขส ` | absent |
| `abs`, `ข ส`, `12a` | invalid |

## Writing a file in a course folder

Every tool that changes a file in a course folder:

1. copies the current file to `<course>/history/<YYYYMMDD-HHMMSS>_<tool>_<action>/<path relative to course>`;
2. appends one JSON line to `<course>/history/log.jsonl`:
   `{"id", "ts", "tool", "action", "files": [relative paths], "cells", "note", …}`;
3. writes the new file atomically (temp file in the same folder, then `os.replace`), keeping the BOM (if any) and the
   line endings, and leaving every cell it didn't mean to change byte-identical.

`exam scores` also checks, just before writing, that the file is unchanged since it showed the preview (same
SHA-256); otherwise it stops and asks you to run it again.

`grader history` lists the entries; `grader undo [ID]` restores one (default: the newest change that isn't an
automatic total sync and hasn't been undone), saving the current version first so the undo can be undone.
