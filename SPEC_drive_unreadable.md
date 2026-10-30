# SPEC — A Drive copy that can't be read (Drive for Desktop not running)

## Context

`grader update -i ../repclasslist_Astro52.xls` in `~/cmru/teachings/2569-2/2026_S2_Astro51_SEC_51/` (31 Oct 2026,
00:35) merged the roster, then crashed while it checked the Drive copy before the rename (SPEC_sections.md R2):

```
File "src/rename.py", line 99, in plan          waiting = webdrive.unpulled(mirror)
File "src/webdrive.py", line 160, in archived_keys   for text in path.read_text(...)
TimeoutError: [Errno 60] Operation timed out
```

Google Drive for Desktop wasn't running. macOS still lists `My Drive/grade_courses/2569-2/2026_S2_Astro51_SEC_51/`
from its cache, so `mirror.is_dir()` is True and grader thinks the copy is there. Every read of a file in it fails
at once (`Operation timed out`, in about 0.02 s). `webdrive.journal()` turns that into a message; `archived_keys`,
`webpull`'s push.json read and `rename._count` don't, so the error escapes as a traceback. Nothing was renamed or
half-renamed: the roster update had already finished and is fine to repeat.

Goal: every command that uses the Drive copy checks it can read it **before it writes anything**, and says plainly
what's wrong and what to do. `update -i` keeps its roster update and skips the rename and push.

## Decisions (interview)

| # | Decision |
|---|---|
| U1 | **`update -i` keeps the roster, skips the rename and push.** It prints a ⚠️ warning naming the unreadable copy and what to do, and exits 0 (the roster part succeeded and needs no Drive). |
| U2 | **Every Drive command gets the same check:** `update -i` (rename and push offer), plain `grader update` (push offer), `grader web-push`, `grader web-pull`, `grader undo` of a rename. One shared function in `src/webdrive.py`. |
| U3 | **Nothing on Drive or the Mac is renamed or written** when the check fails. A rename moves the Mac folder and the Drive copy together or not at all, as before. |

## Behaviour

### `webdrive.check_readable(mirror, nothing="Nothing on Drive was changed.")` (new)
- Reads every file under `mirror` (course.json, push.json, web_edits.jsonl, archive/*.jsonl, course_info/, data/;
  they are small). The first `OSError` (TimeoutError, PermissionError, …) raises `Refused`:
  ```
  ❌ Can't read the web copy grade_courses/2569-2/2026_S2_Astro51_SEC_51/ (push.json: Operation timed out).
     Google Drive for Desktop isn't running, or these files aren't downloaded yet.
     Start Google Drive, wait until it shows "up to date", then run this again. Nothing on Drive was changed.
  ```
  The last sentence is the `nothing` argument (callers say "Nothing was renamed." and so on).
- A copy that isn't there (`not mirror.is_dir()`) passes: there's nothing to read, as today.
- `web_edits.jsonl` is left to `webdrive.journal()`, which already refuses with its own message (web/SPEC.md edge 19,
  `❌ Couldn't read …/web_edits.jsonl (…)`, pinned by tests). Both refusals are `webdrive.Unreadable`, a `Refused`, so
  `update -i` treats them the same way.

### Where it runs
- **`rename.plan`** (used by `update -i` and `grader undo` of a rename): right after `drive_copy()`, with
  `nothing="Nothing was renamed."`, before `unpulled()`.
  - `update -i`: `rename.offer` already prints a `Refused` and carries on. It now prints it as `⚠️` and adds
    `The roster was updated; only the rename waits.` Exit code 0.
  - `grader undo <rename id>`: prints the message and exits 1, nothing renamed (as for any refused undo).
- **`rename.offer_push`**: checks before counting students; on failure prints the message (⚠️, `Not pushed.`)
  and returns. Also guards `_count` against `OSError`.
- **`webpush.push`**: checks the new copy and the old flat copy (when there is one) before the first write. On
  failure it raises `Refused` as today (exit 1, Drive untouched).
- **`webpull.pull`**: checks the copy before reading push.json. On failure it raises `Refused` (exit 1, nothing
  applied).
- **Belt and braces:** `webdrive.archived_keys` and `webpull`'s push.json read catch `OSError` and raise the same
  `Refused`, so a file that becomes unreadable between the check and the read still gives the message, never a
  traceback.

## Files
`src/webdrive.py` (`check_readable`, `archived_keys` guard), `src/rename.py` (`plan`, `offer`, `offer_push`,
`_count`), `src/webpush.py` (`push`), `src/webpull.py` (`pull`), `MANUAL.md` (Troubleshooting: "Can't read the web
copy"), `tests/test_drive_unreadable.py` (new).

## Out of scope
- Detecting whether Google Drive for Desktop is running from its process (the read check is what matters, and it
  also catches files that aren't downloaded).
- Retrying or waiting for Drive to come back.
- A Drive write failing halfway through a push (the check runs before the first write; a failure after that is
  as today).
- Running anything on the real course or the real Drive: you do that (see step 4 below).

## Tests (`tests/test_drive_unreadable.py`, new)
The unreadable copy is simulated with `chmod 000` on one of its files (the test is skipped when run as root). For
each case the Drive copy's bytes and the Mac course's file names are compared before and after.
- `update -i -y` with a new section and an unreadable `archive/*.jsonl`: roster has the new section, folder not
  renamed, Drive untouched, the ⚠️ message names the file and "Google Drive for Desktop", no traceback, no exit.
- `update -i -y` with a known section and an unreadable `push.json`: same (the Astro case today).
- plain `grader update` with a grown roster and an unreadable copy: no push question, the ⚠️ message.
- `grader web-push`: `Refused`, exit 1, Drive untouched. `grader web-pull`: `Refused`, nothing applied.
- `grader undo <rename id>` with an unreadable copy: exit 1, the course keeps its name, Drive untouched.
- `check_readable` passes for a missing copy and for a readable one.
- Every existing suite stays green: `python -m pytest tests/`, `cd rust_tui && cargo test`, `web/scripts/e2e.sh`.

## End-to-end verification
1. All suites pass (above).
2. Scratch copy of the real course and a scratch Drive holding a pushed copy. `chmod 000` one archive file, then
   `grader update -i ../repclasslist_Astro52.xls -y` in the course: ⚠️ message, exit 0, folder still
   `2026_S2_Astro51_SEC_51`, Drive copy byte-identical to before.
3. `chmod 644` it back and run the same command: it renames to `2026_S2_Astro_SEC_51-52` and pushes, as in
   SPEC_sections.md Revision 2.
4. On your Mac (you): with Google Drive for Desktop quit, run `grader web-push` in the Astro course. You get the
   message, not a traceback. Start Drive, wait for "up to date", then `grader update -i ../repclasslist_Astro52.xls`
   renames and pushes the real course.
