# SPEC — One course folder, one sub-folder per section (Astronomy SC 2202, sec 51 + 52)

Replaces SPEC_sections.md (one folder with a `Section` column, Revisions 1-2). Its All / 51 / 52 selector, section
blocks, colours and "phone opens on the section in class" stay; where they get their data from changes.

## Context

The university gives one class list per section. They are now named `repclasslist_Astro_sec51.xls` and
`repclasslist_Astro_sec52.xls` (`~/cmru/teachings/2569-2/`). Today a multi-section course is one folder: one roster
with a `Section` column, one set of score CSVs mixing both sections, and the apps filter by section. You want the
sections kept apart on disk: each section has its own roster, score files and attendance sheet, in its own sub-folder
of the course, and the course shares one config. grade-tui and grade_web show the course once with **All | 51 | 52**,
and All can be edited too.

The real course `2026_S2_Astro51_SEC_51/` (one folder, 55 students, 28 attendance marks in sec 51's `a1`, no scores
yet) moves to the new layout with `grader split`.

## Decisions (interview)

| # | Decision |
|---|---|
| F1 | **A section is a sub-folder** of the course folder. It holds its own roster, score CSVs, attendance sheet and reports. |
| F2 | **One shared config** at the course level, `course_info/<course prefix>_config.yaml`: shared keys at the top, everything per section under `sections:`. No config in a section folder. |
| F3 | **Names:** course folder `<term>_<abbr>` (`2026_S2_Astro`); section folders `sec<N>` (`sec51`); files inside a section keep a full prefix `<term>_<abbr>_SEC_<N>_…` (`2026_S2_Astro_SEC_51_homework.csv`). |
| F4 | **The trigger:** a class list named `repclasslist_<abbr>_sec<N>.xls[x]`, or several class lists, makes the section layout. Several sections always means this layout. |
| F5 | **All / 51 / 52** in grade-tui and grade_web, and **All is editable**: each edit goes to the student's own section folder. Fill in All fills every section. |
| F6 | **One history/** at the course level for everything (config, every section's files). A change across sections is one entry; one `grader undo` reverses it. |
| F7 | **One web copy per course** on Drive with the section folders inside and one journal. The phone lists the course once with the chips. |
| F8 | **exam_projects:** an exam links to the course; `exam mark roster` uses every section's roster; `exam submit scores` writes each student's score into their section's CSV. |
| F9 | **`grader split`** turns a one-folder multi-section course (a roster with a `Section` column) into this layout, keeping every score and mark. |
| F10 | **The one-folder model is replaced.** No new course is made that way; `update -i` adding a section to one says to run `grader split`. The Revision 2 rename offer is removed. |

Defaults chosen for you (say if you want otherwise):
- **A student found in another section's class list** moves: their rows (scores, attendance marks) go from the old
  section's files to the new one's, with `⚠️ 68161301 moves sec 51 → 52 (scores and marks moved)`.
- **Columns are shared.** Every section's score CSV has the config's columns (`grader update` keeps them in step).
  A column added by hand to one section's CSV is offered by `grader sync` as usual and, once in the config, created
  (empty) in the other sections.
- **Attendance:** each section's sheet gets its dates from its own `sections[N].class_schedule` and the course's
  `term_start_date`. Session columns are named the same in every section (`a1…a15`).
- **The phone opens on the section in class** (SPEC_sections.md R7), from `sections[N].class_schedule`.

## Layout

```
2026_S2_Astro/
├── course_info/2026_S2_Astro_config.yaml     shared config (F2)
├── history/                                   every change (F6): paths like sec51/data/…_homework.csv
├── reports/                                   combined exports (all sections, in section blocks)
├── sec51/
│   ├── course_info/2026_S2_Astro_SEC_51_student_info.csv    Student ID,Name,Class Group
│   ├── data/2026_S2_Astro_SEC_51_{homework,midterm,final,attendance}.csv, …_attendance.xlsx
│   └── reports/2026_S2_Astro_SEC_51_{final_grades,copy_friendly_scores}.csv
└── sec52/ …
```

```yaml
# course_info/2026_S2_Astro_config.yaml
course_id: SC 2202
course_name: ดาราศาสตร์และอวกาศ
term: 2026_S2
teacher: …
credits: 3(2-2-5)
university: … / campus: … / program: …
term_start_date: ''
weights: {attendance: 0.1, homework: 0.15, …}
data_mapping: {homework: [hw1, hw2], …}
grade_boundaries: {A: 80, …}
rules: {…}
sections:                        # numeric order
  '51':
    folder: sec51
    class_schedule: {day: ศ., time: 08:30-12:30, classroom: SCI7-206}
    exam_schedule: F 16 Feb 2027 15:10-17:10, M 15 Dec 2026 15:10-17:10
  '52':
    folder: sec52
    class_schedule: {day: ศ., time: 13:30-17:30, classroom: SCI7-206}
    exam_schedule: …
```

Rosters lose the `Section` column (the folder says it). A **section folder** is a folder whose parent's config lists
it under `sections[N].folder`; a **course folder with sections** is one whose config has `sections` with a `folder`.

## The course model (`src/course.py`, new: the one place that knows the layout)

`Course.at(path)`: from any path inside a course (the course folder, a section folder, or a file in either), it
returns:
- `root` (the course folder), `config_path`, `prefix` (the config's stem).
- `sections`: `[Section(num, path, prefix)]` in numeric order. A flat one-section course is
  `[Section(sec_num, root, prefix)]`, so every caller works on sections and never on the layout.
- `here`: the section the path is in, or None at the course level.
- `history`: `root/history`.

Every module that today derives paths from a course folder goes through it: `data_loader` (`load_config`,
`load_course_data(section)`, `get_course_file_prefix`), `sync` (`config_file`, `prefix_of`), `attendance`,
`columns`, `history` (`course_dir_of` returns the course root, so a section's changes log at the top), `sections`
(rewritten: sections come from `Course`, not a roster column), `tui_api`, `dashboard`, `webpush`, `webpull`,
`complete`, and `grader.py`. A flat course behaves exactly as today, byte for byte.

## Behaviour

### `grader init -i <file> [-i <file> …]`
- `repclasslist_<abbr>_sec<N>.xls[x]` (`_sec` is any case): `<abbr>` and `<N>` come from the name. `<N>` must equal
  the sheet's `Sec`, else grader refuses and names the file. Several files must share `term` and `course_id` and
  have distinct sections (as today).
- One `_sec` file, or several files: makes `<term>_<abbr>/` with `course_info/` (config), `history/`, `reports/`,
  and `sec<N>/` per file (roster, empty score CSVs from the config, attendance sheet). Without `_sec` in the name,
  the abbreviation is the common part of the file names with the trailing digits dropped (as today).
- One file without `_sec`: a flat course, as today.
- Output names the sections: `✅ 2026_S2_Astro/: sec51 (28 students), sec52 (27 students)`.

### `grader update -i <file>`
- Runs from the term folder, the course folder or any section folder. It finds the course by term + course_id (as
  today) and the section by the file's `Sec`.
- **Known section:** merges into that section's roster (outer merge, nobody removed), as today.
- **New section:** asks `Add section 52 (27 students) to 2026_S2_Astro? [y/N]` (`-y` yes; no terminal and no
  `-y` → refuses with the hint). It creates `sec52/` with score CSVs and an attendance sheet, and adds
  `sections['52']` to the config.
- **A flat course with a `Section` column (the old model):** refuses with `This course keeps several sections in one
  folder. Run grader split first.`
- **A flat one-section course and another section's list:** asks the same question. On yes it moves the course into
  the layout first, as `grader split` does: the folder becomes `<term>_<abbr>/` holding `sec<old>/`.
- A student moving section: see Defaults.
- One history entry covers the roster(s), config and attendance files it changed.

### `grader split` (new, F9)
- Run inside a one-folder course whose roster has ≥2 sections in its `Section` column (or `grader split COURSE`).
- **Refuses**, changing nothing, when: the roster has students with no section; the target `<term>_<abbr>/` exists;
  the Drive copy has web edits not pulled yet (pull first) or can't be read (SPEC_drive_unreadable.md).
- Makes `<term>_<abbr>/` next to the old folder. The config moves to the top with `sections[N].folder` added and the
  top-level `sec_num`/`class_schedule`/`exam_schedule` dropped (they are in `sections:`). Each score CSV and the
  attendance csv/xlsx are split by the roster's `Section`, keeping every value, header and `(Npts)`. Rows stay in
  roster (ID) order. The rosters lose `Section`. `history/` moves to the top, its paths rewritten.
- The old folder is renamed `<old name>_before_split` (not deleted). `grader split` prints a line per section
  (`sec51: 28 students, 28 attendance marks`) and says to delete the old folder once you're happy.
- `grader undo` of the split restores the old folder name and removes the new course (a history entry in the new
  course's history/; the `_before_split` folder holds the old history).
- Then it offers `Push the new course to the web copy? [y/N]`. The old Drive copy (`…/2026_S2_Astro51_SEC_51`) is
  left as it is, and grader prints that you can delete it in Drive.

### Other grader commands
- `grader update` (no `-i`), `grader sync`, `grader mkdb`: run from the course or any section folder and work on
  **every section** (one history entry). Each section's CSVs get the config's columns, and totals are refreshed in
  each. Every line naming a student is prefixed `[51]`.
- `grader history` / `grader undo`: the course's history, wherever they run.
- `grader dashboard`: lists the course once and asks `Show section [all/51/52]`.
- **Exports** (`dashboard.export_reports`, grade-tui `e`): each section's files in `sec<N>/reports/`, and the
  combined files (with a `Section` column, in section blocks) in the course's `reports/`.
- `grader mock`: a mock course in the section layout (2 sections).
- `grader init` (no `-i`): flat, as today.
- Tab completion (`src/complete.py`): `split` and its `COURSE` argument.

### grade-tui (`src/tui_api.py`, `rust_tui/`)
- **Course list:** a course with sections is listed once (`ดาราศาสตร์และอวกาศ · 51, 52`); section folders are never
  listed on their own.
- `get_course_data(course)` loads every section and merges them for All: `student_grades`/`raw_scores` in section
  blocks, each record with `"Section"`, plus `sections` and `by_section` (as today, so grade-tui's selector, blocks,
  header lines and colours work unchanged). Grade calculation, analytics and the distribution run over the merged
  rows (All) and per section (`by_section`).
- **Edits:** a record's section says which folder its cell is in. `apply_edits`, `update_student_score`,
  `update_column_score` and the attendance writes route each edit to `sec<N>/data/…`. One Ctrl+S is one history
  entry, whatever sections it touched. Fill in All fills every section's rows; in one section, that section's.
- Settings (weights, boundaries) write the shared config.
- **Rust:** nothing changes except the course-list label. The bridge already sends what the selector needs.

### grade_web (`src/webpush.py`, `src/webpull.py`, `web/apps_script/`)
- **web-push** pushes `grade_courses/<semester>/2026_S2_Astro/`: `course.json` (the merged course: shared config,
  `sections` with each section's schedule and `folder`, and `files` listing `sec51/data/…`), each section's roster
  and data CSVs under `sec<N>/`, `push.json`, `web_edits.jsonl`. It runs from the course or any section folder.
- **Server (`Code.js`):** a course is a folder holding `course.json` (as today). It reads every roster in
  `course.json` (`rosters: {"51": "sec51/course_info/…", …}`) and every file in `files`, under its section folder.
  A course with sections is one course in the list.
- **Client:** the roster reader builds `state.sections` from the section rosters (no `Section` column). Everything
  else (chips, blocks, colours, section in class, Fill in the shown rows) is unchanged. A journal line's `file` is
  the path in the course (`sec52/data/…_attendance.csv`).
- **web-pull** applies each line to its file, in that section's folder; one history entry. The preview prefixes
  students `[52]`.
- A flat course is pushed and pulled exactly as today.

### exam_projects (`exam_projects/cli/exam_cli/gradebook.py`, `link.py`, `status.py`; INTEGRATION.md)
- **Finding the course:** unchanged (`*/course_info/*_config.yaml`): it finds `2026_S2_Astro/`. A section folder
  has no config, so it is never a match of its own.
- **`exam submit link`** records `grading_dir: <path to 2026_S2_Astro>` (the course, not a section).
- **`exam mark roster`** reads every section's roster (`sections[N].folder` + `course_info/*_student_info.csv`) and
  lists absent students and misread IDs across all of them, tagged `[51]`.
- **`exam submit scores`** looks up each student's section, writes the score into
  `sec<N>/data/<section prefix>_<category>.csv`, and `ขส` for absent students in their own section's file. The
  preview groups by section. It snapshots into the course's `history/` (one entry), as today.
- **INTEGRATION.md** (identical in both repos; the existing test checks this): adds the section layout (course
  folder, `sections[N].folder`, a section's roster and data paths, history at the top) and drops the `Section`
  column note.

## Files
grade_dashboard: `src/course.py` (new), `src/data_loader.py`, `src/sync.py`, `src/attendance.py`, `src/columns.py`,
`src/history.py`, `src/sections.py`, `src/rename.py` (rename offer removed; the module keeps what `split` reuses),
`src/split.py` (new), `src/tui_api.py`, `src/dashboard.py`, `src/webpush.py`, `src/webpull.py`, `src/complete.py`,
`grader.py`, `course_info_prep/convert_student_info.py` (the `_sec<N>` name), `rust_tui/src/ui.rs` (course list
label), `web/apps_script/{Code.js,client_state.html}`, `MANUAL.md`, `INTEGRATION.md`, `CLAUDE.md`,
`SPEC_sections.md` (marked as replaced). exam_projects: `cli/exam_cli/{gradebook,link,status}.py`, `INTEGRATION.md`.

## Out of scope
- Per-section weights, columns, points or grade boundaries (F2: one config).
- Keeping the one-folder `Section`-column model working beside the new layout (F10). `grader split` converts it.
- Moving or deleting the old Drive copy of a split course (grader says you can delete it).
- More than one level of nesting, and a section folder outside its course folder.
- Running `grader split` on the real course, deploying grade_web (`clasp push`) and pushing to the real Drive: you
  do those.

## Tests
Python (`python -m pytest tests/`), with fake class lists named `repclasslist_Astro_sec51.xlsx` / `…_sec52.xlsx`:
- `tests/test_section_folders.py` (new), init:
  - Two `_sec` files make the layout; one `_sec` file makes `sec51/` only.
  - A name/sheet section mismatch refuses; a file without `_sec` makes a flat course.
  - Several files without `_sec` still make the layout.
- `tests/test_section_folders.py`, update and the commands that run on every section:
  - `update -i`: known section; new section with y / N / `-y` / no tty; a flat one-section course moved into the
    layout; a flat `Section`-column course refused.
  - A student moving section takes their scores and marks with them.
  - `grader update`/`sync` from a section folder change every section with one history entry, and `grader undo`
    reverses it in both.
- `tests/test_split.py` (new):
  - The Astro shape (55 students, a1 marks in sec 51) splits with every value kept, byte-compared per row.
  - Refusals: no section, target exists, unpulled or unreadable Drive copy.
  - `grader undo` of the split; the `_before_split` folder is untouched.
- `tests/test_section_folders.py`, readers:
  - `Course.at()` from every kind of path.
  - A flat course gives byte-identical output for init, update, export, push and course.json (existing goldens
    unchanged).
- tui_api: All merges sections in blocks; `by_section`; an edit in All lands in the student's section file; Fill
  in All fills both; one Ctrl+S is one history entry.
- Web push/pull: `course.json` `sections`/`rosters`/`files`; a pulled sec-52 edit lands in `sec52/`; one history
  entry.
- The existing section tests (`test_sections.py`, `test_rename.py`) are rewritten for the layout. Their behaviour
  (selector data, blocks, exports per section, CLI `[51]` tags) is kept.

Rust (`cargo test`): the course-list label. Web (`node --test 'web/tests/*.test.js'`): rosters from section folders
(`sections.test.js`), a course with sections listed once (`server.test.js`), journal paths into section folders.
Goldens unchanged (`make_golden.py --check`). exam_projects (`./setup.sh --test`): link to a course with sections,
`mark roster` across sections, `submit scores` into each section's CSV with one snapshot. INTEGRATION copy test green.

## Delivery
New branch `section-folders` off `sections`. Local commits per area: course model + init/update, split,
sync/history/exports, tui_api + grade-tui, grade_web, exam_projects (its own repo). You push and deploy.

## End-to-end verification (scratchpad only, never `~/cmru/teachings` or the real Drive)
1. All suites pass: `python -m pytest tests/`, `cd rust_tui && cargo test`, `web/scripts/e2e.sh`, and in
   exam_projects `./setup.sh --test`.
2. **New course:** copy `repclasslist_Astro_sec51.xls` and `…_sec52.xls` into a scratch term folder and run
   `grader init -i repclasslist_Astro_sec51.xls -i repclasslist_Astro_sec52.xls`. Check `2026_S2_Astro/` with the
   config at the top (`sections: 51, 52` and their folders), `sec51/` with 28 students and `sec52/` with 27, each
   with score CSVs and its own attendance sheet.
3. **Split the real shape:** copy `2026_S2_Astro51_SEC_51/` into the scratch term folder and run `grader split` in
   it. Check `2026_S2_Astro/`: sec51's attendance csv and xlsx hold the 28 `a1` marks, sec52 none; nothing else was
   lost (a script compares every cell, old vs new). The history moved, and `2026_S2_Astro51_SEC_51_before_split/`
   is left. `grader undo` of the split brings the old folder back.
4. **grade-tui** from the scratch term folder: Astro is listed once. `n` cycles All (55, two blocks) → 51 (28) → 52
   (27). An edit to a sec-52 student in All lands in `sec52/data/…`, and one `grader undo` reverts it. Fill in All
   fills 55 rows across both folders. `e` writes `sec51/reports/`, `sec52/reports/` and the combined
   `reports/` files.
5. **grade_web:** `grader web-push --drive-root <scratch>/drive` from `sec51/`. course.json lists both sections, and
   `node web/scripts/gas_run.js` lists the course once. Saving a sec-52 attendance mark through the fake server,
   then `grader web-pull --drive-root <scratch>/drive --yes`, writes it into `sec52/data/` only, under `[52]`.
6. **exam_projects:** a scratch exam linked to `2026_S2_Astro/` with a results.csv for students of both sections:
   `exam mark roster` lists absences across 55 students, and `exam submit scores` writes each score into its
   section's CSV (one history entry; `grader undo` reverts both).
7. **You, after `clasp push`:** on the phone the Astro course opens on the section in class, All shows both blocks,
   and a mark saved for sec 52 comes back into `sec52/` with `grader web-pull`.
