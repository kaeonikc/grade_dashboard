# SPEC — Tab completion for `grader`, and short course folder names from `grader init`

Status: **confirmed** · 2026-10-20 · grade_dashboard (plus one row of `INTEGRATION.md`, which is
also copied in exam_projects)
Previous specs: `SPEC_attendance_sync.md` (was `SPEC.md`), `SPEC_total_sync.md`, `SPEC_default_points.md`.

## Context

1. **No Tab completion.** `grader` is `grader.py` (argparse, 11 subcommands), symlinked into `~/.mytools/bin`. In
   zsh, `grader <TAB>` lists files. To see subcommands, options or a history ID you have to run `grader -h`,
   `grader <cmd> -h` or `grader history`. `exam` already has completion (`exam_projects/cli/exam_cli/complete.py`).
   This spec follows that pattern.
2. **Long Thai folder names.** `grader init -i repclasslist.xls` creates
   `2026_S1_ฟิสิกส์ยุคใหม่_SEC_51_grading/` with files `2026_S1_ฟิสิกส์ยุคใหม่_SEC_51_*`. These names are hard to type in a
   shell, and `_grading` adds nothing. You already rename the class list to `repclasslist_ModPhys.xls`. The folder
   should be `2026_S1_ModPhys_SEC_51/`.

## Decisions (from the interview)

| Topic | Decision |
|---|---|
| Completion approach | Generated from grader's own argparse parser into a static zsh script (`_grader`). No new dependency. Nothing runs pandas on Tab |
| Install | `grader completion install` writes `_grader` to oh-my-zsh's generated-completions folder, already on `fpath`. No `~/.zshrc` edit |
| Staying current | After that, every `grader` run quietly rewrites the installed `_grader` when `grader.py` or `src/complete.py` is newer than it. The next shell sees new options |
| Values completed | Course folders, `undo` history IDs, and file filters for `-i` and config files. `--semester` and `--drive-root` are not completed (free text, folders) |
| `undo` IDs | Same filter as `grader undo` with no ID: no undo entries, no automatic totals syncs, nothing already undone. Newest first, at most 20, each with its `[tool action, N cells] files` description |
| Help text in the menu | Short summary: text up to the first `: ` or `. `, cut at 70 characters with `…`. `-h` keeps the full text, and argparse help strings are unchanged |
| Bare Tab | Lists the positional values **and** the options not used yet, in separate groups, including for subcommands that take a positional |
| Mode exclusions | `init`: `-i` hides `--course_name/--term/--course_id`, and the reverse (`--abbr` fits both). `update`: `-i` hides `config_file`, `--purge-empty-orphans` and `-y`, and the reverse. A short/long pair counts as one option |
| Abbreviation source | `--abbr`, then the class-list file name `repclasslist_<ABBR>.<ext>`, then a prompt whose default is the course ID (when not on a terminal, the course ID with a warning). If `--abbr` and the file name disagree, `--abbr` wins and one line says so. No remembered-abbreviations file |
| Abbreviation scope | The folder **and** every file prefix inside it. The Thai name stays in `config.yaml` (`course_name:`) |
| Existing courses | Unchanged. New courses only, and no rename command. Every tool still accepts both folder shapes |

## Part A — Tab completion

### What Tab offers

```
$ grader <TAB>
-- grader command --
completion  -- Print or install the zsh Tab completion for grader
dashboard   -- Launch the grade dashboard
history     -- List the saved versions in a course's history/
init        -- Initialize a new course grading directory
mkdb        -- Create empty database files for all categories from config
mock        -- Generate a complete mock course under courses/ for testing grade-tui
sync        -- After editing score CSVs or the attendance sheet by hand
undo        -- Restore files from history/ (newest change not undone yet, or ID)
update      -- Update student list from raw file or update database files from config
web-pull    -- Bring grade_web edits back into the course (preview; --yes applies)
web-push    -- Copy a course to Google Drive for the grade_web app (phone or browser)
-- option --
--help -h   -- show this help message and exit
```

