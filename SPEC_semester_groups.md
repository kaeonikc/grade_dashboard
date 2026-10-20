# Semester groups for grade_web

## Context
The user teaches many courses each semester, and the laptop already groups them by semester
(`~/cmru/teachings/2569-1/2026_S1_…_grading`). Today `grader web-push` copies every course flat into
`My Drive/grade_web/<course>/`, and the phone lists everything in grade_web. The user wants to manage what the phone
shows with Drive shortcuts: the real copies stay in semester folders, and grade_web holds shortcuts for the current
term only. Removing a shortcut hides the old term from the app, and its data stays where it is. v12 already follows a
shortcut to a single course folder. This spec adds semester groups and moves web-push's target to match.

Status: approved 2026-10-20. Implemented test first.

## Decisions (interview 2026-10-20)
- **D1 Real copies.** web-push writes to `My Drive/grade_courses/<laptop parent folder>/<course folder>/`. For example,
  `~/cmru/teachings/2569-1/X_grading` goes to `grade_courses/2569-1/X_grading`. The root name defaults to
  `grade_courses` and is changed with `$GRADE_WEB_COURSES`. `--semester NAME` overrides the parent folder name. No
  sharing is needed: grade_courses is in the same CMRU My Drive the app runs as. (A folder in the personal gmail Drive
  would need edit access shared to the CMRU account.)
- **D2 grade_web is what the phone shows.** The user adds shortcuts by hand in Drive, usually one per term
  (`grade_web/2569-1 → grade_courses/2569-1`). A shortcut to a single course works too (v12), and so do old flat
  folders.
- **D3 Course or group.** A grade_web item (folder or folder shortcut) that holds `course.json`, `push.json` or
  `web_edits.jsonl` is a course, and gets the existing availability check. Any other item is a **group**: its
  subfolders that hold one of those three files are its courses, one level only. Other subfolders are skipped
  silently, so the semester folder can hold anything else. A group with no courses shows the heading and the line
  "No pushed courses in 2569-1".
- **D4 Course identity = its path in grade_web.** That is `<course>` or `<group>/<course>`. The phone sends the path
  to every server function, and the path keys drafts (`gw:draft:`), UI memory (`gw:ui:`), `gw:last` and the
  in-memory LRU. Pending and trim markers stay keyed by folder id, so they are unchanged. Migration: when a fresh list
  arrives, a draft or UI key under a bare `<name>` that matches no listed course is renamed, provided exactly one
  listed course is `<group>/<name>`.
- **D5 Phone list.** One heading per group, sorted by name descending (2569-1 before 2568-2). Courses directly in
  grade_web come last, under "Other courses". With no groups, there are no headings and the list looks as it does
  today.
- **D6 Drafts left behind.** Shown only after a fresh, successful `listCourses` (never from the cached list, never
  after a failed list). Below the list: "Unsaved edits for a course no longer in grade_web: <path> (3 edits)
  [Discard]". Discard uses the existing confirm dialog. Restoring the shortcut brings the course and its draft back.
- **D7 web-push and old flat copies.** If `grade_web/<course>` exists as a real folder:
  - with unpulled edits, web-push refuses: "run grader web-pull first";
  - with none, web-push pushes to the new place and prints "Delete the old copy in Drive: grade_web/<course>".
  
  After every push, if `grade_web/<semester>` isn't visible in the Drive for Desktop folder, web-push prints a
  one-line hint to add the shortcut in Drive (right-click › Organise › Add shortcut › grade_web).
- **D8 web-pull** reads the new place, or the old `grade_web/<course>` when only that one holds a push.json. When
  both do, it reads the one with web edits not pulled (the new place when neither has any), and refuses, naming
  both, when both have edits. An old copy with the same push_id as the new one counts as the same copy (Drive for
  Desktop can show a grade_web shortcut as a folder of its own), and so does a link to it. web-push's D7 checks use
  the same rule. The D7 refusal holds even with `--force`: `--force` drops only the edits on the copy it replaces.

## Design
### Server (`web/apps_script/Code.js`; `drive.js` unchanged)
- New `coursesIn_(root)` returns `[{path, group, folder}]` and the listings it made. It lists grade_web's children,
  then lists every item's children in one batch (`childrenOf_`, already batched), and classifies each item (D3). It
  then lists the subfolders of the groups in one more batch. An item name containing `/` is reported unavailable
  ("Folder names can't contain /").
