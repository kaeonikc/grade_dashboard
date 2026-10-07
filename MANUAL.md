# grade_dashboard — User Manual

grade_dashboard keeps one folder per course section with the class roster, the grading scheme and every raw score.
It turns those into final scores and letter grades that you can paste into the university system.

It has two commands:

| Command | What it's for |
|---|---|
| `grader` | Sets up and maintains course folders: create one from the class list, create the score files, update the roster, history and undo. |
| `grade-tui` | The dashboard: scores, analytics and grade rounding, editing scores, exporting the submission file. |

Exams made with **exam_projects** (`exam …`) send their scores straight into these course folders. See
[Scores from exam_projects](#7-scores-from-exam_projects).

---

## Contents

1. [Setup](#1-setup)
2. [The semester at a glance](#2-the-semester-at-a-glance)
3. [Creating a course](#3-creating-a-course)
4. [The grading scheme (config.yaml)](#4-the-grading-scheme-configyaml)
5. [Score files](#5-score-files)
6. [Attendance](#6-attendance)
7. [Scores from exam_projects](#7-scores-from-exam_projects)
8. [The dashboard (grade-tui)](#8-the-dashboard-grade-tui)
9. [How the final score is calculated](#9-how-the-final-score-is-calculated)
10. [Submitting grades](#10-submitting-grades)
11. [History and undo](#11-history-and-undo)
12. [Changes during the semester](#12-changes-during-the-semester)
13. [Troubleshooting](#13-troubleshooting)
14. [Command reference](#14-command-reference)

---

## 1. Setup

```bash
cd grade_dashboard
pip install -r requirements.txt xlrd       # xlrd reads the university's .xls class lists
(cd rust_tui && cargo build --release)     # builds the dashboard binary used by grade-tui
```

`grader` and `grade-tui` are linked into `~/.mytools/bin`, so they work from any folder.

**Optional colour theme:** copy `theme.json.example` to `~/.config/grade_dashboard/theme.json` (or next to the
`grade-tui` binary) and change the colours.

**Where to run the commands.** Keep the course folders for one term together, for example
`~/cmru/teachings/2569-1/`. Run `grader init` there. Run the other commands either there or inside a course folder:
`grade-tui` lists the course folders in the current directory and in `./courses/`.

---

## 2. The semester at a glance

| When | What you do | Command |
|---|---|---|
| Before the first class | Download the class list (`repclasslist*.xls`) from the registration system | — |
| | Create the course folder | `grader init -i repclasslist.xls` |
| | Set the weights, score columns and grade boundaries | edit `course_info/<prefix>_config.yaml` |
| | Create the empty score files | `grader mkdb` |
| Every week | Take attendance | `data/<prefix>_attendance.xlsx` or `grade-tui` |
| | Enter homework, lab and quiz scores | `grade-tui`, or edit the CSV |
| Late registrations or withdrawals | Merge the newer class list | `grader update -i repclasslist.xls` |
| Midterm and final | Mark the OMR sheets and send the scores in | `exam grade` → `exam roster` → `exam scores` |
| End of term | Check the grades, rounding and absences, then export | `grade-tui` → `e` |
| | Paste into the university system | `reports/<prefix>_copy_friendly_scores.csv` |
| Any time something looks wrong | See what changed and undo it | `grader history`, `grader undo` |

---

## 3. Creating a course

```bash
cd ~/cmru/teachings/2569-1
grader init -i repclasslist_IndustPhysics.xls
```

The class list is read for the term (`ภาคการศึกษา 1/2569` → `2026_S1`), course code and name, section, teacher,
class day/time/room and exam schedule. It also reads every student row (`รหัสประจำตัว`, `ชื่อ`, `หมู่เรียน`).

It creates:

```
2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51_grading/
├── course_info/
│   ├── <prefix>_config.yaml        grading scheme + course details
│   └── <prefix>_student_info.csv   the roster: Student ID, Name, Class Group
└── data/
    ├── <prefix>_attendance.xlsx    attendance sheet (one column per class date)
    └── <prefix>_attendance.csv     its copy that the dashboard reads
```

`<prefix>` is the folder name without `_grading`, for example `2026_S1_ฟิสิกส์สำหรับอุตสาหกรรม_SEC_51`.

**The roster is the single student list.** grade-tui, `exam roster` and `exam scores` all use
`course_info/<prefix>_student_info.csv`. Change it only with `grader update -i` (see
[section 12](#12-changes-during-the-semester)). Don't edit it by hand.

Without a class list you can run `grader init --course_name "General Relativity" --term 2026_S2 --course_id PHYS4101`.
This gives an empty roster that you fill in yourself.

**Practice course:** `grader mock` creates `courses/0_ฟิสิกส์ทั่วไป_(ข้อมูลจำลอง)_grading` with 30 made-up students and
a few deliberate problems (scores over the maximum, missing scores, invalid attendance codes). Use it to try things
out.

---

## 4. The grading scheme (config.yaml)

Edit `course_info/<prefix>_config.yaml`. The course details at the top come from the class list. These keys decide the
grade:

```yaml
term_start_date: 2026-06-15       # YYYY-MM-DD, first week of term; attendance dates are counted from it

weights:                          # must add up to 1.0
  attendance: 0.10
  homework: 0.20
  midterm: 0.30
  final: 0.40

data_mapping:                     # category → its score columns, with points
  homework:
    - hw1 (15pts)
    - hw2 (15pts)
  midterm:
    - midterm_mcq: 35             # same as "midterm_mcq (35pts)"
    - midterm_showsol: 5
  final:
    - final_exam: 25

grade_boundaries:                 # lowest score for each grade; anything lower is F
  A: 80
  B+: 75
  B: 70
  C+: 65
  C: 60
  D+: 55
  D: 50

rules:
  drop_lowest_homework: true      # drop each student's weakest homework (needs ≥ 2 homework columns)
```

**Rules of thumb**

- **Give every column its points**, either as `name (Npts)` or `- name: N`. A column without points gets a default
  maximum, and the percentages will be wrong.
- **Every category in `weights` needs a `data_mapping` entry.** A weight with no columns (e.g. `quiz: 0.15` but no
  `quiz:` under `data_mapping`) gives every student 0 for that part, and nothing warns you.
- The names `midterm` and `final` are special: they're reported separately. Every other category (attendance,
  homework, quiz, lab, …) adds up to the *Coursework* score.
- Column names are what `exam link` / `exam scores --column` use (`midterm_mcq`, or `final` for a category that has
  one column).
- Optional: a category can be written as `{total_pts: 30, columns: [...]}` to fix its total; a warning shows if the
  columns don't add up to it.

After changing `data_mapping`, run `grader update` from inside the course folder. It adds the new columns to the
score files and never deletes a score.

You can also change the weights and boundaries from the dashboard (`w`, `b`). That rewrites the YAML file, and any
comments in it are lost.

---

## 5. Score files

```bash
cd 2026_S1_…_SEC_51_grading
grader mkdb
```

This creates one CSV per category in `data/`, with every student on the roster:

```
Student ID,Name,midterm_mcq (35pts),midterm_showsol (5pts),total (40pts)
69143302,นาย …,,,
```

- The points come from the header `(Npts)`.
- `total` is filled in by the dashboard. Don't type into it.
- `mkdb` never overwrites a file that already exists.

### What to put in a score cell

| Cell | Meaning | Counts as |
|---|---|---|
| `12`, `12.5` | the score | that number |
| *(empty)* | not entered yet | 0 |
| `ขส` | absent from the exam (ขาดสอบ) | 0, shown as absent in the dashboard and in the report |
| anything else (`abs`, `-`, `ข ส`) | invalid | 0, and a warning in the dashboard |

The same rules are written in `INTEGRATION.md`; exam_projects follows them too.

### Ways to enter scores

1. **In grade-tui:** go to *Raw Details*, pick the category, then press `Enter` on a cell to edit it, or `f` to fill
   the whole column with one value.
2. **From an exam:** `exam scores` (see [section 7](#7-scores-from-exam_projects)).
3. **In a spreadsheet:** open the CSV, type the scores, and save it as CSV (UTF-8). Keep the header row and the
   `Student ID` column exactly as they are, and close grade-tui first.

---

## 6. Attendance

`data/<prefix>_attendance.xlsx` has one column per class: 15 weekly dates counted from `term_start_date` and the
class day in `class_schedule`, skipping the midterm week. Until `term_start_date` is set, the columns are called
`a1`…`a15`. Set it, and run `grader update` in the course folder, **before** you start recording attendance.

Enter one of these codes:

| Code | Meaning | Counts as |
|---|---|---|
| `P` | present | 1 |
| `L` | late | 0.8 |
| `X` or `EA` | excused | 1 |
| `A` | absent | 0 |
| *(empty)* | not recorded | 0 |

The attendance score is the sum of the codes ÷ the number of date columns. Until the term ends, the empty future
dates pull the attendance percentage down; that's expected.

You can record attendance in Excel (the dashboard re-reads the `.xlsx` whenever it's newer than the `.csv`), or in
grade-tui. In grade-tui, `Enter` on a cell opens a P/L/A/X picker, and `f` fills a whole date. grade-tui updates both
files.

---

## 7. Scores from exam_projects

exam_projects (`exam …`) writes, prints and marks the MCQ exams, then sends the scores into the course folder. It
uses the roster from this folder, so it can tell you who was absent before anything is written.

```bash
cd ~/cmru/teachings/2569-1/midterm_exams/2026_S1_midterm_exam_IndustPhys
exam link          # once: finds this course (course code + term), asks for the column, e.g. midterm_mcq
exam grade         # marks the scanned OMR sheets
exam roster        # who sat the exam, who was absent, which IDs don't match the roster
exam roster --fix  # accept the suggested corrections for misread IDs
exam scores        # preview → y/N → writes the scores, and ขส for absent students
```

What `exam scores` does to your course folder:

- It changes **only the score cells** of one column. It never adds or removes students or columns, and never
  touches `total`, the roster or the config.
- Absent students get `ขส`, **but only in an empty cell**. A score you already entered, such as a make-up exam, is
  kept.
- It saves the file in `history/` first, so `grader undo` can put it back.
- If one exam covers two sections (two course folders), each student's score goes to the section whose roster lists
  them.

Essay or hand-marked exams don't go through `exam scores`. Type those scores in grade-tui, or into the CSV, and use
`ขส` for absent students.

---

## 8. The dashboard (grade-tui)

```bash
cd ~/cmru/teachings/2569-1
grade-tui
```

Pick a course with `▲/▼` and `Enter`. The dashboard has four tabs; `Tab` and `Shift-Tab` move between them.

| Tab | What it shows |
|---|---|
| **1 Summary** | *Summary Scores*: every student's category scores, final score and grade, with a panel for the selected student (including any `ขส`). *For Submission*: Cumulative / Midterm / Final in the layout the university system expects. |
| **2 Raw Details** | The raw scores per category, where you edit them. `ขส` cells are highlighted. `Enter` on a student's name opens all of that student's scores. |
| **3 Analytics** | *Overview* (mean, median, SD, pass rate, histogram, box plot) · *Progress Over Time* (class average per item) · *Item Analysis* (difficulty and discrimination per score column) · *Correlation Matrix* (between categories) · *At-Risk Students* (failing or below the lower quartile) |
| **4 Roundup** | Which students' grades changed because each component is rounded up (see [section 9](#9-how-the-final-score-is-calculated)). |

The header shows the course, the term, the mode (weighted or raw) and the number of `ขส` cells. A yellow
**warnings** bar at the bottom lists problems in the data: scores over the maximum, text in score cells, invalid
attendance codes, totals that don't match.

### Keys

| Key | Where | Action |
|---|---|---|
| `▲ ▼ ◀ ▶` / `j k` | everywhere | move |
| `Ctrl-D` / `Ctrl-U` | tables | half a page down / up |
| `Tab` / `Shift-Tab` | dashboard | next / previous tab |
| `→` or `Enter` | category list | focus the table |
| `←` or `Esc` | table | back to the category list |
| `[` / `]` | Raw Details, Analytics | previous / next category |
| `Enter` | Raw Details cell | edit the score (`Enter` saves, `Esc` cancels); attendance opens a P/L/A/X picker |
| `f` | Raw Details | fill the whole column with one value |
| `c` | dashboard | switch between weighted scores and raw percentages |
| `w` / `b` | dashboard | edit weights / grade boundaries (saved to config.yaml) |
| `e` | dashboard | export the reports (see [section 10](#10-submitting-grades)) |
| `Esc` | dashboard | back to the course list |
| `q` | not while editing | quit |

**What opening a course writes.** grade-tui keeps each score file's `total` column up to date. It writes a file only
when a total actually changed, and only the total cells. Every write it makes, edits included, is saved in
`history/` first.

---

## 9. How the final score is calculated

1. **Each category:** add up the student's scores and divide by the category's maximum points. Empty, `ขส` and
   invalid cells count as 0. With `drop_lowest_homework`, each student's weakest homework (by percentage) is left
   out.
2. **Weight it:** category % × weight × 100. Example: midterm 30/40 = 75 % × 0.30 → 22.5 points.
3. **Group:** every category except `midterm` and `final` adds up to *Coursework Total*.
4. **Round up:** *Coursework Total*, the midterm points and the final points are each rounded **up** to a whole
   number (22.5 → 23). This is deliberate. The Roundup tab shows whose grade this changed.
5. **Final Score** = Coursework + Midterm + Final. **Grade:** the highest boundary the score reaches; below the
   lowest one is F.

Press `c` to see raw percentages instead of weighted points.

---

## 10. Submitting grades

1. In grade-tui check the warnings bar, the `ขส` count, and the Roundup tab.
2. Press `e`. This writes `reports/`:
   - `<prefix>_final_grades.csv`: every student, category scores, final score, grade, and an `absent` column naming
     the exams where the student has `ขส`.
   - `<prefix>_copy_friendly_scores.csv`: `Student ID | Cumulative | Midterm | Final` blocks separated by blank
     columns, ready to copy and paste into the university system.
3. Paste the blocks into the university system. Use the `absent` column to decide on special cases, such as an
   incomplete grade for a student who missed the final.

---

## 11. History and undo

Before any tool changes a file in a course folder, it saves the old version:

```
<course>/history/20261007-141323_exam_scores/data/<prefix>_midterm.csv
<course>/history/log.jsonl      one line per change: when, which tool, which files, how many cells, a note
```

This covers `grader update`, edits and fills in grade-tui, total updates, and `exam scores`.

```bash
grader history                       # newest first; marks the ones already undone
grader history -n 50 --course <dir>
grader undo                          # restore the newest real change (asks first)
grader undo 20261007-141323_exam_scores
grader undo --yes                    # don't ask
```

- `grader undo` without an ID skips grade-tui's automatic total updates and anything already undone. Running it again
  goes one step further back.
- Restoring an older entry also discards later changes to the same file. `grader undo` lists those changes before it
  asks.
- An undo is saved too, so you can undo it.
- Run these commands inside the course folder, or pass `--course <folder>`.

`history/` grows by one small copy per change. To save space, delete old entry folders once the term is closed.

---

## 12. Changes during the semester

**Students added or dropped.** Download a new class list, then:

```bash
grader update -i repclasslist_IndustPhysics.xls     # from the term folder or inside the course folder
grader update                                       # inside the course folder: add the new students to the score files
```

New students are added. Students who are no longer on the list stay in the roster: nothing is deleted
automatically.

**New score columns or categories.** Edit `data_mapping`, then run `grader update` inside the course folder.

- New columns and files are added.
- Renamed columns keep their scores.
- A column that's no longer in the config is kept. Add `--purge-empty-orphans` to remove such columns, but only when
  every cell in them is empty.

---

## 13. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `grade-tui` shows "No course directories found" | Run it from the term folder (the one that holds the `*_grading` folders) or inside a course folder. |
| A category is 0 for everybody | Its weight has no columns in `data_mapping`, or the column names in the config and the CSV header differ. Run `grader update`. |
| Percentages look too low or too high | A column has no `(Npts)`. Add the points in the config and run `grader update`. |
| Warning "… is not a score … counted as 0" | Text in a score cell. Use a number, leave it empty, or `ขส`. |
| `exam scores` says a student has no row in the data file | The roster has a student the score file doesn't. Run `grader update` inside the course folder. |
| `exam scores` says the file "changed after the preview" | grade-tui or another tool saved the file meanwhile. Run `exam scores` again. |
| `grader init -i` can't read the .xls | Install `xlrd` (`pip install xlrd`). The class list must be the original `.xls`, not a `.csv`. |
| Something got overwritten | `grader history`, then `grader undo <ID>`. |

---

## 14. Command reference

| Command | Does |
|---|---|
| `grader init -i <class list.xls>` | create a course folder from the class list |
| `grader init --course_name N --term 2026_S1 --course_id C` | create one without a class list |
| `grader mkdb [config.yaml]` | create the missing score files from `data_mapping` |
| `grader update -i <class list.xls>` | merge a newer class list into the roster |
| `grader update [config.yaml] [--purge-empty-orphans]` | align the score files with the config |
| `grader history [--course DIR] [-n N]` | list saved versions |
| `grader undo [ID] [--course DIR] [--yes]` | restore a saved version |
| `grader mock` | create the practice course |
| `grade-tui` | open the dashboard |

The file formats and the rules shared with exam_projects are in `INTEGRATION.md`.