| Subcommand | Positional (bare Tab, together with the option group) | Option values |
|---|---|---|
| `init` | — | `-i/--input`: folders + `*.xls *.xlsx *.csv`. `--abbr`, `--course_name`, `--term`, `--course_id`: free text |
| `mkdb` | `config_file`: folders + `*.yaml` | `-i/--input`: folders + `*.yaml` |
| `update` | `config_file`: folders + `*.yaml` | `-i/--input`: folders + `*.xls *.xlsx *.csv` |
| `undo` | `entry`: undoable history IDs of the resolved course (below) | `--course`: course folders |
| `sync`, `history` | — | `--course`: course folders. `-n`: free text |
| `web-push`, `web-pull` | `COURSE`: course folders | `--semester`: free text. `--drive-root`: folders |
| `completion` | `zsh` / `install` | — |
| `mock`, `dashboard` | — | — |

**Course folders** are folders under `./` and `./courses/` that contain `course_info/`, listed with their relative
paths. A folder path typed by hand still completes through the normal folder fallback.

**Which course `undo <TAB>` reads:** `--course` if it is on the line, otherwise the folder you're in if it has
`course_info/`, otherwise the course under `./` or `./courses/` whose `history/log.jsonl` changed most recently. That
is grader's own rule minus the `.bak` timestamps. If no course is found, nothing is listed and you can still type an
ID.

All options are hidden after `--help`, and an option can't be offered twice. `-n` and every value-taking option use
`_arguments` value specs, so `grader history -n <TAB>` waits for text and doesn't list files.

### Files

