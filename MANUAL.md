# Grading System Manual

Two commands:

- `grader` (`grader.py`) sets up and maintains a course folder.
- `grade-tui` (`rust_tui/`, which calls `src/tui_api.py`) is the dashboard: scores, analytics, editing, export.

Run both from the folder that holds your course folders (e.g. `~/cmru/teachings/2569-1`) or from inside one course
folder.

---

## 🏗️ Managing Courses

### Creating a course from the registration list

```bash
grader init -i repclasslist.xls      # the CMRU class list (.xls)
```

This creates `<term>_<course name>_SEC_<n>_grading/` in the current folder:

- `course_info/<prefix>_student_info.csv`: the roster (`Student ID,Name,Class Group`). It's the one student list both
  `grade-tui` and `exam` use.
- `course_info/<prefix>_config.yaml`: weights, `data_mapping`, grade boundaries.
- `data/<prefix>_attendance.xlsx` (+ `.csv`): attendance sheet.

Without a class list: `grader init --course_name X --term 2026_S1 --course_id PHYS1120`.

### Score files

Edit `data_mapping` in the config, then:

```bash
grader mkdb          # creates data/<prefix>_<category>.csv for each category (never overwrites)
grader update        # realigns those files after a config change (adds columns/students, never deletes scores)
grader update -i repclasslist.xls   # merges a newer class list into the roster
```

Each score file looks like `Student ID,Name,midterm_mcq (35pts),midterm_showsol (5pts),total (40pts)`. The points
come from the header; `total` is filled in by the dashboard.

### What to put in a score cell

| Cell | Meaning |
|---|---|
| a number | the score |
| empty | not entered yet (counts as 0) |
| `ขส` | absent from the exam: counts as 0, shown as absent in the dashboard and the report |
| anything else | invalid: counts as 0 and shows a warning |

### Exam scores from `exam`

Exams made with exam_projects send their scores here with `exam link` (once per exam) and `exam scores`. `exam roster`
compares the answer sheets with this course's roster and lists who was absent. Details: `INTEGRATION.md`.

---

## 🕘 History and undo

Before any tool changes a file in a course folder (`grader update`, edits in `grade-tui`, `exam scores`), the old version
is saved in `<course>/history/` and listed in `history/log.jsonl`.

```bash
grader history              # newest first; --course DIR, -n 50
grader undo                 # restores the newest change not undone yet (asks first)
grader undo 20261007-101500_exam_scores    # restores that one
```

An undo saves the current version first, so it can be undone too. Opening a course in `grade-tui` only writes when a
`total` actually changed, and those automatic total updates are skipped by `grader undo`.

---

## 📊 Exporting Reports

In `grade-tui`, press `e`. This writes `reports/`:

1. `<prefix>_final_grades.csv`: every student, category scores, final score and grade. When anyone has `ขส`, an
   `absent` column lists their exam columns.
2. `<prefix>_copy_friendly_scores.csv`: Student ID next to Cumulative / Midterm / Final, ready to paste into the
   university system.
