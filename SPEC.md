# Spec: Shrink git repo size (strip committed build artifacts + junk from history)

## Context

"Clean up the memory" = shrink the git repository (`.git` was **413MB**), not
Claude's memory system or app runtime RAM. Confirmed with user.

Root cause: `rust_tui/target/` (Cargo build output — 875MB on disk, 11,545 files) had been
committed to git across many commits, including individual blobs up to 23MB
(`libtokio-*.rlib`, `dep-graph.bin` incremental-compilation files). `.gitignore` was added
for `courses/`, `__pycache__/`, etc. at some point, but never for `rust_tui/target/`, and
files already tracked before a `.gitignore` rule exists stay tracked regardless of the rule.

**Correction made mid-conversation:** `course_info_prep/`'s 3 tracked files
(`convert_student_info.py`, `excel_cleaner.py`, `.agents/skills/excel-prep/SKILL.md`) turned
out to be legitimate source files, not bloat — `repclasslist.xls` is actually a separate
16KB file at repo root, and it's small enough not to be worth touching. `course_info_prep/`
was left untouched.

## Scope — paths stripped from git history (via `git filter-repo`)

1. `rust_tui/target/` — the 875MB Cargo build directory (source `rust_tui/src/`,
   `Cargo.toml`, `Cargo.lock`, `CLAUDE.md`, `SPEC.md` were kept, only `target/` went).
2. All tracked `__pycache__/` contents (5 files).
3. All tracked `.DS_Store` files (7).
4. Backup files: `grader.py.bak`, `src/dashboard.py.bak`.

Nothing else was touched — `courses/`, `src/*.py`, `grader.py`, `course_info_prep/`,
`repclasslist.xls`, `test_formula_header.xlsx`, `theme.json.example`, docs, and the
`grader`/`grade-tui` symlinks are all left exactly as they were.

## Out of scope

- Claude Code's own memory files (not what "memory" referred to).
- Streamlit runtime/caching behavior.
- Rewriting/squashing commit messages or reordering history — `filter-repo` only removed
  the listed paths from every commit's tree; commit structure and messages are otherwise
  preserved (22 original commits + 1 new `.gitignore` commit = 23).
- Touching `course_info_prep/` or `repclasslist.xls`.
- Any changes to app logic in `src/`, `grader.py`, or `rust_tui/src/`.

## What was done

1. **Safety backup** — `git bundle create ../grade_dashboard_backup_20260720_005651.bundle --all`,
   verified with `git bundle verify` before proceeding.
2. **Installed** `git-filter-repo` via `pip3 install --user git-filter-repo`.
3. **Rewrote history** with `git filter-repo --force --invert-paths` over the 7 paths listed
   above. `filter-repo` auto-removed the `origin` remote as a safety measure.
4. **Updated `.gitignore`** — added `rust_tui/target/`, `*.bak`, `.DS_Store`. Committed as
   `d2a564d`.
5. **Re-added** `origin` remote (`git@github.com:kaeonikc/grade_dashboard.git`).
6. **Verified local shrink** — `.git` went from 413MB → 2.4MB.
7. **`cargo clean`** on the working-tree `rust_tui/target/` — project directory went from
   1.3GB → 91MB.
8. **Force-pushed** — `git push origin --force --all` (solo repo, no other clones, no tags).

## End-to-end verification (all passed)

1. `git count-objects -vH`: `.git` shrank from 413MB to 2.4MB locally.
2. `git log --oneline`: all 22 original commits preserved, plus the new `.gitignore` commit.
3. `git ls-files | grep -E 'rust_tui/target|__pycache__|\.DS_Store|\.bak'` → empty.
4. Fresh clone from `origin`: `.git` is 3.8MB, 23 commits — confirms the shrink landed on
   the remote, not just locally.
5. `python3 grader.py dashboard`: imports cleanly, lists all 7 courses, reaches the
   interactive course-selector prompt (only failed on EOF because the verification run had
   no stdin — proves no tracked file the app needs was caught by the filters).
6. `cargo build --release --manifest-path rust_tui/Cargo.toml` from a clean `target/`:
   succeeds (only pre-existing dead-code warnings, no errors).