| File | Change |
|---|---|
| `grader.py` | Move the parser out of `if __name__ == "__main__"` into `build_parser() -> argparse.ArgumentParser`. `web_push`/`web_pull` still receive their subparser, which can be found via the parser. Add the `completion` subcommand (`zsh` prints the script to stdout, `install` writes it; with no word it prints the subcommand's help). Add `--abbr` to `init` (Part B). After `parse_args()` and before dispatch, call `complete.refresh_installed(parser)`. It never raises and never prints |
| `src/complete.py` (new) | Standard library only, and it imports only `src/history.py` (also stdlib). (1) **Dynamic lists**: `python3 src/complete.py courses` prints one course folder per line. `python3 src/complete.py undo-ids [COURSE]` prints `id<TAB>description` lines, using `history.list_entries` and the same filter as `history.latest_undoable` (`AUTOMATIC`, `undoes`), newest first, at most 20. The zsh script calls this file by absolute path with `python3`, so Tab never loads grader.py or pandas. (2) **`zsh_script(parser) -> str`**: walks the argparse subparsers and actions and emits `#compdef grader` plus `_grader`. It dispatches on the subcommand and calls `_arguments -s -S` with specs built from each action: option strings grouped as `'(-y --yes)'{-y,--yes}'[…]'`, `nargs`/`store_true` deciding whether a value spec follows, and help through `_summary()`. (3) **Tables**: `VALUES` maps `(subcommand, dest)` to a value kind: `course`, `undo-id`, `files:*.xls *.xlsx *.csv`, `files:*.yaml`, `dir`, `choices:…`, `text`. An action not in the table gets `_files` if it takes a value. `EXCLUSIVE` holds the init/update mode groups and becomes `_arguments` exclusion lists. (4) **Bare Tab**: a subcommand with a positional gets a helper `_grader_<cmd>_arg` that runs `_alternative` over the positional's values and an `option` group of the options not on the line yet, with exclusions applied. (5) **`install()`** and **`refresh_installed(parser)`** (below) |
| `tests/zshtab.py` (new) | Copied from `exam_projects/cli/tests/zshtab.py` and adapted: starts `zsh -f -i` on a pty with only the generated `_grader` on `fpath`, types a line, presses Tab and returns the groups and candidates. Nothing is executed |
| `tests/test_completion.py` (new) | See the test plan |
| `MANUAL.md` | A `## grader completion` section (what Tab offers, where the file lives, `exec zsh`). One line in the setup section: run `grader completion install` once |
| `CLAUDE.md` | Commands block: `python grader.py completion install`. `src/complete.py` in the architecture tree |

### Where the file goes

`install()` writes `_grader` to the first of:

1. `$GRADER_ZSH_COMPLETIONS`, if set (tests always set it to a tmp folder);
2. `${ZSH_CACHE_DIR:-$HOME/.oh-my-zsh/cache}/completions/` if `~/.oh-my-zsh` exists (on this Mac:
   `~/.oh-my-zsh/cache/completions/_grader`, next to `_exam`);
3. `~/.zsh/completions/`, after which it prints the `fpath=(… $fpath)` line to add before `compinit`.

The file's second line is `# generated by \`grader completion zsh\` from <abs path of grader.py>; do not edit`.
`install` refuses to overwrite a `_grader` that lacks this header, and says so. The write is atomic (temp file and
rename). Output: `✅ wrote ~/.oh-my-zsh/cache/completions/_grader — open a new terminal (or: exec zsh) to use it`.

### Self-refresh

`refresh_installed(parser)` runs on every grader command except `completion` itself:

- It looks only at the location `install()` would use. If no `_grader` is there, or it lacks our header, it does
  nothing. It never creates the file.
- If `grader.py` or `src/complete.py` has a newer mtime than `_grader`, it regenerates. It writes (atomically) only
  when the text differs; otherwise it touches the file so the check stays a single `stat` comparison.
- Any exception is swallowed, so completion can never break or slow down a grading command. The cost when nothing
  changed is two `stat` calls.

## Part B — `grader init`: short folder names from the abbreviation

### Behaviour

```
$ grader init -i repclasslist_ModPhys.xls
✅ Successfully created course structure at: 2026_S1_ModPhys_SEC_51   (abbreviation ModPhys from the file name)

$ grader init -i repclasslist.xls
Course 1062201 ฟิสิกส์ยุคใหม่, SEC 51
Abbreviation for folder/file names [1062201]: ModPhys
✅ Successfully created course structure at: 2026_S1_ModPhys_SEC_51

$ grader init -i repclasslist_ModPhys.xls --abbr MP
ℹ️  --abbr MP overrides ModPhys from the file name
✅ Successfully created course structure at: 2026_S1_MP_SEC_51
```

| | Before | After |
|---|---|---|
| Folder (class-list mode) | `<term>_<Thai name>_SEC_<n>_grading/` | `<term>_<abbr>_SEC_<n>/` |
| Files (class-list mode) | `<term>_<Thai name>_SEC_<n>_{config.yaml,student_info.csv,attendance.xlsx,…}` | `<term>_<abbr>_SEC_<n>_…` |
| Folder/files (`--course_name --term --course_id` mode) | `<term>_<name>_grading/`, `<term>_<name>_config.yaml` | `<term>_<abbr>/`, `<term>_<abbr>_config.yaml` |
| `grader mock` | `courses/0_ฟิสิกส์ทั่วไป_(ข้อมูลจำลอง)_grading`, prefix `0_ฟิสิกส์ทั่วไป_(ข้อมูลจำลอง)` | `courses/0_GenPhysMock`, prefix `0_GenPhysMock` |
| `config.yaml` | `course_id`, `course_name` (Thai), `term` | unchanged: the Thai name is still shown by the dashboard, grade-tui and grade_web |

**Rules**

- **Order:** `--abbr`, then the file name, then a prompt. The prompt only runs on a terminal (`sys.stdin.isatty()`).
  Otherwise the course ID is used with `⚠️ no abbreviation given (--abbr or repclasslist_<ABBR>.xls); using the course
  ID 1062201`.
- **File name:** the class-list file's name (not its folder) must match `repclasslist_<ABBR>.(xls|xlsx|csv)`,
  case-insensitive. Anything else (plain `repclasslist.xls`, `classlist_ModPhys.xls`) gives no abbreviation. If the
  captured part fails validation (e.g. `repclasslist_ModPhys (1).xls`), a warning names the file and the next source
  is used.
- **Validation:** `^[A-Za-z0-9][A-Za-z0-9_-]{0,29}$`. ASCII only, so the folder can be typed without a Thai keyboard.
  An invalid `--abbr` stops init with `❌` before anything is created, and an invalid prompt answer asks again. An
  empty prompt answer takes the default.
- **Existing folder:** unchanged. `❌ Directory '…' already exists. Use 'grader update -i …'`.

### `grader update -i` with a new-style course

`update_course` already finds the course by the `course_id`/`term`/`sec_num` in its config, not by folder name. But it
builds the roster path from the Thai name (`f"{term}_{name_for_path}_SEC_{sec}_student_info.csv"`), which would leave
a second, Thai-named roster next to `2026_S1_ModPhys_SEC_51_student_info.csv`. **Change:** when the course has a
config, the roster path is `get_course_file_prefix(target_dir) + "_student_info.csv"`. This is correct for old-style
and new-style courses alike. The current construction remains the fallback when there is no config.

### Files

| File | Change |
|---|---|
| `grader.py` | `init` gets `--abbr ABBR`. New `_resolve_abbr(abbr, input_file, course_id, course_name, sec_num) -> tuple[str, str]` returns the abbreviation and where it came from. `init_course` builds the folder and every filename from it and drops `_grading`. `update_course` takes the roster path from the prefix (above). `mock_course` uses `0_GenPhysMock`. The `init` validation message mentions `--abbr` |
| `INTEGRATION.md` (**both copies**: grade_dashboard and exam_projects; a test checks they are identical) | Row "Course folder": `<term>_<abbr>_SEC_<n>/` (from 2026-10-20) or `<term>_<name>[_SEC_<n>]_grading/` (older). Readers take the prefix from `course_info/*_config.yaml`, never from the folder name |
| `MANUAL.md` | `grader init` section: the `repclasslist_<ABBR>.xls` habit, `--abbr`, the prompt, and the new folder example. The troubleshooting line "the `*_grading` folders" becomes "the course folders". The `grader mock` name |
| `tests/test_init_abbr.py` (new) | See the test plan. The class list is a **fake** xlsx built in `tmp_path` with the keyword cells `convert_student_info.py` looks for (term, `รหัสวิชา`, section) and made-up students. The repo's `repclasslist.xls` is never read |

Nothing else needs to change for the new names, as checked by grep on 2026-10-20. `webpush.check_course` uses
`removesuffix("_grading")` only in an error message, which is a no-op on new names. exam_projects' `complete.py` falls
back to `_grading` only when a course has no config. grade-tui and the dashboard find courses through `course_info/`.

## Out of scope

- bash and fish completion, and completion for `grade-tui`.
- Completing `--semester` from Drive, or `--abbr` from the class-list name.
- Changing argparse `help=` strings, or grader's behaviour when options conflict (completion only hides them).
- Renaming existing course folders (no `grader rename`), and any migration of the 2569-1 courses, exam
  `grading_dir:` links or Drive mirrors.
- A remembered course_id → abbreviation file.
- Code changes in exam_projects. Only its `INTEGRATION.md` copy changes.

## Test plan

All tests use `tmp_path` copies (never `~/cmru/teachings`) and set `GRADER_ZSH_COMPLETIONS` to a tmp folder.

**`tests/test_completion.py`**
1. Table ↔ parser: every key in `VALUES` and `EXCLUSIVE` names a real subcommand/dest. Every subcommand and every
   option string of `build_parser()` appears in `zsh_script()`.
2. `_summary`: the sync and `--purge-empty-orphans` texts are cut at the first `: `/`. ` and at 70 characters with
   `…`. Short texts are unchanged. `[ ] : '` are escaped.
3. `src/complete.py courses` from a tmp term folder lists exactly the folders containing `course_info/` (both `./` and
   `./courses/`).
4. `src/complete.py undo-ids` on the conftest course with a hand-written `log.jsonl` (an edit, its `totals`, an undo
   of an earlier edit, and 25 updates) prints 20 lines, newest first, with no `totals`/undo/undone entries, each in
   the form `id\t[tool action, N cells] files`. The resolution covers `--course`, the cwd being a course, and the
   most recent log.
5. `src/complete.py` imports no third-party module (run it with `python3 -I -X importtime` and check that no `pandas`
   or `yaml` is loaded).
6. `install()`: writes to `$GRADER_ZSH_COMPLETIONS`, refuses a foreign `_grader`, and is atomic.
   `refresh_installed`: does nothing without a file. Regenerates after a newer `grader.py` mtime (use `os.utime` on a
   copy). Leaves the content alone and touches when the text is equal. Swallows a read-only folder.
7. **zsh on a pty** (`tests/zshtab.py`, skipped without zsh):
   - `grader <TAB>` lists the 11 subcommands with summaries.
   - `grader undo <TAB>` in a tmp course shows a `history entry` group (20 IDs) **and** an `option` group (`--course`,
     `--yes -y`, `--help -h`).
   - `grader init -i <TAB>` offers `repclasslist_X.xls` and folders but not `notes.txt`.
   - `grader init -i x.xls -<TAB>` offers `--abbr` but not `--term`. `grader init --term 2026_S1 -<TAB>` offers
     `--course_id` but not `-i`.
   - `grader update -i x.xls <TAB>` offers no `config_file` and no `-y`.
   - `grader sync --course <TAB>` lists the course folders.
   - `grader history -n <TAB>` lists no files.
   - `grader completion <TAB>` → `install zsh`.

**`tests/test_init_abbr.py`**
1. `init -i repclasslist_ModPhys.xlsx` creates `2026_S1_ModPhys_SEC_51/` with `course_info/2026_S1_ModPhys_SEC_51_config.yaml`,
   `…_student_info.csv` and `data/…_attendance.xlsx/.csv`, and no `_grading` anywhere. `config.yaml` keeps the Thai
   `course_name`.
2. `--abbr MP` with the same file → `2026_S1_MP_SEC_51/`, and the override line is printed.
3. Plain `repclasslist.xlsx` with stdin not a terminal → the course-ID folder plus the warning. With a fake terminal
   answering `bad name` then `ModPhys` → asks twice, then `2026_S1_ModPhys_SEC_51`.
4. `--abbr 'ฟิสิกส์'` or `--abbr 'a b'` → exit 1, nothing created. `repclasslist_ModPhys (1).xlsx` → warning, then the
   next source.
5. `--course_name X --term 2026_S2 --course_id P1 --abbr GR` → `2026_S2_GR/`, `2026_S2_GR_config.yaml`.
6. `update -i` on the course from (1) writes `2026_S1_ModPhys_SEC_51_student_info.csv` and no Thai-named roster. On
   an old-style `…_grading` course, it still writes that course's own prefix.
7. `mock` → `courses/0_GenPhysMock/` whose prefix is `0_GenPhysMock`.
8. The existing INTEGRATION.md copy test still passes (`../exam_projects/INTEGRATION.md` is identical).

Full suite: `python -m pytest tests/` (and `cargo test` in `rust_tui/`, unchanged, as a regression check).

## Delivery

On a new branch `tab-completion`, off the current `web-app`. web-push/web-pull exist only there, and the completion
must cover them. Commit locally, in two commits (Part A, Part B). The `INTEGRATION.md` row is a separate commit in
exam_projects. You push.

## End-to-end verification

On this Mac, in the scratchpad (never in `~/cmru/teachings`):

1. `python -m pytest tests/` passes, including `test_completion.py` (zsh pty tests not skipped) and
   `test_init_abbr.py`.
2. `grader completion install` → `✅ wrote ~/.oh-my-zsh/cache/completions/_grader`. Run `exec zsh`.
3. In a scratch term folder holding a fake `repclasslist_ModPhys.xlsx` (the test builder, saved to disk):
   `grader <TAB>` lists the 11 subcommands with summaries. `grader init -i <TAB>` offers the xlsx. Run
   `grader init -i repclasslist_ModPhys.xlsx` → `2026_S1_ModPhys_SEC_51/` exists with ModPhys-prefixed files.
4. `cd 2026_S1_ModPhys_SEC_51 && grader update -i ../repclasslist_ModPhys.xlsx -y`, then `grader undo <TAB>` lists that
   update's ID under "history entry", with `--course`/`--yes` under "option".
5. Self-refresh: add a dummy `--zzz` option to `history` in grader.py, run `grader history`, then `exec zsh` and
   `grader history -<TAB>`. `--zzz` is listed. Remove the option, run any grader command again, and it's gone.
6. `grader -h`, `grader sync -h` and every existing command behave exactly as before (the help text is unchanged).
