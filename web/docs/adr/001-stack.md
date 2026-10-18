# ADR 001: Google Apps Script web app on the phone, Python inside grade_dashboard on the Mac

Date: 2026-10-18 · Status: accepted · Deciders: the teacher (user), confirmed in the Gate 1 interview

## Context
The teacher wants to see and edit grade_dashboard courses from an iPhone or any browser: attendance in class, scores
after each homework, weights and boundaries now and then. The Mac may be off while this happens. Data must stay in
the teacher's CMRU Google Workspace account (it holds student names, IDs and grades). Only the teacher may open the
app. The Mac copy of each course stays the master, and grade-tui (`rust_tui/`) must not change. Sync between Drive
and the Mac is manual (`grader web-push` / `grader web-pull`). Targets: 300 students x 80 counted columns, a course
opens on 4G within 8 s, and a 60-cell save finishes within 5 s.

## Decision
- **Phone/browser side: Google Apps Script web app** (`stack.md` rank 4), executed as the owner, access "Only
  myself", deployed with `clasp` from `grade_dashboard/web/apps_script/` (paste-in fallback). Plain HTML, CSS and
  vanilla JS served by HtmlService. Server code uses only built-in services (DriveApp, LockService,
  PropertiesService, HtmlService, Utilities, Session). No Apps Script libraries, no npm runtime packages.
- **Mac side: rank 1 core, but inside the existing grade_dashboard repo**: two new `grader` subcommands
  (`web-push`, `web-pull`) in `src/webdrive.py`, `src/webpush.py`, `src/webpull.py`. They reuse `apply_edits`,
  `update_course_config`, `history.Entry`, `load_config`/`load_course_data`, `csvio` and `attendance`. They run
  on the interpreter and `requirements.txt` grade_dashboard already uses. No separate `uv` project and no new
  Python dependency.
- `node` runs only the tests (`node --test 'web/tests/*.test.js'`), on the pure JS modules shared by the server, the browser
  and the tests (ADR 004).

**Why rank 4 when rank 1 normally comes first:** a rank 1 CLI and a rank 2 Streamlit app both need a running Mac
(or hosting, which is a forbidden default) to reach a phone. Rank 3 (Typst) produces documents, not an editor.
Rank 5 (Rust TUI) is a terminal app, and grade-tui already fills that role. Apps Script is the only house-stack
option that runs while the Mac is off, needs no hosting, and already authenticates the one Google account the data
belongs to. The Mac half is still rank 1. It lives in grade_dashboard rather than a new `uv` project because
web-pull has to call grade_dashboard's own `apply_edits` and history code. Importing that from another project
would break the "no imports across project boundaries" rule, and copying it would fork the grade logic.

## Alternatives considered
| Option | Why not |
|---|---|
| Streamlit (rank 2) on the Mac, reached from the phone through a tunnel | The Mac must be on and reachable. A tunnel is cloud hosting plus an auth problem (both forbidden defaults) |
| Static HTML/JS page kept in Drive | Drive no longer serves HTML. With no server, nothing could check conflicts or serialize saves |
| Google Sheets as the data store (Apps Script over Sheets) | Converting the CSVs breaks byte-identical round-trips (S8.6) and leading-zero IDs (edge 5). Two copies would be master. grade-tui reads CSV |
| React/Vue PWA + Firebase/Cloud Run | Forbidden defaults (frameworks, Node server, cloud hosting, auth system), and far too big for one maintainer |
| Separate `uv` project for web-push/web-pull | It would have to copy or import grade_dashboard's `apply_edits`, history and loaders. The user fixed the code home as `grade_dashboard/web/` + `grader` subcommands |
| Apps Script with a bundler/TypeScript (clasp + esbuild) | A build step and npm dev deps for a few hundred lines of JS. ADR 004 shares code without one |
| Personal Google account instead of CMRU | Student data would leave the institutional account. Only the user may decide this (S0.2). The T1 spike checks CMRU first |

## Consequences
- Easier: nothing to host or patch. Google handles login and access ("Only myself"). The Mac can be off.
  web-pull gets grade-tui's exact write path (conflict check, history, xlsx mirror) for free.
- Harder: Apps Script has no local runtime, so only the pure modules are unit-tested in node. Drive I/O and the UI
  are checked by hand on the phone (the T1 spike, then each UI task). Each DriveApp call costs about 100-300 ms, so
  the server batches reads, and the browser does all the grade math.
- Risk: the CMRU Workspace admin may block web apps or the Apps Script API. T1 is a spike that stops the build if
  so (S0.2). If only the API is blocked, the README's paste-in procedure replaces clasp (S13.2).
- `src/tui_api.apply_edits`, `_sync_total`, `_sync_attendance` and `src/attendance.auto_sync` gain an optional
  `entry=None` argument (ADR 002). With the default, behaviour is unchanged, so grade-tui and its tests are untouched.
- Revisit if: the admin blocks web apps (ask the user, S0.2), offline use is wanted (backlog), or courses grow far
  beyond 300 x 80 (Drive I/O, not the math, becomes the limit).
