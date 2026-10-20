# grade_web: Discard button and faster loading

Status: draft, awaiting approval (2026-10-20). Branch: `web-app`. Scope: `grade_dashboard/web/`.

## Context

The user asked for two things:
1. A visible way to throw away unsaved score edits.
2. Shorter waits. Every wait feels slow on the iPhone: the blank first page, the course list, opening a course,
   Reload and Save.

**What exists today:**
- **Discard** already works, but it's only reachable from the Save sheet ("Discard all…") and ⋯ More, and the draft
  banner offers it after a restore. All three open the S8.10 dialog (`openDiscard`).
- **Loading is serial DriveApp calls.** Counted with the server harness over the 4 fixture courses:

  | Call | Folder listings | File downloads |
  |---|---|---|
  | `listCourses` (4 courses) | 26 | 12 |
  | `loadCourse` (`9_ฟิสิกส์จำลอง_grading`) | 9 | 8 |

  On real Drive each listing or download costs about 0.1–0.5 s. Each listing also walks an iterator and calls
  `isTrashed()` per item. On top of that, each `google.script.run` call has about 1–2 s of fixed overhead.
- **Why it's slow:**
  - `listCourses` runs the full `openCourse_` check (trim, every folder listing, `course.json`, `push.json`, the
    journal) on every course, so the list gets slower with each pushed course.
  - `loadCourse` repeats that check for one course, then downloads the roster and each CSV in turn.
  - `journalReply_` → `pulledThisPush_` lists `archive/` a second time and downloads the newest archive.

## Decisions (interview 2026-10-20)

| # | Decision |
|---|---|
| D1 | **Discard button** in the bottom action bar, to the left of `Save N`. It's labelled `Discard` (outline button, red text) and opens the existing S8.10 dialog unchanged: initial focus on `Keep edits`, and it discards **all** unsaved edits of the course. It shows only while N > 0, so wherever Save shows: column mode, attendance, the table and the student detail, but not the Grading tab, where `.action-bar` is hidden. It's disabled while saving or checking (D7). |
| D2 | **Measure first.** Adding `?timing=1` to the web app URL shows a grey timing line under the header. Phase 1 ships only this, so the user can send baseline numbers before any speedup goes in. It stays in the app as a diagnostic. It shows only times and counts, never student data. |
| D3 | **Advanced Drive service (v3)** for folder listings. It uses the existing `drive` scope, so there's no new OAuth scope and no `UrlFetchApp`. One `Drive.Files.list` call lists the children of many folders (`('a' in parents or 'b' in parents) and trashed = false`), replacing the per-folder iterators and `isTrashed()`. Files are still **found by name** in each call's listing; no folder or file ID is stored between calls. |
| D4 | **Server content cache** in `CacheService.getScriptCache()`. The key is `gw1:<fileId>:<md5Checksum>`, which addresses the content, so a changed file can never hit an old entry. Entries live 6 h. Text over 95 000 UTF-8 bytes is split across chunk keys `…:0`, `…:1` and so on, with a `…:n` count. All the files a call needs are fetched with one `getAll`. A missing chunk, a missing md5 or a cache error counts as a miss, and the file is downloaded. |
| D5 | **The cache serves only the read-only display calls** (`listCourses`, `loadCourse`). Every call that writes or conflict-checks (`saveBatch`, `undoLastSave`, `saveConfig`, roll-forward, trim) reads its files fresh from Drive. It still gets the faster listings (D3). A stale display copy is harmless because Save always conflict-checks against fresh bytes. After a write, the new text is put into the cache under an md5 computed locally (`Utilities.computeDigest(MD5, text, UTF_8)`); the T1 spike proved the written bytes are identical. |
| D6 | **Device cache: the course list only.** `localStorage` key `gw:courses` holds `{v:1, saved_at, courses}`: course name, code, term, push time, journal counts and availability with reason. There's no student data in it. On the course screen it's drawn at once, then replaced by the fresh `listCourses` reply. No names or scores go to storage; the REQUIREMENTS data-classification rule stands. |
| D7 | **In-memory reuse of opened courses** (this tab only, no storage). Up to 3 courses are kept, least recently used dropped first: `{open, rows, byId, max, groups, at}`, where `at` is the time of the last `loadCourse` reply. **A copy ≤ 60 s old** opens normally. **An older copy** opens at once **read-only**: the header says `Checking Drive…`, and inputs, chips, Fill, Save, Discard, the Grading forms, Undo and Reload are locked through the same path as `state.saving` (S8.9). A fresh `loadCourse` runs, and when it lands the view rebuilds from it (tab, category, column, search and scroll kept), the draft is restored against it, and the lock lifts. |
| D8 | **Prefetch the last-opened course.** `localStorage` `gw:last` holds a folder name. After the course list's fresh reply has rendered, the app quietly calls `loadCourse(gw:last)` into the D7 memory. Tapping that course while the call is in flight waits on the same promise (no second call), and with a result ≤ 60 s old it opens editable at once. Tapping a different course just queues behind it, because the server lock takes one call at a time. A prefetch that fails is dropped silently. |
| D9 | **First page:** the timing line also shows doGet's server time and the iframe's time to first paint. Google's own wrapper (the script.google.com redirect and the sandbox iframe) is out of our hands and isn't promised. **Only if** the baseline shows doGet over 300 ms, the evaluated HTML is cached in CacheService (chunked), keyed by a `PAGE_BUILD` constant in `Code.js` that a test checks against the sha256 of the page's source files (`style`, `client_state`, `client_views`, `Index`, `csv`, `grades`, `journal`, `save`). A stale build can then never be served after a deploy. No minify step. |

