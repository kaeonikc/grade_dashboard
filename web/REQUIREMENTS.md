# Requirements: grade_web

Status: draft (Gate 1 pending)
Idea: "I want to create a new feature of grade_dashboard. I want to be able to open it via html and/or on my phone
linking the data files and config files via google drive. The grade-tui is now good, don't need to touch it. But this
new app will be able to edit, update the data, similar to the grade-tui, but it can do on my phone, and/or via html
feature. I will sync the data between on google drive and this machine manually myself."

## Users and context

**One user: the teacher** (course owner, the CMRU Workspace account). Students never
see or use the app.

| Where | Device | What they do | How often |
|---|---|---|---|
| In class | iPhone browser (mobile Safari), standing, one hand | Take attendance on an existing session column | Weekly during term |
| At home / office | Phone or Mac browser | Enter scores after each homework or exam, check totals and letter grades, adjust weights or grade boundaries | After each homework/exam; occasionally |
| At the Mac | Terminal (`grader`) | `grader web-push <course>` before going mobile; `grader web-pull <course>` to bring web edits back | Whenever the teacher chooses (manual, never scheduled) |

**Today:** the teacher edits courses only on the Mac with grade-tui (batch edits, Ctrl+S save, conflict check, Fill
Column, `w`/`b` for weights and boundaries) and the `grader` CLI. Attendance in class is not possible from the phone.

**Constraints decided in the interview** (recorded here so the architect does not reopen them):
- Runtime: a Google Apps Script web app, executed as the owner, access "Only myself". One URL works on phone and
  desktop. The Mac can be off while the web app is used. No offline mode in v1.
- Deploy with clasp from `grade_dashboard/web/`; paste-in deploy is the fallback.
- Data lives in `My Drive/grade_web/<course>/`, reached on the Mac through Drive for Desktop at
  `~/Library/CloudStorage/GoogleDrive-<the CMRU Workspace account>/My Drive/`.
- Sync model: edit journal on Drive + merge on the Mac. Phone-to-Mac must never lose work.
- Code home: `grade_dashboard/web/` on branch `web-app`. `web-push`/`web-pull` are new `grader` subcommands with
  pytest tests. grade-tui (`rust_tui/`) is not modified, and its behaviour and tests stay unchanged.
- Grade math in the browser must equal grade-tui's, proven by golden parity tests (Python writes expected JSON from
  fixture courses; `node --test` must match every student).
- Browser-side drafts of unsaved edits are mirrored to localStorage; saves are serialized on the server
  (LockService).
- Grades are shown weighted only (no raw-percentage toggle).

**Size and speed targets:** up to 300 students and 80 counted columns per course. On phone 4G, a course opens within
8 s and a 60-cell save completes within 5 s.

**Account risk and the spike:** the CMRU Workspace admin may block web-app deployment or the Apps Script API. Build
task 1 is a spike: a minimal "hello" Apps Script web app deployed on the CMRU account and opened on the phone. If it
is blocked, work stops and the lead asks the user (personal account or CMRU IT). Never switch accounts
automatically.

## UI language

| Audience | Language |
|---|---|
| Teacher, web app (labels, buttons, messages, errors) | English, matching grade-tui and `grader` |
| Teacher, `grader web-push` / `web-pull` terminal output | English |
| Data shown in the app | Exactly as written in the files: student names (usually Thai, e.g. `นายสมมติ ทดสอบ`), column headers (`hw1 (10pts)`, `13 Jan 2027`), course name, the absent mark `ขส` (ขาดสอบ) |
| Students | Not an audience |

Numbers use `.` as the decimal separator. Thai UI is backlog.

## Stories and acceptance criteria

Fixture used in every example (fake data, data-safety §1): course folder `9_ฟิสิกส์จำลอง_grading`, file prefix
`9_ฟิสิกส์จำลอง`, weights attendance 0.1 / homework 0.2 / midterm 0.3 / final 0.4, `drop_lowest_homework: true`,
boundaries A 80, B+ 75, B 70, C+ 65, C 60, D+ 55, D 50. Students:

```
Student ID,Name,Class Group
9900000001,นายสมมติ ทดสอบ,SEC1
9900000002,นางสาวตัวอย่าง ใจดี,SEC1
9900000003,นายทดลอง มีชื่อ,SEC2
```

"Drive root" below means the `My Drive` folder. Every test points it at a temporary folder (see S1.8).

**`<course>` argument** (web-push and web-pull): a course folder path, like `grader --course DIR`. When omitted and the
current folder is a course folder (has `course_info/`), the current folder is used.

### S0. As the teacher, I first see a minimal web app open on my phone from the CMRU account, so that we know the platform works before building on it
1. Given a minimal "hello" Apps Script web app deployed from the CMRU account with "Execute as: me" and "Only myself",
   when the teacher opens its URL on the iPhone, then the page shows "hello" (no student data involved).
2. Given deployment or opening is blocked by the Workspace admin, then work stops and the lead asks the user whether to
   use a personal account or contact CMRU IT. No other account is used without the user's answer.

