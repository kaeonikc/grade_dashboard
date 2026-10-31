> **Replaced by SPEC_section_folders.md (2026-10-31):** a course with several sections is now one sub-folder per
> section sharing one config. The All / 51 / 52 selector, section blocks, colours and "phone opens on the section in
> class" below still describe the apps; the one-folder `Section`-column layout and the rename on `update -i` are gone
> (`grader split` converts an old course).

# SPEC — Courses with several sections (Astronomy SC 2202, sec 51 + 52)

## Context

Astronomy (SC 2202, 2/2569) is taught to two sections: sec 51 (Fri 08:30–12:30, 28 students) and sec 52
(Fri 13:30–17:30, 27 students), same room, same exams, same weights. The university's class list is one file per
section (`~/cmru/teachings/2569-2/repclasslist_Astro51.xls`, `…Astro52.xls`), and grader's model is one class list =
one section = one folder. Today only `2026_S2_Astro51_SEC_51/` exists. `grader update -i repclasslist_Astro52.xls`
inside it would merge the students but overwrite `sec_num` with 52 and record nobody's section. grade-tui, grade_web
and the CLI never show which section a student is in. `Class Group` (หมู่เรียน, e.g. `ว 68.ค.บ.4.1`) is a cohort, not
a section, so it can't stand in for one.

A side bug: `รหัสวิชา  SC 2202  ดาราศาสตร์และอวกาศ` is parsed as `course_id: SC`, `course_name: 2202 ดาราศาสตร์…`.

Goal: one course folder holds every section. The roster records each student's section. grade-tui, grade_web and the
`grader dashboard` get an **All | 51 | 52** selector that filters everything. Exports are written per section, and
CLI output names sections.

## Decisions (from the interview)

| # | Decision |
|---|---|
| D1 | **One folder per course.** The roster gets a `Section` column. Score CSVs, weights and grade boundaries are shared. |
| D2 | **`grader update -i <other section>.xls` adds a section after asking** `Add section 52 (27 students) to <course>? [y/N]`; `-y` skips the question. `grader init -i a.xls -i b.xls` (repeatable `-i`) makes a multi-section course in one go. |
| D3 | *(Replaced by R2–R3 in Revision 2: `update -i` offers a rename.)* **Names never change.** Adding a section renames nothing (`2026_S2_Astro51_SEC_51` keeps its name, so the Drive copy, history/ and exam `grading_dir:` links stay valid). After adding, grader prints a one-line note that you can rename the folder by hand. `init` with several files names the course `<term>_<abbr>_SEC_51-52`. |
| D4 | *(All view amended by R5 in Revision 2: grouped blocks with header rows.)* **Selector All / each section**, shown only when a course has ≥2 sections. It filters rows, the attendance grid, stats, the grade distribution and bars. In **All**, each section has its own colour (Sec chip background, row marker line, ID/name text). The choice is remembered per course. |
| D5 | **Attendance: one sheet, shared session columns** (meeting N is the same date for every section; Astro meets on Fridays). Header dates come from the first section's schedule, as today. |
| D6 | **Section lives in the roster**, plus a read-only `Sec` column after `Name` in the **attendance xlsx** (for sorting and filtering in Excel). Score CSVs and the attendance csv are unchanged, and every app joins the section from the roster. |
| D7 | **Exports:** the combined file (with a `Section` column) **plus** one file per section: `…_final_grades_sec51.csv`, `…_copy_friendly_scores_sec51.csv`, and so on. |
| D8 | **In scope extras:** sections shown in CLI output; a section choice in `grader dashboard`; `grader mock` with 2 sections; fixing the `SC 2202` parse. |

## Data model

**Roster** `course_info/<prefix>_student_info.csv`: `Student ID,Name,Class Group,Section`. `init`/`update -i` always
write `Section`, including for single-section courses. A roster without the column is a course without sections, and
everything behaves exactly as it does today.