## Design

### Phase 1: timing (ships alone, then the baseline is taken)
- **`Code.js`**
  - `doGet(e)` passes `timing = e.parameter.timing === '1'` to the template.
  - `withLock_` records `lock_ms` (wait) and `ms` (total).
  - `drive.js` keeps per-call counters `{list, read, hit, miss}`, reset at the start of each server function.
  - Every reply gets `timing: {ms, lock_ms, list, read, hit, miss}`, with numbers only.
  - Each server call logs one line: `<fn> ms=… lock=… list=… read=… hit=… miss=…`. Logs still hold no names, IDs
    or scores.
  - doGet logs `doGet ms=…`, and its time goes to the page as `DOGET_MS`.
- **`Index.html`**
  - Renders `const TIMING = <?= timing ?>; const DOGET_MS = <?= dogetMs ?>;` in the inline script, before the core.
  - Records `performance.now()` at first script run.
- **`client_state.html`**
  - `server()` measures each round trip and keeps `state.timing[name] = {total, server: reply.timing}`.
- **`client_views.html`**
  - With `TIMING` on, a `p.timing` line sits under the page or course header. Example:
    `page 0.9 s (doGet 0.12 s) · list 2.8 s (server 1.6 s, lock 0.0, Drive 26 list / 12 read, cache 0/0) · open 3.4 s (…)`.
  - It's `aria-hidden`. With `TIMING` off, nothing renders.

### Phase 2: Discard button (D1)
- **`client_views.html` (`courseView`):**
  - `cm.discardBtn = button('Discard', openDiscard, 'btn outline danger-text discard-btn')` sits in `.action-bar`
    before `cm.saveBtn`.
  - `refreshChrome`: `cm.discardBtn.hidden = n === 0; cm.discardBtn.disabled = state.saving || state.checking`.
  - After a discard the button hides, and focus moves to the column select (column mode), else to the view's
    heading, so it's never left on a hidden button.
- **`style.html`:**
  - `.action-bar` gets `gap: 0.5rem`.
  - `.discard-btn` uses `min-height: 3rem` like Save, with red text and an outline.
  - It must fit at 320 px wide (`Discard` + `Save 999`) and in landscape 844×340.

### Phase 3: server speed (D3–D5)
- **`appsscript.json`:** `"dependencies": {"enabledAdvancedServices": [{"userSymbol": "Drive", "serviceId": "drive",
  "version": "v3"}]}`. `oauthScopes` stays unchanged.
