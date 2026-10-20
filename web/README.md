# grade_web

View and edit grade_dashboard courses from an iPhone or any browser. A Google Apps Script web app on the CMRU
account reads course copies on Drive. `grader web-push` puts a course in `My Drive/grade_courses/<semester>/<course>/`
(the semester is the folder the course sits in on the Mac, such as `2569-1`), and `grader web-pull` brings the web
edits back to the Mac copy (the master). The design is in `SPEC.md` and `../SPEC_semester_groups.md`.

The phone lists what `My Drive/grade_web/` holds. Each term:
1. Push the term's courses from the Mac: `grader web-push` in each course folder.
2. In Drive, right-click `grade_courses/2569-1` › Organise › Add shortcut › `grade_web`. The phone then lists that
   term's courses under the heading 2569-1.
3. At the end of the term, after the last `grader web-pull`, remove the shortcut from `grade_web`. The copies stay in
   `grade_courses/2569-1`, untouched, and the phone no longer lists them.

A shortcut to a single course folder works too, and so do courses pushed before semester folders (folders directly
in `grade_web`). web-push names such an old copy when it pushes the course to its semester folder; delete it in
Drive then. No sharing is needed when `grade_courses` is in the same CMRU My Drive. A folder in another account's
Drive needs edit access shared to the CMRU account.

Status: the web app follows grade-tui's tabs: [1] Summary Scores, [2] Raw Details (one category at a time, picked
from the ☰ Categories menu; the table on wide screens, column mode on phones, with Fill, Save and undo), [3] Analytics
› Overview (statistics, grade distribution, histogram, box plot) and [4] Grading (weights and boundaries, each
letter's interval, live distribution). Attendance opens as an overview grid like grade-tui's (`../SPEC_attendance_grid.md`). See also
`../SPEC_web_tabs.md`, `../SPEC_grade_order.md` and `../SPEC_landscape.md` (phone landscape).

The web app is 10 files in `apps_script/`, pushed as they are (no build step):

| File | Kind in the editor |
|---|---|
| `appsscript.json` | manifest |
| `Code.js`, `drive.js`, `csv.js`, `grades.js`, `journal.js` | script (`.gs` in the editor) |
| `Index.html`, `style.html`, `client_state.html`, `client_views.html` | HTML |

## Deploy (clasp)

Needs clasp 3 (`npm install -g @google/clasp`), `clasp login` with the CMRU account, and "Google Apps Script API"
turned on at https://script.google.com/home/usersettings. Run every command from `grade_dashboard/web/`.

### First time: create the project

```bash
clasp show-authorized-user          # must print the CMRU account; otherwise: clasp logout && clasp login
clasp create-script --type standalone --title grade_web --rootDir out/clasp_new
rm -r out/clasp_new
sed -i '' 's#"rootDir": "out/clasp_new"#"rootDir": "apps_script"#' .clasp.json
clasp show-file-status              # must list exactly the 10 files in the table above
```

`create-script` writes the starter `Code.js` and `appsscript.json` into its `--rootDir`, overwriting whatever is
there. That's why it runs in the throwaway `out/clasp_new/` (git-ignored) and `.clasp.json` is pointed at
`apps_script/` afterwards. `.clasp.json` holds the script ID and is git-ignored. Never commit it.

On another Mac, for an existing project: `cp .clasp.json.example .clasp.json`, then paste the script ID from the
editor's Project Settings (gear icon).

### Push and deploy

```bash
clasp push --force                                  # --force: replace the starter manifest with ours
clasp create-deployment --description "grade_web"
```

The web app runs as you, and only you can open it. Both settings come from `appsscript.json`
(`executeAs: USER_DEPLOYING`, `access: MYSELF`). To check them, open the editor (`clasp open-script`), then
Deploy > Manage deployments. They should read "Execute as: Me" and "Who has access: Only myself".

After a code change, push and update the **same** deployment so the URL stays the same:

```bash
clasp push --force
clasp list-deployments                              # the ID next to "@<number> - grade_web" (not @HEAD)
clasp update-deployment <that deployment ID> --description "grade_web"
clasp list-deployments                              # must now show the new @<number>
```

`list-deployments` can lag a few seconds behind an update, so list again before concluding anything. With clasp
3.4.1, `update-deployment` without `-V` may create the new version (it prints `Redeployed … @N`) and leave the
deployment on the old one. The sure way is `clasp create-version "<note>"` (prints N) and then
`clasp update-deployment <that deployment ID> -V <N> --description "grade_web"`, for each deployment.

The Apps Script parser rejects BigInt literals (`1n`) in the `.js` files; use `BigInt(1)`.

Keep the deployment ID and the URL out of the repo.

### Authorise

The first run asks for permission: the first time you open the URL, or the first time you run a function in the
editor. Choose the CMRU account and allow "See, edit, create and delete all of your Google Drive files" and "See your
primary Google Account email address". Those are the only two scopes, and the web app needs nothing else.

The manifest also turns on the Advanced Drive service (v3), which lists folders faster. It uses the same Drive scope.
If the Workspace admin blocks advanced services, the page shows a Google error on opening: stop and note the message.

**Timing:** add `?timing=1` to the web app URL to show a grey line under the header with each step's time (page,
list, load, save) and its Drive work (queries, downloads, cache hits). It shows times and counts only.