### S1. As the teacher, I run `grader web-push <course>` on the Mac, so that the web app has a fresh copy of the course on Drive
1. Given the fixture course and an empty Drive root, when `grader web-push` runs, then
   `<Drive root>/grade_web/9_ฟิสิกส์จำลอง_grading/` contains: the course config, the roster
   (`course_info/9_ฟิสิกส์จำลอง_student_info.csv`), every `data/*.csv` (score files and the attendance csv), an empty
   edit journal `web_edits.jsonl`, and a push record holding at least course_id, course_name, term, the Mac folder
   name and the push time. No `.xlsx`, `history/` or `reports/` content is copied.
2. Given any course, when `grader web-push` runs, then every file in the Mac course folder has the same SHA-256
   before and after (web-push never writes into the Mac course folder, including the attendance auto-sync that
   loading a course normally triggers).
3. Given the Drive journal holds 3 unpulled lines, when `grader web-push` runs without `--force`, then it exits
   non-zero, prints the 3 edits (student ID, column, old → new value, time), and nothing on Drive changes.
4. Given the same 3 unpulled lines, when `grader web-push --force` runs, then the 3 lines are kept as a file in
   `grade_web/9_ฟิสิกส์จำลอง_grading/archive/`, marked as discarded and named in the output (never silently deleted),
   and the push proceeds.
5. Given the attendance xlsx and csv on the Mac need a decision from `grader sync` (for example `9900000002` /
   `20 Jan 2027` is `P` in the xlsx and `A` in the csv, both changed since the last sync), when `grader web-push`
   runs, then it refuses and prints "run `grader sync` first"; nothing on Drive changes.
6. Given a data CSV that is not valid UTF-8, when `grader web-push` runs, then it refuses, naming the file.
7. Given an earlier push that included `data/9_ฟิสิกส์จำลอง_quiz.csv` and the Mac course no longer has that file, when
   `grader web-push` runs with an empty journal, then the Drive course folder ends up holding exactly the newly pushed
   set (the stale quiz file is gone from it; `archive/` is kept).
8. Given the Drive root option or environment override is set to a temporary folder, when the pytest suite runs, then
   nothing is read from or written to `~/Library/CloudStorage/...` or `~/cmru/teachings`.
9. Given the Drive root folder does not exist (Drive for Desktop not running), when `grader web-push` runs, then it
   exits non-zero naming the missing path and writes nothing.
