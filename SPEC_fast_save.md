# grade_web: Save in the background, with fewer Drive reads

Status: built, and deployed as version 25 on 2026-11-01. The real iPhone check is still to do. Date: 2026-11-01.

## Why

Saving takes about as long for one student as for fifty, and the page stays locked until it finishes.

Every `saveBatch` runs one fixed sequence: 4 folder listings, up to 5 downloads (`course.json`, `push.json`, the journal,
the score file, the newest pull record), then 2 uploads. Each extra category adds one download and one upload. October's
measurements give 0.3–0.5 s per Drive call plus about 1.4 s of `google.script.run` overhead, so a save is very roughly
5–7 s. That figure is an estimate: `clasp logs` can't run here because the app has no Google Cloud project ID.

## Decisions

| # | Decision |
|---|---|
| S1 | **Save runs in the background.** After `Save n cells` in the sheet, the page stays usable: type, mark, Fill, scroll, change tab or section. The Save button reads `Saving n…`, and the line under the course name says `Saving n cells…`. |
| S2 | **Only what could clash waits.** A second Save, Discard, Undo, Reload, the Grading forms and ← Back wait until the reply. Cell editing, the P/L/A/X pop-up and Fill don't. Undo, Reload and config saves keep today's full lock. |
| S3 | **Edits made during a save stay unsaved.** The save sends a copy of the edits. When the reply comes, a cell leaves the unsaved list only if its value still equals what was sent. A cell changed again keeps the newer value, unsaved, with the saved value as its start value. |
| S4 | **The reply doesn't redraw the page.** Changed rows and the counts repaint in place, so the scroll position, an open cell, a pop-up and a sheet all stay. |
| S5 | **A failed save loses nothing.** Every edit stays unsaved, in the phone's draft as now, and the same `Retry` alert shows. Conflicts behave as they do today. |
| S6 | **Save and leave stays a wait.** The Leave sheet's `Save and leave` closes the course only after the reply, as today. |
| S7 | **A closed tab is safe.** The draft stays until the reply. If the tab closes mid-save, the server normally finishes, and on reopening the existing draft check drops edits already on Drive. If it doesn't finish, they come back as unsaved. |
| S8 | **Fewer downloads.** `saveBatch` and `undoLastSave` take `course.json`, `push.json` and the pull record from the content cache, whose key includes the file's current md5. The journal and score files are still downloaded fresh, so the conflict check is unchanged. `saveConfig`, and any call with a save pending, stay all fresh. |

## Decisions I made that you can overrule

- **← Back waits during a save** rather than leaving mid-save. It's a few seconds, and it means the reply always lands on
  the course it belongs to.
- **Only one save at a time.** While one runs, the button stays `Saving n…`; afterwards it reads `Save m` for edits made
  in the meantime. There is no automatic second save.
- **Journal first, then scores, stays.** It's what lets an interrupted save finish later.
- **No parallel downloads.** They'd need a new Google permission prompt and fresh byte-exact tests, for a small gain.

## Out of scope

- Auto-save.
- Removing the 4 folder listings. They also detect duplicate files, and the rule is that files are found by name on each
  call.
- `grader`, grade-tui and the journal format.

## Interfaces and files

**`web/apps_script/client_state.html`**
- `state.sending` (new): the save on its way, as a copy of its edits. Only `state.saving` feeds `locked()`, which keeps
  blocking the S2 list; cell editing checks a new `busy()` that is true for `state.saving` without `state.sending`.
- `saveEdits()` keeps the copy, and `applySaved()` follows S3.

**`web/apps_script/client_views.html`**
- `doSave()` sets `state.sending`, and on success calls a new `refreshSaved(reply)` in place of `renderView()` (S4). It
  repaints the rows involved, the attendance grid's numbers, the student page and the counts.
- `refreshChrome()` shows `Saving n…`. The `locked()` checks on cell editing, the pop-up and Fill move to `busy()`.
- `Save and leave` keeps its wait (S6).

**`web/apps_script/Code.js`, `drive.js`**
- `withCourse_` and `openCourses_` take a third cache mode, `'meta'`: `course.json` and `push.json` as with `cache`, the
  journal fresh. `saveBatch` and `undoLastSave` use it.
- `pulledThisPush_` reads the pull record through the cache in that mode.

**Docs:** `web/README.md`, and a note in `SPEC_discard_and_speed.md` D5.

## Tests (written first)

**`web/tests/fast_save.test.js`** (new, `node:vm` over `client_state.html`)
- An edit made during a save stays unsaved with the newer value, and its start value becomes the saved one.
- A cell not touched during the save leaves the unsaved list.
- A failed save keeps every edit, including new ones, and the draft holds them.
- `busy()` and `locked()` during a Save, an Undo and a Drive check.

**`web/tests/speed.test.js`**
- `saveBatch` with a warm cache downloads only the journal and the edited files, not `course.json` or `push.json`, with
  no more listings than before.
- With a save pending, everything is read fresh.
- `saveConfig` reads `course.json` fresh.
- A `course.json` changed on Drive (new md5) is read fresh.

**Regression:** `web/tests/*.test.js`, `pytest tests/` and `web/scripts/e2e.sh` all pass, including every existing save,
conflict, undo and roll-forward test.

## End-to-end verification

1. **Browser check** in Chromium at 375×665 and 1280×800 on the scratch Astro copy, with the preview server's replies
   delayed by 3 s:
   - Save 3 cells, and type in a fourth cell while it runs. After the reply, the 3 are saved and the fourth is `Save 1`.
   - Change a cell that is being saved. After the reply the newer value stays unsaved, and the next Save writes it.
   - The scroll position, an open cell and a pop-up survive the reply.
   - Make the server fail: `Retry` shows, and no edit is lost.
   - Close the tab mid-save and reopen: no edit is lost or written twice.
   - During a save, Discard, Undo, Reload and ← Back wait.
2. **Commit** locally on `section-folders`, with no git push. `web/.app/log.jsonl` is left alone.
3. **Deploy** with `web/scripts/deploy.sh`, once you say yes.
4. **You, on the iPhone:** with the `?timing=1` link, save one cell before and after the deploy, and compare the `save`
   lines in the ⋯ menu. Then save and keep typing straight away. Use a scratch value, and Undo afterwards.

## As built

- **A cell being saved stays an edit until the reply**, even when set back to its old value (`putEdit`), so a failed save
  can't lose it and a later value is never overwritten by the reply.
- **`repaintRow` and `repainted`** are `changed()` split in two, so a reply repaints the attendance grid's numbers once
  rather than once per student.
- **`‹ Back` during a save** shows the `Saving…` text instead of leaving.
- **Replies held back:** the browser check holds `saveBatch` replies with a Playwright route rather than a delay in the
  preview server. It also drops a reply after the server has written, to prove the closed-tab case.
- **Browser check:** Chromium at 375×665 with touch and 1280×800 with a mouse: ALL OK. Real Drive times are still to be
  measured with the `?timing=1` line.
