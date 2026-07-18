# Spec: `*_copy_friendly_scores.csv` should mirror the rust_tui "For Submission" tab

## Background

The rust TUI's Dashboard tab [1] has a "For Submission" category
(`SUMMARY_CATEGORIES` in `rust_tui/src/app.rs:15`), rendered by
`draw_submission_table` in `rust_tui/src/ui.rs:588-700`. It shows up to
three side-by-side blocks, in this fixed order, each shown only if the data
exists:

1. **Cumulative Scores** — `Coursework Total`, shown if any row has that key
2. **Midterm** — `midterm_pct`, shown if `midterm_pct` is a summary column
3. **Final** — `final_pct`, shown if `final_pct` is a summary column

Each block has its own **ID** column immediately followed by its score
column, and adjacent blocks are separated by a thin `│` divider
(`rust_tui/src/ui.rs:648-673`). Block header format: `{Label}\n({pts} pts)`,
where `pts` is the category's weight × 100, printed as a bare integer when
whole (e.g. `70`) or with 1 decimal otherwise (e.g. `67.5`) —
`rust_tui/src/ui.rs:653-654`.

The CSV export path is: rust_tui → `bridge.rs::export_reports` → spawns
`python -m src.tui_api export-reports <path> <use_weighted>`
(`rust_tui/src/bridge.rs:160-166`, `src/tui_api.py:901-853`) → calls
`src.dashboard.export_reports` (`src/dashboard.py:224-258`), which writes
both `<prefix>_final_grades.csv` and `<prefix>_copy_friendly_scores.csv`.
**Only the copy-friendly file changes in this spec — `final_grades.csv` is
untouched.**

### Current bug
In today's `export_reports`, only the *first* block (`Coursework Total`)
keeps its `Student ID` column; the `Student ID` column is explicitly
dropped for every subsequent block (`src/dashboard.py:253-254`:
`copy_parts[i] = copy_parts[i].drop(columns=["Student ID"])`). So the
midterm/final blocks currently rely on positional row alignment with no ID
of their own — which is what this change fixes.

## Confirmed decisions (from interview)

1. **Every block gets its own `Student ID` column**, immediately before its
   score column — restoring/adding the ID column that's currently dropped
   for the midterm/final blocks.
2. **Score column headers switch to the TUI's block labels**, replacing
   today's raw-data-mapping-derived names:
   - `Cumulative Scores ({pts} pts)` (replaces today's
     `Coursework Total (Npts)`-style rename-derived header)
   - `Midterm ({pts} pts)` (replaces today's
     `{data_mapping['midterm'][0]} (Npts)`)
   - `Final ({pts} pts)` (replaces today's
     `{data_mapping['final'][0]} (Npts)`)
   - `pts` formatting matches the Rust logic exactly: bare integer if the
     weight×100 value is whole, else 1 decimal place — and note the space
     before `pts` (`"70 pts"`, not today's `"70pts"`).
3. **The repeated ID column is literally named `Student ID` every time**
   (duplicate header text across blocks is intentional and accepted —
   mirrors the TUI, which labels every block's ID column just `ID`).
4. **A blank spacer column is inserted between adjacent blocks** (header:
   empty string, all cells empty) to visually echo the TUI's `│` divider.
   No spacer before the first block or after the last one. If only one
   block exists, no spacer appears at all.
5. Block **order is always Cumulative → Midterm → Final**, regardless of
   `weights`/`data_mapping` order in `config.yaml` — matches the TUI's
   hardcoded order, not config iteration order.
6. Each block is included **only if its source column is present** in
   `final_df` (`"Coursework Total" in final_df.columns`,
   `"midterm_pct" in final_df.columns`, `"final_pct" in final_df.columns`)
   — same presence check already used today, just no longer gated through
   the `_col_headers`/`rename` machinery for these three columns.
7. **No `Name` column** in any block — matches the TUI, which shows ID
   only.
8. Score **values are written as-is** from `final_df` — `Coursework Total`,
   `midterm_pct`, `final_pct` are already `int` post-`ceil()`
   (`src/calculators.py:212-219`), so no additional rounding/formatting is
   needed; they already match what tab [1] displays.
9. If none of the three source columns are present, **no file is written**
   — same as today's `if copy_parts:` guard.

## Files/interfaces involved

- **`src/dashboard.py`** — `export_reports()` (lines 224-258) is the only
  function that changes. Specifically the `copy_parts` construction (lines
  235-256) is replaced with logic that:
  - builds an ordered list of `(id_series, score_series, header_label)` for
    whichever of Cumulative/Midterm/Final blocks are present,
  - concatenates them with a blank spacer `Series` of empty strings between
    consecutive present blocks,
  - writes the result to `<prefix>_copy_friendly_scores.csv` unchanged
    otherwise (same `report_dir`, same guard on non-empty).
  - The `weights` lookup for `pts` (cumulative weight sum excluding
    midterm/final, and `weights.get("midterm"/"final", 0)`) reuses the same
    computation already present in `_col_headers` (lines 152-154) — factor
    or duplicate it, but the resulting numbers must match what
    `_col_headers` computes today (which itself matches the Rust
    `cumulative_pts`/`midterm_pts`/`final_pts` computation).
- **Untouched**: `rust_tui/*`, `src/tui_api.py`, `src/calculators.py`,
  `src/data_loader.py`, the `_final_grades.csv` output, and the
  `_col_headers`/`display_df` machinery used for `final_grades.csv`.

## Out of scope

- Any change to `final_grades.csv`.
- Any change to the TUI's on-screen rendering (`rust_tui/src/ui.rs`) — it's
  the source of truth being mirrored, not something to modify.
- Adding a `Name` column, or any category besides Cumulative/Midterm/Final,
  to the copy-friendly export.
- Reordering blocks based on config — order stays hardcoded
  Cumulative → Midterm → Final.

## End-to-end verification

1. **Three-block case** — run the dashboard against a course with
   homework+midterm+final data, e.g.
   `courses/2026_S1_Cosmology_grading` or
   `courses/0_ฟิสิกส์ทั่วไป_(ข้อมูลจำลอง)_grading` (mock data, all three
   categories present). Trigger export either via the rust TUI's export
   action or directly:
   ```
   python -m src.tui_api export-reports "courses/2026_S1_Cosmology_grading" true
   ```
   Open the resulting
   `courses/2026_S1_Cosmology_grading/reports/2026_S1_Cosmology_copy_friendly_scores.csv`
   and confirm the header row is exactly:
   ```
   Student ID,Cumulative Scores (60 pts),,Student ID,Midterm (30 pts),,Student ID,Final (40 pts)
   ```
   (pts values per that course's actual weights), with a blank column
   between each block, and that every `Student ID` sub-column contains the
   full, correctly-ordered roster (not just the first block).
2. **Cross-check values** — pick 2-3 student rows and confirm the
   Cumulative/Midterm/Final numbers in the CSV match exactly what the rust
   TUI's tab [1] "For Submission" panel shows for those same students
   (same IDs, same integer values).
3. **Single-block edge case** — run against
   `courses/2026_S1_Optics_grading` (homework-only config, no
   midterm/final). Confirm the export either produces just
   `Student ID,Cumulative Scores (100 pts)` with **no spacer column**, or
   (if `Coursework Total` isn't computed for a homework-only weight config)
   confirms the existing "no file written" guard still behaves correctly —
   check which applies before asserting.
4. **Regression check** — confirm `*_final_grades.csv` for the same course
   is byte-identical to a pre-change run (this file's generation path is
   untouched).