**config.yaml**: existing keys keep their meaning, and a `sections` map is added:
```yaml
sec_num: '51'                 # unchanged: the first section (old readers keep working)
class_schedule: {…}           # unchanged: the first section's (attendance dates come from it)
exam_schedule: …
sections:                     # sorted by number; written by init/update -i
  '51': {class_schedule: {day: ศ., time: 08:30-12:30, classroom: SCI7-206}, exam_schedule: F 16 Feb 2027 …}
  '52': {class_schedule: {day: ศ., time: 13:30-17:30, classroom: SCI7-206}, exam_schedule: F 16 Feb 2027 …}
```
`update -i` for section N writes the class list's schedule into `sections[N]`, and into the top-level keys only when N
is the first section. It never clobbers another section's entry.

**Section order** is numeric order everywhere (selector, colours, exports, CLI counts). A section's colour comes from
its position in that order.

## Behaviour

### `grader init`
- `-i` becomes `action="append"`. With several files, all of them must share `term` and `course_id` (compared with
  spaces removed), and their sections must be distinct. Otherwise grader refuses and creates nothing, naming the
  mismatched file.
- Abbreviation: `--abbr`, else the common part of the file-name abbreviations with trailing digits stripped
  (`Astro51` + `Astro52` → `Astro`), else ask (as `_resolve_abbr` does now). Folder name: `<term>_<abbr>_SEC_51-52`.
- Writes the roster with `Section`, `sections:` in config, and one attendance sheet holding every student.

### `grader update -i <file>`
- **Course match** (`find_course_dir`): term + course_id. The course_id is compared with spaces removed, and the
  old broken form is also accepted (config `course_id + course_name` with spaces removed equals the new
  `course_id + course_name` with spaces removed). A match no longer needs `sec_num` to be equal; the file's section is
  looked up in the course's sections.
- **Inside a course folder** (cwd has `course_info/`): the file's term and course_id must match that course's.
  Otherwise grader refuses (today it merges any file silently).
- **New section** → asks `Add section 52 (27 students) to <folder>? [y/N]`. `-y` answers yes. Without a terminal and
  without `-y`, grader refuses with the `-y` hint. On yes, the students are appended with `Section=52` and
  `sections['52']` is added. A course whose roster has no `Section` yet gets its existing rows filled with the
  config's `sec_num` first.
- **Known section** → as today (outer merge, nobody removed), and this file's students get `Section=N`.
- **Student already in another section** → the file wins: `⚠️ 68161301 moves sec 51 → 52 (repclasslist_Astro52.xls)`.
- **Roster rows with a blank Section** in a multi-section course → warned once per update, and shown only under *All*.
- The summary names sections: `✅ Roster: 55 students (sec 51: 28 · sec 52: 27)`, plus the rename note from D3.
- The history snapshot covers the roster, config and attendance files, as now (`grader undo` restores them).
- Config metadata merge: also repairs `course_id`/`course_name` when the parse fix changes them.