- `openCourses_(folders, cache, listed)` gets an optional `listed` map of children it already has, so a top-level
  course isn't listed twice. Query count: flat stays ≤ 4, and with groups it's ≤ 5, whatever the number of courses.
- `listCourses`: each course carries `folder: <path>` and `group: <name|null>`; groups with no courses go in
  `groups: [{name, count}]`.
- `withCourse_(name, path, …)` resolves 1 or 2 segments by name (group first, then course). A path whose first
  segment is a course, or that has more than 2 segments, is `NOT_FOUND`.

### Client
- `client_state.html`: course id = path (no change of shape). Add `strandedDrafts(courses)` (D6) and
  `migrateKeys(courses)` (D4), both called after a fresh list.
- `client_views.html`: `courseList` groups by `group` (D5); empty-group line; the stranded-drafts section with
  Discard.
- `style.html`: `.group-head`, which matches the existing `.muted` and heading scale.

### Mac (`src/webdrive.py`, `src/webpush.py`, `src/webpull.py`, `grader.py`)
- `webdrive.place_of(root, course, semester=None)` returns `(new, old)`, where `new` =
  `root/<$GRADE_WEB_COURSES|grade_courses>/<semester or course.parent.name>/<course.name>` and `old` =
  `root/grade_web/<course.name>`. `mirror_of` callers move to it.
- webpush: target = `new`, with the D7 checks before the first write. That keeps the rule that a refusal writes
  nothing.
- webpull: D8 lookup.
- grader.py: `--semester NAME` on web-push and web-pull, and help text naming `grade_courses/<semester>/`.

## Files
`web/apps_script/{Code.js, client_state.html, client_views.html, style.html}`,
`src/{webdrive,webpush,webpull}.py`, `grader.py`. New tests: `web/tests/groups.test.js`, with additions to
`client_memory.test.js`, `speed.test.js`, `tests/test_web_push.py` and `tests/test_web_pull.py`. In the fake Drive,
symlinks are already shortcuts, so a group is a symlink to a tmp `grade_courses/2569-1`. Docs: `web/SPEC.md`
(availability, browser storage keys, Mac commands), `web/README.md` (the term workflow: push, add one shortcut per
term, remove it at term end), and `INTEGRATION.md` only if it names the Drive path (it doesn't today).

## Edge cases
- The same course name in two linked groups: these are distinct paths, and the cards show the group heading.
- A group shortcut whose target is gone: the group is empty, so it shows "No pushed courses in <name>".
- A course moved from flat to a group while a phone holds its draft: the draft is migrated (D4), and the existing
  push-changed check (edge 38) still applies.
- Drive briefly lists nothing: no stranded-drafts line (D6), and nothing is deleted.
- A cached list from before the update (no `group` field) is drawn flat until Drive answers.
- A laptop course not under a semester folder (`~/cmru/teachings/X_grading`) goes to `grade_courses/teachings/…`.
  web-push prints the target, and `--semester` fixes it.

## Out of scope
- The app creating or removing shortcuts. web-push moving or deleting old flat copies itself.
- Groups nested more than one level. Grouping by course.json `term`.
- grade-tui and exam_projects.

## Verification
1. Test first: the new and extended node and pytest tests fail before the change and pass after. Full suites: node
   (155 + new), pytest (168 + new), `web/scripts/e2e.sh` → `E2E OK`.
2. Extend `e2e.sh` with a tmp-only end-to-end run:
   - lay a fixture course copy at `tmp/teachings/2569-1/<course>`;
   - run `grader web-push --drive-root tmp/drive` and check that it lands in `grade_courses/2569-1/` and prints the
     shortcut hint;
   - symlink `grade_web/2569-1 → grade_courses/2569-1`, then `listCourses` through `gas_run.js` shows the group;
   - `saveBatch` on `2569-1/<course>`, then `grader web-pull --yes` brings the edit into the tmp Mac copy;
   - remove the symlink: the course is no longer listed;
   - an old flat copy with an unpulled edit makes web-push refuse.
3. WebKit iPhone 13 preview at 390 and 844 widths: group headings, the empty-group line, and the stranded-drafts line
   with Discard.
4. Deploy v13 to both deployments. On the real Drive, the user pushes a **test copy** (never a real course folder in
   `~/cmru/teachings`) to `grade_courses/test/`, adds the shortcut `grade_web/test`, and opens it on the phone with
   `?timing=1`.