- **`drive.js`** is rewritten around plain records `{id, name, mimeType, md5, parents}`:
  - **`childrenOf_(folderIds)`:** one `Drive.Files.list` per ≤ 40 parents, with
    `fields: 'nextPageToken, files(id,name,mimeType,md5Checksum,parents)'`, `pageSize: 1000`, following the page
    tokens. It returns `{<parentId>: [record]}` with duplicate names kept, so conflict copies are still detected.
  - **`gradeWebFolder_()`:** `'root' in parents and name = 'grade_web' and mimeType = folder and trashed = false`.
  - **`readTexts_(records, {cache})`:**
    - With `cache`, one `getAll` for every record that has an md5, then downloads only the misses and `putAll`s them.
    - Without `cache`, it downloads everything.
    - **Download path:** a spike (Phase 3, first task) round-trips the T1 Thai + BOM + CRLF fake through
      `Drive.Files.get(id, {alt: 'media'})`. If that's byte-identical it's used; otherwise
      `DriveApp.getFileById(id).getBlob().getDataAsString()` is.
  - **`writeText_(record, text)`:** `DriveApp.getFileById(id).setContent(text)` (the proven write), then the
    write-through `put` under the local md5.
- **`Code.js`:**
  - **`openCourse_` → `openCourses_(folders, {cache})`** works on many courses at once:
    - level 1: the course folders' children, one listing;
    - level 2: their `archive/` and data dirs, one listing;
    - then one batched read of `course.json` and `push.json`, and after those, the journals.
  - **Unchanged:** the availability checks, reasons, trim, roll-forward and their order, and `unavailableResetTrim_`.
  - **Trim:** when trim must read fresh archives or rewrite the journal, that course's reads are fresh (D5).
  - **`listCourses`** calls `openCourses_(all, {cache: true})`.
  - **`loadCourse`** calls `openCourses_([one], {cache: true})`, then one `readTexts_` for the roster and data files.
  - **`withCourse_` for writes** passes `{cache: false}`.
  - **`pulledThisPush_`** uses the `archive/` listing from level 2 and the cached read of the newest archive. There's
    no second listing.
- **Fakes (`web/tests/gas_fake.js`):**
  - `Drive.Files.list` parses the `in parents` / `name =` / `mimeType =` / `trashed = false` subset used here, over
    the same tmp Drive, with a real md5 of the bytes and page tokens (page size forced small in one test).
  - `Drive.Files.get(alt=media)`.
  - `CacheService.getScriptCache()` with `get/getAll/put/putAll/remove`, a 100 KB value limit (it throws above it)
    and an `evict()` helper.
  - The counters `gas.counts` keep working.

### Phase 4: client speed (D6–D8)
- **`client_state.html`**
  - **`courseListCache()` / `rememberCourseList(reply)`** read and write `gw:courses` inside try/catch. A bad or old
    `v` is ignored.
  - **`state.loaded`:** the LRU `Map` of D7.
  - **`state.checking`:** the read-only flag, folded into every place that tests `state.saving` for locking.
  - **`openCourse(folder)`** becomes:
    1. A memory copy ≤ 60 s old, or the in-flight prefetch promise, is used as is.
    2. An older copy is shown read-only, then rechecked.
    3. With no copy, the call runs as today.
  - Successful replies of `loadCourse`, Reload, Save, Undo and config save update the memory entry. Save and Undo
    keep `at`, because only `loadCourse`/Reload refreshes `at`. `closeCourse` keeps the entry; Discard keeps it too,
    since it never changes Drive values.
  - **`prefetch(folder)`** returns and stores a single promise per folder.
  - **`gw:last`** is written when a course opens.
