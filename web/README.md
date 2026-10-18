# grade_web

View and edit grade_dashboard courses from an iPhone or any browser. A Google Apps Script web app on the CMRU
account reads course copies in `My Drive/grade_web/<course>/`. The design is in `SPEC.md`.

Status: T1 spike. The web app shows `hello` and the folder names under `My Drive/grade_web/`. No student data.

## Deploy (clasp)

Needs clasp 3 (`npm install -g @google/clasp`), `clasp login` with the CMRU account, and "Google Apps Script API"
turned on at https://script.google.com/home/usersettings. Run every command from `grade_dashboard/web/`.

### First time: create the project

```bash
clasp show-authorized-user          # must print the CMRU account; otherwise: clasp logout && clasp login
clasp create-script --type standalone --title grade_web --rootDir out/clasp_new
rm -r out/clasp_new
sed -i '' 's#"rootDir": "out/clasp_new"#"rootDir": "apps_script"#' .clasp.json
clasp show-file-status              # must list exactly apps_script/appsscript.json, Code.js, Index.html
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
```

Keep the deployment ID and the URL out of the repo.

### Authorise, and run the T1 round-trip spike

1. `clasp open-script` opens the editor.
2. Pick `spikeRoundTrip` in the function menu next to Run, then click **Run**.
3. The first run asks for permission. Choose the CMRU account and allow "See, edit, create and delete all of your
   Google Drive files" and "See your primary Google Account email address". Those are the only two scopes, and the
   web app needs nothing else.
4. Read the Execution log. Report its four lines:
   `PASS|FAIL createFile bytes …`, `PASS|FAIL setContent bytes …`, `PASS|FAIL getDataAsString text …` and
   `SPIKE PASS|SPIKE FAIL`.

The spike writes one fake CSV (IDs `99…`, invented Thai names, BOM, CRLF) into `My Drive/grade_web/_spike/`, then
trashes the file and the folder. If `grade_web/` doesn't exist yet, the spike creates it (empty).

### Open it on the iPhone (M1)

1. To see a folder listing before any `grader web-push`, create one or two empty folders in
   `My Drive/grade_web/` at drive.google.com (for example `test_a`, `test_b`).
2. `clasp open-web-app`, then pick the `grade_web` deployment (not `@HEAD`). The URL opens in the Mac browser. It
   looks like `https://script.google.com/a/macros/<domain>/s/<deployment ID>/exec`.
3. Send the URL to the iPhone (AirDrop or Notes) and open it in Safari, signed in to the CMRU account.
4. Expected: `hello`, then the folder names (or `grade_web folder not found`). No student data appears.

If deploying or opening is blocked by the Workspace admin (an error page from Google, or a policy message), stop.
Note the exact message and don't try another account. The lead asks whether to use a personal account or contact
CMRU IT.

### Second account check (M3)

1. In a private window, sign in to a different Google account and open the URL. Expected: Google's own "no
   permission" page, or `Not available`. Nothing else.
2. In a private window, signed out, open the URL. Expected: Google's sign-in page.

A pass means neither shows `hello` or any folder name.
