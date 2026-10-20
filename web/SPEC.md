# SPEC: grade_web

Status: draft (Gate 2 pending) · Requirements: REQUIREMENTS.md (approved 2026-10-18) · Branch `web-app` of
grade_dashboard · ADRs: `docs/adr/001-004`

## Overview
grade_web lets the teacher view and edit a grade_dashboard course from an iPhone or any browser, and brings those
edits back to the Mac copy (the master) on demand. It has two halves:

- **Web app**: a Google Apps Script web app (`stack.md` rank 4, see `docs/adr/001-stack.md`) on the CMRU account,
  executed as the owner with access "Only myself". It serves plain HTML/CSS/vanilla JS. It reads and edits CSV
  copies of a course in `My Drive/grade_courses/<semester>/<course>/`, listed through the shortcuts in
  `My Drive/grade_web/` (SPEC_semester_groups.md), and writes each change to an edit journal.
- **Mac**: two new `grader` subcommands inside grade_dashboard (rank 1 core, existing interpreter and
  `requirements.txt`, no new dependency). `web-push` copies a course to Drive and writes a resolved `course.json`.
  `web-pull` replays the journal through grade-tui's own `apply_edits` as one undoable history entry.

The browser computes every total and letter grade with a JS port of grade-tui's math. Golden files generated from
grade-tui's real loader prove it matches (`docs/adr/003-course-json.md`). The journal is safe against Drive for
Desktop lag because each Drive file has a single writer (`docs/adr/002-journal-single-writer.md`).

## Modules
Paths are relative to the grade_dashboard repo root.

| Path | Responsibility |
|---|---|
| **Mac side (Python)** | |
| `grader.py` (edited; `grader` is a git-tracked symlink to it, and so is `~/.mytools/bin/grader`) | Adds `web-push [COURSE] [--force] [--semester NAME] [--drive-root DIR] [--debug]` and `web-pull [COURSE] [-y/--yes] [--semester NAME] [--drive-root DIR] [--debug]`: parse args, resolve the course, print, set the exit code. No logic beyond that. Without `--debug`, an unexpected exception prints one line (`❌ Unexpected error: {message}. Run again with --debug for the details.`) and exits 1. With `--debug`, it prints the traceback. web-push has no `--yes` (it never asks), so there is nothing to alias there |
| `src/webdrive.py` (new) | The Drive side of the contract: resolve the Drive root, mirror paths, read/parse the journal (bad line numbers), archived keys, unpulled lines, conflict-copy check, write archive files |
| `src/webpush.py` (new) | web-push: read-only checks of the Mac course, staging copy, `build_course_json`, copy the pushed set, remove stale files, `--force` discard archive |
| `src/webpull.py` (new) | web-pull: net change per cell/config part, classification against the Mac (apply/already/conflict/skip/no change), preview text, apply in one `history.Entry`, archive |
| `src/tui_api.py` (edited) | `apply_edits(course, edits, entry=None)`, `_sync_total(course, csv, entry=None)`, `_sync_attendance(course, entry=None)`: when `entry` is given, capture into it instead of opening a new snapshot, and don't close it. Default behaviour unchanged |
| `src/attendance.py` (edited) | `auto_sync(course, tool="grade-tui", entry=None)`: same optional entry |
| `tests/conftest.py` (edited; existing fixtures untouched) | Adds the autouse `drive_root` fixture (tmp `My Drive`, `GRADE_WEB_DRIVE_ROOT` set for every test, S1.8), plus `web_course` (copy of F1) and `web_course_att` (plus the attendance xlsx and baseline) |
| `tests/webtools.py` (new) | Test helpers: `grader_cli` (in-process `grader.py` via `runpy`), `grader_proc` (subprocess, TTY or fake HOME), `tree_sha`, `mirror`, `put_journal` |
| `tests/test_web_push.py`, `tests/test_web_pull.py`, `tests/test_web_golden.py` (new) | pytest for S1, S11 and golden drift |
| `tests/test_web_fixtures.py`, `tests/test_web_hygiene.py` (new) | Fixture integrity (IDs `99…`, UTF-8, totals current, no `history/`/`.xlsx`). Repo hygiene (S13.3: no secrets, Drive IDs or account names; existing tests and `rust_tui/` unchanged since `7a233a4`) |
| **Web app (`web/apps_script/`, pushed by clasp as-is)** | |
| `appsscript.json` | Manifest: V8, `Asia/Bangkok`, webapp `executeAs: USER_DEPLOYING`, `access: MYSELF`, explicit scopes `drive` + `userinfo.email`; the Advanced Drive service v3 enabled (same `drive` scope, SPEC_discard_and_speed.md D3) |
| `Code.js` | `doGet` (owner check, template, `?timing=1`), the five server functions, `withLock_` (with each reply's `timing`), `openCourses_` (many courses per Drive listing), roll-forward, trim, `core_()` lazy module instances, `clientCore_()` source injection |
| `drive.js` | Drive I/O only: listings through the Advanced Drive service (`childrenOf_`: many folders a query, trashed left out, a shortcut to a folder followed to that folder), read and write text through DriveApp (BOM kept as `﻿`), the md5-keyed content cache in CacheService (display calls only), Drive counters for `timing`, the pending marker in ScriptProperties |
| `csv.js` (pure) | Parse CSV text like Python's `csv.reader` while recording each field's byte span. BOM and EOL detection. **Cell splice** writer. Python-compatible minimal quoting |
| `grades.js` (pure) | `classify`, `sameCell`, `validateTyped`, `canonicalValue`, attendance code values, `mergeCourse` (roster + files → rows in Raw Details order), `fillDefaultMax`, `computeGrades` (output shape under Grade math), `letterGrade`, `round2` (numpy semantics), `sessionDate`, `fillTargets` |
| `journal.js` (pure) | Batch ids, line keys, `parseJournal` (bad line numbers), `archivedKeys`, `unpulled`, `trim`, `summary` (count, last save), `undoTarget`, `cellLines`/`configLine`, `conflictCopies`. Also the **message formatters** for journal and save results (see "User-facing messages" below). It is injected into the browser too |
| `save.js` (pure) | `planSave` (locate cells, conflict check, splice), `planUndo` (inverse edits of a batch), `planConfig` (validate, strict boundary order, stale check, new course.json) |
| `Index.html` | Page shell: viewport meta, includes `style`, the injected pure modules, `client_state`, `client_views` |
| `style.html` | CSS (phone first, table layout at wide widths) |
| `client_state.html` | Browser state: course data, unsaved edits map, live grades via `grades.js`, localStorage draft, UI memory, course list and last course (`gw:draft:`/`gw:ui:`/`gw:courses`/`gw:last` keys), courses kept in memory and the prefetch, `google.script.run` wrappers (promise, Retry, round-trip timing), leave-page warning |
| `client_views.html` | Screens and events: course list, column mode, attendance, student detail, wide table, Fill, Save/Discard/Undo dialogs, weights/boundaries editor (layout owned by app-ux, see Interface) |
| **Tests and tools (`web/`)** | |
| `tests/*.test.js` | `node --test 'web/tests/*.test.js'` (quoted glob: a bare directory argument fails on Node 24): `grades`, `csv`, `validate`, `journal`, `save`, `fill`, `config`, and `server.test.js`. No npm packages |
| `tests/helpers.js` | Node test helper: load a golden file, read the fixture CSVs it names, build rows, apply an overlay |
| `tests/gas_fake.js` | Loads `web/apps_script/*.js` into one `node:vm` context with fakes for DriveApp (over a tmp dir), ScriptProperties, LockService, Session, Utilities, HtmlService, the clock and logs. Used by `server.test.js` and `scripts/gas_run.js`. Test tooling only, never deployed |
| `tests/server.test.js` | Server harness: the five server functions, `doGet`, roll-forward, trim, availability, lock and log hygiene, through `gas_fake.js` |
| `tests/fixtures/<name>_grading/` | Fake course folders F1-F4 (IDs `99…`), shared by node and pytest. No `history/` folders (the parent `.gitignore` ignores them; tests create baselines) and no `.xlsx` (built at test time) |
| `tests/fixtures/csv/*.csv` | CSV shape fixtures (BOM + CRLF + quotes, embedded newline, short rows, no final newline, padded IDs, duplicate IDs) |
| `tests/fixtures/journals/*.jsonl` + `expected.json` | Sample journals and an archive file, read by both `journal.test.js` and `test_web_pull.py`. `expected.json` holds per-journal counts, bad lines and unpulled numbers, so both languages read journals the same way. `from_web.jsonl` is the exact output of `save.js` |
| `tests/fixtures/variants.json` | Golden variants (edits as an overlay, weights or boundaries changes) |
| `tests/golden/<name>.json`, `golden/csv_rows.json`, `golden/canonical.json` | Generated by `make_golden.py`: `{course, expected, variants}` per fixture; Python's parse of every fixture CSV; `fmt_value(_cell_value(x))` and `classify(x)` for a set of inputs |
| `tools/make_golden.py` | Writes `tests/golden/` from the fixtures via `src.webpush.build_course_json` + `tui_api.get_course_data` on temp copies. `--check` compares instead of writing |
| `tools/make_big_fixture.py` | Writes a synthetic 300-student x 80-column course (into `--out`, default `web/out/`, git-ignored) for the S2.5/S8.9 payload proxy and the manual speed checks |
| `scripts/gas_run.js` | `node web/scripts/gas_run.js --drive DIR --props FILE [--now ISO] <function> [json-arg …]`: runs one real server function through `gas_fake.js` over a tmp Drive folder and prints its JSON reply (used by `e2e.sh`) |
| `scripts/e2e.sh` | Push → real `Code.js` saves via `gas_run.js` → pull preview → pull `--yes` → grade-tui loader check → `grader undo`, all in tmp dirs, then `node --test 'web/tests/*.test.js'` (steps in End-to-end verification) |
| `README.md` | Deploy (clasp, paste-in), daily use, limits (Drive edits outside the app aren't pulled, multi-account workaround) |

## Data flow
```
 Mac (master)                                         Google Drive, CMRU account: My Drive/grade_courses/<semester>/<course folder>/
 <term>_<name>_grading/                               (seen on the Mac through Drive for Desktop, which may lag)

 course_info/<prefix>_config.yaml ─┐  grader web-push               course.json   (resolved config; web rewrites on config save)
 course_info/<prefix>_student_info ┤  read-only checks ──────────▶  push.json     (push record; web-push only)
 data/*.csv ───────────────────────┘  staging copy → loaders        course_info/<prefix>_student_info.csv
                                      → course.json                 data/*.csv    ◀── cell splice ───────────┐
                                                                    web_edits.jsonl ◀── append (web only) ───┤
 data/*.csv, attendance .xlsx,     ◀─ apply_edits(entry=e)  ◀─┐                                              │
 course_info/<prefix>_config.yaml  ◀─ update_course_config   ─┤ grader web-pull ◀── read journal + archive ──┤
 history/<id>_grader_web-pull/     ◀─ one history.Entry       ─┘        └──▶ archive/web_edits_<ts>.jsonl (new file)
   (+ copy of the archived journal)                                                                          │
                                                                                                             │
 iPhone / Mac browser ──HTTPS── Apps Script web app (execute as owner, "Only myself")                        │
   Index.html + client_state + client_views     Code.js: listCourses · loadCourse · saveBatch ·              │
   csv.js + grades.js (injected via toString)            undoLastSave · saveConfig                           │
   live totals = saved values + unsaved edits   each call under ScriptLock:                                  │
   localStorage draft (IDs + values, no names)    roll-forward → trim → save.js plan → journal → CSVs ───────┘
```

## Data model and file formats

### Drive layout
The copies live in semester folders, and grade_web holds what the phone lists: shortcuts the teacher adds in Drive,
usually one per semester (SPEC_semester_groups.md). Courses pushed before that may still be folders in grade_web.
```
My Drive/grade_web/
  2569-1 → grade_courses/2569-1               ← a Drive shortcut (a group: the phone lists its courses under 2569-1)
My Drive/grade_courses/2569-1/                ← 2569-1 = the folder the Mac course sits in (or --semester)
  9_ฟิสิกส์จำลอง_grading/                     ← same name as the Mac course folder
    course.json                               ← web-push; rewritten by a web config save
    push.json                                 ← web-push only
    web_edits.jsonl                           ← web app only (web-push creates it empty if absent)
    course_info/9_ฟิสิกส์จำลอง_student_info.csv
    data/9_ฟิสิกส์จำลอง_attendance.csv
    data/9_ฟิสิกส์จำลอง_homework.csv
    data/9_ฟิสิกส์จำลอง_midterm.csv
    data/9_ฟิสิกส์จำลอง_final.csv
    archive/web_edits_20270121-180000.jsonl           ← web-pull (new file per pull)
    archive/web_edits_20270121-175500_discarded.jsonl ← web-push --force
```
Never on Drive: the YAML config, `.xlsx` files, `history/`, `reports/`. The CSV and roster bytes are copied
unchanged from the Mac.

### course.json (fake example)
```json
{
  "format": 1,
  "course_id": "MOCK", "course_name": "ฟิสิกส์จำลอง", "term": "2027_S1",
  "folder": "9_ฟิสิกส์จำลอง_grading", "prefix": "9_ฟิสิกส์จำลอง",
  "category_order": ["attendance", "homework", "midterm", "final"],
  "weights": {"attendance": 0.1, "homework": 0.2, "midterm": 0.3, "final": 0.4},
  "grade_boundaries": {"A": 80, "B+": 75, "B": 70, "C+": 65, "C": 60, "D+": 55, "D": 50},
  "rules": {"drop_lowest_homework": true},
  "data_mapping": {
    "attendance": ["13 Jan 2027", "20 Jan 2027", "27 Jan 2027"],
    "homework": ["hw1", "hw2", "hw3"], "midterm": ["midterm_exam"], "final": ["final_exam"]
  },
  "total_pts": {},
  "max_scores": {"hw1": 10, "hw2": 10, "hw3": 10, "midterm_exam": 30, "final_exam": 40},
  "roster": "course_info/9_ฟิสิกส์จำลอง_student_info.csv",
  "files": ["data/9_ฟิสิกส์จำลอง_attendance.csv", "data/9_ฟิสิกส์จำลอง_final.csv",
            "data/9_ฟิสิกส์จำลอง_homework.csv", "data/9_ฟิสิกส์จำลอง_midterm.csv"],
  "columns": [
    {"name": "13 Jan 2027", "header": "13 Jan 2027", "file": "data/9_ฟิสิกส์จำลอง_attendance.csv", "category": "attendance"},
    {"name": "hw1", "header": "hw1 (10pts)", "file": "data/9_ฟิสิกส์จำลอง_homework.csv", "category": "homework"},
    {"name": "midterm_exam", "header": "midterm_exam (30pts)", "file": "data/9_ฟิสิกส์จำลอง_midterm.csv", "category": "midterm"}
  ]
}
```
- `data_mapping`, `total_pts`, `rules`, `weights` and `grade_boundaries` are what `load_config` returns (attendance
  auto-detect applied, `default_pts` dropped). `category_order` is the YAML order of `weights`. It is kept as a
  list because JS orders integer-like object keys first.
- `max_scores` is what `load_course_data` returns (config points, `pts_each`/lab defaults, header overrides,
  legacy sentinel row), **before** `_fill_default_max_scores`. The JS applies that fill itself, because it depends
  on weights the web may change (ADR 003).
- `columns` lists every counted column found in a pushed file, in Raw Details order (category order, then
  `data_mapping` order). Only these columns can be edited. `total …` columns are never listed.
- A web config save rewrites only `weights` or `grade_boundaries`. Boundaries are read and written in scale order
  (`A, B+, B, C+, C, D+, D`; `Grades.gradeOrder`, `../SPEC_grade_order.md`), never in key order: the key order of
  course.json doesn't survive `google.script.run`. `planConfig` requires them strictly descending in that order (it
  refuses rather than re-sorts the values).

### push.json (fake example)
```json
{"format": 1, "push_id": "p-20270119-201500", "pushed_at": "2027-01-19T20:15:00+07:00",
 "course_id": "MOCK", "course_name": "ฟิสิกส์จำลอง", "term": "2027_S1",
 "mac_folder": "9_ฟิสิกส์จำลอง_grading", "tool": "grader web-push",
 "files": ["course.json", "course_info/9_ฟิสิกส์จำลอง_student_info.csv", "data/9_ฟิสิกส์จำลอง_attendance.csv",
           "data/9_ฟิสิกส์จำลอง_final.csv", "data/9_ฟิสิกส์จำลอง_homework.csv", "data/9_ฟิสิกส์จำลอง_midterm.csv"]}
```

### Journal `web_edits.jsonl`
UTF-8, no BOM, LF, one JSON object per line, `ensure_ascii` off (Thai readable). Only the web app writes it.
```json
{"batch":"b-20270120-091502-a1f3","seq":0,"ts":"2027-01-20T09:15:02+07:00","kind":"cell","push":"p-20270119-201500","file":"data/9_ฟิสิกส์จำลอง_attendance.csv","student_id":"9900000001","column":"20 Jan 2027","value":"P","original":""}
{"batch":"b-20270120-091502-a1f3","seq":1,"ts":"2027-01-20T09:15:02+07:00","kind":"cell","push":"p-20270119-201500","file":"data/9_ฟิสิกส์จำลอง_homework.csv","student_id":"9900000002","column":"hw2","value":"8.5","original":""}
{"batch":"b-20270120-093010-c4d0","seq":0,"ts":"2027-01-20T09:30:10+07:00","kind":"config","push":"p-20270119-201500","part":"weights","value":{"attendance":0.1,"homework":0.25,"midterm":0.3,"final":0.35},"original":{"attendance":0.1,"homework":0.2,"midterm":0.3,"final":0.4}}
{"batch":"b-20270120-094500-77e2","seq":0,"ts":"2027-01-20T09:45:00+07:00","kind":"cell","push":"p-20270119-201500","file":"data/9_ฟิสิกส์จำลอง_homework.csv","student_id":"9900000002","column":"hw2","value":"","original":"8.5","undoes":"b-20270120-091502-a1f3"}
```
| Field | Rule |
|---|---|
| `batch` | `b-YYYYMMDD-HHMMSS-xxxx` (server clock in the script time zone + 4 random hex). One per Save/Undo/config save. Sorting by `batch` = time order |
| `seq` | 0-based index within the batch. **Line key = `batch#seq`**, unique, used by archives and trim |
| `ts` | Server clock, ISO 8601 with offset |
| `kind` | `cell` or `config` |
| `push` | `push_id` of the push the edit was made on |
| `student_id` | Text, trimmed, never a number |
| `column` | Clean column name (`hw2`, not `hw2 (10pts)`; attendance session header as written). Still matches after the Mac changes header points (edge 26) |
| `file` | Drive path of the file written (informational; web-pull finds the column itself) |
| `value` / `original` | Cell text after / before (`""` blank, `ขส`, `P`). `value` is canonical (see CSV handling). `original` is the Drive value the edit was checked against |
| `part` | `weights` or `grade_boundaries` (config lines). `value`/`original` are the whole part as `{key: number}` |
| `undoes` | On every line of an undo batch: the batch it reverses |

A total column never appears in the journal. Lines that aren't valid JSON are never dropped by the web app. Their
line numbers are reported (web-pull refuses, S11.13).

### Archive files (written by the Mac, always new files)
`archive/web_edits_<YYYYMMDD-HHMMSS>.jsonl` (pull) and `archive/web_edits_<YYYYMMDD-HHMMSS>_discarded.jsonl`
(`web-push --force`). `-2`, `-3` are appended if the name exists. Line 1 is a header. Every following line is a
journal line copied as read, plus `result` (and `reason`, `mac` where useful):
```json
{"kind":"pull","ts":"2027-01-21T18:00:00+07:00","tool":"grader web-pull","mac_folder":"9_ฟิสิกส์จำลอง_grading","push":"p-20270119-201500","lines":4,"history":"20270121-180000_grader_web-pull"}
{"batch":"b-20270120-091502-a1f3","seq":1,"kind":"cell","student_id":"9900000002","column":"hw2","value":"8.5","original":"","result":"superseded"}
{"batch":"b-20270120-094500-77e2","seq":0,"kind":"cell","student_id":"9900000002","column":"hw2","value":"","original":"8.5","undoes":"b-20270120-091502-a1f3","result":"no change"}
{"batch":"b-20270120-091502-a1f3","seq":0,"kind":"cell","student_id":"9900000001","column":"20 Jan 2027","value":"P","original":"","result":"applied"}
{"batch":"b-20270120-093010-c4d0","seq":0,"kind":"config","part":"weights","value":{"…":0},"original":{"…":0},"result":"conflict","mac":{"attendance":0.1,"homework":0.15,"midterm":0.3,"final":0.4}}
```
`result` ∈ `applied`, `already applied`, `conflict`, `skipped` (with `reason`: `student not in Mac files`,
`column not in Mac files`, `total column`), `superseded` (a later line for the same cell holds the net change),
`no change` (edited back to its start), `discarded` (`_discarded` files). The header `kind` is `pull` or
`discarded`. Archived keys = `batch#seq` of every non-header line in every archive file.

The pull's Mac history entry gets an identical copy at `<course>/history/<entry id>/web_edits_<ts>.jsonl`. It is
not listed in the entry's `files`, so `grader undo` never "restores" it.

### Mac history entry (one per pull, INTEGRATION.md "Writing a file")
`history/log.jsonl` line:
`{"id":"20270121-180000_grader_web-pull","ts":"…","tool":"grader","action":"web-pull","files":["data/9_ฟิสิกส์จำลอง_homework.csv","data/9_ฟิสิกส์จำลอง_attendance.csv","data/9_ฟิสิกส์จำลอง_attendance.xlsx","history/attendance_sync.json","course_info/9_ฟิสิกส์จำลอง_config.yaml"],"cells":3,"note":"web pull: 3 cells, weights","journal":"web_edits_20270121-180000.jsonl"}`

### Browser storage (localStorage, per device)
**Draft**: key `gw:draft:<course path>`, the course's path in grade_web (`<course>` or `<group>/<course>`, as
`listCourses` gives it in `folder`; SPEC_semester_groups.md D4). Value
`{"v":1,"made_at":"2027-01-20T09:12:40+07:00","push":"p-20270119-201500","edits":[{"student_id":"9900000001","column":"hw2","value":"9","original":""}]}`.
IDs and values only, no names. Replaced on every unsaved change, removed after a fully successful Save or a
Discard. Always offered on reopen, whatever its age (S8.4).