- **`client_views.html`**
  - **`showCourses`:**
    - With a cached list, the cards draw at once with the muted line `Checking Drive…`.
    - The fresh reply replaces them and keeps the scroll position.
    - If the fresh call fails, the cards stay and the line becomes `Couldn't refresh (list from <time>).
      [Try again]`.
    - With no cache, the page behaves as today.
    - After the fresh render it calls `prefetch(gw:last)` when that folder is in the list and available.
  - **`showCourse`:**
    - With a usable memory copy, there's no spinner screen.
    - The recheck's failure states: offline, BUSY or session expired leave the copy on screen, still read-only, with
      `Couldn't check Drive. [Try again]`. `‹ Courses` still works.
    - `UNAVAILABLE` or `NOT_FOUND` drop the copy and show today's `Can't open` notice.

### Phase 5 (conditional): doGet HTML cache (D9)
Only if the baseline doGet is over 300 ms. `PAGE_BUILD` and its test are in `web/tests/server.test.js`, and the
failure message prints the expected value.

## Files
| File | Change |
|---|---|
| `web/apps_script/appsscript.json` | Advanced Drive v3 enabled (Phase 3) |
| `web/apps_script/drive.js` | Listing and reading by records, batched; cache; counters |
| `web/apps_script/Code.js` | `timing` in replies and logs; `openCourses_` batched; cache only on display calls; `doGet(e)`; (Phase 5) `PAGE_BUILD` |
| `web/apps_script/Index.html` | `TIMING`, `DOGET_MS`, start mark |
| `web/apps_script/client_state.html` | Round-trip timing, `gw:courses`, `gw:last`, `state.loaded`, `state.checking`, prefetch |
| `web/apps_script/client_views.html` | Timing line, Discard button, cached course list, read-only reopen |
| `web/apps_script/style.html` | `.discard-btn`, `.action-bar` gap, `.timing` |
| `web/tests/gas_fake.js` | `Drive` advanced-service fake, `CacheService` fake |
| `web/tests/server.test.js`, `availability.test.js` | Call-count and cache tests; all existing availability/trim/save tests unchanged and passing |
| `web/tests/nav.test.js` (or a new `speed.test.js`) | Client logic: memory LRU, the 60 s rule, the prefetch promise, the course-list cache shape |
| `web/SPEC.md` | Modules row for `appsscript.json` (advanced service), Budget rows (below), Data classification row for `gw:courses`, Discard placement in Interface §9/§10 |
| `web/README.md` | Deploy note: approve the advanced service once if asked; `?timing=1` |

The Apps Script file count stays at 11 (budget ≤ 11). There are no new dependencies, libraries or npm packages.

## Targets
Fake Drive, enforced by tests:
- **`listCourses` over the 4 fixtures:** ≤ 4 `Drive.Files.list` calls, whatever the course count. With a warm cache
  it makes 0 downloads; with a cold cache, exactly one download per needed file.
- **`loadCourse`:** ≤ 4 listings; 0 downloads warm.
- **`saveBatch` of S81:** ≤ 4 listings; the edited CSVs and the journal are read fresh even when they're cached.

Real phone, taken from the `?timing=1` line and compared with the Phase 1 baseline:
- **Course list:** cards on screen in ≤ 0.3 s after the first script runs (repeat visit); fresh within the
  `listCourses` round trip, whose server time is ≤ 1.0 s with a warm cache.
- **Opening the last-opened course after the list:** ≤ 0.5 s from the tap.
- **Opening any other course:** server time ≤ 1.0 s warm; at least 50 % less total time than the baseline.
- **Save and Reload:** server time at least 30 % less than the baseline.
- The measured numbers go into `web/SPEC.md` Budget as the new limits.

## Edge cases
- **Cache and correctness:**
  - A changed file has a new md5, so it's a miss and is read fresh.
  - A file without an md5 (not expected for CSV/JSON/JSONL) is always downloaded.
  - Values that are evicted or partly chunked count as misses.
  - A cache exception counts as a miss and is logged as `cache_error`, with no data.
- **Duplicate names and trashed files:** the listing keeps duplicates, so `WHY.copies` still fires. Trashed files
  never come back from the listing (the query says `trashed = false`), which matches today's `untrashed_`.
- **More than 40 folders or 1000 files:** the query splits and page tokens are followed. A test covers this with a
  forced small page size.
- **The draft on reopen from memory:** while read-only, no edit can be made, so the edits equal the draft. When the
  fresh copy lands, the draft is restored against it, as on a cold open: edits already on Drive drop out, and the
  banner comes from the fresh restore.
- **Another device saved while a stale copy was shown:** the fresh copy replaces the values. Nothing could be typed
  in between (D7).
- **A copy ≤ 60 s old is still stale:** another device might have saved in that window. That's accepted; Save's
  conflict check handles it, as for any open page today.
- **Prefetch and the lock:** a prefetch is in flight when the user taps another course → that open waits up to the
  prefetch's duration. A prefetch must never show an error or a notice.
- **`gw:courses` lists a course that's since gone or unavailable:** its card shows until the fresh list replaces it.
  Tapping it gives today's `Can't open` reply.
