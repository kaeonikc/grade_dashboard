# ADR 002: Edit journal merged on the Mac, with one writer per Drive file and one history entry per pull

Date: 2026-10-18 · Status: accepted

## Context
The web app edits the Drive copy of a course. Those edits must reach the Mac copy (the master) without losing work.
They must also not overwrite edits made on the Mac in grade-tui since the push. The Mac sees Drive only through Drive
for Desktop, whose local copy can lag the cloud by seconds to minutes (edge 15). The Mac has no compare-and-set on a
Drive file, so when two parties rewrite the same file, the last writer silently wins (or Drive makes a
`name (1).ext` conflict copy). The brief fixed "journal + Mac merge" and the `web_edits.jsonl` name. This ADR
records how it is made safe.

## Decision
1. **Journal, not file copy.** Each web Save appends one line per changed cell (and one per config part) to
   `grade_web/<course>/web_edits.jsonl`, carrying `original` (the Drive value it started from) and `value`.
   `grader web-pull` replays the journal through grade-tui's own `apply_edits`, so every cell is conflict-checked
   against the Mac's current value. web-pull never copies a Drive CSV over a Mac file.
2. **One writer per file.**
   | Drive file | Written by | Never written by |
   |---|---|---|
   | `web_edits.jsonl` | the web app only (under LockService). web-push only *creates* it when it doesn't exist | web-pull, web-push (no rewrite, no truncate, no delete) |
   | `archive/*.jsonl` | the Mac only, always as a **new** file (never overwritten) | the web app |
   | `push.json`, roster, `data/*.csv` | web-push. The web app splices target cells into `data/*.csv` | — |
   | `course.json` | web-push. The web app rewrites it on a config save | — |
3. **Pulled lines leave the journal by key.** Every line has a key `batch#seq`. A line counts as pulled once its key
   appears in an `archive/` file. web-pull and web-push compute "unpulled" = journal lines minus archived keys. The
   web app physically removes archived lines from `web_edits.jsonl` at the start of its next locked call (the
   *trim*). So the Mac never rewrites a file the cloud may have changed since the Mac's last sync. A line Drive for
   Desktop hasn't brought down yet is invisible to web-pull, isn't archived, and stays for the next pull (edges 15
   and 16).
4. **Journal first, then CSVs, with roll-forward.** A web Save sets a pending marker (ScriptProperties), appends its
   journal lines, splices the CSVs, then clears the marker. If the save dies in between, the next locked call
   re-applies the pending batch from the journal. So a Drive CSV value always has a journal line. A Retry finds the
   cells already holding the value and reports them as saved, with no second journal line (S8.3, edge 35).
5. **One history entry per pull.** web-pull opens one `history.Entry(course, "grader", "web-pull")`, captures the
   config and the attendance baseline itself, and passes the entry into `apply_edits(..., entry=e)`, which passes it
   on to `_sync_total` / `_sync_attendance` / `attendance.auto_sync`. The total refresh and the attendance baseline
   land in the same entry, so a plain `grader undo` reverts the whole pull (S11.3, edge 31).

## Alternatives considered
| Option | Why not |
|---|---|
| web-pull copies the Drive CSVs over the Mac CSVs | Loses every Mac edit made since the push. No per-cell conflict check (S11.4) |
| web-pull rewrites `web_edits.jsonl` without the applied lines (the literal reading of S11.9) | If the local copy is stale, the rewrite drops lines saved in the cloud after the last sync. That breaks edge 15, the hard "never lose work" rule |
| web-push writes a fresh empty `web_edits.jsonl` each time | The same stale-overwrite risk as above, through the push |
| One journal file per batch (`journal/<batch>.jsonl`), moved to `archive/` by web-pull | Also safe, but it departs from the `web_edits.jsonl` name fixed in REQUIREMENTS/brief, and web-pull would move Drive files instead of only creating new ones |
| CSVs first, then journal | A crash between them leaves a Drive value with no journal line. The next push replaces it and the edit is lost |
| Call `apply_edits` as it is (its own snapshot) and `update_course_config` separately | Three or more history entries per pull (edit, totals, attendance, config). `grader undo` would revert only part of the pull |

## Consequences
- Right after a pull, `web_edits.jsonl` still physically holds the pulled lines until the web app's next call trims
  them. Every reader (web-pull, web-push, web app counts, Undo) ignores archived keys, so the visible behaviour of
  S11.9/S11.10 holds. The Gate 2 reviewer should confirm this reading of S11.9.
- If a push races a web save that Drive for Desktop hasn't synced, the journal keeps lines tagged with the old
  `push` id. They stay unpulled (the web app counts them, the next web-push refuses) and web-pull applies them
  against the Mac values as usual. Nothing is lost. The Drive CSV just shows the pushed value until the pull.
- The trim's ScriptProperties record (archive names already processed) is only a cache. Trimming is idempotent, so a
  new script project simply re-reads every archive.
- **Do not "simplify"** web-pull or web-push into rewriting or truncating `web_edits.jsonl`, and do not drop the
  `entry` argument from `apply_edits`. Each reintroduces a loss or partial-undo bug.