10. Given the course has a score file stored as `.xlsx` (for example `data/9_ฟิสิกส์จำลอง_quiz.xlsx`; the attendance
    xlsx doesn't count), when `grader web-push` runs, then it refuses, naming each such file, and nothing on Drive
    changes.
11. Given the current folder is `9_ฟิสิกส์จำลอง_grading/`, when `grader web-push` runs with no `<course>`, then that
    course is pushed; given the current folder is not a course folder and no `<course>` is given, it exits non-zero
    with a usage message.

### S2. As the teacher, I open the one web-app URL on my phone or Mac and pick a course, so that I can work on it anywhere
1. Given two pushed courses, when the teacher opens the URL signed in with the CMRU account, then a course list shows
   both, each with course name, term, push time, and the number of edits not yet pulled with the time of the last
   save (e.g. "4 edits not pulled · last saved 20 Jan 09:15").
2. Given a browser signed in with a different Google account, or signed out, when the URL is opened, then no course
   name, student name, ID or score is shown.
3. Given one Drive course folder lacks its config, when the course list loads, then that course is shown as
   unavailable with the reason, and the other course still opens.
4. Given a course is opened, then the screen shows its push time so the teacher can see how fresh the data is.
5. Given a course of 300 students and 80 counted columns on phone 4G, when the teacher opens it, then it is usable
   within 8 s.

### S3. As the teacher, I pick one column and enter a score per student with Next, so that I can enter a homework set on my phone quickly ("column mode")
1. Given the fixture opened on a phone, then the first screen after choosing the course is column mode: the teacher
   picks a column from those that count (the `data_mapping` columns, grouped by category, plus the attendance session
   columns). `total (…pts)` columns are never offered.
2. Given column `hw2 (10pts)` is chosen, then each student is listed in grade-tui's Raw Details order with ID, name as
   written (`นายสมมติ ทดสอบ`), current value, and one input that opens a numeric keypad with a decimal point.
3. Given the input of `9900000001` holds blank, when the teacher types `9` and taps Next, then focus moves to
   `9900000002`'s input, `9900000001`'s cell shows `9` marked `*` (unsaved), and a badge reads "1 unsaved".
4. Given the focus is on a student, when the teacher taps the `ขส` control, then the cell becomes `ขส` (unsaved) and
   focus moves to the next student; a Clear control sets the cell to blank (unsaved).
5. Given `hw2 (10pts)`, when the teacher types `12`, then it is accepted as an unsaved edit, drawn red, and counted as
   "above max" in the Save summary.
6. Given `9900000001` has an unsaved `9` whose saved value is blank, when the teacher clears it back to blank, then
   the cell is no longer unsaved and the badge count drops by one.
7. Typed values are checked at the cell. Allowed: a number ≥ 0 using `.` for decimals (`9`, `8.5`, `0`), blank, and
   `ขส`. Given the teacher types `8,5`, then the input is refused with "use . for decimals"; given `-3`, it is refused
   with a message that scores can't be negative; given other text (`abc`, `ข ส`, `12a`), it is refused with a message
   listing what is allowed. In each refused case the cell keeps its previous value, no unsaved edit is created, and
   focus stays on the cell. (This replaces the interview's "invalid text accepted and flagged red"; only an
   above-max score is accepted and flagged.)
8. Given column mode on `hw2`, when the teacher types `0002` into the search box, then only `9900000002` is listed;
   when the teacher types `ใจดี`, then only `นางสาวตัวอย่าง ใจดี` is listed. Next moves through the filtered list.
   Clearing the search shows all students again; unsaved edits are kept throughout.

### S4. As the teacher, I tap a student to see their full row, totals and letter grade updating as I type, and edit there too, so that I see the effect of a score before saving
1. Given `9900000001` has attendance `P, P, L` (3 sessions), hw1 `8`, hw2 `9`, hw3 blank, midterm_exam (30pts) `21`,
   final_exam (40pts) blank, when the student is tapped, then the detail shows attendance 9.33, homework 17
   (lowest dropped), Coursework Total 27, midterm 21, final 0, Final Score 48, Grade F, exactly as grade-tui shows for
   the same files.
2. Given the same student, when the teacher types `28` into final_exam in the detail (not yet saved), then the detail
   shows final 28, Final Score 76, Grade B+ immediately; the edit is an unsaved edit like any other. Totals and grades
   everywhere in the app (column mode, detail, wide table) are computed from saved values plus unsaved edits.
3. Given a file cell holds `ขส`, then the detail shows `ขส` (not `0`) and counts it as 0; given a file cell already
   holds `abs` (written by hand on the Mac), it is shown as `abs`, drawn red, and counted as 0. Typing new values in
   the detail follows S3.7.

### S5. As the teacher on a wide screen, I see and edit the whole course as a table, so that I can review everything at once
1. Given the fixture opened in a Mac browser window wide enough for the table, then one table shows every student
   with every counted column, each category's weighted percentage, Coursework Total, Final Score and Grade.
2. Given unsaved edits, over-max values or invalid text already in the files, then they are marked the same way as in
   column mode.
3. Given the window is narrowed to phone width, then the app shows column mode instead.
4. Given the table, when the teacher edits a score cell or an attendance cell, then it becomes an unsaved edit with the
   same validation (S3.7), attendance codes (S6) and live totals (S4.2) as column mode; `total` columns and computed
   columns are not editable.

### S6. As the teacher in class, I tap P / L / A / X per student on today's session column, so that I take attendance without the Mac
1. Given the attendance csv has session column `20 Jan 2027` and today is 20 Jan 2027, when the teacher opens
   attendance, then `20 Jan 2027` is preselected; given no session column is dated today, the teacher picks one.
2. Given `20 Jan 2027` (all blank), when the teacher taps `P` for `9900000001` and `A` for `9900000002`, then both
   cells show the code marked `*` and focus moves to the next student after each tap.
3. Given an existing cell holds `EA`, then it is shown as `EA` and kept unless the teacher taps another code.
4. Given any attendance screen, then there is no way to add, rename or remove a session column.
5. Given the 2 codes above are saved, then the Drive attendance csv holds `P` and `A` in `20 Jan 2027` for those two
   students, the journal gains 2 lines, and the attendance part of each student's total is recomputed with
   P = 1, L = 0.8, X = 1, EA = 1, A = 0.
6. Given the teacher uses Fill on `20 Jan 2027` with `P` (whole column), then taps `A` for one absentee, then 3
   unsaved cells exist (2 `P`, 1 `A`) before Save.
7. Given any attendance edit, then the web app never reads or writes the attendance `.xlsx`.

### S7. As the teacher, I fill a whole column or only its empty cells with one value, so that I can give everyone full marks or zero the missing ones fast
1. Given `hw2 (10pts)` holds `9`, blank, blank, when the teacher chooses Fill, "Only empty cells", value `0`, then the
   dialog reads "2 cells will change" and, on confirm, `9900000002` and `9900000003` get unsaved `0`.
2. Given the same column, when the teacher fills the whole column with `10`, then 3 cells change (a cell already equal
   to the value is not counted).
3. Given `9900000002` has an unsaved `7` in hw2, when "Only empty cells" is used, then that cell counts as filled and
   is not changed.
4. Given a fill, then nothing is written to Drive until Save; the fill value passes the same validation as typed
   values (S3.7: `8,5`, `-1`, `abc` refused); on an attendance column the choices are P, L, A, X and Clear.
5. Given the result of N cells to change is 0, then confirming does nothing.

### S8. As the teacher, I save all unsaved edits at once with a conflict check, and never lose them to a crash or a bad network, so that the data on Drive stays right
1. Given 3 unsaved cells in two files (hw2 ×2 in homework.csv, midterm_exam ×1 in midterm.csv), when the teacher taps
   Save, then both Drive CSVs hold the new values, the journal gains 3 lines sharing one batch id, the app reads
   "Saved 3 cells (2 files)", the unsaved marks and the localStorage draft clear.
2. Given the phone loaded hw2 of `9900000001` as blank, and the Mac browser then saved hw2 = `7` for that student,
   when the phone saves hw2 = `9`, then Drive keeps `7`, the phone reads "Saved 0 cells · 1 changed elsewhere, not
   saved: 9900000001 hw2 (now 7)", the cell stays unsaved with its starting value updated to `7`, and a second Save
   writes `9` on purpose.
3. Given the network is off, when Save is tapped, then the app shows the failure, keeps every edit unsaved, and offers
   Retry; when the network returns and Retry is tapped, each cell is saved exactly once (no duplicate effect on
   Drive values).
4. Given 5 unsaved edits and the browser tab is killed, when the teacher reopens the course on the same device, then a
   banner reads "5 unsaved edits restored (from 20 Jan 09:12)" and the 5 cells show as unsaved. A draft is always
   offered, whatever its age, and the banner shows when it was made (e.g. "from 3 days ago").
5. Given the phone and the Mac browser save at the same moment, then the saves run one after the other, and each
   cell's conflict check sees the other save's result.
6. Given a save, then every Drive CSV cell the save did not target stays byte-identical, and the file's BOM (if any)
   and line endings are kept.
7. Given unsaved edits, when the teacher leaves the page or switches course, then the app warns where the browser
   allows it, and the draft remains restorable.
8. Given the browser refuses storage (e.g. a private window that blocks it), then the app shows a persistent warning
   that unsaved edits will not survive closing the tab.
9. Given 60 unsaved cells on phone 4G, when the teacher taps Save, then the result is shown within 5 s.
10. Given unsaved edits, when the teacher chooses "Discard all unsaved edits" and confirms, then every unsaved mark and
    the draft clear and nothing is written to Drive.

### S9. As the teacher, I tap "Undo last save" on the web, so that I can take back a mistaken save before pulling
1. Given the last batch set hw2 of `9900000001` blank → `9` and `9900000002` blank → `8`, when the teacher taps Undo
   last save, then a confirmation names the batch ("Undo save of 20 Jan 09:15, 2 cells?"); on confirm, Drive holds
   blank in both cells and the journal gains 2 inverse lines in a new batch that records which batch it undoes.
2. Given one of those cells was changed by the other device to `7` after that save, then that cell is not reverted
   and is listed as a conflict; the other cell is reverted.
3. Given the journal was archived by `grader web-pull`, then Undo last save is unavailable and the app says "Already
   pulled to the Mac; use `grader undo` there".
4. Given there are unsaved edits, then Undo last save is unavailable until they are saved or discarded.
5. Given saves A (09:00) and B (09:15) in the current journal, when the teacher taps Undo last save twice, then the
   first press undoes B and the second undoes A (newest save not yet undone first; undo batches themselves are not
   offered for undo). Saves from an earlier, already pulled journal are never offered.

### S10. As the teacher, I edit category weights and grade boundaries on the web, so that I can try a grading scheme from my phone
1. Given weights homework 0.2 and final 0.4, when the teacher changes them to 0.25 and 0.35 and saves, then the Drive
   config holds the new weights, the journal gains one line of kind `config` with old and new values, and every
   student's total and grade is recomputed.
2. Given the weights add up to 1.05, then the app shows "weights sum to 1.05" as a warning and still allows saving
   (as grade-tui does).
3. Given a weight or boundary that is not a number (`0.2x`), then that save is refused with a message naming the field.
4. Given boundary A changes from 80 to 78, then the stored boundaries remain ordered highest first; the set of letters
   and the set of categories cannot be changed on the web.
5. Given the other device saved new weights after this device loaded them, when this device saves, then the save is
   refused, the current Drive values are shown, and nothing is overwritten.

### S11. As the teacher, I run `grader web-pull <course>` on the Mac, so that every web edit lands in the real course files safely and undoably
1. Given the Drive journal holds 4 lines, when `grader web-pull` runs without `--yes`, then it prints the journal's line
   count and last save time, a summary per column, each change as `ID column: Mac value → web value`, and every
   conflict or skipped line; it writes nothing and exits 0. Without a TTY and without `--yes` it does the same.
2. Given the same journal, when `grader web-pull --yes` runs, then the Mac CSVs hold the web values, each touched score
   file's `total` column follows the total rule in INTEGRATION.md, and `grader history` shows one new entry labelled as
   a web pull covering every file the pull changed.
3. Given a pull was applied, when the teacher runs `grader undo` once (no ID), then every file the pull changed is back
   to its pre-pull bytes (including the attendance xlsx and the config, if they changed).
4. Given hw2 of `9900000001` was blank at push, the web set it to `9`, and grade-tui on the Mac set it to `7` after the
   push, when the pull is applied, then the Mac keeps `7` and the output lists "conflict: 9900000001 hw2 — Mac 7, web 9
   (not applied)".
5. Given a journal line for student `9900000099` (not in the Mac files) or for column `hw9` (not in any Mac file), then
   the line is listed as skipped with the reason, and the other lines apply.
6. Given the journal sets hw2 of `9900000001` blank → `9` in one batch and `9` → `8` in a later batch, then the pull
   treats it as one change, blank → `8`, checked against the push-time value (blank).
7. Given a journal line whose web value already equals the Mac value (for example a duplicate line from a retried
   save), then it is reported as "already applied", not as a conflict.
8. Given attendance lines for `20 Jan 2027`, when the pull is applied, then both the Mac attendance csv and the
   attendance xlsx hold the codes, and the xlsx keeps its formulas, dropdown and colour rules.
9. Given a pull was applied, then the applied journal lines (with the pull's conflicts and skips recorded) are written
   to `grade_web/<course>/archive/web_edits_<YYYYMMDD-HHMMSS>.jsonl` on Drive and copied into the pull's Mac history
   entry, and the Drive journal no longer holds them; a line appended on Drive after web-pull read the journal stays
   for the next pull.
10. Given a pull was applied, when `grader web-pull --yes` runs again, then it reports "Nothing to pull" and creates no
    history entry.
11. Given a `config` line changing weights from the pushed `{homework: 0.2, final: 0.4, …}` to
    `{homework: 0.25, final: 0.35, …}`, and the Mac weights still equal the pushed values, when the pull is applied,
    then the Mac config's weights equal the web values and every other config key keeps its value (YAML comments and
    quoting may change, as with grade-tui's `w`/`b`).
12. Given the same `config` line, but the Mac weights were changed after the push (e.g. homework 0.15 on the Mac),
    when the pull is applied, then the Mac weights are kept unchanged and the output lists the phone's values as a
    conflict ("conflict: weights — Mac {…homework 0.15…}, web {…homework 0.25…}; apply by hand if wanted"). The same
    rule applies to grade boundaries.
13. Given the journal's line 3 is not valid JSON (for example truncated), then web-pull lists the bad line numbers,
    applies nothing and archives nothing.
14. Given the Drive push record names course_id `MOCK` / term `2027_S1` but the Mac course is `PHYS1120` / `2027_S2`,
    then web-pull refuses.
15. Given the attendance xlsx is open in Excel (`~$` lock file present), or the attendance pair needs `grader sync`,
    and the journal holds attendance lines, then web-pull `--yes` refuses the whole pull with the reason; the preview
    still works.
16. Given the current folder is a course folder and no `<course>` is given, then that course is used (as in S1.11).

### S12. As the teacher, I trust that the web shows the same totals and letter grades as grade-tui, so that I never see two different grades for one student
1. Given each fixture course, when the Python side writes the expected values per student (each category's weighted
   percentage, Coursework Total, Final Score, Grade) from what grade-tui shows for that course, and `node --test` runs
   the web's grade math on the same files, then every value for every student matches exactly.
2. The fixture set covers at least: `drop_lowest_homework` on and off; `total_pts`; `pts_each` and the built-in `lab`
   default with bare headers; header points overriding config points; a column with no points anywhere (the
   weight-derived default grade-tui applies, else 100); attendance columns auto-detected when `data_mapping` has no
   `attendance`; codes P/L/A/X/EA and blank; `ขส`; invalid text already in a file (`abs`, `ข ส`, `12a`); a score above
   max; values whose weighted percentage lands exactly on `x.xx5` (rounding) and just above a whole number (ceiling);
   a final score exactly on a boundary (80 → A) and one point below (79 → B+); weights that do not sum to 1.0; a
   category with weight but no columns.
3. Given the score-cell table and the total-rule table in INTEGRATION.md, then the web's cell classification passes
   both tables (needed for cells already in the files, even though typed invalid input is refused).

### S13. As the teacher, I deploy the web app with a few documented commands, so that I get one URL that only I can open
1. Given a clean Mac with Node, when the teacher follows the README (install clasp, `clasp login` with the CMRU
   account, push, deploy from `web/`), then one web-app URL exists, configured "Execute as: me" and "Who has access:
   Only myself".
2. Given clasp or the Apps Script API is blocked by the Workspace admin (but web apps are allowed, per S0), then the
   README's paste-in procedure produces the same web app.
3. Given the repo, then it contains no student data (fixtures only, IDs starting `99`), no OAuth tokens, no
   `.clasp.json`, and no Drive file or folder IDs of real data.

## Inputs

| Input | Format | Encoding | Example (fake) | Notes |
|---|---|---|---|---|
| Mac course folder (web-push, web-pull) | Folder `<term>_<name>[_SEC_<n>]_grading/` with `course_info/`, `data/`, `history/` | — | `9_ฟิสิกส์จำลอง_grading/` | `<course>` = folder path; default the current folder when it is a course folder. Owned by grade_dashboard; layout per INTEGRATION.md |
| Course config | YAML `course_info/<prefix>_config.yaml` | UTF-8 | `weights: {attendance: 0.1, homework: 0.2, midterm: 0.3, final: 0.4}` | Keys used: `course_id`, `course_name`, `term`, `weights`, `data_mapping` (lists, `pts_each` dicts, per-column points, `total_pts`), `grade_boundaries`, `rules.drop_lowest_homework`, `term_start_date`, `class_schedule` |
| Roster | CSV `course_info/<prefix>_student_info.csv`, header `Student ID,Name,Class Group` | UTF-8, BOM optional | `9900000001,นายสมมติ ทดสอบ,SEC1` | Read-only everywhere in this app |
| Score file | CSV `data/<prefix>_<category>.csv` | UTF-8, BOM optional, LF or CRLF | header `Student ID,Name,hw1 (10pts),hw2 (10pts),hw3 (10pts),total (30pts)`; row `9900000001,นายสมมติ ทดสอบ,8,9,,17` | Headers may be bare at the category default (`4`). Cells: number, blank, `ขส`, or other text (invalid, from hand edits). Names may contain spaces, commas or quotes (quoted CSV fields). `.xlsx` score files: web-push refuses the course |
| Attendance file | CSV `data/<prefix>_attendance.csv` (+ `.xlsx` on the Mac only) | UTF-8 | header `Student ID,Name,13 Jan 2027,20 Jan 2027,…,total (15pts)`; row `9900000001,นายสมมติ ทดสอบ,P,,…,1` | Session columns are dated (`13 Jan 2027`) or placeholders `a1…aN`. Codes P, L, A, X, EA, blank |
| Drive course folder (web app, web-pull) | `My Drive/grade_web/<course folder name>/` | — | see Outputs | Written by web-push, edited by the web app |
| Edit journal (web-pull) | JSON Lines `web_edits.jsonl`, one object per line | UTF-8, no BOM | see "Journal line format" | Appended by the web app only |
| Teacher input on the web | Typed score text, taps on P/L/A/X/`ขส`/Clear, fill value, search text, weight and boundary numbers | — | `8.5`, `ขส`, `P`, `0002`, `0.25` | Scores: number ≥ 0 with `.`, blank or `ขส`; everything else refused (S3.7). Weights/boundaries: numbers (S10.3) |
| Browser draft | localStorage, per course, per device | — | unsaved edits `{student_id, column, value, original}` plus the time made | Holds unsaved edits only; no names |

### Journal line format

One line per changed cell, one line per config change. Required fields (extra fields are allowed; exact batch-id
and file layout are the architect's choice):

```json
{"batch": "b-20270120-091502-a1", "ts": "2027-01-20T09:15:02+07:00", "kind": "cell",
 "student_id": "9900000001", "column": "20 Jan 2027", "value": "P", "original": ""}
{"batch": "b-20270120-093010-c4", "ts": "2027-01-20T09:30:10+07:00", "kind": "config", "part": "weights",
 "value": {"attendance": 0.1, "homework": 0.25, "midterm": 0.3, "final": 0.35},
 "original": {"attendance": 0.1, "homework": 0.2, "midterm": 0.3, "final": 0.4}}
```

- `student_id` is text (never a number), trimmed. `column` names the column so it still matches after a header's
  points suffix changes (`hw1 (10pts)` → `hw1 (15pts)`).
- `original` is the Drive value the edit started from; `value` is the new cell text (`""` for blank, `ขส` for
  absent).
- An undo batch carries the id of the batch it reverses.
- `part` is `weights` or `grade_boundaries`.
- `ts` comes from the server clock, ISO 8601 with offset.

## Outputs

| Output | Format | Location | Overwrites? | Example |
|---|---|---|---|---|
| Drive course mirror | config, roster CSV, `data/*.csv`, push record | `My Drive/grade_web/<course>/` | Yes, by web-push: the folder ends up holding exactly the pushed set (plus `archive/`). Refused while unpulled journal lines exist (unless `--force`) | `grade_web/9_ฟิสิกส์จำลอง_grading/data/9_ฟิสิกส์จำลอง_homework.csv` |
| Edited Drive CSVs | Same CSV, only target cells changed | Drive course mirror | In place, by each web Save / Undo; untouched cells, BOM and line endings kept | hw2 cell of `9900000001`: `` → `9` |
| Edited Drive config | Same keys, only `weights` or `grade_boundaries` changed | Drive course mirror | In place, by a web config save | `homework: 0.25` |
| Edit journal | JSON Lines | `My Drive/grade_web/<course>/web_edits.jsonl` | Append-only by the web app; applied lines archived by web-pull | see Journal line format |
| Journal archive | JSON Lines, with the pull's conflicts and skips recorded | Drive `grade_web/<course>/archive/web_edits_<YYYYMMDD-HHMMSS>.jsonl`, plus a copy in the pull's Mac history entry | Never overwritten; new file per pull | `archive/web_edits_20270121-180000.jsonl` |
| Discarded journal (`web-push --force`) | JSON Lines, marked discarded | Drive `grade_web/<course>/archive/` | Never overwritten; new file per forced push | `archive/web_edits_20270121-175500_discarded.jsonl` |
| Mac score and attendance CSVs | Same CSV | `<course>/data/` | In place, only by `web-pull --yes`; untouched cells byte-identical; totals recomputed | `9900000001` hw2 `` → `9`, `total (30pts)` `8` → `17` |
| Mac attendance xlsx | Same workbook | `<course>/data/<prefix>_attendance.xlsx` | Target cells only, by `web-pull --yes` (mirrored from the csv) | `20 Jan 2027` = `P` |
| Mac config | YAML | `<course>/course_info/<prefix>_config.yaml` | `weights` / `grade_boundaries` only, by `web-pull --yes`, and only when the Mac values still equal the pushed values; comments and quoting may change | `homework: 0.25` |
| History entry | Snapshot folder + one `log.jsonl` line (INTEGRATION.md "Writing a file"), holding the archived journal copy | `<course>/history/` | Never; new entry per pull | `20270121-180000_grader_web-pull/` |
| Terminal preview / report | Plain English text | stdout | — | `9900000001 hw2: (blank) → 9` / `conflict: 9900000001 hw2 — Mac 7, web 9 (not applied)` |
| Browser draft | localStorage | Phone / Mac browser | Replaced on every unsaved change; cleared after a successful Save or Discard | 5 unsaved edits |

## Data classification

| Field | Class (PII / grade / public) | Leaves the machine? |
|---|---|---|
| Student ID | PII | Yes: Drive (CMRU Workspace), the script's CacheService (Google side, ≤ 6 h), browser memory, journal, archives, localStorage drafts |
| Student name | PII | Yes: Drive, the script's CacheService and browser display/memory. Not in localStorage (drafts or the course list), not in the journal |
| Class Group | public (section code) | Yes: Drive |
| Score cells, `ขส`, attendance codes | grade | Yes: Drive, the script's CacheService, browser, journal, drafts |
| Computed category %, Coursework Total, Final Score, letter grade | grade | Computed in the browser; stored only as the `total` columns already in the files |
| Weights, grade boundaries, course id/name/term, schedule | public | Yes: Drive; course id/name/term also in the device's course list (`gw:courses`) |
| Teacher name in config | public (the user) | Yes: Drive |
| Journal lines and archives | PII + grade | Yes: Drive (and on the Mac after pull) |
| Apps Script execution logs | must hold no student names, IDs or scores | — |

No LLM is called anywhere, so data-safety §4 does not apply. Any later feature that sends data to an LLM must apply
§4 (pseudonymise names and IDs). Development and tests use fixtures only (IDs starting `99`), never
`~/cmru/teachings` and never the real Drive folder. The S0 spike uses no student data. Student data stays in the CMRU
account; moving it to any other account needs the user's explicit decision (S0.2). Note: the repo's existing mock
course uses IDs `6920xxxx`, which look like a real cohort prefix; this app's fixtures must use `99…` IDs instead.

## Edge cases

**Files and formats**
1. CSV with a UTF-8 BOM: `Student ID` is still found; the BOM is kept on every write (Drive and Mac).
2. CRLF line endings: kept on every write.
3. Non-UTF-8 file (e.g. saved as cp874 by Excel): web-push refuses, naming it (S1.6).
4. Names with spaces, commas or double quotes (`"นายสมมติ, ทดสอบ"`): round-trip byte-identical; shown as written.
5. Student IDs with leading zeros or 11 digits: always handled as text, compared trimmed; never shown in scientific
   notation.
6. Duplicate Student ID inside a data file: the web shows it once and a save sets every row with that ID (same as
   grade-tui's apply_edits); web-push prints a warning naming the duplicate.
7. Missing `Student ID` column in a data file, or no config: web-push refuses, naming the file.
8. Empty data file (header only) or empty roster: web-push refuses ("no students").
9. Columns in a file that are not in `data_mapping` (added by hand): not shown and never written, as in grade-tui.
10. `total (…pts)` columns: never editable on the web; the journal never holds total cells; web-pull's write
    recomputes Mac totals by the total rule.
11. Score files stored as `.xlsx` (not attendance): web-push refuses the course and names each file (S1.10).
12. Bare headers at the category default (`4`) and `name (Npts)` headers: both resolved to the same max points as
    grade-tui.
13. Comma decimal typed on the phone (`8,5`): refused with "use . for decimals" (S3.7), because grade-tui's cell rules
    would read it as 85.

**Sync and Drive for Desktop**
14. web-push while unpulled lines exist: refused; `--force` keeps them in `archive/` marked discarded (S1.3–4).
15. Drive for Desktop lag: the local Drive copy can be older than the cloud. No sequence of web save, web-push and
    web-pull may delete a journal line that was neither applied nor explicitly discarded with `--force`, even if the
    Mac's local copy is stale when the command runs. web-pull prints the journal's line count and last save time, and
    the web app shows the same two numbers, so the teacher can compare before applying.
16. Lines appended on Drive after web-pull read the journal: stay for the next pull (S11.9).
17. Drive conflict copies (`web_edits (1).jsonl`, `…_homework (1).csv`) or two files with the same name in a Drive
    course folder: the web app refuses to open that course and names the files; web-pull refuses until resolved.
18. Drive root missing (Drive for Desktop off or signed out): web-push and web-pull exit non-zero naming the path.
19. Drive files online-only (streamed): reading them must still work; a read failure is reported, not treated as an
    empty journal.
20. Drive course folder pushed from a different course (folder renamed, or same name reused): web-pull checks the push
    record's course_id and term against the Mac course and refuses on mismatch (S11.14).
21. Drive copy edited outside the web app (opened in Google Sheets, edited by hand): those edits are not pulled (only
    the journal is) and the next web-push replaces them. The README states this.

**Merging on the Mac**
22. Cell changed on the Mac since the push: Mac value kept, listed as conflict with both values (S11.4).
23. Cell changed on the Mac to the same value the web set: "already applied", not a conflict.
24. Same cell edited several times on the web: one net change, checked against the push-time value (S11.6); a cell
    edited and then edited back nets to no change and is reported as such.
25. Student removed from the Mac roster/files, or column removed or renamed on the Mac: listed and skipped (S11.5).
26. Column's header points changed on the Mac (`hw1 (10pts)` → `hw1 (15pts)`): the line still applies to `hw1`.
27. New students added on the Mac after the push: untouched by the pull; the next push includes them.
28. web-pull run twice, or after a crash between applying and archiving: idempotent; the second run finds every value
    already applied, writes nothing, then archives (S11.10).
29. Truncated or invalid journal line: nothing applied, nothing archived, line numbers printed (S11.13).
30. Attendance xlsx open in Excel, or the attendance pair needs `grader sync`: `--yes` refuses the whole pull
    (S11.15). The pull must not leave the xlsx and csv disagreeing.
31. After a pull, a plain `grader undo` must revert the pull, not an automatic follow-up entry (attendance baseline or
    total refresh) written by the same pull (S11.3).
32. Config changed on the Mac since the push: the Mac wins; the phone's values are listed as a conflict to apply by
    hand (S11.12). Config unchanged on the Mac: the phone's values are applied (S11.11). Several config lines for the
    same part: one net change, checked against the pushed values.
33. `update_course_config` today rewrites the whole YAML and takes no snapshot. The pull's config write must be
    snapshotted and undoable (S11.3). Losing YAML comments or quoting is accepted (same as grade-tui's `w`/`b`).

**Web app editing**
34. Two devices open at once: saves are serialized; stale cells come back as conflicts and are never overwritten
    (S8.2, S8.5). Config saves follow the same rule (S10.5).
35. Partial failure inside one Save (e.g. one CSV written, the next write or the journal append fails): the teacher sees
    the save as failed with edits kept for Retry. A value written to a Drive CSV must always have its journal line;
    Retry must not produce a conflicting double effect; web-pull tolerates duplicate lines (S11.7).
36. Apps Script time or quota limit hit during Save: treated as a failed save (edits kept, Retry offered).
37. Google session expired mid-class: Save fails with a clear "sign in again" message; edits kept in the draft.
38. Draft restored after a new web-push (data replaced since the draft was made): each restored edit is conflict-checked
    on Save as usual; edits for students or columns that no longer exist come back as "not found" and stay listed.
    Drafts are always offered whatever their age, with the age shown (S8.4).
39. Phone signed in to several Google accounts at once (Apps Script web apps often fail to open this way): the README
    documents the workaround; the app must not show another account's data.
40. iPhone storage for the web app's frame may be limited or purged by the browser: the app must detect when the draft
    cannot be stored and warn (S8.8). Verifying restore on iPhone Safari is part of v1 acceptance.
41. Over-max score (`12` in a 10-point column): accepted, shown red, counted per grade-tui rules. Invalid text already
    in a file (hand edit on the Mac, e.g. `abs`): shown as written, red, counted as 0; the teacher can replace it with
    a valid value. Typing invalid text, negatives or `8,5` is refused (S3.7).
42. Existing `EA` attendance code: displayed and preserved; not offered as a tap choice.
43. Undo last save with pending unsaved edits: blocked until saved or discarded (S9.4). Undo after the journal was
    pulled: unavailable (S9.3). Repeated presses walk back newest first (S9.5).
44. Course size: up to 300 students × 80 counted columns within the speed targets (S2.5, S8.9). A larger course must
    still work correctly, even if slower.
45. Weights that do not sum to 1.0: warning, save allowed (S10.2).
46. Search with no match: an empty list with "No students match"; Next does nothing. Search text never changes data.
47. No session column dated today: nothing preselected; the teacher picks (S6.1).
48. The CMRU account cannot deploy or open web apps: the S0 spike stops the build; the lead asks the user (S0.2).

## v1 scope
v1 sits at the 10-task ceiling. If the plan runs over, move these to the backlog first: Undo last save (S9), then
editing in the wide table (S5.4).

1. Spike: minimal "hello" web app deployed on the CMRU account and opened on the iPhone; stop and ask if blocked (S0).
2. `grader web-push <course>` with `--force`, Drive-root override, cwd default and refusal checks (S1).
3. `grader web-pull <course>`: preview by default, `--yes` applies through the existing apply_edits and
   update_course_config paths, Mac-wins config rule, one history entry, archive to Drive plus Mac copy, idempotent
   (S11).
4. JS port of grade-tui's grade math (cells, points, calculators, and the defaults grade-tui applies when loading a
   course) with golden parity tests (S12).
5. Web app shell: course list, access "Only myself", push time and unpulled count; clasp deploy and paste-in
   fallback README (S2, S13).
6. Column mode score entry with ID/name search, Next, `ขส`, Clear, refusal of bad input, over-max flag (S3).
7. Student detail and wide-screen table, both editable, with live totals and grades from unsaved edits (S4, S5).
8. Attendance taking on existing session columns with today preselected (S6), and Fill Column: whole column or only
   empty cells (S7).
9. Batch Save with conflict check, serialized saves, journal append, Retry, Discard, localStorage draft restore with
   age (S8); repeatable Undo last save (S9).
10. Weights and boundaries editor with journaled config saves (S10).

## Backlog (not v1)
- Export reports (`reports/*_final_grades.csv`) and analytics (histogram, at-risk, item analysis) on the web.
- Roster changes or adding students on the web.
- Adding, renaming or removing attendance session columns.
- Editing the attendance `.xlsx` on the web.
- Offline use and a queue of edits made without a connection.
- Thai UI.
- History browser on the web.
- Any change to grade-tui.
- Automatic or scheduled sync between Drive and the Mac.
- Fill targets beyond whole/empty: marked rows, row ranges, Class Group (grade-tui has them).
- Step-by-step undo of unsaved changes (grade-tui's `u`: one typed cell or one whole fill per step).
- Date labels for placeholder attendance columns `a1…aN` (grade-tui computes them from `term_start_date`).
- Raw (unweighted) percentage view toggle.
- Adding or removing grade letters or weight categories on the web.
- Web support for courses with `.xlsx` score files.

## Open questions
None.