**UI memory**: key `gw:ui:<course path>`. Value `{"v":1,"column":"hw2","tab":"scores"}`, where `column` is a
`columns[].name` or null and `tab` ∈ `scores`, `attendance`, `grading`, `table`. It holds no PII and no grades:
column names and the tab only. It is written when the column or tab changes and read on open (the "column used last on
this device"). An unknown column or tab is ignored. If a write fails, the storage-refused strip shows (S8.8). Nothing
else is lost.

**Course list** (SPEC_discard_and_speed.md D6): key `gw:courses`. Value `{"v":1,"saved_at":"<reply now>","courses":
[…]}` with the `listCourses` fields of each course (folder, course id/name/term, push time, journal counts, or the
unavailable reason). No student data. Written after every successful `listCourses`, drawn at once on the next visit.

**Last course** (D8): key `gw:last`, a course path, written when a course opens. When a fresh list no longer has a
draft's, UI memory's or gw:last's bare course name but exactly one group has that course, the key moves to its path;
a draft whose course isn't listed at all is shown under the list with Discard (SPEC_semester_groups.md D4, D6). The list prefetches it.

Opened courses are kept in the tab's memory only (at most 3, never in storage); see SPEC_discard_and_speed.md D7.

## CSV handling (both halves)
- **Read** (`csv.js`, `csvio.read_csv_text`): BOM detected and remembered. EOL = `\r\n` if the text contains it,
  else `\n`. Fields follow Python's `csv` excel dialect (quotes, doubled quotes, embedded newlines). Rows shorter
  than the header read as blank cells. Student IDs are text, compared trimmed.
- **Write on Drive = cell splice**: `csv.js` keeps each field's span in the original text and replaces only the
  spans of targeted cells (appending `,` padding when a row is short). Every other byte, including BOM, EOL,
  quoting style and the stored `total` cells, stays identical (S8.6). The web never rewrites a whole file from
  parsed rows, and never recomputes `total` cells on Drive (they aren't targeted). Totals on screen are computed.
  The Mac recomputes stored totals on pull.
- **Write on the Mac**: only through `apply_edits` / `csvio.write_csv_text` (atomic, BOM and EOL kept).
- **Canonical value** written by the web = what `apply_edits` writes for the same text
  (`fmt_value(_cell_value(text))`): trimmed; with a `.` → float → `"8"` for `8.0`, shortest repr for `8.50` →
  `"8.5"`; without `.` → integer text (`"08"` → `"8"`); `ขส`, `P`/`L`/`A`/`X`, `""` as they are. Values are always
  *compared* by meaning (`sameCell` = equal `classify` results), so a textual difference in exotic numbers
  (e.g. `1e-05`) never causes a false conflict.
- **Typed input** (`grades.validateTyped`, S3.7): after trimming, allowed are `^(\d+(\.\d*)?|\.\d+)$`, `""`, and
  `ขส`. A comma between digits (`8,5`) → reason `comma` ("use . for decimals"). A leading `-` before a number →
  `negative`. Anything else → `other`. Attendance cells accept only `P`, `L`, `A`, `X`, `""` from taps and Fill
  (an existing `EA` is kept untouched). The server re-checks every value in `saveBatch` (reason `invalid`).

## Grade math in the browser (parity rules, `grades.js`)
The JS mirrors `load_course_data` → `_fill_default_max_scores` → `calculate_final_grades` step by step, in the
same operation order, so floats round the same way:
1. **Rows**: union of Student IDs from the roster and every pushed data CSV (rows with a blank ID dropped; a
   legacy sentinel first row `Full Score`/`Max`/`Max Score`/`Full` skipped). Sorted by ID as text = Raw Details
   order. Name = first non-empty name (roster first).
2. **Cells**: `classify` (INTEGRATION.md table, including `,` stripping for cells already in files) → number, else 0
   for empty/`ขส`/invalid. A student with no row in a file → 0. Attendance: trimmed code → P 1, L 0.8, X 1, EA 1,
   A 0, anything else 0.
3. **Max**: `max_scores` from course.json, then `fillDefaultMax` with the *current* weights (weight x 100 minus the
   specified sum, split over unspecified `data_mapping` columns, absent columns included, as Python does), then 100
   for anything still missing.
4. **Per category in `category_order`** (skip a category with no present columns: pct 0, no Coursework share):
   attendance sum / number of present sessions. `homework` with `drop_lowest_homework` and ≥ 2 columns drops the
   first column with the lowest score/max ratio (pandas `idxmin`: first minimum, NaN skipped). Otherwise sum / Σ max.
   `total_pts` raises the possible max. Possible max 0 → 0.
5. weighted = pct x 100 x weight. Displayed `{cat}_pct` = `round2(weighted)`, where `round2(x)` = numpy
   `rint(x*100)/100` (half-to-even on the scaled double, **not** `Math.round`). Coursework Total = sequential sum
   of the unrounded weighted values of every category except `midterm`/`final`, then `round2`, then `ceil`.
   `midterm_pct`/`final_pct` = `ceil(round2(weighted))`. Final Score = CT + midterm + final (integers). Grade =
   the first boundary (sorted by value, highest first) with Final ≥ threshold, else `F`.
6. Sums run left to right in column order. **Parity hazard:** if pandas' row sum ever uses numpy pairwise
   summation (categories of 9+ columns), last-ulp differences could flip a `ceil`. The fixtures include a category
   with ≥ 9 columns and values just above a whole number. If golden tests fail there, the JS implements numpy's
   pairwise order. The golden test, not this paragraph, is the authority.
7. **Output** of `computeGrades(course, rows, overlay)` (overlay = unsaved edits), one object per student in
   Raw Details order:
   `{student_id, pct: {<category>: round2 weighted, midterm/final as ceil'd integers}, coursework_total, final_score,
   grade, dropped}`. `dropped` is the clean name of the homework column removed by `drop_lowest_homework` for that
   student (the pandas `idxmin` choice above), or `null` when the rule is off or doesn't apply (< 2 columns). The
   golden files check every field except `dropped` (grade-tui doesn't output it). `grades.test.js` checks `dropped`
   on the drop-lowest fixtures, including ties (first column wins).
8. Known, accepted display differences (both count 0): a pandas NA token (`NA`, `N/A`, `null`) shows blank in
   grade-tui and as invalid red text on the web. Leading-zero IDs (ADR 003). Fixtures avoid both.

### User-facing messages (decision)
The result messages built from server replies and timestamps live in `journal.js`, in one `fmt` group:
`plural`, `fmtTime(iso, nowIso)` and `fmtAgo(iso, nowIso)` (formats of Interface "Formats"), `draftAge`,
`saveResult(reply, columns)` ("Saved 3 cells (2 files)", conflicts, not found, push changed), `undoTitle`,
`undoResult`, and `journalLine` ("4 edits not pulled · last saved …"). They return the Interface copy-table strings.
`journal.js` is injected into the browser with `csv.js` and `grades.js` (ADR 004), so node tests check the exact
strings, and no new Apps Script file is needed: the budget stays at 11. Times are formatted from the ISO text's own
offset (server clock, `+07:00`), never from the device's time zone. `{ago}` uses the server `now` that every reply
carries, not the device clock. Typed-value refusal texts (`bad.comma`, etc.) are built from `grades.validateTyped`'s
reason in `client_state.html`. Screen layout strings stay in `client_views.html`.

## Apps Script server API
All five functions are called through `google.script.run` and take/return plain JSON. Each runs inside
`withLock_`: `LockService.getScriptLock().waitLock(25000)` (on timeout → `{ok:false, code:"BUSY"}`). Then, for
the course(s) concerned, **roll-forward** and **trim** (below), then the function body, then release. Expected
failures return `{ok:false, code, message}`. Every reply, success or failure, also carries `now` (server time,
ISO 8601 with offset) for the `{ago}` formats. Unexpected exceptions propagate to the client's failure handler,
which treats them as a failed call (edits kept, Retry offered). Nothing is ever written to `console`/`Logger`
except an error code and a course folder name (no names, IDs or scores).

`doGet()`: if `Session.getActiveUser().getEmail()` ≠ `Session.getEffectiveUser().getEmail()` → a page reading
"Not available" with no data (defence in depth behind "Only myself", S2.2). Otherwise
`HtmlService.createTemplateFromFile('Index').evaluate()` with a `viewport` meta tag and title "grade_web".

| Function | Request | Success reply |
|---|---|---|
| `listCourses()` | — | `{ok, now, courses:[{folder, group, available:true, course_id, course_name, term, pushed_at, unpulled, last_saved, older_push}, {folder, group, available:false, reason}], groups:[{name, count}]}`. `folder` is the course's path in grade_web and `group` its group's name or null (SPEC_semester_groups.md); every other function takes that path as `folderName`. `older_push` (boolean) is true when at least one **unpulled** journal line (after trim) has a `push` different from the current `push.json` `push_id`. That only happens when web-push ran while Drive for Desktop hadn't yet synced a web save (ADR 002). Such lines are still pulled normally and still block the next push, and Undo never offers them |
| `loadCourse(folder)` | course folder name | `{ok, folder, course:<course.json>, push:<push.json>, roster:"<text>", files:{"data/…csv":"<text>"}, journal:<J>}` |
| `saveBatch(folder, edits)` | `edits: [{student_id, column, value, original}]` | `{ok, batch|null, ts, saved:[{student_id,column,value}], already:[…], conflicts:[{student_id,column,now,reason}], files, push_changed, journal:<J>}` |
| `undoLastSave(folder, batch)` | the batch the teacher confirmed | `{ok, batch, undoes, saved, already, conflicts, journal:<J>}` |
| `saveConfig(folder, part, value, original)` | `part` ∈ weights/grade_boundaries; `value` `{key: text}` as typed; `original` `{key: number}` as loaded | `{ok, batch, course:<course.json>, warning|null, journal:<J>}` |

`<J>` = `{unpulled, last_saved, undo:{batch, ts, cells, edits}|null, undo_note:null|"Nothing to undo"|"Already pulled to the Mac; use \`grader undo\` there"}`.
`undo.cells` is the number of cell lines in the target batch. `undo.edits` lists the first 10 of them in `seq` order as
`[{student_id, column, value, original}]` (the values the save wrote and what Undo puts back), so the Undo dialog can
list them and say "and {cells − 10} more". Built by `journal.undoTarget`. No names: the client looks them up.
Failure codes: `NOT_FOUND` (no `grade_web` or no such course), `UNAVAILABLE` (missing `course.json`/`push.json`,
unreadable file, conflict copies: message names the files), `BUSY`, `INVALID` (+ `field`), `STALE_CONFIG`
(+ `current`), `UNDO_UNAVAILABLE` (+ the note), `UNDO_CHANGED` (the newest save isn't the confirmed batch: reload).
`listCourses` never fails for one bad course. That course is `available:false` with its `reason` (S2.3).

### Course availability (checked by `listCourses` and `loadCourse`)
An item in `grade_web/` (a folder, or a Drive shortcut to one, named by the shortcut; its files, pending and trim
markers are the target folder's) that holds `course.json`, `push.json` or `web_edits.jsonl` is a course. Any other
item is a group: its subfolders that hold one of those files are its courses, path `<group>/<course>`; anything else
in it is left out, and a group with none shows "No pushed courses in <group>." A shortcut to a file is not a course.
A shortcut whose target is gone or not shared is an empty group. A name with `/` is unavailable (why.slash).
Unavailable when `course.json` or `push.json` is missing or not valid JSON, when a file listed in `course.json` is
missing, when `web_edits.jsonl` is missing or has lines that aren't valid JSON (reason names the line numbers and
points to the README's "Damaged journal"; freezing the course keeps the hand repair single-writer), or when `journal.conflictCopies` finds two files with the same name in a folder, or a name like
`<stem> (<n>)<ext>` whose `<stem><ext>` is an expected file (`web_edits (1).jsonl`, `…_homework (1).csv`)
(edge 17). A read error is reported as unavailable. A missing journal file is never treated as an empty journal
(edge 19). `loadCourse`, `saveBatch`, `undoLastSave` and `saveConfig` run this check first (after roll-forward and
trim) and return `UNAVAILABLE` with the reason. So while a course has duplicate files or a damaged journal, the
web app writes nothing to it, and the teacher can repair it by hand without a second writer.

### Saving (`saveBatch`, under the lock)
1. Read `push.json`, the journal, and each target file named by `course.json.columns` for the edited columns.
   `push_changed` = the edits' draft push ≠ current push (informational, edge 38).
2. `save.planSave(files, course, edits)`. For each edit: find the column's header in its file (trimmed equality)
   and every row whose trimmed ID equals `student_id` (duplicate IDs: the first row is checked, all rows are set,
   like `apply_edits`, edge 6). No column/row → conflict `not found`. Invalid value → conflict `invalid`. Current
   cell `sameCell` value → `already`. Current `sameCell` original → **change**. Otherwise conflict `changed` with
   `now` = current text (S8.2).
3. No changes → reply (`batch:null`). Otherwise:
   a. set ScriptProperty `pending:<course folder id>` = `{batch, kind:"cell"}`;
   b. write the journal = old text + one `cell` line per change (one `setContent`);
   c. write each changed CSV once (spliced text);
   d. delete the pending property.
4. The client counts `saved + already` as saved ("Saved 3 cells (2 files)"). The "(N files)" is computed **by the
   client**: the number of distinct `course.columns[].file` among the saved + already cells. A Retry after a lost
   reply therefore shows the same message as the original save. The reply's `files` field counts only the files
   written by this call. It is informational, and the client doesn't use it for the message. Conflicts stay unsaved with their
   `original` replaced by `now`, so a second Save writes them on purpose (S8.2). The client clears the draft only
   when no edit remains unsaved.
5. Two devices: the ScriptLock runs saves one after the other, and step 2 always reads the files as the previous
   save left them (S8.5, edge 34). A Retry after a lost reply finds every cell `already` → no second journal line
   (S8.3).

**Roll-forward** (start of every locked call, per course): if `pending:<id>` exists, re-read the journal lines of
that batch. For a `cell` line whose current cell `sameCell` its `original`, splice in `value`. For a `config` line
whose current part equals its `original`, set it. Then delete the property. If the batch never reached the journal,
just delete the property. Result: a Drive CSV value always has a journal line, and a failed save is either fully
absent or completed before anything else runs (edges 35 and 36).

**Trim** (start of every locked call, per course): list `archive/`. For archive names not yet in ScriptProperty
`trimmed:<id>` (a JSON list), read their keys. If any journal line has one of those keys, rewrite the journal without
those lines (invalid lines and everything else kept byte-identical). Then record the names. This is idempotent, so
the property is only a cache (ADR 002).

### Undo last save (`undoLastSave`)
`journal.undoTarget(lines, push_id)`: among unpulled lines of the **current push**, cell batches without `undoes`
and not referenced by any undo batch's `undoes`. The newest one wins (S9.5). Config batches are not offered (the
teacher re-edits weights in the editor). None → `UNDO_UNAVAILABLE` with "Already pulled to the Mac; use
`grader undo` there" when `archive/` holds a `pull` file for the current push, else "Nothing to undo" (S9.3). If the
target ≠ the `batch` argument → `UNDO_CHANGED`. Otherwise `save.planUndo` builds the inverse edits
(`value ← original`, `original ← value`) and they go through steps 2-3 of Saving, with `undoes` on every line. A
cell changed since (by the other device) comes back as a conflict and isn't reverted (S9.2). The client disables
Undo while unsaved edits exist (S9.4).

### Config save (`saveConfig`)
`save.planConfig`: every value must be non-empty and parse as a finite number ≥ 0 (else `INVALID` with `field` = the
key, S10.3; the same reasons as the client: not a number, comma, negative, empty). The key set must equal the current
one (no new letters or categories, S10.4). For `grade_boundaries`, the values must be **strictly descending in scale
order** (`Grades.gradeOrder`: A > B+ > B …; a letter outside the scale goes by its saved value). Otherwise `INVALID`
with `field` = the first letter whose value isn't lower than the letter above it. The server writes the letters in
that order and never re-sorts the values, so the letters keep their meaning (S10.4).
`original` must deep-equal the current `course.json[part]` (else `STALE_CONFIG` with `current`, nothing written,
S10.5). A weights sum ≠ 1 is **not** an error: the reply carries `warning: "weights sum to 1.05"` and the save goes
through (S10.2, edge 45). The write follows
the Saving steps 3a-3d with one `config` line, then the rewritten `course.json`.

## Mac commands

### Drive root and course resolution
- `<course>`: positional folder path (like `grader --course DIR`). If omitted and the current folder has
  `course_info/`, the current folder is used. Otherwise argparse usage error, exit 2 (S1.11, S11.16).
- Drive root (the `My Drive` folder): `--drive-root DIR`, else env `GRADE_WEB_DRIVE_ROOT`, else the single match of
  `Path.home() / "Library/CloudStorage"` glob `GoogleDrive-*@g.cmru.ac.th/My Drive`. `src/webdrive.py` must use
  `Path.home()` (never a literal `~` path or `$HOME` read elsewhere), so tests can point it at a fake HOME. Zero or several matches → exit 1 asking for
  `--drive-root`. The repo holds no account name and no Drive IDs (S13.3). Missing root → exit 1 naming the path,
  nothing written (S1.9, edge 18). The mirror is `<root>/grade_courses/<semester>/<Mac course folder name>/`, the
  semester being the Mac course's parent folder name or `--semester`, and `grade_courses` being `$GRADE_WEB_COURSES`
  when set. web-pull also reads an old flat copy `<root>/grade_web/<course>/` (SPEC_semester_groups.md D7, D8).
- pytest: `tests/conftest.py` sets `GRADE_WEB_DRIVE_ROOT` to a tmp folder for every test (autouse). Fixtures live in
  `web/tests/fixtures/`. Nothing touches `~/Library/CloudStorage` or `~/cmru/teachings` (S1.8).

### `grader web-push <course> [--force]`
Every check runs before the first write. A refusal writes nothing anywhere.
1. **Read-only checks of the Mac course** (S1.2: nothing here writes, so the loaders are never run on the Mac folder):
   config present and valid UTF-8 YAML (edge 7); roster present, has `Student ID`, ≥ 1 student (edge 8); every
   `data/*.csv` strict UTF-8 (S1.6, edge 3), has `Student ID` (edge 7), ≥ 1 row (edge 8); duplicate IDs → warning
   naming them (edge 6); any `data/*.xlsx` not ending `attendance.xlsx` → refuse naming each (S1.10, edge 11);
   attendance: `attendance.plan(course)` (read-only) — if it needs a question **or has any pending change**, refuse
   with "run `grader sync` first" (S1.5). *Design choice:* a no-question pending sync is refused too, because applying
   it would write into the Mac folder (S1.2) and pushing without it would push a stale attendance csv.
2. **Drive checks**: root exists. If the mirror folder exists: refuse on conflict copies (edge 17). Read
   `web_edits.jsonl`. A read failure → exit 1 (edge 19), invalid lines → exit 1 naming the line numbers. Unpulled =
   lines minus archived keys. Unpulled lines and no `--force` → print each (`ID column: original → value, time`)
   and exit 1 (S1.3, edge 14).
3. **Staging**: copy the config, roster and `data/*.csv` into a `tempfile.TemporaryDirectory()` course folder.
   `build_course_json(staging)` runs `load_config` + `load_course_data` there (no attendance xlsx in staging, so
   auto-sync has nothing to do), then assembles course.json (format above).
4. **Write** (each file via `csvio.atomic_write_bytes`): with `--force` first write
   `archive/web_edits_<ts>_discarded.jsonl` with the unpulled lines (`result: discarded`) and print its name
   (S1.4). Then roster, `data/*.csv` (bytes as on the Mac), `course.json`, and `push.json` last (new `push_id`).
   Create `web_edits.jsonl` empty **only if it doesn't exist** (it is never rewritten, ADR 002). Delete any other
   file under the mirror's `data/` and `course_info/`, and any other top-level file except `web_edits.jsonl`,
   `course.json`, `push.json` (S1.7). `archive/` is never touched.
5. Print the pushed files, course name/term, `push_id`, and "N edits not pulled" (normally 0).

### `grader web-pull <course> [-y/--yes]`
1. Resolve course and root. The mirror must exist (else "not pushed", exit 1). Refuse on conflict copies (edge 17).
   Read `push.json`. Its `course_id` and `term` must equal the Mac config's, else refuse (S11.14, edge 20).
2. Read the journal (read failure → exit 1, edge 19). Any invalid line → print the line numbers, apply nothing,
   archive nothing, exit 1 (S11.13, edge 29). Unpulled = lines minus archived keys. None → "Nothing to pull",
   exit 0, no history entry (S11.10).
3. Print the journal's unpulled line count and last save time (edge 15), so the teacher can compare them with
   the web app's "N edits not pulled · last saved …".
4. **Net change** per `(student_id, column)` in journal order: base = first line's `original`, final = last line's
   `value`. Earlier lines are `superseded`. `sameCell(base, final)` → `no change` (S11.6, edge 24). Config: the same
   per `part`, comparing dicts by key with numeric equality (edge 32).
5. **Classify against the Mac** (read-only: `tui_api._find_column_file` + `csvio.read_csv_text`, first matching
   row): total column → skipped. Column not found → skipped `column not in Mac files`. Student not found → skipped
   `student not in Mac files` (S11.5, edges 25 and 27). Mac `sameCell` final → `already applied` (S11.7, edge 23).
   Mac `sameCell` base → `apply`. Otherwise `conflict` (Mac kept; "conflict: 9900000001 hw2 — Mac 7, web 9 (not
   applied)", S11.4, edge 22). Config: Mac part == final → already applied. == base → apply (S11.11). Else
   conflict ("conflict: weights — Mac {…}, web {…}; apply by hand if wanted", S11.12). Header points changed on the
   Mac still match by clean name (edge 26).
6. **Preview** (always printed): per-column summary, each change `ID column: Mac value → web value`, every
   conflict, skip, already applied and no change. Without `--yes` (TTY or not): exit 0, nothing written (S11.1).
7. **Apply (`--yes`)**. If any `apply` cell is in the attendance csv and the attendance xlsx is locked (`~$` file)
   or `attendance.warnings(course)` is non-empty → refuse the whole pull, exit 1 (S11.15, edge 30). Otherwise:
   - `e = history.Entry(course, "grader", "web-pull", note=…)`. Capture the config (if a config part applies) and
     `history/attendance_sync.json` (if attendance cells apply) **before** any write.
   - `tui_api.apply_edits(course, [{student_id, column, value: final, original: Mac value}], entry=e)`: one
     conflict check, CSV writes, attendance xlsx mirror (S11.8), and totals/attendance baseline refreshed
     **into `e`** (S11.2, edge 31). A conflict it reports (grade-tui saved in between) is listed as a conflict.
   - Config: `update_course_config(course, weights_dict=…, boundaries_dict=…)` for the parts to apply (edge 33).
   - If `e` captured anything: write the archive copy into `e.dir`, then
     `e.close(cells=n, journal="web_edits_<ts>.jsonl")`. **One** entry: `grader undo` restores every changed file,
     including the xlsx, config and baseline (S11.3).
   - Write `archive/web_edits_<ts>.jsonl` on Drive with **every unpulled line read**, each with its `result`
     (S11.9). The journal itself is not modified (the web app trims it, ADR 002). Lines appended after step 2 aren't
     in the archive and stay unpulled (S11.9, edge 16).
   - Crash after applying but before archiving: a rerun finds every value `already applied`, opens no history entry,
     and archives (edge 28).
8. Print the result (applied, conflicts, skips, the history id, the archive name). Exit 0.

### Drive for Desktop lag (edge 15): why no line can be lost
- The Mac never rewrites, truncates or deletes `web_edits.jsonl`, and only *creates* new files in `archive/`. A stale
  local copy can therefore only make the Mac see *fewer* lines, never remove one.
- A line leaves the journal only when its key is in an archive file, and archive files contain only lines the Mac
  actually read and applied/classified (pull) or listed and discarded with `--force` (push).
- web-push never rewrites the journal. If it pushes while a web save is still unsynced, that save's lines survive
  with the old `push` id: still unpulled, counted by the web app, blocking the next push, and applied by the next
  pull against the Mac values.
- Online-only (streamed) files are read with normal file I/O, which makes Drive for Desktop fetch them. A failure is
  an error, never an empty journal (edge 19).
- web-pull and the web app show the same two numbers (unpulled count, last save time). If they differ, the teacher
  waits for Drive to sync and runs the command again.

### Hand-repair procedures (README sections, written in T5)
Both procedures run while the web app refuses the course (duplicate files and damaged journals make it
`UNAVAILABLE`), so the Mac is briefly the only writer of `web_edits.jsonl`. This is the one sanctioned exception to
ADR 002's single-writer rule, and it is done by the teacher by hand, never by a command.

**"Duplicate files"** (`web_edits (1).jsonl`, `…_homework (1).csv`, `course (1).json`, or two files with the same name
in Google Drive):
1. Wait until Drive for Desktop shows "up to date". Don't use the web app for this course until the end.
2. Journal copy: copy `web_edits.jsonl` and the copy somewhere outside the course folder first (e.g. the Desktop), as a
   backup. Then, in a text editor, append to `web_edits.jsonl` every line of the copy whose `batch` + `seq` pair isn't
   already in it, and sort all lines by `batch`, then `seq` (batch ids sort by time). Never change a line. Delete the
   copy (Finder or drive.google.com). Put no backup inside `archive/`, because every file there is read as an archive.
3. Any other copy (CSV, `course.json`, `push.json`): delete the `(1)` copy. Those files are rebuilt from the Mac. If
   unsure which one is right, delete the copy anyway, then run `grader web-pull` (preview, then `--yes`) and
   `grader web-push` to refresh Drive. The journal, not the CSVs, carries the web edits.
4. Wait for "up to date", reload the web app (the course opens again), then run `grader web-pull`.

**"Damaged journal"** (`web_edits.jsonl has lines that aren't valid JSON: 3, 7`; web-push and web-pull refuse, and the
web app shows the course as unavailable):
1. Wait for "up to date". Copy `web_edits.jsonl` outside the course folder as a backup.
2. Open it in a text editor and go to the named lines. A line that is a cut-off copy of a complete line nearby (same
   `batch` and `seq`): delete it. A line cut off with no complete twin: if the JSON is obviously completable (a
   missing `"}` at the end), fix it; otherwise delete it and write down its student ID, column and value from the
   readable part, to re-enter by hand on the Mac after the pull. Never edit or delete a valid line.
3. Save, wait for "up to date", run `grader web-pull` (it must now preview without the error), then `--yes`. Reload
   the web app.

## Data safety
- **Fixtures only** (data-safety §1): every test and tool uses `web/tests/fixtures/` (10-digit IDs starting `99`,
  invented Thai names) and tmp folders. `GRADE_WEB_DRIVE_ROOT` is forced to tmp in pytest. `make_golden.py` reads
  only fixtures. The T1 spike uses a fake file. Agents never read `~/cmru/teachings` or the real Drive folder. The
  user runs real pushes and pulls.
- **Snapshot before writing user files** (§2): web-push never writes into the Mac course (SHA-256 test, S1.2).
  web-pull captures every Mac file it will change (CSVs, attendance xlsx, attendance baseline, config) into one
  history entry before writing, with atomic writes. `grader undo` restores the entry. Drive files are copies the
  app created. Their safety net is the journal, web "Undo last save", and `--force` keeping discarded lines in
  `archive/` (never deleted).
- **Preview, then confirm** (§3): web-pull is a dry run unless `--yes`. web-push refuses while unpulled lines exist.
  On the web: Fill shows "N cells will change" before confirming, Save shows a summary (above max), and Discard and
  Undo each ask for confirmation. A hand edit on the Mac is never overwritten: it is listed as a conflict.
- **No PII to LLMs** (§4): no LLM anywhere.
- **Where PII lives**: Drive (CMRU account), browser memory, journal and archives (IDs, no names), localStorage
  drafts (IDs + values, no names). Apps Script logs hold no names, IDs or scores.
- **Secrets** (§5): `.clasp.json` git-ignored. `~/.clasprc.json` stays in the home folder. No OAuth tokens, Drive
  file/folder IDs or account names in the repo (folders are found by name) (S13.3).

## Error handling
| Condition | Behaviour | Exit code |
|---|---|---|
| `<course>` omitted and cwd isn't a course folder | argparse usage message | 2 |
| Drive root missing / not found / ambiguous | "Drive folder not found: <path> (is Drive for Desktop running?)" or "use --drive-root", nothing written | 1 |
| Config/roster/data CSV missing, not UTF-8, no `Student ID`, no students | Refuse, naming the file | 1 |
| Score file stored as `.xlsx` | Refuse, naming each file | 1 |
| Attendance pair needs `grader sync` (push: any pending change) | "run `grader sync` first", nothing written | 1 |
| Duplicate Student ID in a data file | Warning naming file + ID, continue | 0 |
| Unpulled journal lines at push, no `--force` | List the edits, nothing written | 1 |
| `--force` with unpulled lines | Archive `_discarded` file named in output, push proceeds | 0 |
| Journal unreadable (online-only fetch failed) | Error, never treated as empty | 1 |
| Journal has invalid lines | Line numbers listed, nothing applied/archived/pushed | 1 |
| Conflict copies in the Drive course folder | Refuse, naming the files (web: course unavailable) | 1 |
| Mirror folder missing at pull | "not pushed yet" | 1 |
| push.json course_id/term ≠ Mac | Refuse, both shown | 1 |
| Nothing to pull | "Nothing to pull", no history entry | 0 |
| Pull preview (no `--yes`, TTY or not) | Preview, nothing written | 0 |
| Attendance lines + xlsx open in Excel or pair needs sync, `--yes` | Refuse the whole pull (preview still printed) | 1 |
| Pull applied with conflicts/skips | Listed. Mac values kept | 0 |
| `apply_edits` returns an error mid-pull | Close the entry with what it captured (undo works), no archive, print "run again" | 1 |
| Archive write fails after applying | "Applied but not archived: run `grader web-pull --yes` again" (idempotent) | 1 |
| Unexpected exception in web-push/web-pull | One line `❌ Unexpected error: {message}. Run again with --debug for the details.` With `--debug`: the full traceback | 1 |
| Web: journal has invalid lines | Course unavailable (reason names the line numbers and the README's "Damaged journal"), nothing written | — |
| Web: signed in as another account / signed out | Google refuses ("Only myself"). `doGet` owner check shows "Not available", no data | — |
| Web: no `grade_web` folder | Course list: "No pushed courses: run `grader web-push` on the Mac" | — |
| Web: course unavailable | Listed with reason, can't be opened, others work (S2.3) | — |
| Web: lock busy | "Another save is running; try again", edits kept | — |
| Web: network down, quota/time limit, server exception | "Save failed" + Retry, edits kept unsaved and in the draft (S8.3, edge 36) | — |
| Web: session expired | "Sign in again; your edits are kept" (edge 37) | — |
| Web: conflicts | Listed with Drive value. Cells stay unsaved with updated start value | — |
| Web: stale config | Refused, current Drive values shown | — |
| Web: localStorage refused | Persistent warning that unsaved edits won't survive closing the tab (S8.8) | — |
| Web: typed `8,5` / `-3` / `abc` | Refused at the cell with the S3.7 message. Value and focus unchanged | — |

## Budget
| Metric | Limit |
|---|---|
| deps | 0 |
| install_mb | 0 |
| peak_rss_mb | 200 |
| apps_script_libraries | 0 |
| npm_packages (runtime and test) | 0 |
| apps_script_files | ≤ 11 |
| apps_script_source_kb | ≤ 150 |
| loadCourse payload, 300 x 80 course | ≤ 500 KB |
| open course on phone 4G, 300 x 80 | ≤ 8 s (S2.5) |
| save 60 cells on phone 4G | ≤ 5 s (S8.9) |
| Drive queries: `listCourses` (4 courses), `loadCourse`, `saveBatch` | ≤ 4 each, whatever the course count (`speed.test.js`) |
| downloads, warm cache: `listCourses`, `loadCourse` | 0 (`speed.test.js`) |
| server time, warm cache (measured v11): `listCourses` / `loadCourse` | ≤ 1.5 s / ≤ 1.0 s (1.13 s / 0.70 s on 2026-10-20) |

- `deps 0`: no new runtime dependency on either side. The Python code inherits grade_dashboard's existing
  `requirements.txt` unchanged. Apps Script uses only built-in services. Node tests, the server harness and
  `gas_run.js` use only Node built-ins (`node:test`, `node:assert`, `node:fs`, `node:path`, `node:os`, `node:vm`,
  `node:crypto`). No `package.json`.
- `install_mb 0`: nothing new is installed for the app. clasp is a deploy tool installed once by the user, and
  Apps Script has no install.
- `peak_rss_mb 200`, loosened from the Python CLI default of 150 on purpose: importing grade_dashboard's `src`
  (pandas + openpyxl) alone measures 104 MB on this Mac, and web-push/web-pull must run grade-tui's own loaders and
  `apply_edits` for parity and safety.

Dependency justifications (inherited, already in `requirements.txt`; none added):
- `pyyaml`: read the course YAML and write it through `update_course_config`. The config format is grade_dashboard's.
- `pandas`: grade-tui's `load_config`/`load_course_data`/`get_course_data` build `course.json` and the golden
  values. Parity requires the same code, not a re-implementation.
- `openpyxl`: `apply_edits` mirrors pulled attendance codes into the attendance xlsx, keeping formulas and rules.
- `rich`: not used by the new code.

## Toolchain
Checked with `command -v` on 2026-10-18.

| Tool | Needed for | Present |
|---|---|---|
| `python3` | web-push/web-pull, pytest, `make_golden.py` | yes: `/usr/local/bin/python3` 3.14.8 with pandas 2.3.3, pyyaml 6.0.3, openpyxl 3.1.5 (brew; a `brew upgrade` may relink it to a version without these packages, so check `python3 -c "import pandas"` first) |
| `pytest` | Mac-side tests | yes: 9.0.2 |
| `node` | `node --test 'web/tests/*.test.js'` (quoted glob; `node --test web/tests/` fails on Node 24, which treats the directory as one file), `scripts/gas_run.js` | yes: v24.2.0 |
| `npm` | installing clasp only | yes |
| `clasp` | `clasp push` / `clasp deploy` (S13.1) | **missing**: the user installs it with `npm install -g @google/clasp`, then `clasp login` with the CMRU account, and turns on "Google Apps Script API" at https://script.google.com/home/usersettings |
| `git` | commits on `web-app` | yes |
| `uv` | not used (ADR 001) | yes (unused) |
| Drive for Desktop, CMRU account | real pushes/pulls by the user (never by tests) | yes: a `~/Library/CloudStorage/GoogleDrive-…@g.cmru.ac.th` folder exists |
| iPhone Safari | S0, S2.5, S8.4/edge 40, S8.9 manual checks | the user's phone |

## Spike results (T1)
<!-- T1 fills this in: CMRU deployment allowed? Phone opens the URL? Second account refused? DriveApp setContent
round-trips a Thai + BOM + CRLF fake CSV byte-identically (if not: drive.js uses the advanced Drive service)? -->
Pending.

## Interface
Written by app-ux. The UI is English and the data is shown verbatim (names, headers, course name, `ขส`, codes).
Wording follows grade-tui (SPEC_batch_editing.md) and `grader` wherever the same idea exists.

### Vocabulary (one term per idea, everywhere)
| Term | Meaning | grade-tui equivalent |
|---|---|---|
| **unsaved edit** | A changed cell held on this device and not yet written to Drive. Marked `*` | same |
| **Save** | Write every unsaved edit to Drive in one batch | `Ctrl+S` Save |
| **Discard** | Drop every unsaved edit (nothing written) | Discard |
| **Fill Column** (button: "Fill…") | Put one value in the whole column or only its empty cells, as unsaved edits | Fill Column |
| **changed elsewhere** | Conflict: the Drive value is no longer the one this edit started from | "changed on disk" |
| **above max** | Score higher than the column's max. Accepted, drawn red | same |
| **Undo last save** | Revert the newest web save not yet undone or pulled | (none, `grader undo` on the Mac) |
| **pushed / not pulled** | Freshness of the Drive copy / journal lines waiting for `grader web-pull` | — |
| **draft** | The browser's backup of unsaved edits (localStorage) | (none) |

### Formats
- **Times** (server clock, Asia/Bangkok, 24 h): `{time}` = `20 Jan 09:15` in the current year, `20 Jan 2027 09:15`
  otherwise. `{ago}` = `just now` (< 1 min), `5 min ago`, `2 h ago`, `1 day ago`, `3 days ago`.
- **Numbers**: `.` decimals. Weighted category values = `round2` with trailing zeros trimmed (`9.33`, `17`, `27`).
  Midterm, final, Coursework Total and Final Score are integers. Weights shown as typed in course.json (`0.25`).
- **Blank** shows as an empty input/cell. In sentences, a blank value reads `blank` (web) or `(blank)` (terminal).
- **Plurals**: `1 cell` / `2 cells`, `1 edit` / `2 edits`, `1 file` / `2 files`, `1 student` / `2 students`.
- **Student IDs** are text: never reformatted, shown in tabular figures.

### Screen map and navigation
```
 Not available (wrong account)

 Course list ──tap course──▶ Course ─────────────────────────────────────────────┐
     ▲                         │  phone (< 960 px): tabs  Scores │ Attendance │ Grading
     └──‹ Courses / Switch─────┤  wide (≥ 960 px):  views Table │ Scores │ Attendance │ Grading
        (unsaved → Leave dialog)│
                               ├─ tap a student name ──▶ Student detail (phone: full screen; wide: side panel)
                               ├─ Fill… ──▶ Fill Column sheet
                               ├─ Save / "● N unsaved" ──▶ Save sheet ──▶ result banner
                               └─ ⋯ More ──▶ Undo last save · Discard all unsaved edits · Reload from Drive ·
                                             Switch course   (header line: Drive journal numbers)
```
> **Superseded for navigation (2026-10-19):** the views below are now reached through grade-tui's tabs, [1] Summary,
> [2] Raw Details (one category at a time: the table on wide screens, column mode on phones), [3] Analytics ›
> Overview and [4] Grading, with a ☰ Categories menu. A course opens on the tab and category used last on the
> device (first visit: Summary). See `../SPEC_web_tabs.md`. Editing, Fill, Save, Undo and the detail are unchanged.
> Raw Details › attendance is a grade-tui-style grid (chips, Total over held sessions, 80% flag); a session header
> opens the one-session view described below. See `../SPEC_attendance_grid.md`.
> Phone landscape (short screens, height ≤ 500 px) gets its own rules: see `../SPEC_landscape.md`.

- **Breakpoint**: CSS width ≥ 960 px shows the view switch with **Table** as the default view. Below 960 px the Table
  view isn't offered. If the window is narrowed while in Table, the app switches to **Scores** with the column of the
  focused cell selected (S5.3). Unsaved edits, search text and the selected column survive every view, tab and
  detail change.
- **First screen after opening a course**: column mode, on the tab (Scores or Attendance) and column used last on
  this device (`gw:ui:<folder>`; a saved Grading tab opens Scores, and a column that no longer exists is ignored); on a first
  visit, no column is picked and the list shows the "Pick a column" empty state (S3.1). On the Attendance tab, the
  session dated today is preselected (S6.1).
- In Scores, the column picker also lists the attendance sessions (group `attendance`). Choosing one switches to the
  Attendance tab with that session.
- iOS Safari ignores `beforeunload` in many cases. The draft is the real protection; the browser prompt is a bonus
  where it works (S8.7).

### Common chrome
**Phone header** (sticky top, 2 lines):
```
┌──────────────────────────────────────────┐
│ ‹  ฟิสิกส์จำลอง          ● 3 unsaved   ⋯ │
│ Pushed 19 Jan 20:15 · 4 edits not pulled │
└──────────────────────────────────────────┘
```
- `‹` = back to Courses (44x44 target, label "Courses"). Course name truncates with an ellipsis.
- `● 3 unsaved` badge appears only when there is at least one unsaved edit; tapping it opens the Save sheet. It reads
  `1 unsaved` for one edit (S3.3).
- Line 2: `Pushed {time}` + ` · {n} edits not pulled` (hidden when 0). Turns into `Saving 3 cells…` while saving.
- `⋯` opens the More sheet.

**Phone bottom stack** (sticky bottom, hidden while the keypad is open, because iOS covers it):
```
│ [ Fill… ]                  [  Save 3  ]  │   action bar (Save only when unsaved > 0)
├──────────────────────────────────────────┤
│   Scores    │  Attendance  │   Grading   │   tab bar (56 px tall)
└──────────────────────────────────────────┘
```
The Grading tab has no action bar (its forms have their own Save buttons).

**Wide header** (one toolbar row, sticky):
```
grade_web › ฟิสิกส์จำลอง (MOCK · 2027_S1)   Pushed 19 Jan 20:15 · 4 edits not pulled · last saved 20 Jan 09:15   ● 3 unsaved  [ Save 3 ]  [ More ▾ ]
[ Table | Scores | Attendance | Grading ]     Search [ ID or name        ]            [ Fill… hw2 (10pts) ]
```

**More sheet / menu**:
```
┌──────────────────────────────────────────┐
│ Drive: 4 edits not pulled                │
│        last saved 20 Jan 09:15           │
│──────────────────────────────────────────│
│ Undo last save                           │
│   20 Jan 09:15 · 2 cells                 │
│ Discard all unsaved edits (3)            │
│ Reload from Drive                        │
│ Switch course                            │
│──────────────────────────────────────────│
│ [ Close ]                                │
└──────────────────────────────────────────┘
```
- The Drive line shows the same two numbers `grader web-pull` prints (edge 15).
- **Undo last save** subtitle shows the target (`{time} · {n} cells`) or, when unavailable, the reason in place of the
  subtitle and the item is disabled: `Save or discard your 3 unsaved edits first` (S9.4), `Nothing to undo`, or
  `Already pulled to the Mac; use grader undo there` (S9.3).
- **Discard all unsaved edits (N)** is disabled with `No unsaved edits` when N = 0.
- **Reload from Drive** re-reads the course and keeps unsaved edits on top (they are conflict-checked on Save).

**Status area**: one line above the bottom stack (phone) or under the wide header. Success messages stay 4 s;
conflicts and failures stay until dismissed (`×`, label "Dismiss"). Polite live region for success, `role="alert"`
for failures and refusals.

### 1. Not available (doGet owner check, S2.2)
```
┌──────────────────────────────────────────┐
│ Not available                            │
│                                          │
│ This page opens only for the Google      │
│ account that owns it.                    │
└──────────────────────────────────────────┘
```
No course name, student data, owner address or folder name appears. Signed-out visitors meet Google's own sign-in or
"no permission" page before this ("Only myself").

### 2. Course list (S2.1, S2.3)
```
┌──────────────────────────────────────────┐
│ grade_web                                │
│ Courses on Drive                         │
├──────────────────────────────────────────┤
│ ฟิสิกส์จำลอง                           › │
│ MOCK · 2027_S1                           │
│ Pushed 19 Jan 20:15                      │
│ 4 edits not pulled · last saved 20 Jan   │
│ 09:15                                    │
│ ● 2 unsaved on this device               │
├──────────────────────────────────────────┤
│ ⚠ 8_กลศาสตร์_grading        Unavailable  │
│ course.json is missing. Push the course  │
│ again from the Mac: grader web-push      │
└──────────────────────────────────────────┘
```
- Each available course is one button (whole card, ≥ 72 px tall): `course_name` verbatim, `course_id · term`,
  `Pushed {time}`, the journal line, and `● N unsaved on this device` when this browser holds a draft for it.
- The journal line: `{n} edits not pulled · last saved {time}` (S2.1), or `No edits waiting to be pulled` when 0.
- `older_push` true adds: `Some of these edits were saved while the latest push was syncing. They're kept; pull them
  on the Mac: grader web-pull` (web-push refuses until they are pulled).
- When two courses share a `course_name`, the folder name is shown under it in muted text.
- Unavailable courses (S2.3) are not buttons: folder name, `Unavailable`, and the reason (copy table "Unavailable
  reasons"). The other courses still open.

| State | Shows |
|---|---|
| Loading | Title, 2 grey placeholder cards, `Loading courses…` |
| Empty (`NOT_FOUND` or no course folders) | `No pushed courses yet.` / `On the Mac, run grader web-push <course>, wait for Drive to finish uploading, then reload this page.` + `[ Reload ]` |
| Failed (network/exception) | `Couldn't load the course list.` / `Check your connection, then try again.` + `[ Try again ]` |
| `BUSY` | `Drive is busy with a save from another device.` + `[ Try again ]` |

### 3. Opening a course
| State | Shows |
|---|---|
| Loading | Full screen: course name, spinner, `Opening ฟิสิกส์จำลอง…` / `Reading the course from Drive`. After 8 s add `Still working. Large courses take a little longer.` |
| Failed | `Couldn't open ฟิสิกส์จำลอง.` + cause line (copy table) + `[ Try again ]` `[ Back to courses ]` |
| Unavailable (`UNAVAILABLE`) | `Can't open ฟิสิกส์จำลอง.` + the reason + `[ Back to courses ]` |
| Draft found (S8.4, edge 38) | Course opens with the edits applied and marked `*`, plus a banner (below) |
| Storage refused (S8.8, edge 40) | Persistent strip under the header (below) on every course screen |

**Draft banner** (dismissable with `×`; dismissing keeps the edits):
```
┌──────────────────────────────────────────┐
│ 5 unsaved edits restored                 │
│ (from 20 Jan 09:12)                      │
│ [ Review ]   [ Discard… ]              × │
└──────────────────────────────────────────┘
```
- Age: `(from {time})` when under 1 day, `(from {time}, {ago})` otherwise, e.g. `(from 17 Jan 09:12, 3 days ago)`.
  Always offered, whatever its age.
- Added lines when they apply: `The course was pushed again since then; each edit is checked when you save.` (draft
  push ≠ current push) and `2 are for students or columns no longer in this course.` (edge 38).
- Draft edits whose value already equals the Drive value are dropped on restore. If all were: info line
  `Your draft from 20 Jan 09:12 is already on Drive; nothing to restore.` and the draft is removed.
- `Review` opens the Save sheet. `Discard…` opens the Discard dialog.

**Storage refused strip** (not dismissable, one line, tap expands):
`Unsaved edits can't be backed up in this browser. Save often: closing this tab loses them.` Expanded:
`Storage is blocked here (for example in a private window). Saved edits on Drive are safe.` Shown when a test write
at load or any draft write throws.

### 4. Scores: column mode, phone (S3)
```
┌──────────────────────────────────────────┐
│ ‹  ฟิสิกส์จำลอง          ● 2 unsaved   ⋯ │
│ Pushed 19 Jan 20:15 · 4 edits not pulled │
├──────────────────────────────────────────┤
│ Column                                   │
│ [‹] [ hw2 (10pts)                  ▾ ] [›]│
│ homework · max 10 · 2 of 3 entered       │
│ [ Search ID or name            ] [Fill…] │
├──────────────────────────────────────────┤
│ 9900000001                    ┌───────┐  │
│ นายสมมติ ทดสอบ             ›  │   9   │* │
│ was blank                     └───────┘  │
├──────────────────────────────────────────┤
│ 9900000002                    ┏━━━━━━━┓  │  ← focused
│ นางสาวตัวอย่าง ใจดี         ›  ┃  12   ┃* │
│ above max 10 · was blank      ┗━━━━━━━┛  │
├──────────────────────────────────────────┤
│ 9900000003                    ┌───────┐  │
│ นายทดลอง มีชื่อ             ›  │       │  │
│                               └───────┘  │
├──────────────────────────────────────────┤
│ [ Fill… ]                  [  Save 2  ]  │
│   Scores    │  Attendance  │   Grading   │
└──────────────────────────────────────────┘
```
- **Column picker**: a native `<select>` with one `<optgroup>` per category in `category_order` (label = category key
  as written), options = `columns[].header` verbatim (`hw2 (10pts)`), each with its progress: `hw2 (10pts) · 2/3`.
  `total (…pts)` columns never appear (S3.1, edge 10). `‹` / `›` step to the previous/next column (labels
  "Previous column", "Next column"); disabled at the ends.
- **Column line**: `{category} · max {max} · {k} of {n} entered` (k counts non-blank values, unsaved included).
- **Rows** in Raw Details order (S3.2). Left part (ID, name, sub-line) is one button that opens the Student detail
  (label `Open {name} {id}`). Right part is the input: `type="text" inputmode="decimal" enterkeyhint="next"
  autocomplete="off"`, 96 x 48 px, 18 px text, value selected on focus so typing replaces it.
- **Sub-line** (muted, ≤ 1 line): `was {saved value}` for an unsaved cell, `above max {max}` (red) for an over-max
  value, `not a number, counts as 0` (red) for invalid text already in the file (`abs`), joined with ` · `.
- **Marks**: unsaved = amber cell background + `*` after the input (S3.3). Over max = red value text + the sub-line
  (S3.5, edge 41). Invalid file text = red value + dotted underline + its sub-line (S4.3).
- **Search** (S3.8): filters by ID substring (`0002`) or name substring (`ใจดี`), trimmed, case-insensitive for Latin
  letters. Next moves through the filtered rows only. Clearing it (`×` button inside the field, label "Clear
  search") shows everyone. Search never changes data.
  - No match (edge 46): the list area reads `No students match "0009".` with `[ Clear search ]`. Next does nothing.

| State | Shows |
|---|---|
| No column picked | List area: `Pick a column to enter scores.` |
| Column picked, nobody entered yet | Normal list; column line `0 of 3 entered` |
| Saving | Inputs read-only, Save button `Saving 3 cells…` with spinner, header line 2 `Saving 3 cells…` |

#### Typing rules (column mode, detail, table)
1. **Commit** happens on Next, Enter, Tab, or leaving the field. Typing alone never creates an edit, but the
   detail's totals preview the focused input while its text is valid (S4.2).
2. On commit, the text is trimmed. If it means the same as the cell's current value (`sameCell`, e.g. `9.0` vs `9`,
   or untouched `abs`), nothing happens and no validation message appears.
3. Otherwise `validateTyped` decides:
   - **ok**: the canonical value becomes the cell's unsaved value (`08` → `8`, `8.50` → `8.5`). If it means the same
     as the Drive value, the unsaved edit is removed instead and the badge drops by one (S3.6).
   - **refused** (`comma`, `negative`, `other`): the message appears under the row (red, `role="alert"`), the input
     gets a red border, the typed text stays selected so the next keystroke replaces it, focus stays on the cell,
     the cell keeps its previous value, no edit is created (S3.7). The message also appears live while typing,
     as soon as the text is invalid.
   - Leaving the field by tapping elsewhere with refused text puts the previous value back in the input; the
     message stays until the next commit.
4. **Next** moves focus to the next visible row's input and scrolls it to the middle of the space above the
   keypad. On the last row the Next button reads **Done**: it closes the keypad and scrolls Save into view, with the
   status line `End of list · 3 of 3 entered`.

#### Keypad accessory bar (phone, while an input has focus)
```
│ [   ขส   ]  [  Clear  ]  [    Next ↓    ] │  ← pinned just above the keypad
╞══════════════════════════════════════════╡
│   1   2   3  /  4   5   6  /  7   8   9   │  iOS decimal keypad
│   .   0   ⌫                               │  (+ Safari's ‹ › Done bar)
```
- Positioned with `visualViewport` so it sits above the keyboard and Safari's form bar. Buttons 48 px tall; Next is
  the widest (primary).
- `ขส`: sets the focused cell to `ขส` (unsaved) and moves to the next student (S3.4). `Clear`: sets it to blank
  (unsaved; removes the edit when the Drive value is blank) and stays. `Next ↓`: commit and move.
- Builder note: these buttons call `preventDefault()` on `pointerdown` so the input doesn't blur and the keypad
  stays open, and they call `focus()` on the next input synchronously inside the tap handler (iOS opens the keypad
  only from a user gesture).

### 5. Attendance (S6)
```
┌──────────────────────────────────────────┐
│ ‹  ฟิสิกส์จำลอง          ● 2 unsaved   ⋯ │
│ Pushed 19 Jan 20:15 · 4 edits not pulled │
├──────────────────────────────────────────┤
│ Session                                  │
│ [‹] [ 20 Jan 2027 · today          ▾ ] [›]│
│ P 1 · L 0 · A 1 · X 0 · EA 0 · blank 1   │
│ [ Search ID or name            ] [Fill…] │
├──────────────────────────────────────────┤
│ 9900000001  นายสมมติ ทดสอบ          P* › │
│ [  P  ][  L  ][  A  ][  X  ]   [ Clear ] │
├──────────────────────────────────────────┤
│▌9900000002  นางสาวตัวอย่าง ใจดี      A* › │  ← next student (focus)
│ [  P  ][  L  ][▐A▌ ][  X  ]   [ Clear ] │
├──────────────────────────────────────────┤
│ 9900000003  นายทดลอง มีชื่อ          EA › │
│ [  P  ][  L  ][  A  ][  X  ]   [ Clear ] │
├──────────────────────────────────────────┤
│ [ Fill… ]                  [  Save 2  ]  │
│   Scores    │  Attendance  │   Grading   │
└──────────────────────────────────────────┘
```
- **Session picker**: native `<select>` of the attendance session headers verbatim (`13 Jan 2027`, `a1`); the one
  dated today (server date) reads `20 Jan 2027 · today` and is preselected. If none matches (S6.1, edge 47), the
  picker shows `Pick a session` and the list area reads `No session is dated today (Wed 21 Jan 2027). Pick one
  above.`
- **Counts line** (live, unsaved included): `P n · L n · A n · X n · EA n · blank n`. `EA` appears only when present.
- **Row**: line 1 = ID, name (one line, ellipsis), current code with `*` when unsaved, `›` opens the detail (whole line
  is the button). Line 2 = four code buttons, 56 x 48 px each, 8 px apart, plus `Clear` (64 x 48, outline style,
  disabled when the cell is blank). Comfortable with the right thumb on a 375 px wide phone.
- **Tap a code**: sets the cell (unsaved, `*`), the button shows filled, and focus moves to the next student's row,
  which scrolls to the middle of the screen (S6.2). Tapping the code the cell already holds does nothing.
- `Clear` sets blank (unsaved) and doesn't move.
- **EA** (edge 42): shown as written at the end of line 1, no button is pressed, and it is kept until the teacher
  taps another code (S6.3). It is never offered as a choice.
- Other text already in a session cell is shown as written in red (`not a code, counts as 0` in the row's label).
- No control adds, renames or removes a session (S6.4). The app never mentions or touches the xlsx (S6.7).

| State | Shows |
|---|---|
| Course has no session columns | `This course has no attendance sessions. Add them on the Mac, then push again.` |
| No session dated today | Picker `Pick a session` + the message above |

### 6. Student detail (S4)
Phone: full screen pushed over the tab. Wide: a 420 px side panel over the right edge of the table (`Esc` closes).
```
┌──────────────────────────────────────────┐
│ ‹ hw2                    ● 2 unsaved   ⋯ │
├──────────────────────────────────────────┤
│ 9900000001 · SEC1        [‹ Prev][Next ›]│
│ นายสมมติ ทดสอบ                            │
│ ┌──────────────────────────────────────┐ │
│ │ Final Score 76           Grade  B+   │ │
│ │ Coursework Total 27                  │ │
│ │ Includes 1 unsaved edit              │ │
│ └──────────────────────────────────────┘ │
│ attendance               9.33 of 10    ▾ │
│   13 Jan 2027   [P][L][A][X][Clear]   P  │
│   20 Jan 2027   [P][L][A][X][Clear]   P  │
│   27 Jan 2027   [P][L][A][X][Clear]   L  │
│ homework                   17 of 20    ▾ │
│   hw1 (10pts)                 [   8   ]  │
│   hw2 (10pts)                 [   9   ]* │
│   hw3 (10pts)   dropped       [       ]  │
│ midterm                    21 of 30    ▾ │
│   midterm_exam (30pts)        [  21   ]  │
│ final                      28 of 40    ▾ │
│   final_exam (40pts)          [  28   ]* │
└──────────────────────────────────────────┘
```
- `‹ {column}` returns to the list it came from, focus back on that student's row.
- Summary card: `Final Score {n}` and `Grade {letter}` (largest text on the screen), `Coursework Total {n}`, and
  `Includes {n} unsaved edit(s)` when the student has any. Values are live from saved values + unsaved edits, and
  preview the focused input while its text is valid (S4.2: typing `28` in final_exam shows 76 / B+ at once).
- One section per category in `category_order` (heading = category key verbatim, then `{weighted} of
  {weight × 100}`), collapsible. Attendance starts collapsed when it has more than 6 sessions. A category with
  weight but no columns shows `no columns` and `0 of {w}`.
- Items show `columns[].header` verbatim; inputs follow the typing rules; Next/Enter moves to the **next item of
  this student** (grade-tui popup parity). `ขส` and Clear appear in the keypad bar as in column mode.
- `dropped` (muted) marks the homework column removed by `drop_lowest_homework` (`computeGrades` → `dropped`).
- `ขส` shows as `ขส` (counts 0); `abs` shows as `abs` in red with `not a number, counts as 0` (S4.3).
- `‹ Prev` / `Next ›` step through the same (filtered) student order as the list.

### 7. Wide table (S5)
```
grade_web › ฟิสิกส์จำลอง (MOCK · 2027_S1)   Pushed 19 Jan 20:15 · 4 edits not pulled · last saved 20 Jan 09:15   ● 3 unsaved  [ Save 3 ]  [ More ▾ ]
[ Table | Scores | Attendance | Grading ]     Search [ ID or name        ]            [ Fill… hw2 (10pts) ]
┌──────────┬────────────────────╥──────┬──────┬──────┬─────╥─────┬─────┬─────┬─────╥──────┬─────╥──────┬─────╥──────┬──────┬─────┐
│Student ID│Name                ║13 Jan│20 Jan│27 Jan│att. ║hw1  │hw2  │hw3  │hw.  ║mid-  │mid. ║final_│fin. ║Course│Final │Grade│
│          │                    ║ 2027 │ 2027 │ 2027 │ /10 ║(10  │(10  │(10  │ /20 ║term_ │ /30 ║exam  │ /40 ║-work │Score │     │
│          │                    ║      │      │      │     ║pts) │pts) │pts) │     ║exam  │     ║(40   │     ║Total │      │     │
├──────────┼────────────────────╫──────┼──────┼──────┼─────╫─────┼─────┼─────┼─────╫──────┼─────╫──────┼─────╫──────┼──────┼─────┤
│9900000001│นายสมมติ ทดสอบ       ║  P   │  P   │  L   │9.33 ║  8  │ 9*  │     │ 17  ║  21  │ 21  ║ 28*  │ 28  ║  27  │  76  │ B+  │
│9900000002│นางสาวตัวอย่าง ใจดี   ║  P   │  A*  │  P   │6.67 ║ 10  │12▲* │  7  │ 20  ║  18  │ 18  ║  30  │ 30  ║  27  │  75  │ B+  │
│9900000003│นายทดลอง มีชื่อ       ║  EA  │      │  P   │6.67 ║ abs │     │  5  │ 2.5 ║      │  0  ║      │  0  ║  10  │  10  │  F  │
└──────────┴────────────────────╨──────┴──────┴──────┴─────╨─────┴─────┴─────┴─────╨──────┴─────╨──────┴─────╨──────┴──────┴─────┘
  ID and Name frozen; header rows sticky; headers verbatim, wrapped; computed columns (att., hw., mid., fin.,
  Coursework Total, Final Score, Grade) on grey; stored total (…pts) columns not shown
```
(Values in rows 2-3 are illustrative.)
- Columns: ID, Name (frozen, `position: sticky`), then per category in `category_order`: its counted columns
  (headers verbatim, wrapped) followed by the computed `{category} /{w}` column (full key, e.g. `homework /20`;
  abbreviated in the wireframe only), then
  `Coursework Total`, `Final Score`, `Grade` (S5.1). Computed columns have a grey background, aren't focusable for
  editing, and announce as "computed".
- Same marks as column mode (S5.2): unsaved amber + `*`, above max red + `▲`, invalid file text red + dotted
  underline. Rows with any unsaved edit show a 3 px amber bar on the left of the ID cell.
- Editing (S5.4) is spreadsheet style (keyboard table below). Double-click or Enter opens the editor in the cell; a
  refused value shows its message in a small red popover under the cell. Attendance cells take P/L/A/X keys or a
  click opens a small picker `P L A X Clear`.
- Clicking a name opens the detail side panel. Clicking a column header selects that column for `Fill…`.
- The search box filters rows the same way as column mode. No match: one row reading `No students match "…"`.
- Above 300 x 80 cells, rendering may take a moment: `Building the table…` shows until the first paint.

### 8. Fill Column sheet (S7)
Score column:
```
┌──────────────────────────────────────────┐
│ Fill hw2 (10pts)                         │
│                                          │
│ Cells   (•) Only empty cells             │
│         ( ) Whole column                 │
│ Value   [ 0            ]   [ ขส ]        │
│                                          │
│ → 2 cells will change                    │
│                                          │
│ [ Cancel ]            [ Fill 2 cells ]   │
└──────────────────────────────────────────┘
```
Attendance column: the Value row is a choice of `[P] [L] [A] [X] [Clear]` (one pressed at a time, S7.4).
- Default target is **Only empty cells** (the safer one). Unsaved values count as filled (S7.3).
- Count line updates live: `→ {n} cells will change`. Cells already equal to the value don't count (S7.2). With
  Whole column on an attendance session that has EA cells: extra line `Includes 1 EA cell.`
- When a search is active: `Fill covers all 3 students, not only the ones your search shows.`
- Value follows the typing rules (S7.4): the refusal message appears under the field and the Fill button is
  disabled. Empty value: Fill disabled, hint `Type a value, or tap ขส.`
- n = 0: button reads `Nothing to change` and is disabled (S7.5).
- Confirm adds the cells as unsaved edits; nothing is written to Drive. Status: `Filled 2 cells (unsaved)`.
- `Cancel` / `Esc` / tapping outside closes without changes.

### 9. Save (S8)
**Save sheet** (from the Save button, the badge, `Ctrl/Cmd+S`, or the draft banner's Review):
```
┌──────────────────────────────────────────┐
│ Save 3 cells?                            │
│                                          │
│ hw2 (10pts)        2 cells, 1 above max ▸│
│ midterm_exam (30pts)          1 cell    ▸│
│                                          │
│ [ Discard all… ]       [ Save 3 cells ]  │
│                     [ Keep editing ]     │
└──────────────────────────────────────────┘
```
- One line per column; `▸` expands it to `{id} {name}: {was} → {new}` lines (blank reads `blank`).
- `above max` count per column (S3.5) and in total when > 0: `1 is above max; it will be saved as typed.`
- Edits for students/columns not in the loaded course: `2 can't be saved: student or column not in this course.`
  with `[ Drop these 2 ]`.
- The primary button sits at the bottom right, where the Save button was, so two taps in the same place save.
- While saving: the sheet closes, the Save button reads `Saving 3 cells…`, edits are locked (S8.9: ≤ 5 s target).

**Results** (status area):
| Case | Message | After |
|---|---|---|
| All saved (S8.1) | `Saved 3 cells (2 files)` | Marks and draft clear. Undo item refreshes |
| Retry after a lost reply (all `already`) | `Saved 3 cells (2 files)` | Same (files = distinct files of saved + already cells) |
| Some changed elsewhere (S8.2) | `Saved 0 cells · 1 changed elsewhere, not saved: 9900000001 hw2 (now 7)` | Those cells stay unsaved, `was` = Drive value; a second Save writes them |
| More than 3 conflicts | `Saved 12 cells · 5 changed elsewhere, not saved: 9900000001 hw2 (now 7), 9900000002 hw2 (now 8), 9900000003 hw1 (now 5) and 2 more` + `[ Show all ]` | Conflict list sheet |
| Not found (edge 38) | `… · 2 not found (student or column not in this course): 9900000099 hw2, 9900000001 hw9` | Stay unsaved, listed in the Save sheet with Drop |
| Push changed since the draft | extra sentence: `Some edits were made before the latest push; they were checked against the new data.` | — |
| Nothing to write (all edits equal Drive) | `Nothing to save: Drive already has these values` | Marks clear |

**Conflict list sheet**:
```
┌──────────────────────────────────────────┐
│ Changed elsewhere, not saved (2)         │
│ 9900000001 นายสมมติ ทดสอบ                 │
│   hw2   Drive now 7 · yours 9    [Go to] │
│ 9900000002 นางสาวตัวอย่าง ใจดี             │
│   hw2   Drive now 8 · yours 10   [Go to] │
│                                          │
│ These stay unsaved. Save again to write  │
│ your values, or change them first.       │
│                              [ Close ]   │
└──────────────────────────────────────────┘
```
`Go to` opens that column with the row focused.

**Failures** (persistent banner, `role="alert"`; every edit stays unsaved and in the draft; S8.3, edges 35-37):
| Cause (client classification) | Banner |
|---|---|
| `navigator.onLine` false | `Save failed: you're offline. Your 3 edits are kept. [ Retry ]` |
| `BUSY` | `Another save is running; try again. Your 3 edits are kept. [ Retry ]` |
| Failure text mentions authorization / sign-in, or HTTP 401/403 | `Signed out of Google. Sign in again; your edits are kept. [ Sign in ]` (`Sign in` reloads the page; the draft restores) |
| Script timeout / quota / any other failure | `Save failed: Google didn't finish the save. Your 3 edits are kept. [ Retry ]` |
| `UNAVAILABLE` (duplicate files or a damaged journal appeared on Drive) | `Not saved: {reason} Your 3 edits are kept on this device.` + `[ Back to courses ]` (no Retry: Retry can't succeed until the hand repair; after it, reopening the course restores the draft) |
`Retry` resends the same edits (Retry after a lost reply ends as `already`, no double effect).

### 10. Discard (S8.10)
```
┌──────────────────────────────────────────┐
│ Discard 3 unsaved edits?                 │
│ They were never saved to Drive and can't │
│ be brought back.                         │
│                                          │
│ [ Keep edits ]        [ Discard 3 edits ]│
└──────────────────────────────────────────┘
```
Initial focus on `Keep edits`. `Discard` is red. Result: `Discarded 3 edits`; marks and draft clear; nothing written.

### 11. Undo last save (S9)
```
┌──────────────────────────────────────────┐
│ Undo save of 20 Jan 09:15, 2 cells?      │
│ 9900000001 hw2: 9 → blank                │
│ 9900000002 hw2: 8 → blank                │
│ Drive gets the earlier values back.      │
│ Cells changed since then are left alone. │
│                                          │
│ [ Cancel ]                [ Undo save ]  │
└──────────────────────────────────────────┘
```
- Title is exactly `Undo save of {time}, {n} cells?` (S9.1), with `{n}` = `undo.cells`. The list shows
  `undo.edits` (up to 10, in save order) as `{id} {column}: {value} → {original}`, names looked up by the client
  (shown after the ID when the line fits: `9900000001 นายสมมติ ทดสอบ hw2: 9 → blank`). When `undo.cells` > 10, a
  last line reads `and {undo.cells − 10} more` (e.g. 14 cells: `and 4 more`).
- Only from the More menu, and only when allowed (S9.3, S9.4; reasons listed under Common chrome).
- Results: `Undid save of 20 Jan 09:15: 2 cells restored` / `Undid 1 of 2 cells · 1 changed since, left as is:
  9900000002 hw2 (now 7)` (S9.2) / all conflicts: `Nothing undone · 2 changed since, left as is: …`.
- `UNDO_CHANGED`: `Another device saved since this page loaded. Reload to see the newest save, then try again.
  [ Reload ]`. `UNDO_UNAVAILABLE`: the note as the message. `UNAVAILABLE`: as for Save (`fail.unavailable`).
- Saves from an earlier push (`older_push`) are never offered; when they are the only saves left, the item reads
  `Nothing to undo`.
- Pressing again walks back to the next older save (S9.5); the menu subtitle shows which.

### 12. Leaving with unsaved edits (S8.7)
In-app (`‹ Courses`, Switch course):
```
┌──────────────────────────────────────────┐
│ 3 unsaved edits in ฟิสิกส์จำลอง           │
│ They stay on this device as a draft if   │
│ you leave without saving.                │
│                                          │
│ [ Keep editing ]                         │
│ [ Leave, keep draft ]   [ Save and leave ]│
└──────────────────────────────────────────┘
```
`Save and leave` saves first; on conflicts or failure it stays on the course and shows the result. Closing or
reloading the tab triggers the browser's own `beforeunload` prompt where supported.

### 13. Grading: weights and boundaries (S10)
```
┌──────────────────────────────────────────┐
│ Weights                                  │
│   attendance      [ 0.1   ]              │
│   homework        [ 0.25  ]  *           │
│   midterm         [ 0.3   ]              │
│   final           [ 0.4   ]              │
│ ⚠ weights sum to 1.05                    │
│ With these weights 2 grades change.  ▸   │
│ [ Reset ]               [ Save weights ] │
├──────────────────────────────────────────┤
│ Grade boundaries (highest first)         │
│   A  X ≥ 80           [ 80    ]          │
│   B+ 75 ≤ X < 80      [ 75    ]          │
│   B  70 ≤ X < 75      [ 70    ]          │
│   C+ 65 ≤ X < 70      [ 65    ]          │
│   C  60 ≤ X < 65      [ 60    ]          │
│   D+ 55 ≤ X < 60      [ 55    ]          │
│   D  50 ≤ X < 55      [ 50    ]          │
│   F  X < 50                              │
│ [ Reset ]          [ Save boundaries ]   │
├──────────────────────────────────────────┤
│ Grade distribution (preview)             │
│   A   ▇▇▇▇▇▇░░░░        2 (22.2%)        │
│   …                                      │
│   F   ▇▇▇▇▇▇▇▇▇▇        4 (44.4%)        │
├──────────────────────────────────────────┤
│ Undo last save doesn't cover weights or  │
│ boundaries: change them back here.       │
└──────────────────────────────────────────┘
```
- Labels are the keys verbatim (category keys in `category_order`, letters in scale order: `Grades.gradeOrder`).
  Each letter shows its interval under it (`70 ≤ X < 75`; `—` while a field is refused), and letters are coloured
  as in grade-tui (`--grade-*` tokens). The Grade distribution (count and % per letter, then F) follows the saved
  values plus unsaved edits, or the typed weights/boundaries with a `(preview)` tag. See `../SPEC_grade_order.md`.
  Its bars (and Analytics › Overview's) are filled from the palette tokens `--bar-*`, with a 1px edge in the letter
  colour in light mode and none in dark mode (`../SPEC_bar_colours.md`).
  No control adds or
  removes a key (S10.4). Inputs `inputmode="decimal"`. Changed fields show `*`.
- Sum line: `Weights sum to 1` (muted) when it equals 1, else `⚠ weights sum to 1.05` (warning colour). Save stays
  enabled (S10.2).
- Preview line: `With these weights {n} grades change.` (`▸` lists `{id} {name}: B → B+`), `No grade changes.` when 0.
  Totals elsewhere change only after saving.
- Field checks (live, and they disable that form's Save): not a number → `{field}: '{text}' isn't a number (e.g.
  0.25)` (S10.3); `,` → `{field}: use . for decimals (0.25)`; negative → `{field}: can't be negative`; empty →
  `{field}: enter a number (0 is allowed)`; boundaries not strictly descending in letter order → `{letter} {value}
  must be lower than {letter above} {value above}`.
- Saving: button `Saving weights…`. Success: `Weights saved. Totals and grades updated.` (with the warning: `Weights
  saved (they sum to 1.05). Totals and grades updated.`); `Boundaries saved. Grades updated.`
- `STALE_CONFIG` (S10.5): banner `Weights were changed on another device after you opened them. Nothing was saved.`
  + `On Drive now: attendance 0.1, homework 0.2, midterm 0.3, final 0.4` + `[ Use Drive values ]` (loads them into
  the form and the course) and `[ Keep mine ]` (keeps the form; the next Save uses the Drive values as the starting
  point). Same wording with "Boundaries".
- `INVALID` from the server: the field message above for `field`. `UNAVAILABLE`: banner `Not saved: {reason}` (the
  form keeps its values).
- Leaving the tab keeps the form's changes; leaving the course with a changed form adds `Weights not saved.` to the
  Leave dialog.

### Edge-case coverage (web)
| Edge / story | Visible behaviour |
|---|---|
| 4, 5 | Names and IDs shown exactly as in the files (quotes, commas, leading zeros) |
| 6 | Shown once; web-push prints the duplicate warning |
| 9, 10 | Hand-added and `total` columns never listed or editable |
| 13, S3.7 | `'8,5': use . for decimals (8.5)` at the cell |
| 15 | Same two numbers in the More sheet / course list and in `grader web-pull` |
| 17, 19, 29 | Course `Unavailable` with the named files, the damaged line numbers, or the read failure; a save, undo or config save that meets it reads `Not saved: {reason}` and keeps the edits |
| 34, S8.2 | Conflict message and list; cells stay unsaved |
| 35, 36, S8.3 | `Save failed…` + Retry |
| 37 | `Signed out of Google…` + Sign in |
| 38 | Draft banner lines; `not found` in the result and Save sheet with Drop |
| 39, S2.2 | Google's page or `Not available`; never another account's data |
| 40, S8.8 | Storage refused strip |
| 41 | Above max red + text; invalid file text red + `not a number, counts as 0` |
| 42 | EA shown, kept, not a choice |
| 43 | Undo item disabled with the reason |
| 44 | `Still working…` after 8 s; `Building the table…` |
| 45 | `⚠ weights sum to 1.05`, Save allowed |
| 46 | `No students match "…"`; Next does nothing |
| 47 | `Pick a session` + `No session is dated today (…)` |

### Keyboard (desktop)
| Where | Keys |
|---|---|
| Anywhere in a course | `Ctrl/Cmd+S` opens the Save sheet (browser save suppressed). `/` focuses Search. `Esc` closes the top sheet, dialog or side panel |
| Column mode input | `Enter` / `Tab` = Next. `Shift+Enter` / `Shift+Tab` = previous student. `Esc` puts back the value the cell had when focused. `ขส` and `Clear` buttons are in tab order after the list's current row |
| Attendance | `↑` `↓` move between students. `P` `L` `A` `X` set the focused student's code and move down. `Backspace`/`Delete` clear. `Enter` on the name line opens the detail |
| Table, not editing | Arrows move. `0-9` or `.` start editing with that character. `Enter` edits the current value. `Backspace`/`Delete` set blank (unsaved). `-` sets `ขส` and moves down. `P` `L` `A` `X` on attendance cells set the code and move down. `Enter` on a name opens the detail |
| Table, editing | `Enter` / `↓` commit and move down. `Tab` / `Shift+Tab` commit and move right/left. `↑` commit and move up. `Esc` cancel this cell's typing |
| Dialogs and sheets | Focus is trapped inside. `Esc` = the safe choice (Cancel / Keep). `Enter` on a focused button activates it |

grade-tui parity: Enter moves down, `-` = ขส and P/L/A/X move down in the table. In inputs that are always in edit
mode (column mode, detail), `-` is ordinary text so `-3` gets the negative-number message.

### Accessibility (WCAG 2.1 AA)
- **Targets**: everything tappable ≥ 44 x 44 CSS px; attendance codes 56 x 48; score inputs 96 x 48; keypad bar
  buttons 48 tall; tabs 56 tall; ≥ 8 px between adjacent targets. The Save button and the attendance codes sit in
  the bottom two thirds of the screen for one-handed use.
- **Colour is never the only signal**: unsaved = amber + `*` + `was …`; above max = red + `above max {max}` / `▲`;
  invalid = red + dotted underline + text; selected code = filled button + `aria-pressed="true"`; grade letters are
  text.
- **Contrast** (light theme; all ≥ 4.5:1 for text, ≥ 3:1 for borders and focus):
  | Token | Value | On | Ratio |
  |---|---|---|---|
  | text | `#1b1b1f` | `#ffffff` | ≈ 17:1 |
  | muted text | `#5b5e66` | `#ffffff` / `#f4f5f7` | 6.5:1 / 5.9:1 |
  | primary button | `#ffffff` on `#1558b0` | — | 6.9:1 |
  | danger / above max / A button | `#b3261e` (text or bg with white) | `#ffffff` | 6.5:1 |
  | unsaved cell bg | `#fff1c2`, text `#1b1b1f` | — | 15:1 (red on it 5.8:1) |
  | unsaved mark `*`, L button bg | `#8a5a00` | `#ffffff` | 5.9:1 |
  | P button bg | `#1e6b34` with white | — | 6.5:1 |
  | X button bg | `#1558b0` with white | — | 6.9:1 |
  | focus ring | 3 px `#1558b0`, 2 px white offset | — | 6.9:1 |
  Dark theme (`prefers-color-scheme: dark`): bg `#121316`, text `#ececf0`, muted `#a9abb3`, danger `#ff8a80`,
  unsaved bg `#3d3214`, mark `#f2c14e`, accent `#8ab4f8` (buttons: text `#0b1b33` on `#8ab4f8`). Polish re-checks
  every pair with a contrast checker.
- **Fonts** (system only, no downloads): `font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
  "Sukhumvit Set", Thonburi, "Noto Sans Thai", "Leelawadee UI", Tahoma, sans-serif`. iOS and macOS fall back to
  Sukhumvit Set/Thonburi for Thai glyphs. `line-height: 1.5` (Thai upper and lower marks need room; inputs get enough
  padding that marks aren't clipped). Scores and IDs use `font-variant-numeric: tabular-nums`. Body 17 px on phone,
  15 px wide; **every input ≥ 16 px** so iOS doesn't zoom on focus. Sizes in `rem`.
- **Zoom**: viewport `width=device-width, initial-scale=1` without `maximum-scale` or `user-scalable=no`. Layout
  reflows at 200 % zoom (phone layout takes over below 960 px of CSS width).
- **Language**: `<html lang="en">`; any name, header or course name containing Thai script is wrapped in
  `lang="th"` so VoiceOver reads it in Thai.
- **Names and roles**: score input `aria-label="{header} for {name} {id}"` and `aria-describedby` → its sub-line and
  refusal message; attendance row `role="group"` `aria-label="Attendance {session} for {name} {id}"`, buttons
  `Present (P)`, `Late (L)`, `Absent (A)`, `Excused (X)`, `Clear`; table `role="grid"` with `aria-rowcount`,
  `aria-colindex`, headers as `columnheader`, frozen cells as `rowheader`; computed cells `aria-readonly="true"`;
  badge `aria-label="3 unsaved edits"`; icon buttons (`‹`, `›`, `⋯`, `×`) have text labels.
- **Live regions**: one polite region announces commits (`hw2 9 for นายสมมติ ทดสอบ, unsaved. 1 unsaved.`), save
  and undo results, fills; `role="alert"` for refusals, save failures and conflicts. Keystrokes are not announced.
- **Focus order** (phone column mode): back → course title → badge → More → column picker → previous/next column →
  search → Fill → rows (name button, then input, per row) → Save → tabs. Sheets and dialogs move focus to their title
  on open, trap it, and return it to the control that opened them. Destructive dialogs start on the safe button.
  Focus never moves on its own except after a commit (Next, a code tap, `ขส`), which the user asked for (3.2.1).
- **Motion**: scroll and sheet transitions ≤ 150 ms; none with `prefers-reduced-motion: reduce`.
- **No time limits**: banners with actions never auto-hide; the draft has no expiry.

### Copy table (web)
Variables in `{braces}`. Plurals per Formats.

| ID | Text |
|---|---|
| **Page and list** | |
| `page.title` | `grade_web` |
| `na.title` / `na.body` | `Not available` / `This page opens only for the Google account that owns it.` |
| `list.heading` | `Courses on Drive` |
| `list.loading` | `Loading courses…` |
| `list.empty` | `No pushed courses yet.` / `On the Mac, run grader web-push <course>, wait for Drive to finish uploading, then reload this page.` |
| `list.failed` | `Couldn't load the course list.` / `Check your connection, then try again.` |
| `list.pushed` | `Pushed {time}` |
| `list.journal` | `{n} edits not pulled · last saved {time}` |
| `list.journal0` | `No edits waiting to be pulled` |
| `list.olderPush` | `Some of these edits were saved while the latest push was syncing. They're kept; pull them on the Mac: grader web-pull` |
| `list.draft` | `● {n} unsaved on this device` |
| `list.unavailable` | `Unavailable` |
| **Unavailable reasons** (server `reason`/`message`) | |
| `why.noCourseJson` | `course.json is missing. Push the course again from the Mac: grader web-push` |
| `why.noPushJson` | `push.json is missing. Push the course again from the Mac: grader web-push` |
| `why.badJson` | `{file} is damaged (not valid JSON). Push the course again from the Mac: grader web-push` |
| `why.missingFile` | `{file} is missing. Push the course again from the Mac: grader web-push` |
| `why.noJournal` | `web_edits.jsonl is missing. Push the course again from the Mac: grader web-push` |
| `why.copies` | `Drive has duplicate files: {names}. See the README, "Duplicate files", then reload.` |
| `why.badJournal` | `web_edits.jsonl has damaged lines: {lines}. See the README, "Damaged journal", then reload.` (`{lines}` = line numbers, e.g. `3, 7`) |
| `why.readError` | `Couldn't read {file} from Drive. Try again in a minute.` |
| **Opening** | |
| `open.loading` / `open.sub` | `Opening {course}…` / `Reading the course from Drive` |
| `open.slow` | `Still working. Large courses take a little longer.` |
| `open.failed` | `Couldn't open {course}.` |
| `open.offline` | `You're offline. Connect, then try again.` |
| `open.busy` | `Drive is busy with a save from another device. Try again in a moment.` |
| `open.error` | `Google didn't answer. Try again in a moment.` |
| `open.cant` | `Can't open {course}.` |
| `btn.tryAgain` / `btn.back` / `btn.reload` | `Try again` / `Back to courses` / `Reload` |
| **Header and chrome** | |
| `hdr.pushed` | `Pushed {time}` (wide and course header add ` ({ago})`) |
| `hdr.notPulled` | `{n} edits not pulled` |
| `hdr.lastSaved` | `last saved {time}` |
| `hdr.badge` | `● {n} unsaved` |
| `hdr.saving` | `Saving {n} cells…` |
| `tab.scores` / `tab.attendance` / `tab.grading` / `view.table` | `Scores` / `Attendance` / `Grading` / `Table` |
| `btn.save` | `Save {n}` |
| `btn.fill` | `Fill…` (wide: `Fill… {header}`) |
| `more.drive` | `Drive: {n} edits not pulled` / `last saved {time}` (0: `Drive: no edits waiting to be pulled`) |
| `more.undo` | `Undo last save` / subtitle `{time} · {n} cells` |
| `more.undo.unsaved` | `Save or discard your {n} unsaved edits first` |
| `more.undo.none` | `Nothing to undo` |
| `more.undo.pulled` | `Already pulled to the Mac; use grader undo there` |
| `more.discard` | `Discard all unsaved edits ({n})` (0: `No unsaved edits`, disabled) |
| `more.reload` | `Reload from Drive` (status after: `Reloaded. Your {n} unsaved edits are kept.` or `Reloaded`) |
| `more.switch` | `Switch course` |
| `btn.close` / `btn.dismiss` | `Close` / `Dismiss` |
| **Draft and storage** | |
| `draft.restored` | `{n} unsaved edits restored ({age})` where `{age}` = `from {time}` or `from {time}, {ago}` |
| `draft.pushed` | `The course was pushed again since then; each edit is checked when you save.` |
| `draft.gone` | `{n} are for students or columns no longer in this course.` |
| `draft.already` | `Your draft from {time} is already on Drive; nothing to restore.` |
| `draft.review` / `draft.discard` | `Review` / `Discard…` |
| `storage.off` | `Unsaved edits can't be backed up in this browser. Save often: closing this tab loses them.` |
| `storage.more` | `Storage is blocked here (for example in a private window). Saved edits on Drive are safe.` |
| **Column mode** | |
| `col.label` / `col.pick` | `Column` / `Pick a column to enter scores.` |
| `col.option` | `{header} · {k}/{n}` |
| `col.line` | `{category} · max {max} · {k} of {n} entered` |
| `col.prev` / `col.next` | `Previous column` / `Next column` |
| `search.placeholder` / `search.label` | `Search ID or name` / `Search students` |
| `search.none` | `No students match "{text}".` + button `Clear search` |
| `row.was` | `was {value}` (`was blank`) |
| `row.overMax` | `above max {max}` |
| `row.invalid` | `not a number, counts as 0` |
| `row.open` | `Open {name} {id}` (aria) |
| `kb.absent` / `kb.clear` / `kb.next` / `kb.done` | `ขส` / `Clear` / `Next ↓` / `Done` |
| `col.end` | `End of list · {k} of {n} entered` |
| **Typed-value refusals** (S3.7, also Fill) | |
| `bad.comma` | `'{text}': use . for decimals ({suggestion})` (suggestion = text with the comma replaced, only when it is a single comma between digits; otherwise `'{text}': use . for decimals`) |
| `bad.negative` | `'{text}' is negative; scores start at 0` |
| `bad.other` | `'{text}' isn't a score. Use a number (8.5), ขส, or leave it blank.` |
| `bad.server` | `Drive refused '{text}' for {id} {column}: not a valid score.` (server `invalid` conflict; shown in the conflict list) |
| **Attendance** | |
| `att.label` | `Session` |
| `att.today` | `{session} · today` |
| `att.pick` | `Pick a session` |
| `att.noToday` | `No session is dated today ({weekday} {date}). Pick one above.` |
| `att.counts` | `P {n} · L {n} · A {n} · X {n} · EA {n} · blank {n}` (EA part only when > 0) |
| `att.none` | `This course has no attendance sessions. Add them on the Mac, then push again.` |
| `att.btn` | `P` `L` `A` `X` `Clear` (aria: `Present (P)`, `Late (L)`, `Absent (A)`, `Excused (X)`, `Clear`) |
| `att.invalid` | `not a code, counts as 0` |
| **Detail** | |
| `det.back` | `‹ {column}` (from Attendance: `‹ {session}`) |
| `det.prev` / `det.next` | `‹ Prev` / `Next ›` |
| `det.final` / `det.grade` / `det.ct` | `Final Score {n}` / `Grade {letter}` / `Coursework Total {n}` |
| `det.unsaved` | `Includes {n} unsaved edits` |
| `det.cat` | `{category}` + `{weighted} of {w}` |
| `det.noCols` | `no columns` |
| `det.dropped` | `dropped` |
| **Table** | |
| `tbl.id` / `tbl.name` | `Student ID` / `Name` |
| `tbl.cat` | `{category} /{w}` |
| `tbl.ct` / `tbl.final` / `tbl.grade` | `Coursework Total` / `Final Score` / `Grade` |
| `tbl.building` | `Building the table…` |
| `tbl.none` | `No students match "{text}"` |
| **Fill** | |
| `fill.title` | `Fill {header}` |
| `fill.cells` / `fill.empty` / `fill.whole` | `Cells` / `Only empty cells` / `Whole column` |
| `fill.value` | `Value` |
| `fill.count` | `→ {n} cells will change` |
| `fill.ea` | `Includes {n} EA cells.` |
| `fill.search` | `Fill covers all {n} students, not only the ones your search shows.` |
| `fill.needValue` | `Type a value, or tap ขส.` |
| `fill.go` / `fill.zero` / `btn.cancel` | `Fill {n} cells` / `Nothing to change` / `Cancel` |
| `fill.done` | `Filled {n} cells (unsaved)` |
| **Save** | |
| `save.title` | `Save {n} cells?` |
| `save.colLine` | `{header}  {n} cells` + `, {m} above max` when m > 0 |
| `save.cellLine` | `{id} {name}: {was} → {new}` |
| `save.overMax` | `{m} is above max; it will be saved as typed.` (plural: `{m} are above max; they will be saved as typed.`) |
| `save.gone` | `{n} can't be saved: student or column not in this course.` + `Drop these {n}` |
| `save.go` / `save.keep` / `save.discardAll` | `Save {n} cells` / `Keep editing` / `Discard all…` |
| `save.ok` | `Saved {n} cells ({f} files)` |
| `save.conflicts` | `Saved {n} cells · {c} changed elsewhere, not saved: {id} {column} (now {value}), …` (first 3, then ` and {k} more` + `Show all`) |
| `save.notFound` | ` · {k} not found (student or column not in this course): {id} {column}, …` |
| `save.pushChanged` | `Some edits were made before the latest push; they were checked against the new data.` |
| `save.nothing` | `Nothing to save: Drive already has these values` |
| `conf.title` | `Changed elsewhere, not saved ({n})` |
| `conf.line` | `{column}   Drive now {value} · yours {mine}` + `Go to` |
| `conf.help` | `These stay unsaved. Save again to write your values, or change them first.` |
| `fail.offline` | `Save failed: you're offline. Your {n} edits are kept.` + `Retry` |
| `fail.busy` | `Another save is running; try again. Your {n} edits are kept.` + `Retry` |
| `fail.auth` | `Signed out of Google. Sign in again; your edits are kept.` + `Sign in` |
| `fail.other` | `Save failed: Google didn't finish the save. Your {n} edits are kept.` + `Retry` |
| `fail.unavailable` | `Not saved: {reason} Your {n} edits are kept on this device.` + `Back to courses` (`{reason}` = a `why.*` text) |
| **Discard, Undo, Leave** | |
| `disc.title` / `disc.body` | `Discard {n} unsaved edits?` / `They were never saved to Drive and can't be brought back.` |
| `disc.keep` / `disc.go` / `disc.done` | `Keep edits` / `Discard {n} edits` / `Discarded {n} edits` |
| `undo.title` | `Undo save of {time}, {n} cells?` |
| `undo.line` | `{id} {column}: {value} → {original}` (`blank` for empty), up to 10 from `undo.edits` |
| `undo.more` | `and {k} more` (`k` = `undo.cells` − 10, only when > 0) |
| `undo.body` | `Drive gets the earlier values back. Cells changed since then are left alone.` |
| `undo.go` | `Undo save` |
| `undo.working` | `Undoing save of {time}…` |
| `undo.ok` | `Undid save of {time}: {n} cells restored` |
| `undo.partial` | `Undid {n} of {m} cells · {c} changed since, left as is: {id} {column} (now {value}), …` |
| `undo.noneDone` | `Nothing undone · {c} changed since, left as is: {id} {column} (now {value}), …` |
| `undo.changed` | `Another device saved since this page loaded. Reload to see the newest save, then try again.` + `Reload` |
| `leave.title` / `leave.body` | `{n} unsaved edits in {course}` / `They stay on this device as a draft if you leave without saving.` |
| `leave.config` | `Weights not saved.` / `Boundaries not saved.` |
| `leave.keep` / `leave.go` / `leave.save` | `Keep editing` / `Leave, keep draft` / `Save and leave` |
| **Grading** | |
| `cfg.weights` / `cfg.bounds` | `Weights` / `Grade boundaries (highest first)` |
| `cfg.fRow` | `below {lowest}` |
| `cfg.sum1` / `cfg.sumOff` | `Weights sum to 1` / `weights sum to {sum}` (with `⚠`) |
| `cfg.preview` / `cfg.preview0` | `With these weights {n} grades change.` (boundaries: `With these boundaries…`) / `No grade changes.` |
| `cfg.previewLine` | `{id} {name}: {old} → {new}` |
| `cfg.nan` | `{field}: '{text}' isn't a number (e.g. 0.25)` |
| `cfg.comma` | `{field}: use . for decimals ({suggestion})` |
| `cfg.negative` | `{field}: can't be negative` |
| `cfg.empty` | `{field}: enter a number (0 is allowed)` |
| `cfg.order` | `{letter} {value} must be lower than {upper} {upperValue}` |
| `cfg.saveW` / `cfg.saveB` / `cfg.reset` | `Save weights` / `Save boundaries` / `Reset` |
| `cfg.savingW` / `cfg.savingB` | `Saving weights…` / `Saving boundaries…` |
| `cfg.okW` / `cfg.okWwarn` / `cfg.okB` | `Weights saved. Totals and grades updated.` / `Weights saved (they sum to {sum}). Totals and grades updated.` / `Boundaries saved. Grades updated.` |
| `cfg.stale` | `{Weights|Boundaries} were changed on another device after you opened them. Nothing was saved.` |
| `cfg.staleNow` | `On Drive now: {key} {value}, …` |
| `cfg.useDrive` / `cfg.keepMine` | `Use Drive values` / `Keep mine` |
| `cfg.noUndo` | `Undo last save doesn't cover weights or boundaries: change them back here.` |

### Terminal: `grader web-push` and `grader web-pull`
Style follows the existing `grader` output: a `🔄` heading line, two-space indented detail lines with `✍️`/`⏭`/`📦`
markers, `⚠️` warnings, `❌` errors on stdout, and a final `✅` line that names the next command or the undo
command. No ANSI colour. Paths are shown relative to the course folder or to `My Drive/` (the full path when
`--drive-root` points somewhere else). Columns are padded by display width (count characters whose
`unicodedata.category` is not `Mn`/`Me`/`Cf`, so Thai marks don't break alignment). Lines stay within 80 columns
except Thai names and long paths. Times print as `20 Jan 2027 09:15`. Unexpected exceptions print
`❌ Unexpected error: {message}. Run again with --debug for the details.` and exit 1.

#### `grader -h` (lines added to the command list)
```
    web-push            Copy a course to Google Drive for the grade_web app (phone or browser)
    web-pull            Bring grade_web edits back into the course (preview; --yes applies)
```

#### `grader web-push -h`
```
usage: grader web-push [-h] [--force] [--semester NAME] [--drive-root DIR] [--debug] [COURSE]

Copy a course to Google Drive (My Drive/grade_courses/<semester>/<course folder>/, the semester
being the folder the course sits in on the Mac). The grade_web app lists it once My Drive/
grade_web/ has a shortcut to that semester folder. Reads the course and never writes into it.
Refuses while web edits are waiting to be pulled, so nothing made on the phone is lost.

positional arguments:
  COURSE            Course folder (default: the folder you're in, if it has course_info/)

options:
  -h, --help        show this help message and exit
  --force           Push even if web edits are waiting to be pulled. They are kept in
                    <course>/archive/ on Drive marked as discarded, never deleted
  --semester NAME   Semester folder on Drive (default: the name of the folder the course is in,
                    e.g. 2569-1). The folder above it is $GRADE_WEB_COURSES, else grade_courses
  --drive-root DIR  Your "My Drive" folder (default: $GRADE_WEB_DRIVE_ROOT, else the Google Drive
                    for Desktop folder of your @g.cmru.ac.th account)
  --debug           Show the full traceback on unexpected errors

examples:
  grader web-push                                   # inside 9_ฟิสิกส์จำลอง_grading/
  grader web-push courses/9_ฟิสิกส์จำลอง_grading
  grader web-pull                                   # later: see what the web changed
```

#### `grader web-pull -h`
```
usage: grader web-pull [-h] [-y] [--drive-root DIR] [--debug] [COURSE]

Bring the edits made in the grade_web app back into the course. Without --yes it only shows
what would change. Cells changed on the Mac since the push keep the Mac value (listed as
conflicts). Everything it writes is one history entry: grader undo puts it all back.

positional arguments:
  COURSE            Course folder (default: the folder you're in, if it has course_info/)

options:
  -h, --help        show this help message and exit
  -y, --yes         Apply the changes (default: preview only, nothing written)
  --drive-root DIR  Your "My Drive" folder (default: $GRADE_WEB_DRIVE_ROOT, else the Google
                    Drive for Desktop folder of your @g.cmru.ac.th account)
  --debug           Show the full traceback on unexpected errors

examples:
  grader web-pull                 # preview, inside the course folder
  grader web-pull --yes           # apply
  grader undo                     # take the whole pull back
```

#### Sample session: push (fixture, empty Drive root)
```
$ cd courses/9_ฟิสิกส์จำลอง_grading && grader web-push
🔄 Web push: 9_ฟิสิกส์จำลอง_grading → My Drive/grade_courses/2569-1/9_ฟิสิกส์จำลอง_grading/
   ฟิสิกส์จำลอง (MOCK, 2027_S1) · 3 students · 8 counted columns
  ✍️  course.json
  ✍️  course_info/9_ฟิสิกส์จำลอง_student_info.csv
  ✍️  data/9_ฟิสิกส์จำลอง_attendance.csv
  ✍️  data/9_ฟิสิกส์จำลอง_final.csv
  ✍️  data/9_ฟิสิกส์จำลอง_homework.csv
  ✍️  data/9_ฟิสิกส์จำลอง_midterm.csv
  ✍️  web_edits.jsonl (new, empty)
  ✍️  push.json (p-20270119-201500)
  ⏭  Not copied: data/9_ฟิสิกส์จำลอง_attendance.xlsx (the web edits the csv), history/, reports/
✅ Pushed 19 Jan 2027 20:15. 0 edits waiting to be pulled.
   Wait until Drive for Desktop shows "up to date", then open grade_web on your phone.
   Bring web edits back with: grader web-pull
```
Variants inside the same layout:
- Existing mirror: second line adds `   Replacing the copy pushed 18 Jan 2027 08:00.` and the journal line reads
  `  ⏭  web_edits.jsonl kept (0 edits not pulled)`.
- Stale file (S1.7): `  🗑️  Removed from Drive: data/9_ฟิสิกส์จำลอง_quiz.csv (no longer in the course)`.
- Duplicate ID (edge 6): `⚠️  data/9_ฟิสิกส์จำลอง_homework.csv: Student ID 9900000002 is on 2 rows. The web shows it
  once and a save sets both rows.`

#### Sample session: push refused, unpulled edits (S1.3), then `--force` (S1.4)
```
$ grader web-push
🔄 Web push: 9_ฟิสิกส์จำลอง_grading → My Drive/grade_courses/2569-1/9_ฟิสิกส์จำลอง_grading/
❌ 3 web edits haven't been pulled yet (last saved 20 Jan 2027 09:15):
     9900000001  20 Jan 2027   (blank) → P     20 Jan 2027 09:15
     9900000002  20 Jan 2027   (blank) → A     20 Jan 2027 09:15
     9900000002  hw2           (blank) → 8.5   20 Jan 2027 09:15
   Bring them in first:  grader web-pull         (preview, then --yes)
   Or drop them:         grader web-push --force (kept in archive/, marked discarded)
   Nothing on Drive was changed.
$ echo $?
1
$ grader web-push --force
🔄 Web push: 9_ฟิสิกส์จำลอง_grading → My Drive/grade_courses/2569-1/9_ฟิสิกส์จำลอง_grading/
⚠️  3 web edits not pulled are dropped from this push. They are kept in
    archive/web_edits_20270121-175500_discarded.jsonl
   ฟิสิกส์จำลอง (MOCK, 2027_S1) · 3 students · 8 counted columns
  ✍️  … (as above)
✅ Pushed 21 Jan 2027 17:55. 0 edits waiting to be pulled.
```
A config line in the list prints as `     weights       homework 0.2 → 0.25, final 0.4 → 0.35   20 Jan 2027 09:30`.

#### Sample session: pull preview, then apply (S11.1-S11.9)
Journal: 7 unpulled lines (two attendance codes, hw2 for `9900000001` blank → 9 while the Mac now has 7, hw2 for
`9900000002` blank → 9 then 9 → 8, a weights line, and a line for `9900000099`).
```
$ grader web-pull
🔄 Web pull: My Drive/grade_courses/2569-1/9_ฟิสิกส์จำลอง_grading/ → 9_ฟิสิกส์จำลอง_grading
   ฟิสิกส์จำลอง (MOCK, 2027_S1) · pushed 19 Jan 2027 20:15 (p-20270119-201500)
   Journal: 7 edits not pulled · last saved 20 Jan 2027 09:45
   (grade_web shows the same two numbers. If not, wait for Drive to sync and run again.)

By column:
  20 Jan 2027   2 to apply
  hw2           1 to apply · 1 conflict · 1 skipped
  weights       1 to apply

To apply (Mac value → web value):
  9900000001 20 Jan 2027: (blank) → P
  9900000002 20 Jan 2027: (blank) → A
  9900000002 hw2: (blank) → 8
  weights: homework 0.2 → 0.25, final 0.4 → 0.35

Not applied (Mac values kept):
  conflict: 9900000001 hw2 — Mac 7, web 9 (not applied)
  skipped: 9900000099 hw2 — student not in Mac files

Already applied: 0 · No change: 0 · Replaced by a later edit: 1

Preview only: nothing was written. Apply with: grader web-pull --yes
$ grader web-pull --yes
… (the same preview, without its last line) …
  ✍️  data/9_ฟิสิกส์จำลอง_attendance.csv: 2 cells (attendance xlsx too)
  ✍️  data/9_ฟิสิกส์จำลอง_homework.csv: 1 cell (total column refreshed)
  ✍️  course_info/9_ฟิสิกส์จำลอง_config.yaml: weights
  📦 Archived on Drive: archive/web_edits_20270121-180000.jsonl (7 lines)
✅ Pulled 3 cells and weights. 1 conflict and 1 skipped are listed above (Mac values kept).
   Undo with: grader undo 20270121-180000_grader_web-pull
```
Line formats used in the lists:
| Result | Line |
|---|---|
| apply (cell) | `  {id} {column}: {mac} → {web}` |
| apply (config) | `  {part}: {key} {mac} → {web}, …` (changed keys only) |
| conflict (cell) | `  conflict: {id} {column} — Mac {mac}, web {web} (not applied)` |
| conflict (config) | `  conflict: {part} — Mac {k v, …}, web {k v, …}; apply by hand if wanted` (all keys, S11.12) |
| skipped | `  skipped: {id} {column} — student not in Mac files` / `column not in Mac files` / `total column` |
| already applied | `  already applied: {id} {column} = {value}` (listed after the summary line) |
| no change | `  no change: {id} {column} (edited back to {value})` |
`{part}` prints as `weights` or `grade boundaries`. Superseded lines are only counted ("Replaced by a later edit").

#### Terminal messages (every one ends with what to do next)
| Trigger | Output | Exit |
|---|---|---|
| No `COURSE`, cwd not a course folder (S1.11, S11.16) | `usage: grader web-push [-h] [--force] [--drive-root DIR] [--debug] [COURSE]` / `grader web-push: error: no course folder here; give one, e.g. grader web-push courses/9_ฟิสิกส์จำลอง_grading` (same for web-pull) | 2 |
| `COURSE` isn't a course folder | `❌ {path} is not a course folder (no course_info/).` | 1 |
| Drive root missing (S1.9, edge 18) | `❌ Drive folder not found: {path} (is Drive for Desktop running?). Nothing was written. Start it, or pass --drive-root DIR.` | 1 |
| No CMRU Drive folder found | `❌ No Google Drive folder for an @g.cmru.ac.th account under ~/Library/CloudStorage/. Start Drive for Desktop, or pass --drive-root DIR.` | 1 |
| Several found | `❌ Found 2 Google Drive folders: {a}, {b}. Choose one with --drive-root DIR (or set GRADE_WEB_DRIVE_ROOT).` | 1 |
| Config missing / bad YAML (edge 7) | `❌ No config in course_info/ (expected 9_ฟิสิกส์จำลอง_config.yaml). Nothing was pushed.` / `❌ course_info/{file} can't be read: {yaml error with line}. Fix it, then push again.` | 1 |
| Not UTF-8 (S1.6, edge 3) | `❌ data/{file} is not UTF-8 text (byte 0x{xx} at position {n}; saved by Excel as Thai?). Save it as "CSV UTF-8", then push again.` | 1 |
| No `Student ID` (edge 7) | `❌ data/{file} has no 'Student ID' column (header: {first 3 headers}…). Fix the header, then push again.` | 1 |
| No students (edge 8) | `❌ data/{file} has no students (header only). Add them with grader update, or remove the file, then push again.` (roster: `❌ course_info/{file} has no students.`) | 1 |
| `.xlsx` score files (S1.10, edge 11) | `❌ grade_web reads score files as CSV only: data/9_ฟิสิกส์จำลอง_quiz.xlsx. Keep those scores in a .csv file, then push again. Nothing on Drive was changed.` (one file per line when several) | 1 |
| Attendance pair needs sync (S1.5) | `❌ The attendance xlsx and csv differ: run \`grader sync\` first, then grader web-push again. Nothing on Drive was changed.` followed by the `grader sync` preview lines (e.g. `  9900000002 20 Jan 2027: xlsx P / csv A`) | 1 |
| Conflict copies (edge 17) | `❌ Drive has duplicate files in grade_web/9_ฟิสิกส์จำลอง_grading/: web_edits (1).jsonl. Fix them as the README's "Duplicate files" says, then run again.` | 1 |
| Journal unreadable (edge 19) | `❌ Couldn't read grade_web/9_ฟิสิกส์จำลอง_grading/web_edits.jsonl ({error}). If Drive for Desktop shows it as online-only, wait for it to download, then run again.` | 1 |
| Invalid journal lines (S11.13, edge 29) | `❌ web_edits.jsonl has lines that aren't valid JSON: 3, 7. Nothing was applied, archived or pushed. See the README, "Damaged journal".` | 1 |
| Unpulled edits at push | see sample session | 1 |
| `--force` | see sample session | 0 |
| Mirror missing at pull | `❌ 9_ฟิสิกส์จำลอง_grading hasn't been pushed: My Drive/grade_courses/2569-1/9_ฟิสิกส์จำลอง_grading/ doesn't exist. Push it with: grader web-push` | 1 |
| Other course on Drive (S11.14, edge 20) | `❌ The Drive copy is another course: Drive has MOCK 2027_S1, this folder is PHYS1120 2027_S2. Nothing was pulled. Check the folder names.` | 1 |
| Nothing to pull (S11.10) | `✅ Nothing to pull: no web edits since the last pull.` | 0 |
| Only already-applied lines, preview | `Nothing to change on the Mac: all {n} edits are already applied. Run grader web-pull --yes to mark them pulled.` | 0 |
| Only already-applied lines, `--yes` (edge 28) | `  📦 Archived on Drive: archive/web_edits_{ts}.jsonl ({n} lines)` / `✅ Nothing to change on the Mac ({n} already applied).` (no history entry) | 0 |
| xlsx open in Excel, `--yes` (S11.15) | preview, then `❌ Not applied: data/9_ฟิสิกส์จำลอง_attendance.xlsx is open in Excel. Close it, then run grader web-pull --yes again. Nothing was written.` | 1 |
| Pair needs sync, `--yes` (S11.15) | preview, then `❌ Not applied: the attendance xlsx and csv differ; run \`grader sync\` first, then grader web-pull --yes again. Nothing was written.` | 1 |
| `apply_edits` error mid-pull | `❌ Pull stopped while writing {file}: {error}. What was written can be undone: grader undo {id}. Nothing was archived; run grader web-pull --yes again to finish.` | 1 |
| Archive write failed | `⚠️  Applied on the Mac (undo with: grader undo {id}) but not archived on Drive: {error}.` / `   Run grader web-pull --yes again: it finds the cells already applied and only archives.` | 1 |
| Preview without TTY, no `--yes` | Same preview as with a TTY | 0 |

#### Exit codes
`0` done or preview · `1` refused or failed (nothing written unless the message says so) · `2` usage error.

## Test plan
Written by app-tester (mode `plan`). The tests encode REQUIREMENTS and the Interface above (exact copy strings,
exit codes, file formats), not one implementation. Every test reads only `web/tests/fixtures/` and tmp folders.

### Layers and commands
Run from the grade_dashboard repo root.

| Layer | Runner | Files | What it proves |
|---|---|---|---|
| 1. Pure JS units | `node --test 'web/tests/*.test.js'` | `grades`, `csv`, `validate`, `journal`, `save`, `fill`, `config` `.test.js` | Grade parity with grade-tui (golden), cell rules, CSV parse/splice bytes, journal keys/trim/undo target, save/config plans, fill counts |
| 1b. Server harness | same command | `server.test.js` + `web/tests/gas_fake.js` | `Code.js` + `drive.js` + the pure modules, loaded in `node:vm` with Apps Script services faked over a tmp dir: the five server functions and `doGet` (Interface "Apps Script server API"), roll-forward, trim, availability, lock, logs |
| 2. Mac CLI | `python3 -m pytest tests/` | `test_web_push.py`, `test_web_pull.py`, `test_web_golden.py`, `test_web_fixtures.py`, `test_web_hygiene.py` + all existing files unchanged | S1, S11, golden drift, fixture integrity, repo hygiene (S13.3), and the existing suite still green |
| E2E | `bash web/scripts/e2e.sh` | `web/scripts/e2e.sh`, `web/scripts/gas_run.js` | Real `grader web-push` → real `Code.js` saves over the same tmp Drive dir → `web-pull` preview/`--yes` → grade-tui's loader shows the S4.1 values → `grader undo` byte for byte |
| 3. Manual | iPhone Safari + Mac browser | checklist M1-M26 below | What Apps Script and a real phone alone can show: deploy and access, LockService under real concurrency, drafts after a killed tab, keypad bar, session expiry, 4G timings |

**Node command:** `node --test web/tests/` (a directory argument) **fails on Node 24**: the runner treats the
directory as one test file (checked 2026-10-18 with v24.2.0). Use `node --test 'web/tests/*.test.js'` (quoted, so
Node expands the glob). Helper files (`helpers.js`, `gas_fake.js`) don't end in `.test.js` and aren't run as tests.

**Naming:** pytest `test_ac<story>_<n>_<slug>` (`test_ac11_4_mac_change_is_conflict`), edge tests
`test_edge<k>_<slug>`. Node `test('ac<story>_<n> <slug>', …)` / `test('edge<k> <slug>', …)`. Fixture self-checks and
golden drift have plain names.

### Fixtures (`web/tests/fixtures/`, committed, deterministic)
Rules (data-safety §1): invented Thai-looking names, IDs starting `99` (10 digits as in REQUIREMENTS, plus one
11-digit ID for edge 5), no `6920…` IDs, no `history/` folder anywhere (the parent `.gitignore` drops it; tests build
baselines in tmp), no `.xlsx` committed (the attendance xlsx is built at test time from the csv codes with
`grader.save_attendance_excel`, as `tests/test_attendance.py::att` does). Every stored `total` cell already follows
INTEGRATION.md's total rule and the attendance total follows `attendance.att_total`, so loading a fixture copy changes
no data byte (checked by `test_web_fixtures.py`).

#### F1 `9_ฟิสิกส์จำลอง_grading/`: the REQUIREMENTS course (push-time state)
Config `course_info/9_ฟิสิกส์จำลอง_config.yaml`:
```yaml
course_id: MOCK
course_name: ฟิสิกส์จำลอง
term: 2027_S1
term_start_date: 2027-01-13
weights: {attendance: 0.1, homework: 0.2, midterm: 0.3, final: 0.4}
data_mapping:
  attendance: [13 Jan 2027, 20 Jan 2027, 27 Jan 2027]
  homework: [hw1: 10, hw2: 10, hw3: 10]
  midterm: [midterm_exam: 30]
  final: [final_exam: 40]
grade_boundaries: {A: 80, B+: 75, B: 70, C+: 65, C: 60, D+: 55, D: 50}
rules: {drop_lowest_homework: true}
```
Files (UTF-8, LF, no BOM):
```
course_info/9_ฟิสิกส์จำลอง_student_info.csv
Student ID,Name,Class Group
9900000001,นายสมมติ ทดสอบ,SEC1
9900000002,นางสาวตัวอย่าง ใจดี,SEC1
9900000003,นายทดลอง มีชื่อ,SEC2

data/9_ฟิสิกส์จำลอง_attendance.csv
Student ID,Name,13 Jan 2027,20 Jan 2027,27 Jan 2027,total (3pts)
9900000001,นายสมมติ ทดสอบ,P,,L,1.8
9900000002,นางสาวตัวอย่าง ใจดี,P,,A,1
9900000003,นายทดลอง มีชื่อ,EA,,X,2

data/9_ฟิสิกส์จำลอง_homework.csv
Student ID,Name,hw1 (10pts),hw2 (10pts),hw3 (10pts),total (30pts)
9900000001,นายสมมติ ทดสอบ,8,,,8
9900000002,นางสาวตัวอย่าง ใจดี,10,,7,17
9900000003,นายทดลอง มีชื่อ,abs,,5,5

data/9_ฟิสิกส์จำลอง_midterm.csv
Student ID,Name,midterm_exam (30pts),total (30pts)
9900000001,นายสมมติ ทดสอบ,21,21
9900000002,นางสาวตัวอย่าง ใจดี,18,18
9900000003,นายทดลอง มีชื่อ,ขส,0

data/9_ฟิสิกส์จำลอง_final.csv
Student ID,Name,final_exam (40pts),total (40pts)
9900000001,นายสมมติ ทดสอบ,,0
9900000002,นางสาวตัวอย่าง ใจดี,,0
9900000003,นายทดลอง มีชื่อ,,0
```
(The exact total texts are whatever grade-tui writes for these cells; `test_web_fixtures.py` decides.)

Why this state: the REQUIREMENTS examples describe different moments of one course. F1 is the **push-time** state
that S3.3 (hw2 blank), S6.2/S6.5 (`20 Jan 2027` blank), S7.1 (after S3.3's `9`), S8.2, S9.1, S11.4 and S11.6 start
from. **S4.1's state is F1 plus exactly the S3.3 edit (`9900000001` hw2 = `9`) and the S6.2 edit (`9900000001`
`20 Jan 2027` = `P`)**: attendance P, P, L → 9.33; homework 8, 9, blank with hw3 dropped → 17; Coursework Total 27;
midterm 21; final 0; Final Score 48; F. Adding final_exam `28` gives 76 / B+ (S4.2). Other edges F1 carries: `EA`
kept (S6.3), `abs` in a file (S4.3), `ขส` (S4.3), drop-lowest ties (`9900000001` base hw2 = hw3 = 0 → `dropped`
`hw2`; `9900000002` 10, blank, 7 → `hw2`), the REQUIREMENTS Outputs example (`9900000001` hw2 → `9` makes
`total (30pts)` 8 → 17).

#### F2 `9_กลศาสตร์ทดลอง_grading/`: rounding, boundaries, codes, text, CSV shapes
Weights `attendance 0.1, homework 0.2, project 0.05, midterm 0.3, final 0.4` (sum **1.05**), drop-lowest **off**,
F1's boundaries. Columns: sessions `13 Jan 2027`, `20 Jan 2027`, `27 Jan 2027`; `hw1..hw3 (10pts)`;
`project1 (8pts)`; `midterm_exam (30pts)`; `final_exam (40pts)`. File shapes: roster with BOM; homework with
**BOM + CRLF**; project with CRLF; midterm with **no final newline**; others LF.

| ID | Name (as written in the CSV) | Attendance | hw1, hw2, hw3 | project1 | midterm | final | Exercises (verified 2026-10-18 with `calculate_final_grades`) |
|---|---|---|---|---|---|---|---|
| 9900000101 | นายกล้า ทดสอบ | P,P,P | 5,5,5 | 0 | 24 | 36 | Final Score **80 → A** (on a boundary) |
| 9900000102 | นางสาวแก้ว ทดสอบ | P,P,P | 5,5,5 | 0 | 24 | 35 | **79 → B+** (one below) |
| 9900000103 | นายขวัญ สมมุติ | P,P,P | 5,5,5 | 1 | 24 | 30 | project 0.625 → **0.62** (numpy half-to-even; `Math.round` gives 0.63); 75 → B+ |
| 9900000104 | นางสาวคำ ลองดู | L,A,A | 3,3.5,blank | blank | 25 | 22 | Coursework Total 7.000000000000001 → **7** (round2 before ceil; ceil alone gives 8); midterm 25.000000000000004 → **25**; final 22.000000000000004 → **22**; 54 → D |
| 9900000105 | นายงาม ใจเย็น | X,EA,`p` | `12`, `"8,5"`, blank | 8 | 30 | 40 | above max (`12`); comma stripping in files (`8,5` counts 85, INTEGRATION.md classify); lowercase `p` counts 0 |
| 9900000106 | `"นายสมมติ, ทดสอบหก"` | A,P,L | `ข ส`, `12a`, 4 | blank | `ขส` | blank | invalid text, `ขส`; name with a comma (quoted field) |
| 9900000107 | `"นางสาว ""ฝน"" ตัวอย่าง"` | A,A,A | 8.25, blank, blank | 2 | 0 | 0 | name with doubled quotes; decimal score |
| 9900000108 | นายเงียบ ไม่มีแถว | (no row) | (no row) | (no row) | (no row) | (no row) | in the roster only: every cell counts 0 |
| 9900000109 | นายนอก ทะเบียน | — | 6,6,6 (homework file only) | — | — | — | not in the roster: row from a data file, name from that file |

#### F3 `9_ไฟฟ้าจำลอง_grading/`: points defaults and the loader's rules
Weights `attendance 0.1, lab 0.15, quiz 0.1, homework 0.2, project 0.1, final 0.3, participation 0.05, extra 0.0`
(sum 1.0), drop-lowest **on**. `data_mapping` has **no `attendance`** (auto-detected from the csv). Config:
```yaml
data_mapping:
  lab: [1, 2, 3, 4, 5: 20, 6, 7, 8, 9, 10, 11, 12]        # built-in lab default 10: bare headers 1..12, "5 (20pts)"
  quiz: {pts_each: 4, columns: [q1, q2, q3, q4: 6]}         # bare q1..q3, "q4 (6pts)"
  homework: {total_pts: 50, columns: [hw1: 10, hw2, hw3]}   # header "hw1 (15pts)" overrides config 10; hw2, hw3 bare
  project: [p1, p2]                                         # no points anywhere: weight-derived 5 each
  extra: [x1]                                               # weight 0: no derived max, grade-tui uses 100
  final: [final_exam: 30]
# participation (weight 0.05) has no data_mapping entry: weight but no columns
```
Attendance csv sessions are placeholders `a1, a2, a3, a4` + `total (4pts)`. Students `9900000201`-`9900000205` and
`99000002061` (11 digits: text order puts it after `9900000206`-like prefixes, never as a number). Rows:
`9900000201` has homework 12, 2, 2.5 and one-decimal values in all 12 lab columns (7.3, 8.6, 9.1, 6.4, 15.7, 8.8, 7.7, 9.9, 6.6, 8.2, 7.1, 9.4:
not exactly representable, so the summation order of a 12-column category matters); `9900000202` homework 7.5, 1.25,
2.5 (ratios 0.5, 0.5, 1.0: **tie, hw1 dropped**); `9900000203` all homework and lab blank (all-zero tie: hw1 dropped),
attendance A, A, A, A; `9900000204` hw3 the unique lowest, quiz q1 `5` (above the 4-point default); `9900000205`
codes P, L, X, EA, x1 `50`; `99000002061` codes EA, EA, blank, P. hw2/hw3 maxima resolve to (20 − 15) / 2 = 2.5 each
and `total_pts` 50 raises homework's possible max (per student after the drop).

#### F4 `9_ดาราศาสตร์จำลอง_grading/`: legacy shapes, no attendance
Weights `homework 0.3, quiz 0.2, midterm 0.2, final 0.3`, drop-lowest **on** with a **single** homework column
`hw1 (20pts)` (rule doesn't apply: `dropped` null). Quiz file with bare headers `quiz1,quiz2` (no points in config)
and a **legacy sentinel first row** `Full Score,,10,5,…` (max from that row). No attendance weight or file (the web
shows `att.none`). Students `9900000301`-`9900000303`. If grade-tui's loader can't round-trip the sentinel file
(totals rewrite), drop the sentinel from F4 and record it here at build time.

#### S12.2 coverage (each item has a fixture and a literal check)
| S12.2 item | Where | Literal assert (in `test_web_golden.py::test_ac12_2_fixture_set_covers_hazards`, on the golden file) |
|---|---|---|
| drop_lowest on / off | F1, F3 / F2 | node checks `dropped` (F1 `9900000001` `hw2`, F3 `9900000202` `hw1`, F4 null) |
| `total_pts` | F3 homework | course.json `total_pts.homework` = 50; `9900000201` (hw 12, 2, 2.5: ratios 0.8, 0.8, 1.0, hw1 dropped) has `pct.homework` 1.8 = 4.5 / 50 x 20, not 4.5 / 5 x 20 |
| `pts_each`, built-in `lab`, bare headers | F3 | course.json `max_scores`: `1`..`12` = 10 except `5` = 20; `q1`..`q3` = 4, `q4` = 6 |
| header overrides config | F3 `hw1 (15pts)` | `max_scores.hw1` = 15 |
| no points anywhere (weight-derived, else 100) | F3 `p1`, `p2`, `hw2`, `hw3`, `x1` | course.json has **no** max for `p1`, `p2`, `hw2`, `hw3`, `x1` (the JS fills them); golden reflects 5, 5, 2.5, 2.5, 100 |
| attendance auto-detected | F3 | course.json `data_mapping.attendance` = `a1..a4` |
| codes P/L/A/X/EA, blank | F1, F2, F3 | covered by golden values |
| `ขส` | F1, F2 | golden |
| invalid text `abs`, `ข ส`, `12a` | F1, F2 | golden |
| above max | F2 `12`, F3 q1 `5` | golden |
| exact `x.xx5` rounding | F2 `9900000103` | `pct.project` = 0.62 |
| just above a whole number (ceiling) | F2 `9900000104` | `coursework_total` 7, `pct.midterm` 25, `pct.final` 22 |
| boundary 80 → A, 79 → B+ | F2 `9900000101`/`102` | 80 A / 79 B+ |
| weights not summing to 1.0 | F2 (1.05) | golden |
| category with weight, no columns | F3 participation | `pct.participation` = 0 |
| category of ≥ 9 columns (summation order) | F3 lab (12) | golden |
| extra hazards | F2/F3/F4 | comma stripping, roster-only and file-only students, 11-digit ID order, sentinel row, BOM/CRLF/no final newline, quoted names |

#### Other committed fixtures
- `web/tests/fixtures/csv/`: `bom_crlf_quotes.csv`, `embedded_newline.csv` (a quoted name with a line break),
  `short_rows.csv` (rows shorter than the header), `no_final_newline.csv`, `padded_ids.csv` (` 9900000001 ` with
  spaces), `duplicate_ids.csv` (one ID on two rows). Used by `csv.test.js` and `save.test.js`.
- `web/tests/fixtures/journals/` (read by **both** `journal.test.js` and `test_web_pull.py`; `push` fields are
  rewritten to the current push id by the pytest helper when a test needs it):

  | File | Lines | Used for |
  |---|---|---|
  | `seven_lines.jsonl` | The "Sample session: pull" journal: `20 Jan 2027` P (`…0001`) and A (`…0002`); hw2 `…0001` blank → 9; hw2 `…0002` blank → 9 then (later batch) 9 → 8; weights 0.2/0.4 → 0.25/0.35; hw2 `9900000099` blank → 5. Last line 2027-01-20 09:45 | S11.1 exact preview, S11.3, S11.5, S11.6 |
  | `four_lines.jsonl` | `20 Jan 2027` P/A, hw2 `…0001` blank → 9, midterm_exam `…0002` 18 → 20 | S11.2, S11.8, S11.9 |
  | `three_unpulled.jsonl` | The S1.3 sample: P, A, hw2 `…0002` blank → 8.5 (09:15) | S1.3, S1.4 |
  | `net_change.jsonl` | hw2 `…0001` blank → 9, later 9 → 8; hw3 `…0002` 7 → 5, later 5 → 7 (edited back) | S11.6, edge 24 |
  | `duplicates.jsonl` | One cell line twice with the same `batch#seq`, and a second batch setting the same value | S11.7, edge 35 |
  | `truncated.jsonl` | 5 lines, line 3 cut mid-object | S11.13, edge 29, web availability |
  | `config_weights.jsonl`, `config_boundaries.jsonl` | weights 0.2/0.4 → 0.25/0.35; boundaries A 80 → 78; plus a two-line variant for the same part (net change) | S11.11, S11.12, edge 32 |
  | `unknown.jsonl` | `9900000099` hw2, `9900000001` hw9, `9900000001` `total (30pts)`, plus one good line | S11.5, edge 25 |
  | `undo_batches.jsonl` | Save A 09:00 (2 cells), save B 09:15 (2 cells), config batch 09:20, undo of B 09:30, a save on an older push id | S9.5, edge 43, `older_push` |
  | `archive_pull_4.jsonl` | An archive file (header `kind: pull` + the first 4 keys of `seven_lines`, with results) | unpulled/trim on both sides |
  | `from_web.jsonl` | The exact text `save.js`/`journal.js` produce for the S8.1 batch on F1 with a fixed clock and batch id. `save.test.js` asserts the module output equals this file byte for byte; `test_web_pull.py` pulls it cleanly | the journal contract across languages |
  | `expected.json` | Per journal: line count, bad line numbers, unpulled count against `archive_pull_4.jsonl`, last save time | asserted by both node and pytest, so both sides read journals the same way |
- `web/tests/fixtures/variants.json`: golden variants (below).

#### Generated at test time (never committed)
- Temp course copies (`tmp_path`), the attendance xlsx + `history/attendance_sync.json` baseline (via
  `grader.save_attendance_excel` + `grader.sync_cmd(course, yes=True)`), fake Drive roots, fake HOME folders.
- `web/tools/make_big_fixture.py --out <tmp>`: 300 students x 80 counted columns (seeded, IDs `99…`), for the S2.5/S8.9
  proxies and the manual speed checks (`web/out/`, git-ignored).

### Golden files (`web/tools/make_golden.py`, T4)
- For each of F1-F4: copy the fixture to a temp dir, `build_course_json(copy)` (the web-push builder), then
  `tui_api.get_course_data(copy)` on **another** temp copy (it writes totals and syncs attendance, so never on the
  fixture). Write `web/tests/golden/<fixture>.json` =
  `{course: <course.json>, expected: [{student_id, name, pct: {<cat>: number}, coursework_total, final_score, grade}],
  variants: [...]}`, students in Raw Details order. `pct` keys are every category in `weights`; midterm/final are the
  ceil'd integers grade-tui shows.
- **Variants** (`variants.json`): `{fixture, name, edits?: [{student_id, column, value}], weights?, grade_boundaries?}`.
  Python applies the edits with `tui_api.apply_edits` (grade-tui's writer) and the config with
  `update_course_config` on a temp copy, then `get_course_data`. Node applies the same edits as an **overlay of unsaved
  edits** and replaces `weights`/`grade_boundaries` in course.json. Variants: `s4_1_detail` (F1 + hw2 `9` + `20 Jan
  2027` `P` for `9900000001`), `s4_2_typed_final` (+ final_exam `28`), `s10_1_weights_edit` (F3, lab 0.2 /
  homework 0.15: weight-derived maxima change), `s10_4_boundaries_edit` (F2, A 78: `9900000102` becomes A).
- Also written: `golden/csv_rows.json` (every fixture CSV, and every file in `fixtures/csv/`, parsed by
  `csvio.read_csv_text`: header + rows as text) and `golden/canonical.json` (inputs `9`, `08`, `8.50`, `8.0`, `.5`,
  `5.`, `0`, ` 9 `, `ขส`, `""`, `P`, `0.1`, `12345678.9`, `0.30000000000000004`, `0.00001`, `10000000000000000.0` →
  `fmt_value(_cell_value(x))` and `classify(x)`).
- `--check` regenerates in memory and exits 1 on any difference. `tests/test_web_golden.py::test_golden_files_match_grade_tui`
  runs it, so a change to grade-tui's math or loader shows up as drift.

### Layer 1: node tests (pure modules)
Shared helper `web/tests/helpers.js`: load a golden file, read the fixture CSV texts named in `course.files` and
`course.roster`, build rows with `grades.mergeCourse`, apply an overlay.

| File | Tests (task) |
|---|---|
| `grades.test.js` (T4) | `ac12_1 golden parity <fixture>` ×4: every field of every student equals the golden with `assert.strictEqual` on numbers (no tolerance), and the student order and names match. `ac12_1 golden variants`: each variant. `ac4_1 detail values for 9900000001` (F1 + the two edits as overlay → `pct.attendance` 9.33, `pct.homework` 17, CT 27, midterm 21, final 0, Final 48, `F`). `ac4_2 typed 28 shows 76 B+`. `ac4_3 ขส and abs count 0`. `ac12_3 classify passes INTEGRATION cell table` and `ac12_3 total rule table`: both tables are **parsed from `INTEGRATION.md`** at test time (≥ 5 rows each, else the test fails), the total table summed over the mapped columns `a`, `b` only. `dropped is the pandas idxmin choice` (F1, F3 ties, F4 null). `round2 is numpy rint` (0.625 → 0.62, 0.125 → 0.12, 2.675 → 2.67, 0.875 → 0.88). `letterGrade uses sorted thresholds` (80 A, 79 B+, below 50 F, an unordered boundary dict). `fillDefaultMax uses current weights` (F3 project 5 → 7.5 after project 0.15). `ac2_5 computeGrades 300x80 under 1 s` (in-memory synthetic course; a proxy, not the 8 s target) |
| `csv.test.js` (T4 read, T7 splice) | `csv parse matches Python csv` for every file in `golden/csv_rows.json`. `edge1 BOM kept`, `edge2 CRLF kept`, `edge4 quoted names round-trip`. `ac8_6 splice changes only target spans`: for each fixture data file, splice one cell; every byte outside that field's span is identical, BOM/EOL unchanged; splicing into a short row pads with `,`. `splice of no targets returns identical bytes` (every fixture file) |
| `validate.test.js` (T6) | `ac3_7 allowed values`: `9`, `8.5`, `0`, `""`, `ขส`, `.5`. `ac3_7 comma refused`: `8,5` → reason `comma`. `ac3_7 negative refused`: `-3` → `negative`. `ac3_7 other refused`: `abc`, `ข ส`, `12a`, `1e5`, `8.5.1` → `other`. `ac3_5 above max accepted` (`12` is ok). `canonicalValue matches Python` for every `golden/canonical.json` entry (exact text for ordinary numbers; `sameCell` equality for the exotic ones). `sameCell compares by meaning` (`9.0`≡`9`, `" ขส "`≡`ขส`, `""`≡`" "`) |
| `journal.test.js` (T5, T7) | `journal contract matches expected.json` (every journal file). `edge29 bad line numbers` (`truncated.jsonl` → `[3]`). `ac2_1 summary counts unpulled and last save` (`seven_lines` + `archive_pull_4` → 3 unpulled, last 09:45). `trim removes only archived keys` (other lines, invalid lines byte-identical; idempotent). `edge17 conflictCopies` (`web_edits (1).jsonl`, `9_ฟิสิกส์จำลอง_homework (1).csv`, two same names; `notes (1).txt` that isn't an expected file → not reported). `ac9_5 undoTarget newest first` (`undo_batches`: B undone → target A; config batch and older-push batch never offered; undo batches never offered). `ac9_3 undoTarget none after pull` → null. `cellLines and configLine shape` (fields of SPEC "Journal", `seq` 0-based, `student_id` text, `ensure_ascii` off) |
| `save.test.js` (T7) | `ac8_1 planSave three cells in two files` (F1: hw2 ×2, midterm_exam ×1 → 3 changes, 2 files, one batch). `ac8_2 stale original is a conflict` (Drive `7`, edit original blank → `changed`, `now` 7; nothing spliced for it). `ac8_3 retry is all already` (plan again on the spliced texts → 0 changes, 3 `already`, no lines). `edge6 duplicate ID sets every row` (`duplicate_ids.csv`). `edge38 missing student or column is not found`. `invalid value is refused server-side`. `ac9_1 planUndo inverts the batch` (value ↔ original, `undoes` set). `ac9_2 planUndo skips a cell changed since` (one reverted, one conflict). `ac6_5 attendance P and A spliced` (F1 `20 Jan 2027`; `EA` cell untouched, S6.3). `from_web.jsonl is what save writes` (fixed clock and batch id) |
| `fill.test.js` (T9) | `ac7_1 only empty cells counts 2` (hw2 = overlay `9`, blank, blank; value `0`). `ac7_2 whole column counts 3` (value `10`; a cell already `10` not counted). `ac7_3 unsaved value counts as filled` (`9900000002` overlay `7`). `ac7_5 zero targets`. `ac7_4 fill value validated` (`8,5`, `-1`, `abc` refused). `ac6_6 fill P then one A gives 3 unsaved` (whole column `P` → 3 targets; then `A` for one student → overlay has 2 `P` + 1 `A`). `ac6_1 sessionDate and today's session` (`20 Jan 2027` on 2027-01-20 → preselected; 2027-01-21 → none; `a1` → no date) |
| `config.test.js` (T10) | `ac10_2 sum warning` (`weights sum to 1.05`, save allowed). `ac10_3 not a number names the field` (`0.2x` → `INVALID`, field `homework`; also `0,25`, `-1`, empty). `ac10_4 boundaries strictly descending in scale order` (A 78 accepted, order kept; B+ 81 → `INVALID` field `B+`; values never re-sorted). `ac10_4 key order of the stored boundaries does not matter` (the phone's A, B, C, D, D+, C+, B+ order accepted and written in scale order; B+ 69 → field `B`). `ac10_4 key set fixed` (extra letter/category refused, missing key refused). `ac10_5 stale original refused` (`STALE_CONFIG` with `current`). `ac10_1 new course.json changes only the part` + one `config` line with old and new values |

### Layer 1b: server harness (`server.test.js`, T5/T7/T9/T10)
`web/tests/gas_fake.js` loads `web/apps_script/*.js` into one `node:vm` context (the Apps Script global scope) with
fakes for the services the server uses: DriveApp over a tmp directory standing for `My Drive` (folders, files,
`getBlob().getDataAsString()`, `setContent`, `createFile`, name listing), ScriptProperties over a JSON file,
LockService (records acquire/release order; a test can make `waitLock` time out), Session (active/effective emails
set per test), Utilities (`formatDate` in Asia/Bangkok, seeded `getUuid`), HtmlService (returns the template name and
evaluated output), a fixed clock, a captured `console`/`Logger`, and failure injection (`failOn('setContent', n)`). If
`drive.js` needs a DriveApp method the fake lacks, the engineer adds it to the fake (tooling, not assertions). The
Drive tree is built by copying a fixture the way web-push lays it out (or by running `build_course_json` output
committed in the golden file).

| Test | Criteria |
|---|---|
| `ac2_2 doGet shows Not available to another account` (emails differ → page has `Not available` and none of: course name, a student name, an ID, the folder name) | S2.2 |
| `ac2_1 listCourses lists two courses with unpulled and last saved` (F1 + F2 mirrors; F1 journal `seven_lines` + `archive_pull_4` → `unpulled` 3, `last_saved` 09:45) | S2.1 |
| `ac2_3 course without course.json is unavailable, the other opens` (reason = `why.noCourseJson`) | S2.3 |
| `ac2_4 loadCourse returns push time` | S2.4 |
| `edge17 conflict copies make the course unavailable` / `edge29 damaged journal makes it unavailable` (reason names line 3) / `edge19 missing journal is unavailable, not empty` | edges 17, 19, 29 |
| `ac8_1 saveBatch writes CSVs and one batch of journal lines` (3 cells, 2 files, same `batch`, reply `saved` 3) | S8.1 |
| `ac8_2 second device conflict` (device A saves hw2 = 7; device B's edit with original blank → conflict `now` 7; Drive keeps 7; B's resend with original 7 writes 9) | S8.2 |
| `ac8_3 retry after a lost reply adds no journal line` | S8.3 |
| `ac8_5 saves run under the lock one after another` (lock acquire/release pairs never interleave; the second save's conflict check sees the first's result) and `BUSY when the lock times out` (edits not written) | S8.5 |
| `ac8_6 untouched bytes, BOM and CRLF survive a save` (F2 homework, BOM + CRLF) | S8.6 |
| `edge35 crash between journal and CSV is rolled forward` (`failOn('setContent', 2)` → call fails; next call completes the CSV from the journal; every Drive value has its journal line) | edge 35, 36 |
| `trim removes archived lines on the next call` (after an archive file appears; unarchived and invalid lines kept byte-identical) | ADR 002, S11.9 |
| `ac6_5 attendance save writes P and A and 2 journal lines`; `ac6_7 nothing named .xlsx is read or written` (fake records every file access) | S6.5, S6.7 |
| `ac9_1 undoLastSave writes inverse lines that name the batch`; `ac9_2 changed cell kept as conflict`; `ac9_3 unavailable after pull` (note text exact); `ac9_5 two presses undo B then A`; `UNDO_CHANGED when another save came first` | S9.1-S9.3, S9.5 |
| `ac10_1 saveConfig rewrites course.json and appends one config line`; `ac10_5 stale config refused, nothing written` | S10.1, S10.5 |
| `edge38 draft edits after a new push come back as not found or conflicts` | edge 38 |
| `logs hold no names, IDs or scores` (after every test above: captured log text has no `99\d{8,9}`, no fixture name, no score value) | Data classification |

### Layer 2: pytest (Mac side)
Additions to `tests/conftest.py` (written by the tester in build mode; existing fixtures untouched):
- autouse `drive_root(tmp_path, monkeypatch)`: creates `tmp_path/"My Drive"` and sets `GRADE_WEB_DRIVE_ROOT` to it
  for **every** test (S1.8).
- `web_course(tmp_path)`: copy of F1 at `tmp_path/"mac"/"9_ฟิสิกส์จำลอง_grading"`. `web_course_att`: plus the
  attendance xlsx built from the csv codes and a baseline from `grader.sync_cmd(course, yes=True)`.
- helpers in `tests/webtools.py`: `grader_cli(argv, cwd=None)` runs `grader.py` in-process with `runpy.run_path(...,
  run_name="__main__")`, patched `sys.argv`/cwd, captured stdout, returns `(exit_code, out)` (grader.py builds its
  parser under `__main__`, so this needs no change to it); `grader_proc(argv, cwd, tty=False, home=None)` for the few
  real-subprocess tests (usage errors, TTY, fake HOME; with a fake HOME it keeps `PYTHONUSERBASE` pointing at the
  real user base); `tree_sha(path)`; `mirror(root, course)`; `put_journal(mirror, name, push=None)`.

`tests/test_web_push.py` (T2): `test_ac1_1_push_copies_pushed_set` (exact relative file list on Drive: course.json,
push.json, empty web_edits.jsonl, the roster, 4 data CSVs, byte-identical to the Mac; push.json has course_id,
course_name, term, mac_folder, pushed_at; no `.xlsx`, `history/`, `reports/` even when the Mac course has them),
`test_ac1_2_push_never_writes_mac_folder` (course with xlsx + baseline + a history entry + a stale score `total`
that loading would rewrite: SHA-256 of every Mac file equal before/after, and after each refusal below too),
`test_ac1_3_unpulled_lines_refuse_push` (exit 1; the 3 lines printed as in the sample session; Drive tree SHA
unchanged), `test_ac1_4_force_archives_discarded_lines` (one new `archive/web_edits_<YYYYMMDD-HHMMSS>_discarded.jsonl`,
header `kind: discarded`, 3 lines `result: discarded`, its name printed; journal bytes untouched; push proceeds;
unpulled now 0), `test_ac1_5_attendance_needing_sync_refuses` (xlsx `P` / csv `A` for `9900000002` `20 Jan 2027`,
both changed since the baseline: exit 1, `run \`grader sync\` first`, the `xlsx P / csv A` line, Drive unchanged),
`test_ac1_6_non_utf8_csv_refused` (cp874 bytes in homework: message names the file), `test_ac1_7_stale_drive_file_removed`
(earlier push with `quiz.csv`; `archive/` kept), `test_ac1_8_env_root_isolates_tests` (fake HOME holding
`Library/CloudStorage/GoogleDrive-x@g.cmru.ac.th/My Drive`: with the env set, nothing appears there),
`test_ac1_8_default_root_resolution` (fake HOME, env unset: one match is used; zero or two matches → exit 1 with the
Interface messages), `test_ac1_9_missing_drive_root` (exit 1 naming the path, nothing created),
`test_ac1_10_xlsx_score_file_refused` (`quiz.xlsx` named; attendance xlsx doesn't count), `test_ac1_11_cwd_default`
and `test_ac1_11_usage_error_outside_a_course` (exit 2, usage line). Edges: `test_edge6_duplicate_id_warning`,
`test_edge7_missing_student_id_or_config_refused`, `test_edge8_header_only_refused`, `test_edge1_2_bom_crlf_copied_bytes`
(F2), `test_edge17_conflict_copies_refuse_push`, `test_edge19_unreadable_journal_refuses` (chmod 000; skipped as
root), `test_edge29_invalid_journal_refuses_push`, `test_ac3_1_course_json_lists_counted_columns_only` (no `total`
column, Raw Details order, grouped by `category_order`), `test_debug_flag_and_one_line_error`.

`tests/test_web_pull.py` (T3, T7 for `from_web.jsonl`, T10 for config lines):
`test_ac11_1_preview_matches_sample_session` (push F1, Mac sets hw2 `9900000001` = 7, `seven_lines`: output from
`By column:` to the last line equals the SPEC sample text exactly; exit 0; Mac tree unchanged),
`test_ac11_1_preview_same_with_and_without_tty` (subprocess, stdin from `/dev/null` and from a pty),
`test_ac11_2_yes_applies_with_totals_and_one_history_entry` (`four_lines`: cells, `total (30pts)` 8 → 17, total rule;
`grader history` has exactly one new line containing `web-pull`), `test_ac11_3_one_undo_restores_every_file`
(`web_course_att` + `seven_lines` incl. weights: after a plain `grader undo --yes`, every file in `data/`,
`course_info/` and `history/attendance_sync.json` equals its pre-pull bytes; edge 31, 33),
`test_ac11_4_mac_change_is_conflict` (exact line `conflict: 9900000001 hw2 — Mac 7, web 9 (not applied)`; Mac keeps
7), `test_ac11_5_unknown_student_or_column_skipped` (+ total column → `total column`), `test_ac11_6_net_change_against_push_value`,
`test_ac11_7_equal_value_is_already_applied` (and edge 23: Mac changed to the web value), `test_ac11_8_xlsx_mirror_keeps_formulas_validation_and_colours`
(openpyxl: target cells P/A; total column cells still formulas; data-validation ranges and conditional-format rules
equal before/after), `test_ac11_9_archive_on_drive_and_in_history` (archive name pattern, header + 4 lines with
`result`, identical copy in the history entry, not in the entry's `files`; Drive journal bytes untouched; unpulled 0;
then a line appended to the journal (as if it arrived after the read) is the only unpulled line next time),
`test_ac11_10_second_pull_nothing` (`✅ Nothing to pull: no web edits since the last pull.`, no new history entry),
`test_ac11_11_config_applied_when_mac_unchanged` (weights equal web values; every other YAML key equal by
`yaml.safe_load`), `test_ac11_12_config_conflict_when_mac_changed` (Mac homework 0.15: exact conflict line; Mac
weights unchanged; same for boundaries), `test_ac11_13_invalid_line_applies_nothing` (lines `3` listed; nothing
applied or archived; exit 1), `test_ac11_14_other_course_refused` (Mac config edited to `PHYS1120`/`2027_S2`),
`test_ac11_15_locked_xlsx_or_unsynced_pair_refuses_yes` (preview printed; exit 1; Mac and Drive unchanged) and
`test_edge30_lock_ignored_without_attendance_lines`, `test_ac11_16_cwd_default`.
Edges: `test_edge15_stale_local_journal_never_loses_cloud_lines` (Drive copy holds lines 1-3 of 5; pull `--yes`;
then the full 5-line journal appears; the next pull applies exactly lines 4-5; every key ends up in one archive),
`test_edge15_push_during_unsynced_save_keeps_lines` (push with an empty local journal; 2 lines with the old push id
appear; next push refuses listing them; pull applies them), `test_edge15_mac_never_writes_the_journal` (journal SHA
unchanged across push, push `--force`, pull, pull `--yes`), `test_edge15_prints_count_and_last_save`,
`test_edge17_conflict_copies_refuse_pull`, `test_edge19_unreadable_journal_refuses_pull`, `test_edge24_edited_back_is_no_change`,
`test_edge26_header_points_changed_still_applies` (Mac header `hw2 (15pts)`), `test_edge27_new_mac_student_untouched`,
`test_edge28_crash_before_archive_rerun_only_archives` (archive dir read-only during the first `--yes`: exit 1 with
the "Applied … but not archived" lines; after restoring permissions the rerun archives and opens no history entry),
`test_edge32_several_config_lines_net_change`, `test_from_web_journal_pulls_cleanly` (`from_web.jsonl`),
`test_journal_contract_matches_expected_json`, `test_apply_edits_entry_captures_into_one_entry` and
`test_auto_sync_entry_param` (the new optional `entry=` arguments: one entry holds CSV, xlsx, totals and baseline;
default behaviour is covered by the unchanged existing tests).

`tests/test_web_golden.py` (T4): `test_golden_files_match_grade_tui` (`make_golden.py --check` exits 0),
`test_ac12_2_fixture_set_covers_hazards` (the literal asserts in the S12.2 table), `test_ac4_1_detail_values_from_grade_tui`
(F1 copy + `apply_edits` of the two edits → `get_course_data` shows 9.33 / 17 / 27 / 21 / 0 / 48 / F; the node test
asserts the same literals, so both sides agree), `test_ac2_5_big_course_payload_within_budget` (`make_big_fixture.py`
into tmp; course.json + roster + data CSVs ≤ 500 KB).

`tests/test_web_fixtures.py` (T2): every fixture ID starts `99`; no `6920` anywhere; no `history/` or `.xlsx` under
`web/tests/fixtures/`; all files strict UTF-8; `get_course_data` on a copy of each fixture changes no byte under
`data/` (totals current).

`tests/test_web_hygiene.py` (T5): `test_ac13_3_no_secrets_or_real_data` (`git ls-files web` has no `.clasp.json`,
no `.clasprc.json`, no `*.xlsx`; no token-like strings (`ya29.`, `"refresh_token"`, `"scriptId"`) and no Drive-ID-like
strings (`[-\w]{28,}` next to `id`/`folder`/`file`) in `web/apps_script`, `web/tools`, `web/scripts`, `web/tests`,
`src/web*.py`; no `@g.cmru.ac.th` address with a user part in those paths), `test_existing_tests_unchanged`
(`git diff --quiet 7a233a4 -- tests/` excluding `tests/conftest.py`, `tests/webtools.py` and `tests/test_web_*.py`;
`7a233a4` = "docs: requirements for grade_web", the last commit before build work), `test_rust_tui_untouched`
(`git diff --quiet 7a233a4 -- rust_tui/`). Skipped (not failed) when not run inside the git checkout.

The existing 85 tests (23 s on 2026-10-18) must pass with no edit to their files. The `entry=None` defaults keep
`test_apply_edits.py`, `test_attendance.py`, `test_history.py` and `test_serve.py` green as they are.

### Layer 3: manual checklist (user, on fixtures only)
Setup: copy F1 and F2 to a scratch folder outside the repo (e.g. `~/grade_web_trial/`), `grader web-push` both to the
real Drive, deploy per README. Never a real course. Record each result (date, device, pass/fail, note) in the table
under "Manual results" below.

| ID | Steps | Expected (Interface copy) | Criteria | Task |
|---|---|---|---|---|
| M1 | Open the T1 spike URL on the iPhone from the CMRU account | `hello` and the `grade_web/` folder names; no student data | S0.1 | T1 |
| M2 | If deploy or open is blocked: stop, lead asks the user | No other account used | S0.2 (process) | T1 |
| M3 | Open the URL in a browser signed in with a second Google account, and signed out | Google's own page or `Not available`; no course, name, ID or score | S2.2, edge 39 | T1, T5 |
| M4 | Phone signed in to two Google accounts at once; follow the README workaround | Only the owner's data, or Google's refusal | edge 39 | T5 |
| M5 | Course list with F1 (4 unpulled lines) and F2; delete F2's course.json on Drive and reload | `4 edits not pulled · last saved {time}`; F2 `Unavailable` with `why.noCourseJson`; F1 still opens; header shows `Pushed {time}` | S2.1, S2.3, S2.4 | T5 |
| M6 | 300 x 80 big course on 4G: tap it, time to usable | ≤ 8 s (record the time) | S2.5 | T5 |
| M7 | Column mode on hw2: type `9`, Next; `ขส`; Clear; `12`; clear `9` back to blank; type `8,5`, `-3`, `abc` | Focus moves; `9*`; `1 unsaved`; `12` red + `above max 10`; badge drops; refusals `'8,5': use . for decimals (8.5)`, `'-3' is negative; scores start at 0`, `'abc' isn't a score…`, value and focus unchanged | S3.1-S3.7 | T6 |
| M8 | Keypad accessory bar while typing | Bar sits above the iOS keypad; `ขส` and `Next ↓` keep the keypad open and move focus | S3.3, S3.4 | T6 |
| M9 | Search `0002`, then `ใจดี`, then `0009`, then clear | One row each; `No students match "0009".`; unsaved edits kept | S3.8, edge 46 | T6 |
| M10 | Tap `9900000001` (after hw2 `9` and `20 Jan 2027` `P`), then type `28` in final_exam | 9.33 / 17 / 27 / 21 / 0 / 48 / F, then 76 / B+ at once; `abs` red, `ขส` shown | S4.1-S4.3 | T8 |
| M11 | Mac browser ≥ 960 px: table; edit a score and an attendance cell; narrow the window | Every column, computed columns grey and not editable; same marks; narrow → Scores with that column | S5.1-S5.4 | T8 |
| M12 | Attendance on the day of a session (or a fixture session dated today) | Today's session preselected (`· today`); P/A taps move focus; `EA` kept; no add/rename/remove control | S6.1-S6.4 | T9 |
| M13 | Fill `20 Jan 2027` whole column `P`, tap `A` once, Save; check Drive csv and journal | 3 unsaved before Save; csv holds P/A; journal +N lines | S6.5, S6.6 | T9 |
| M14 | Fill hw2 only-empty `0`, then whole `10` | `→ 2 cells will change`, `→ 3 cells will change`; `Nothing to change` when 0 | S7.1-S7.5 | T9 |
| M15 | Save 3 cells in 2 files | `Saved 3 cells (2 files)`; marks and draft clear | S8.1 | T7 |
| M16 | Phone loads; Mac browser saves hw2 `7`; phone saves `9`, then saves again | `Saved 0 cells · 1 changed elsewhere, not saved: 9900000001 hw2 (now 7)`; second Save writes 9 | S8.2 | T7 |
| M17 | Airplane mode, Save; network back, Retry | `Save failed: you're offline. Your N edits are kept.`; Retry saves each cell once (journal has no duplicate) | S8.3 | T7 |
| M18 | 5 unsaved edits, kill the Safari tab, reopen; also a draft made days ago | `5 unsaved edits restored (from {time})` / `(from {time}, 3 days ago)` | S8.4, edge 40 | T7 |
| M19 | Phone and Mac browser tap Save together (same and different cells) | Both finish; the later one's conflict check sees the earlier result; no lost value | S8.5 | T7 |
| M20 | Leave the course / close the tab with unsaved edits; private window | Leave dialog / browser prompt where supported; draft restorable; storage strip `storage.off` in a private window | S8.7, S8.8 | T7 |
| M21 | 60 unsaved cells on 4G, Save | Result within 5 s (record the time) | S8.9 | T7 |
| M22 | Discard all; Undo last save twice; Undo after `grader web-pull`; Undo with unsaved edits | Nothing written on Discard; `Undo save of {time}, 2 cells?`; walks back B then A; `Already pulled to the Mac; use grader undo there`; `Save or discard your N unsaved edits first` | S8.10, S9.1-S9.5 | T7 |
| M23 | Session expiry: sign out of Google in another tab, then Save | `Signed out of Google. Sign in again; your edits are kept.`; edits kept | edge 37 | T7 |
| M24 | Grading tab: weights 0.25/0.35 (sum 1.05 warning first), `0.2x`, A 78, stale save from a second device | `⚠ weights sum to 1.05` with Save allowed; field message; order kept; `Weights were changed on another device…` | S10.1-S10.5 | T10 |
| M25 | Deploy from a clean checkout following the README (clasp), and once by paste-in | One URL, "Execute as: me", "Only myself" | S13.1, S13.2 | T5 |
| M26 | After a session, open the Apps Script Executions log | Only error codes and folder names; no names, IDs or scores | Data classification | T7 |

**Manual results** (filled by the lead as each check is run):

| ID | Date | Device | Result | Note |
|---|---|---|---|---|

### Acceptance criteria coverage
Every criterion has at least one test. "N:" = node (layer 1), "H:" = server harness, "P:" = pytest, "E" = e2e.sh,
"M" = manual.

| AC | Test(s) | Task |
|---|---|---|
| S0.1 | M1 | T1 |
| S0.2 | M2 (process: the lead stops and asks) | T1 |
| S1.1 | P: `test_ac1_1_push_copies_pushed_set`; E step 3 | T2 |
| S1.2 | P: `test_ac1_2_push_never_writes_mac_folder`; E step 3 | T2 |
| S1.3 | P: `test_ac1_3_unpulled_lines_refuse_push` | T2 |
| S1.4 | P: `test_ac1_4_force_archives_discarded_lines` | T2 |
| S1.5 | P: `test_ac1_5_attendance_needing_sync_refuses` | T2 |
| S1.6 | P: `test_ac1_6_non_utf8_csv_refused` | T2 |
| S1.7 | P: `test_ac1_7_stale_drive_file_removed` | T2 |
| S1.8 | P: autouse `drive_root`, `test_ac1_8_env_root_isolates_tests`, `test_ac1_8_default_root_resolution` | T2 |
| S1.9 | P: `test_ac1_9_missing_drive_root` | T2 |
| S1.10 | P: `test_ac1_10_xlsx_score_file_refused` | T2 |
| S1.11 | P: `test_ac1_11_cwd_default`, `test_ac1_11_usage_error_outside_a_course` | T2 |
| S2.1 | H: `ac2_1 …`; N: `ac2_1 summary …`; M5 | T5 |
| S2.2 | H: `ac2_2 doGet …`; M3 | T5 |
| S2.3 | H: `ac2_3 …`; M5 | T5 |
| S2.4 | H: `ac2_4 …`; M5 | T5 |
| S2.5 | M6 (target); P: `test_ac2_5_big_course_payload_within_budget`, N: `ac2_5 computeGrades 300x80` (proxies) | T5 |
| S3.1 | P: `test_ac3_1_course_json_lists_counted_columns_only`; M7 | T2, T6 |
| S3.2 | N: golden order and names; M7 | T4, T6 |
| S3.3 | M7, M8 | T6 |
| S3.4 | N: `ac3_7 allowed values` (`ขส`); M7, M8 | T6 |
| S3.5 | N: `ac3_5 above max accepted`; M7 | T6 |
| S3.6 | N: `sameCell compares by meaning`; M7 | T6 |
| S3.7 | N: `ac3_7 …` ×4; M7 | T6 |
| S3.8 | M9 | T6 |
| S4.1 | N: `ac4_1 …`, golden variant `s4_1_detail`; P: `test_ac4_1_detail_values_from_grade_tui`; E step 9; M10 | T4, T8 |
| S4.2 | N: `ac4_2 …`, variant `s4_2_typed_final`; M10 | T4, T8 |
| S4.3 | N: `ac4_3 …`, golden F1/F2; M10 | T4, T8 |
| S5.1-S5.3 | M11 | T8 |
| S5.4 | N: validation shared (`ac3_7`); M11 | T8 |
| S6.1 | N: `ac6_1 …`; M12 | T9 |
| S6.2 | M12 | T9 |
| S6.3 | N: `ac6_5 …` (EA untouched); M12 | T9 |
| S6.4 | M12 | T9 |
| S6.5 | N: `ac6_5 …`; H: `ac6_5 …`; golden (code values); E step 6; M13 | T7, T9 |
| S6.6 | N: `ac6_6 …`; M13 | T9 |
| S6.7 | P: `test_ac1_1_…` (no xlsx on Drive); H: `ac6_7 …` | T2, T9 |
| S7.1-S7.3, S7.5 | N: `ac7_1`, `ac7_2`, `ac7_3`, `ac7_5`; M14 | T9 |
| S7.4 | N: `ac7_4 …`; M14 | T9 |
| S8.1 | N: `ac8_1 …`; H: `ac8_1 …`; M15 | T7 |
| S8.2 | N: `ac8_2 …`; H: `ac8_2 …`; M16 | T7 |
| S8.3 | N: `ac8_3 …`; H: `ac8_3 …`; E step 6c; M17 | T7 |
| S8.4 | M18 | T7 |
| S8.5 | H: `ac8_5 …`; M19 | T7 |
| S8.6 | N: `ac8_6 …`; H: `ac8_6 …` | T7 |
| S8.7, S8.8 | M20 | T7 |
| S8.9 | M21 | T7 |
| S8.10 | M22 | T7 |
| S9.1 | N: `ac9_1 …`; H: `ac9_1 …`; E step 6d; M22 | T7 |
| S9.2 | N: `ac9_2 …`; H: `ac9_2 …` | T7 |
| S9.3 | N: `ac9_3 …`; H: `ac9_3 …`; M22 | T7 |
| S9.4 | M22 | T7 |
| S9.5 | N: `ac9_5 …`; H: `ac9_5 …`; M22 | T7 |
| S10.1 | N: `ac10_1 …`, variant `s10_1_weights_edit`; H: `ac10_1 …`; M24 | T10 |
| S10.2-S10.4 | N: `ac10_2`-`ac10_4`; variant `s10_4_boundaries_edit`; M24 | T10 |
| S10.5 | N: `ac10_5 …`; H: `ac10_5 …`; M24 | T10 |
| S11.1 | P: `test_ac11_1_preview_matches_sample_session`, `test_ac11_1_preview_same_with_and_without_tty`; E step 7 | T3 |
| S11.2 | P: `test_ac11_2_…`; E step 8 | T3 |
| S11.3 | P: `test_ac11_3_one_undo_restores_every_file`; E step 11 | T3 |
| S11.4 | P: `test_ac11_4_…`; E step 7 | T3 |
| S11.5 | P: `test_ac11_5_…` | T3 |
| S11.6 | P: `test_ac11_6_…`; E (undo net no change) | T3 |
| S11.7 | P: `test_ac11_7_…` | T3 |
| S11.8 | P: `test_ac11_8_…`; E step 8 | T3 |
| S11.9 | P: `test_ac11_9_…`; H: trim; E steps 8, 12 | T3 |
| S11.10 | P: `test_ac11_10_…`; E step 10 | T3 |
| S11.11 | P: `test_ac11_11_…` | T3 |
| S11.12 | P: `test_ac11_12_…` | T3 |
| S11.13 | P: `test_ac11_13_…` | T3 |
| S11.14 | P: `test_ac11_14_…` | T3 |
| S11.15 | P: `test_ac11_15_…`, `test_edge30_…` | T3 |
| S11.16 | P: `test_ac11_16_cwd_default` | T3 |
| S12.1 | N: `ac12_1 golden parity` ×4 + variants; P: `test_golden_files_match_grade_tui` | T4 |
| S12.2 | P: `test_ac12_2_fixture_set_covers_hazards`; fixture table above | T4 |
| S12.3 | N: `ac12_3 …` ×2 | T4 |
| S13.1, S13.2 | M25 | T1, T5 |
| S13.3 | P: `test_ac13_3_no_secrets_or_real_data` | T5 |

Edge cases (REQUIREMENTS 1-48): 1-2 N `edge1`/`edge2`, P `test_edge1_2_…`, H `ac8_6`; 3 P `ac1_6`; 4 N `edge4`, golden
F2; 5 golden F3 (11-digit order), N `csv` padded IDs; 6 P `edge6`, N `edge6`; 7-8 P `edge7`, `edge8`; 9-10 P `ac3_1`,
golden; 11 P `ac1_10`; 12 golden F3; 13 N `ac3_7`; 14 P `ac1_3`/`ac1_4`; 15 P `edge15` ×4; 16 P `ac11_9`; 17 P/H/N
`edge17`; 18 P `ac1_9`; 19 P/H `edge19`; 20 P `ac11_14`; 21 README (M25 reviews it); 22-24 P `ac11_4`, `ac11_7`,
`edge24`; 25-27 P `ac11_5`, `edge26`, `edge27`; 28 P `edge28`; 29 P/H/N `edge29`; 30 P `ac11_15`; 31 P `ac11_3`; 32 P
`ac11_11`/`ac11_12`/`edge32`; 33 P `ac11_3`; 34 H `ac8_2`/`ac8_5`, M19; 35-36 H `edge35`, N `ac8_3`; 37 M23; 38 H/N
`edge38`; 39 M3/M4; 40 M18/M20; 41 golden, N `ac3_5`, M7; 42 N `ac6_5`, M12; 43 N `ac9_5`, M22; 44 M6/M21 + proxies;
45 N `ac10_2`; 46 M9; 47 N `ac6_1`, M12; 48 M2.

### Build-mode expectations (fail first)
At the build step, before T2-T10 code exists: node tests fail on `require('../apps_script/…')` (module missing) or on
a missing golden file (generated by T4's `make_golden.py`); the harness fails loading `Code.js`; pytest web tests fail
on the unknown `web-push`/`web-pull` subcommands or the missing `src.webpush`/`src.webpull`. `test_web_fixtures.py`
and the hygiene tests may pass at once (they check committed fixtures and the repo, not app code); they are reported
as such, not counted as acceptance tests. Every `test_ac…`/`ac…` test must fail.

## Out of scope
From the REQUIREMENTS backlog: reports/analytics export on the web; roster changes or new students; adding,
renaming or removing attendance sessions; editing the attendance `.xlsx` on the web; offline use and an edit queue;
Thai UI; a history browser on the web; any change to grade-tui; automatic or scheduled sync; Fill targets beyond
whole/empty (marked rows, ranges, Class Group); step-by-step undo of unsaved changes; date labels for `a1…aN`
columns; a raw-percentage toggle; adding/removing grade letters or categories on the web; courses with `.xlsx`
score files. Also out: undoing a *config* save with "Undo last save" (re-edit in the editor instead).

## End-to-end verification
From the grade_dashboard repo root, all on fixtures and tmp folders:
```bash
python3 -c "import pandas, openpyxl, yaml"   # brew python3 may have been relinked to a version without packages
python3 -m pytest tests/                     # existing suite unchanged + S1, S11, golden drift, fixtures, hygiene
node --test 'web/tests/*.test.js'            # pure modules + server harness (NOT `node --test web/tests/`: fails on Node 24)
python3 web/tools/make_golden.py --check     # golden files still match grade-tui's output
bash web/scripts/e2e.sh                      # the round trip below; last line "E2E OK"
git diff --quiet 7a233a4 -- rust_tui/        # grade-tui untouched
```

### `web/scripts/e2e.sh`
`set -euo pipefail`. Runs from any cwd (it `cd`s to the repo root). Every command it runs is the real entry point:
`python3 grader.py web-push|web-pull|undo|history` and `node web/scripts/gas_run.js`, which loads the real
`web/apps_script/` code (Code.js + drive.js + the pure modules) through `web/tests/gas_fake.js` with DriveApp mapped
onto the same tmp Drive folder the Mac commands use. So the web saves are made by the real server code and pure
modules, writing the files `grader web-pull` then reads. `gas_run.js` usage:
`node web/scripts/gas_run.js --drive DIR --props FILE [--now ISO] <function> [json-arg …]`, printing the function's
JSON reply on stdout.

Guards: `T=$(mktemp -d)`, `trap 'rm -rf "$T"' EXIT`. It exits 1 before doing anything if `$T` resolves under
`$HOME/Library/CloudStorage` or `$HOME/cmru`. `GRADE_WEB_DRIVE_ROOT` and `--drive-root` both point at `$T/MyDrive`.
`git status --porcelain` is captured at the start and must be identical at the end (the script writes nothing in the
repo). Each step prints `== step N: …`. Any failed check prints `E2E FAIL: step N: <what>` and exits 1.

| Step | Action | Checks (all must hold) |
|---|---|---|
| 1 | Copy F1 to `$T/mac/9_ฟิสิกส์จำลอง_grading` (`$C`); `mkdir $T/MyDrive` | — |
| 2 | Build the attendance xlsx from the csv codes and a baseline: `python3 - "$C"` heredoc calling `grader.save_attendance_excel` + `grader.sync_cmd(course, yes=True)` | xlsx and `history/attendance_sync.json` exist |
| 3 | `S0` = SHA-256 of every file under `$C` (`shasum -a 256`). `python3 grader.py web-push "$C" --drive-root "$T/MyDrive"` | exit 0; a line starts `✅ Pushed`; the sorted file list under `$T/MyDrive/grade_web/9_ฟิสิกส์จำลอง_grading/` equals exactly `course.json`, `course_info/9_ฟิสิกส์จำลอง_student_info.csv`, `data/9_ฟิสิกส์จำลอง_{attendance,final,homework,midterm}.csv`, `push.json`, `web_edits.jsonl` (empty); each CSV `cmp`-equal to the Mac file; SHA list of `$C` equals `S0` (S1.1, S1.2) |
| 4 | A grade-tui edit on the Mac after the push: `python3 -c` → `tui_api.apply_edits(C, [{student_id: "9900000003", column: "hw2", value: "7", original: ""}])` | returns ok; `S1` = SHA list of `$C` now |
| 5 | `gas_run listCourses` | the course is available, `unpulled` 0 |
| 6a | `gas_run saveBatch` with `9900000001` hw2 `9`, `9900000001` `20 Jan 2027` `P`, `9900000002` `20 Jan 2027` `A`, `9900000003` hw2 `5` (all original `""`) | `ok`; 4 `saved`; 0 conflicts; `journal.unpulled` 4; the 4 journal lines share one `batch`; Drive homework/attendance CSVs hold the values; every other line of those files byte-identical to the push |
| 6b | `gas_run saveBatch` with `9900000001` hw2 `6`, original `""` (a stale device) | 0 saved; 1 conflict `changed`, `now` `9`; Drive keeps `9`; unpulled 4 (S8.2) |
| 6c | Resend 6a unchanged (Retry after a lost reply) | `batch` null; 4 `already`; unpulled 4; journal byte-identical (S8.3) |
| 6d | `gas_run saveBatch` `9900000002` hw1 `4` (original `10`), then `gas_run undoLastSave` with that batch | save: 1 saved; undo: 1 saved, every undo line has `undoes` = that batch; Drive hw1 back to `10`; unpulled 6 (S9.1) |
| 6e | `gas_run saveConfig grade_boundaries {A: "78", …unchanged}` with the loaded original | `ok`, `warning` null; course.json `grade_boundaries.A` 78, letter order kept; unpulled 7 |
| 7 | `python3 grader.py web-pull "$C" </dev/null` (preview) | exit 0; output has the lines `   Journal: 7 edits not pulled · last saved …`, `  9900000001 hw2: (blank) → 9`, `  9900000001 20 Jan 2027: (blank) → P`, `  9900000002 20 Jan 2027: (blank) → A`, `  grade boundaries: A 80 → 78`, `  conflict: 9900000003 hw2 — Mac 7, web 5 (not applied)`, `  no change: 9900000002 hw1 (edited back to 10)`, `Preview only: nothing was written. Apply with: grader web-pull --yes`; SHA list of `$C` equals `S1` (S11.1, S11.4, S11.6) |
| 8 | `python3 grader.py web-pull "$C" --yes` | exit 0; lines `  ✍️  data/9_ฟิสิกส์จำลอง_attendance.csv: 2 cells (attendance xlsx too)`, `  📦 Archived on Drive: archive/web_edits_`…`(7 lines)`, a line starting `✅ Pulled 3 cells`, `   Undo with: grader undo <id>` (id matches `[0-9]{8}-[0-9]{6}_grader_web-pull`). A python check: homework.csv `9900000001` hw2 `9` and `total (30pts)` `17`, `9900000003` hw2 `7` (Mac kept); attendance csv and xlsx `20 Jan 2027` = P / A, xlsx total cells still formulas; config `grade_boundaries.A` 78 and every other key equal; `grader history --course "$C"` shows exactly one new line containing `web-pull`; the history entry folder holds `web_edits_*.jsonl` identical to the Drive archive; `web_edits.jsonl` SHA unchanged by the pull (S11.2, S11.8, S11.9, S11.11) |
| 9 | Copy `$C` to `$T/check` and run `tui_api.get_course_data` there | `9900000001`: attendance_pct 9.33, homework_pct 17, Coursework Total 27, midterm_pct 21, final_pct 0, Final Score 48, Grade F: S4.1 through grade-tui's own loader on the pulled files |
| 10 | `python3 grader.py web-pull "$C" --yes` again | exit 0; `✅ Nothing to pull: no web edits since the last pull.`; history line count unchanged (S11.10) |
| 11 | `python3 grader.py undo --course "$C" --yes` (no ID) | exit 0; SHA of every file under `data/`, `course_info/` and `history/attendance_sync.json` equals its value in `S1` (pre-pull), xlsx and config included (S11.3) |
| 12 | `gas_run listCourses` (the next locked web call trims) | `unpulled` 0; `web_edits.jsonl` now holds 0 lines (all keys archived); the conflict line's key is in the archive with `result: conflict` (no line lost) |
| 13 | `python3 grader.py web-push "$C"` | exit 0; `0 edits waiting to be pulled`; push.json has a new `push_id`; `archive/` unchanged |
| 14 | `node --test 'web/tests/*.test.js'` | exit 0 |
| — | End | `git status --porcelain` unchanged; prints `E2E OK`; exit 0 |

Exit criteria: exit code 0 and last line `E2E OK`, under 120 s on this Mac, nothing left outside the removed `$T`, and
no file in the repo changed. Any other outcome is a failure (non-zero exit with `E2E FAIL: step N: …`).

### By hand (the user, fixtures only)
Copy F1 and F2 to a scratch folder outside the repo, `grader web-push` both to the real Drive, `clasp push && clasp
deploy` (or paste-in), then run the manual checklist M1-M26 (Test plan, layer 3) on the iPhone and a Mac browser.
Finish with `grader web-pull <scratch course>` (preview), `--yes`, check the cells and the xlsx mirror, then
`grader undo`. Never on a real course.