### Parse fix (`course_info_prep/convert_student_info.py`)
`รหัสวิชา\s*([A-Za-z]+\s?\d+[A-Za-z0-9]*)` → `course_id: "SC 2202"`, kept exactly as the university prints it
(exam_projects matches `course_id` as a substring of the exam's `course:` line), and `course_name: ดาราศาสตร์และอวกาศ`.
`PHYS1120` still parses as `PHYS1120`. The `_resolve_abbr` default turns the space into `-` (existing sanitiser).

### Attendance xlsx (`grader.py:save_attendance_excel`, `src/attendance.py`, `src/tui_api.py`)
- With ≥2 sections, the header is `Student ID | Name | Sec | <sessions> | total (Npts)`. Session columns start at
  column D, and the COUNTIF range, data validation and conditional formatting shift with them.
- Every reader of the xlsx treats `Sec` like `Name`, never as a session: `align_rows`, `make_csv`, the xlsx↔csv sync,
  `_update_xlsx_attendance(_bulk)` and web-pull's attendance write-back. The attendance **csv** never has `Sec`.
- Adding a section to an existing course regenerates the sheet through `save_attendance_excel` (it already keeps the
  marks) and inserts `Sec`. Marks and session columns survive, and a test checks this.

### grade-tui (`rust_tui/`) and its bridge (`src/tui_api.py`)
- `get_course_data(course_path, use_weighted)` adds `sections: ["51","52"]` and `record["Section"]` per student
  (alongside `_class_groups`, read from the same roster), plus `by_section: {"51": {grade_distribution,
  roundup_summary, analytics}, …}` (raw_index into the whole course), so switching costs no round trip.
- grade-tui keeps the whole course in `App.full_data`; `course_data` is the shown view (`only_section`, raw_index
  renumbered), so every tab, the cursor and Fill Column work on the shown rows unchanged. Edits are keyed by student
  ID, so they survive switching.
- **Selector bar** is one line between the tab row and the panel, on every tab: `Sec: ▸All  51 (28)  52 (27)  28 of
  55 students · n next section`. Key **`n`** cycles All → 51 → 52 → All (`e` exports and `s` hides the panel; `n` was
  free). Hidden for <2 sections; `[n] Next Section` joins the footer only then.
- Filtered by the selection: Summary, Raw Details, Analytics (from `by_section`), Roundup, the attendance
  grid, and the counts in titles (`Students: 28 of 55`).
- **Bulk edits respect the selector.** Fill/clear "all rows" or "empty rows" act on the visible section only; the
  dialog reads `All 18 in sec 52` and the result `Filled hw3 = 4 for 18 students in sec 52`.
- **All view colours** (no extra column, so the width maths stays as it is): a `▌` row marker in the section colour,
  the ID cell as a chip (section colour background), and the name in that colour, on Summary, For Submission and
  Raw Details. Theme key `sections: [81, 221, 141, 114]` (cycled) is added to
  `style.rs` defaults and `theme.json.example`.
- Export (`e`) writes the D7 files whatever the selection, and its message names the per-section files.
- The choice is remembered per course for the session (kept in `App`, keyed by course path).

### grade_web (`web/apps_script/`)
- `classGroups(roster)` grows into a roster reader returning group **and** section per student. `state.section`
  defaults to `'all'`.
- A chip row `[All] [51] [52]` sits above the tabs in the course view (phone and desktop), hidden for <2 sections.
  It filters the score table, attendance grid (`byAttendance` included), grade summary/bars, and search results
  (search ANDs with the selector). The detail view shows `Section 51`.
- All-view colours: CSS tokens `--sec-1…--sec-4` defined on `:root` with dark-mode variants. A chip background on
  the Sec cell, a left border line on the row, and tinted ID/name text.
- Remembered per course in `localStorage` (try/catch; falls back to All).
- Edits made while a section is selected only touch visible rows (bulk fill, same as the TUI).

### `grader dashboard` (`src/dashboard.py`)
It's a rich console app (not Streamlit). For ≥2 sections it prints the counts and asks `Show section [all/51/52]`
(default all); the metrics, roundup, table and distribution then cover that section. Export writes the D7 files.

### Exports (one shared helper)
`src/dashboard.py:export_reports`, already shared by `grader dashboard` and `tui_api.run_export`, writes the combined
files (with `Section` after Name) and `_sec<N>` files per section, in roster order. Single-section courses write
exactly today's files.

### CLI output
- `grader web-push`: `55 students (sec 51: 28 · sec 52: 27)` in its summary.
- `grader web-pull` preview, `grader sync`, `grader update`: any line naming a student is prefixed `[51]`, and the
  lists are sorted by section, then by ID.
- `grader history` / `undo`: unchanged (they don't list students).

### `grader mock`
The mock course gets two sections (51, 52) with a `Section` column and `sections:` in config, replacing the
`MOCK.SEC.1/2` Class Group stand-in (Class Group becomes a realistic cohort string).

### Tab completion (`src/complete.py`)
`init -i` is now repeatable, so `grader init -i a.xls -i <TAB>` still offers files. Covered by `test_completion.py`.

### INTEGRATION.md (both repos, identical; the existing test checks this)
The roster row becomes `Student ID,Name,Class Group[,Section]`. Add one note: a course may hold several sections in
one folder (`sections:` in config). exam_projects reads the roster by column name (`gradebook.py:179`), so it needs
no code change.

## Out of scope
- Per-section weights, grade boundaries, columns, or attendance dates (D5: shared sessions).
- One attendance sheet per section, or section-specific session columns.
- Renaming existing folders or files (D3).
- Removing a section or students (`update` never removes, as today).
- exam_projects features per section (`exam mark roster` per section, per-section score submission). The INTEGRATION
  note is the only change there.
- Deploying grade_web (`clasp push`) and touching the real course in `~/cmru/teachings`: you do those.

## Test plan
Python (`python -m pytest tests/`):
- `tests/test_sections.py` (new), with a test builder that writes repclasslist xls/xlsx for sec 51/52:
  init with two files (folder `…_SEC_51-52`, roster Section, config `sections`); init refusing a mismatched term or
  course; update adding a section with y / N / `-y` / no-tty refusal; filling the old roster's Section from
  `sec_num`; a moved student; refusing a foreign file inside a course folder; matching the old broken course_id; a
  re-update of sec 51 leaving `sections['52']` intact; the `SC 2202` and `PHYS1120` parses.
- Attendance (in `test_sections.py`): the xlsx has `Sec`, the csv doesn't; the sync round trip; adding a section
  keeps marks and leaves nothing to sync.
- tui_api (in `test_sections.py`): `sections`, `Section` per record, `by_section` counts, raw_index stays a
  whole-course row.
- `test_web_push.py`/`test_web_pull.py`: the per-section count line and the `[51]` prefixes.
- Exports: combined + `_sec51`/`_sec52` files, and single-section output byte-identical to before.
- `test_completion.py`: repeated `-i`. INTEGRATION copy test still green.

Rust (`cd rust_tui && cargo test`): the selector cycles and hides for <2 sections; the choice survives a reload;
bulk fill touches only the visible section; a section's analytics have raw_index renumbered; the bar renders.
`tests/test_web_hygiene.py`'s approved grade-tui file list gains style.rs, types.rs and ui.rs.

Web (`node --test 'web/tests/*.test.js'`): `sections.test.js` (roster parsing, the selector filtering rows, grades,
stats and Fill, memory per course, blocked storage) and `style.test.js` (section colours 4.5:1 in light and dark).
Goldens are unchanged (`python3 web/tools/make_golden.py --check`).

## Delivery
New branch `sections` off `tab-completion`. Local commits per area: data model/CLI + parse fix, attendance,
tui_api + grade-tui, grade_web, dashboard + exports, mock. `INTEGRATION.md` gets a matching commit in
exam_projects. You push and deploy.

## End-to-end verification
In the scratchpad, never in `~/cmru/teachings`:
1. All three suites pass: `python -m pytest tests/`, `cd rust_tui && cargo test`, the web node tests
   (`web/scripts/e2e.sh`).
2. Copy `2026_S2_Astro51_SEC_51/`, `repclasslist_Astro51.xls` and `repclasslist_Astro52.xls` into a scratch term
   folder. In the course folder, run `grader update -i ../repclasslist_Astro52.xls`, answer `y`, and check:
   `Roster: 55 students (sec 51: 28 · sec 52: 27)`, the rename note, config `course_id: SC 2202`, `sections: 51, 52`
   with the two schedules, the attendance xlsx with `Sec` and its old marks intact, the attendance csv without `Sec`.
   `grader undo` then restores the one-section state, and redo.
3. `grader init -i repclasslist_Astro51.xls -i repclasslist_Astro52.xls` in an empty scratch folder →
   `2026_S2_Astro_SEC_51-52/`.
4. Run `grade-tui` from the scratch folder: `e` cycles All/51/52, counts read 55/28/27, Analytics changes with it,
   the All view shows coloured section chips, a bulk fill with sec 52 selected touches 27 rows only, and export
   writes `_sec51`/`_sec52` files.
5. `grader web-push --drive-root <scratch>/drive` prints the per-section count. Editing one sec-52 cell in the pushed
   CSV, then `grader web-pull --drive-root <scratch>/drive`, shows that line with `[52]`.
6. `grader mock`, then `grader dashboard`: the section question filters the tables and distribution.
7. grade_web, after you `clasp push`: open the Astro copy on a phone. The chips appear, filter, are remembered after
   reload, and the colours read well in light and dark.

---

## Revision 2 (2026-10-31): grouped, renamed, pushed

Amends D3 and D4 above; everything else in revision 1 stands.

### Context: why it "didn't work"

The data side of revision 1 is correct. The real Astro course `~/cmru/teachings/2569-2/2026_S2_Astro51_SEC_51/` has
55 students (sec 51: 28 · sec 52: 27), a `Section` column, `sections:` in config, `Sec` in the attendance xlsx, and all
240 Python tests pass. What went wrong is in how it reaches you:

1. **The name still says Astro51 / SEC_51.** D3 chose "never rename". That was the wrong call for a course with
   no exam links yet.
2. **The All view mixes the sections.** Rows are sorted by Student ID alone (`data_loader.py:324`, `grader.py:716`,
   `:1036`), so 68161301 (51) is next to 68161302 (52). A colour marker isn't enough to separate them.
3. **The phone had no chips and no sec 52.** grade_web hasn't been `clasp push`ed since the sections commits, and
   the Drive copy you used at the 13:30 sec-52 class was pushed at 11:05, before sec 52 was added (15:18). It was
   re-pushed at 15:35. Nothing reminded you to push after adding a section.
4. **On the phone, attendance mixed both sections.** This follows from 3, and the app also has no idea which
   section is meeting right now.

### Decisions (revision-2 interview)

| # | Decision |
|---|---|
| R1 | **Keep one folder per course** (D1 stands: shared exams, weights, boundaries, session columns). |
| R2 | **Rename on `update -i`.** When the folder's `_SEC_` part doesn't match the roster's sections (adding sec 52, or the Astro course as it is now), `grader update -i <file>` asks `Rename 2026_S2_Astro51_SEC_51 → 2026_S2_Astro_SEC_51-52? [y/N]`. Replaces D3. |
| R3 | **The rename covers history.** Snapshot files and `log.jsonl` paths are renamed too, and the rename is a logged change, so `grader undo` works across it and can undo it. |
| R4 | **Ask to push.** After a section is added or the course renamed, if a Drive copy exists: `Web copy has 28 students, the course has 55. Push now? [y/N]` (the same as `grader web-push`). |
| R5 | **The All view groups the sections.** In grade-tui, grade_web and `grader dashboard`, rows are sorted by section, then ID, and each block starts with a header line `── Sec 51 · 28 students ──`. Colours stay as a second cue. Replaces D4's "colour only". |
| R6 | **Score CSVs stay as they are.** No sort change and no new column (homework/midterm/final/attendance csv, roster). |
| R7 | **The phone opens on the section meeting now.** grade_web's chip defaults to the section whose `sections[N].class_schedule` covers the current time (30 min before start until the end). Outside class times it uses the last choice for that course, else All. |

### Behaviour

### Rename (`grader.py`, new `src/rename.py`)
- **Target name:** `<term>_<abbr>_SEC_<secs joined by ->`. `abbr` is the current folder's abbreviation with a
  trailing section number stripped (`Astro51` → `Astro`). It is offered only when the folder matches
  `<term>_<abbr>_SEC_<…>` and the `_SEC_` part differs from `'-'.join(sections)`. Folders of the old style
  (`…_grading`) and one-section courses that already match are never offered.
- **Refuses** (and renames nothing) when the target exists, or when the Drive copy has web edits not pulled
  (`webpull` already detects this: it says to run `grader web-pull` first).
- **What moves:** the folder; every file whose name starts with the old prefix in `course_info/`, `data/` and
  `reports/` (`.bak` files included); the same files inside each `history/<id>/` snapshot; the `files` paths in
  `history/log.jsonl`; and any path inside `history/attendance_sync.json` and `config_sync.json`. The rename is
  logged as `{"action": "rename", "from": old, "to": new}`.
- **Drive copy:** `grade_courses/<semester>/<old>` is renamed to `<new>` in place, so Drive keeps its file IDs.
  The push (R4) then rewrites its contents with the new prefix and removes old-prefix files. `course.json` gains
  `renamed_from: [old]`, and grade_web's `migrateKeys` (`client_state.html:150`) moves drafts and remembered
  choices from the old key to the new one.
- **`grader undo`** of a rename renames everything back, Drive copy included, under the same refusal rules.
- **After a rename** grader prints `📁 Renamed → 2026_S2_Astro_SEC_51-52 — cd ../2026_S2_Astro_SEC_51-52`
  (your shell is still in the old path), plus `If an exam links this course (grading_dir:), run exam submit link
  again`. No exam links Astro today.
- **Prompt order** in `update -i`: `Add section 52 (27 students)…? [y/N]` → `Rename …? [y/N]` → `Push now? [y/N]`.
  `-y` answers yes to all three. Without a terminal and without `-y`, grader refuses with the `-y` hint, as today.
  `init -i a -i b` already names the folder `…_SEC_51-52` and is unchanged.

### Grouping (R5)
- **Shared order:** a `src/sections.py:group_order(secmap)` key (section in numeric order, blank last, then ID),
  used by everything that lists students in the All view. Exports' combined file uses it too. Single-section
  courses keep today's order and bytes.
- **grade-tui** (`rust_tui/src/app.rs`, `ui.rs`): `section_view()` in All reorders the rows by section, then ID,
  renumbering `raw_index` as `only_section` already does. The renderer inserts one header row before each block on
  Summary, Raw Details, For Submission and the attendance grid. Header rows are not selectable: j/k and paging skip
  them, scroll accounts for them, and Fill/edits never see them. One section selected (`n`) = no header rows.
- **grade_web** (`client_views.html` `renderTable`, attendance grid): same blocks, with
  `<tr class="sec-head">` rows. "Sort: Lowest %" sorts within each block. Search results keep their blocks.
- **`grader dashboard`** (`src/dashboard.py`): in "all", the table prints a rule row per section.

### Phone default section (R7)
- `webpush.course_json` gains `sections: {"51": {"day": "ศ.", "time": "08:30-12:30"}, …}` from config.
- grade_web's `pickSection(course, now, remembered)` parses Thai day abbreviations (`จ. อ. พ. พฤ. ศ. ส. อา.`) and the
  `HH:MM-HH:MM` range in the browser's local time (Asia/Bangkok). A chip tapped by hand sticks until you leave the
  course. An unparsable schedule is skipped, never an error.

### Push prompt (R4)
- Shown only when a Drive copy of this course exists (`webdrive.copy_paths`) and Drive for Desktop is present.
  It compares the copy's student count with the roster. On y it runs the same code as `grader web-push`.

### How you'll use it (the user guide that goes into MANUAL.md)
1. **New multi-section course:** `grader init -i repclasslist_Astro51.xls -i repclasslist_Astro52.xls` →
   `2026_S2_Astro_SEC_51-52/`.
2. **Add a section later, or fix your Astro course now:** inside the course folder run
   `grader update -i ../repclasslist_Astro52.xls`, answer y to rename and to push, then `cd` to the new name.
3. **Scores:** CSVs as before, one file per category for all 55 students. The exam tools (`exam submit scores`) fill
   them by Student ID, whatever the section.
4. **Attendance:** one sheet, shared sessions a1…a15 (both sections meet Fridays). On the phone, the chip opens on the
   section in class. In grade-tui, press `n` to show one section.
5. **Grades:** grade-tui's All view shows both blocks. `n` → 51 for sec 51 alone, with its own stats and distribution.
   `e` exports the combined file plus `_sec51` / `_sec52` files for submitting each section to the registrar.
6. **Undo:** `grader history` / `grader undo` as before, the rename included.
7. **Deploy the web part once:** `cd web && clasp push` (you do this).

### Files
`grader.py` (update flow and prompts), `src/rename.py` (new), `src/sections.py` (`group_order`, target name),
`src/history.py` (rename entries, undo), `src/webdrive.py`/`src/webpush.py` (Drive rename, `sections`,
`renamed_from`, removing stale files), `src/dashboard.py`, `src/tui_api.py` (grouped order for All),
`rust_tui/src/{app,ui}.rs`, `web/apps_script/{client_state,client_views,style}.html`, `MANUAL.md`, `SPEC_sections.md`.

### Out of scope
- Any change to score CSVs or the roster file (R6).
- Per-section weights, boundaries, columns or session dates. One attendance sheet per section.
- Finding and rewriting exam_projects `grading_dir:` links (grader only prints the note).
- `clasp push`, and running the rename on the real `~/cmru/teachings` course: you do both. I only work on scratch
  copies.

### Tests
- `tests/test_rename.py` (new): target-name rules (Astro51 → Astro; matching names not offered; `_grading` not
  offered); every prefixed file moved, `.bak` and history snapshots included; `log.jsonl` paths rewritten; undo of
  an earlier score change after the rename restores the right new-named file; undo of the rename itself; refusal
  when the target exists or the Drive copy has unpulled edits; prompt order with y / N / `-y` / no tty; Drive copy
  renamed with no old-prefix files left after the push.
- `tests/test_sections.py`: `group_order`; combined export grouped; single-section export byte-identical.
- `tests/test_web_push.py`: `sections` and `renamed_from` in course.json; the push prompt's count line.
- Rust (`cargo test`): header rows in the All view, the cursor skipping them, Fill touching students only, no
  headers with a section selected or in a one-section course.
- Web (`node --test 'web/tests/*.test.js'`): `pickSection` (in class / 30 min before / outside / bad schedule /
  manual pick sticks); grouped table and grid; Lowest % within blocks; `migrateKeys` follows `renamed_from`.
  Goldens unchanged for one-section courses.

### End-to-end verification (scratchpad only)
1. All three suites pass: `python -m pytest tests/`, `cd rust_tui && cargo test`, `web/scripts/e2e.sh`.
2. Copy the real `2026_S2_Astro51_SEC_51/` and both class lists into a scratch term folder, with
   `--drive-root <scratch>/drive` holding a pushed copy. Inside the course run
   `grader update -i ../repclasslist_Astro52.xls`. You get no add question (52 is known), then the rename question:
   y, then the push question: y. Check `2026_S2_Astro_SEC_51-52/` with every file renamed, history snapshots
   renamed, the Drive copy renamed with only new-prefix files, and `course.json` holding `sections` and
   `renamed_from`.
3. `grader history` shows the rename. `grader undo` of the 15:29 score change restores the new-named homework
   csv. `grader undo <rename id>` brings back `2026_S2_Astro51_SEC_51` everywhere, and redoing it works.
4. `grade-tui` from the scratch folder: All shows `── Sec 51 · 28 students ──`, 28 rows, `── Sec 52 · 27 students ──`,
   27 rows, and j/k never lands on a header. `n` → 51 shows 28 rows and no headers. A bulk fill in All touches all
   55 rows. Export writes the combined (grouped) file plus `_sec51`/`_sec52`.
5. `node` check of `pickSection` with Fri 09:00 → 51, Fri 13:15 → 52, Mon → last/All.
6. After you `clasp push`: open the Astro copy on the phone during a class slot. It opens on that section, All shows
   two blocks, and the colours read well in light and dark.