- **Storage blocked:** there's no list cache and no `gw:last`, and everything works as today. `state.storageOff`
  keeps its draft warning.
- **The Discard button while typing:** the dock is hidden while the keypad bar shows (S3), so it can't be pressed
  mid-commit.
- **Discard while checking:** disabled (D7).
- **The draft banner's own `Discard…`:** stays.
- **Grading tab:** no Discard button (the action bar is hidden there). The forms keep their own Reset.
- **The advanced service is blocked by the CMRU admin:** the first `clasp push` or run fails. Work stops and the lead
  asks the user, as REQUIREMENTS says for admin blocks. There's no silent fallback to DriveApp listings.

## Out of scope
- New OAuth scopes, `UrlFetchApp`, parallel downloads.
- Storing course data (names or scores) on the device; any service worker or offline mode.
- Google's own page wrapper time; a minify or build step.
- Changing the conflict-check, journal, trim or roll-forward semantics; `grader web-push`/`web-pull`; grade-tui;
  Python.
- Partial discard (one column or student), and a Discard Undo toast.
- Faster writes (the journal, then each CSV, stays serial by ADR 002).

## Verification (end to end)
1. **Automated** (from `grade_dashboard/`): `node --test 'web/tests/*.test.js' && python3 -m pytest tests/ -q &&
   cargo test --manifest-path rust_tui/Cargo.toml && web/scripts/e2e.sh`. All pass, and e2e ends `E2E OK`. The
   call-count targets above are asserted, and every existing availability, trim, save, undo and config test passes
   unchanged.
2. **Preview harness, WebKit iPhone 13** (scratchpad Playwright, `NOW=` fixed, `?timing=1`):
   - **The course list:** the second visit draws the cards from `gw:courses` before the stubbed `listCourses`
     returns. The stub is delayed by 2 s to show this.
   - **Prefetch:** opening the last course right after the list makes no second `loadCourse` call (the stub's call
     log shows it), and scores are editable immediately.
   - **The 60 s rule:** back to the list, wait 61 s (or advance the client clock), reopen. The view is instant, says
     `Checking Drive…`, and inputs are read-only. Change a cell in the tmp Drive meanwhile; when the recheck lands
     the new value shows and inputs unlock.
   - **Discard:** type 3 scores → `Discard` and `Save 3` show. Tap `Discard` → the dialog has focus on `Keep edits`.
     Confirm → `Discarded 3 edits`, the marks clear, the draft key is gone, the buttons hide, and focus is on the
     column select. Check it at 320×568, 390×664 and 844×340, and look at the screenshots.
3. **Deploy Phase 1 alone:** `cd web && clasp push --force`, `clasp create-version`, then `clasp update-deployment
   <id> -V <N>` for both deployments. The user opens `<exec url>?timing=1` on the iPhone, then: the list, a course,
   back, the same course, Reload, a 1-cell save (then Undo). They send the timing lines; these go into this spec as
   the baseline.
4. **Deploy Phases 2–4** (and 5 if triggered) the same way. On first run, approve the advanced service if Google
   asks. The user repeats step 3's sequence. The new timing lines meet the Targets. Each number is written next to
   its baseline in this spec, and the Budget rows in `web/SPEC.md` are updated.
5. **Commit** locally on `web-app` (no push), one commit per phase:
   - `feat(web): ?timing=1 diagnostic line`
   - `feat(web): Discard button next to Save`
   - `perf(web): batched Drive listings and content cache`
   - `perf(web): instant course list, reuse and prefetch of opened courses`