## Deploy by paste-in (when clasp or the Apps Script API is blocked)

This gives the same web app as clasp. Use it only if `clasp push` is refused by the Workspace admin.

1. Open https://script.google.com signed in to the CMRU account. Click **New project** and rename it `grade_web`
   (click "Untitled project").
2. Project Settings (gear icon): tick **Show "appsscript.json" manifest file in editor**. Back in the Editor
   (`< >` icon), open `appsscript.json` and replace its whole content with `apps_script/appsscript.json`.
3. Script files: open the starter `Code.gs` and replace its content with `apps_script/Code.js`. Then, for each of
   `drive.js`, `csv.js`, `grades.js` and `journal.js`, click **+** next to Files > **Script**, type the name without
   `.js` (`drive`, `csv`, `grades`, `journal`), and paste the file's content over the starter function.
4. HTML files: for each of `Index.html`, `style.html`, `client_state.html` and `client_views.html`, click **+** >
   **HTML**, type the name without `.html` (`Index`, `style`, `client_state`, `client_views`; the case matters), and
   paste the file's content over the starter page.
5. Save (Cmd+S). The Files list now shows exactly the 10 files of the table above.
6. **Deploy > New deployment**. Next to "Select type", click the gear > **Web app**. Description `grade_web`,
   Execute as **Me**, Who has access **Only myself**. Click **Deploy**, authorise (see Authorise above), and copy the
   Web app URL.

After a code change, paste the changed files again, then **Deploy > Manage deployments**, click the pencil on the
`grade_web` deployment, choose Version **New version**, and click **Deploy**. The URL stays the same. (**New
deployment** would make a second URL.)

## Open it on the iPhone

1. `clasp open-web-app`, then pick the `grade_web` deployment (not `@HEAD`). With paste-in, use the copied URL. It
   looks like `https://script.google.com/a/macros/<domain>/s/<deployment ID>/exec`.
2. Send the URL to the iPhone (AirDrop or Notes) and open it in Safari, signed in to the CMRU account.
3. Expected: `grade_web`, `Courses on Drive`, and one card per pushed course with its name, `course ID · term`,
   `Pushed {time}`, and `N edits not pulled · last saved {time}` (or `No edits waiting to be pulled`). Before any
   `grader web-push`: `No pushed courses yet.`

If deploying or opening is blocked by the Workspace admin (an error page from Google, or a policy message), stop.
Note the exact message and don't try another account.

### Another account, or signed out

In a private window signed in to a different Google account, the URL shows Google's own "no permission" page or
`Not available`. Signed out, it shows Google's sign-in page. Neither shows a course, a name, an ID or a score.

### Several Google accounts in one browser

Apps Script web apps often fail to open when the browser is signed in to more than one Google account: Google picks
the default account and shows its own error page (for example "Sorry, unable to open the file at this time"). The
app never shows another account's data, because it runs as you, opens only for you, and checks the account again.
To open it:

- Best: a Safari profile used only for the CMRU account (iOS 17 or later: Settings > Apps > Safari > New Profile).
  Sign in there with the CMRU account only, and open the URL in that profile.
- Or sign out of the other accounts at https://accounts.google.com in that browser.
- Or a private window signed in to the CMRU account only. Unsaved edits can't be backed up in a private window.

## Limits

Only edits made in the web app are pulled. An edit made to a Drive copy any other way (the file opened in Google
Sheets, or edited by hand) is not pulled to the Mac, and the next `grader web-push` replaces it.

## Repairs by hand

The web app shows a course as `Unavailable` when its Drive folder holds duplicate files or a damaged journal, and
`grader web-push` and `grader web-pull` refuse it too. While it is unavailable, the web app writes nothing to the
course, so you can repair it safely by following one of the procedures below. Do it by hand. No command does it for
you.

### Duplicate files

You see `Drive has duplicate files: …` in the web app, or a copy like `web_edits (1).jsonl`,
`…_homework (1).csv` or `course (1).json`, or two files with the same name at drive.google.com. Drive makes these
copies when two devices write the same file at once.

1. Wait until Drive for Desktop shows "up to date". Don't use the web app for this course until the end.
2. If the journal has a copy (`web_edits (1).jsonl`, or a second `web_edits.jsonl`):
   1. Copy `web_edits.jsonl` and its copy somewhere outside the course folder first (for example the Desktop), as a
      backup.
   2. Open both in a text editor. Append to `web_edits.jsonl` every line of the copy whose `batch` and `seq` pair
      isn't already in it.
   3. Sort all lines of `web_edits.jsonl` by `batch`, then by `seq` (batch IDs sort by time). Never change a line.
   4. Save, then delete the copy (in Finder or at drive.google.com).

   Put no backup inside `archive/`, because every file there is read as an archive.
3. Any other copy (a CSV, `course.json`, `push.json`): delete the `(1)` copy. Those files are rebuilt from the Mac.
   If you're unsure which one is right, delete the copy anyway, then run `grader web-pull` (preview, then
   `grader web-pull --yes`) and `grader web-push` to refresh Drive. The journal carries the web edits, not the CSVs.
4. Wait for "up to date", then reload the web app (the course opens again). Then run `grader web-pull`.

### Damaged journal

You see `web_edits.jsonl has damaged lines: 3, 7` in the web app, or `grader web-push` or `grader web-pull` stops
with `web_edits.jsonl has lines that aren't valid JSON: 3, 7`. A line is damaged when it was cut off, for example by
a sync that stopped halfway.

1. Wait for "up to date". Copy `web_edits.jsonl` somewhere outside the course folder (for example the Desktop), as a
   backup.
2. Open it in a text editor and go to the line numbers shown. For each damaged line:
   - If it is a cut-off copy of a complete line nearby (same `batch` and `seq`), delete it.
   - If it has no complete twin and the JSON is obviously completable (for example a missing `"}` at the end), fix
     it.
   - Otherwise, delete it, and first write down its student ID, column and value from the readable part. Re-enter
     that value by hand on the Mac after the pull.

   Never edit or delete a valid line.
3. Save, wait for "up to date", and run `grader web-pull`. It must now show the preview without the error. Then run
   `grader web-pull --yes` and reload the web app.

## The T1 round-trip spike

The spike checks that Drive keeps a CSV's bytes (Thai, BOM, CRLF) through a write and a read.

1. `clasp open-script` opens the editor.
2. Pick `spikeRoundTrip` in the function menu next to Run, then click **Run** (authorise the first time).
3. Read the Execution log. Report its four lines:
   `PASS|FAIL createFile bytes …`, `PASS|FAIL setContent bytes …`, `PASS|FAIL getDataAsString text …` and
   `SPIKE PASS|SPIKE FAIL`.

The spike writes one fake CSV (IDs `99…`, invented Thai names, BOM, CRLF) into `My Drive/grade_web/_spike/`, then
trashes the file and the folder. If `grade_web/` doesn't exist yet, the spike creates it (empty). While `_spike`
exists, the course list shows it as unavailable (it has no `course.json`).
