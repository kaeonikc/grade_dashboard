# Spec: Rich Terminal Dashboard

## Summary

Replace the Streamlit web GUI (`src/dashboard.py`) with a sequential terminal dashboard
using `python-rich`. The launch command (`python grader.py dashboard`) is unchanged.
No browser or server is involved — everything renders in the current terminal session.

---

## Dependencies

**Removed from `requirements.txt`:**
- `streamlit>=1.30.0`

**Added to `requirements.txt`:**
- `rich>=13.0.0`

`pandas`, `pyyaml`, `openpyxl` unchanged. `altair` was a transitive Streamlit
dependency and is no longer required.

---

## Files Changed

| File | Change |
|---|---|
| `src/dashboard.py` | Full rewrite — Rich terminal flow replaces Streamlit script |
| `requirements.txt` | Swap `streamlit` → `rich` |
| `grader.py` | `run_dashboard()` imports and calls `src.dashboard.run()` directly (no subprocess) |

`src/data_loader.py` and `src/calculators.py` are **not touched**.

---

## Terminal Flow

The dashboard runs as a sequential interactive loop. Prompts are handled by
`rich.prompt.Prompt` and `rich.prompt.Confirm`.

```
python grader.py dashboard
  │
  ├─ [find_courses()] scan ./ and courses/ for dirs containing config.yaml
  │
  ├─ [select_course()] numbered list → Prompt.ask("Select course", default="1")
  │
  ├─ load_config()  →  load_course_data()
  │
  ├─ [show_warnings()]  Panel with yellow text — only printed if validation warnings exist
  │
  ├─ Confirm.ask("Show weighted scores?", default=True)
  │
  ├─ calculate_final_grades(use_weighted)
  │
  ├─ Rule  ─── Course Name — Term ───
  │
  ├─ [show_metrics()]         Table: Total Students | Average Score | Highest Score
  │
  ├─ [show_roundup_summary()] Panel (border=blue):
  │     "Grades improved by rounding: N"
  │     Table: Grade | Original | Rounded | Change (green/red delta)
  │     └─ if N > 0: Confirm.ask("Show students with improved grades?")
  │           └─ Table: Student ID | Name | Original Final Score | Final Score | Original Grade | Grade
  │
  ├─ [show_student_table()]
  │     ├─ Summary table (console.print — inline, no pager):
  │     │     Columns: Student ID, Name, *_pct cols, Coursework Total, Final Score, Grade
  │     │     Box: custom _DIVIDER_BOX (│ between columns, ─┼ header separator, no outer border)
  │     │     Headers: two-line (col name / annotation on separate lines)
  │     │
  │     └─ Raw scores table (pager via less -SR):
  │           Columns: Student ID, Name, all raw assignment columns from data_mapping
  │           Box: same _DIVIDER_BOX style
  │           Headers: two-line where annotation exists
  │
  ├─ [show_grade_distribution()]  Rule + ASCII bar chart:
  │     F → A printed top-to-bottom
  │     bar = "█" * filled + "░" * (30 - filled)  (scaled to highest grade count)
  │
  ├─ Confirm.ask("Export final report to CSV?", default=False)
  │     └─ [export_reports()] writes final_grades.csv + copy_friendly_scores.csv
  │           under <course_path>/reports/
  │
  └─ Confirm.ask("View another course?", default=False)
        ├─ Yes → loop back to select_course()
        └─ No  → exit
```

---

## Student Table Styling

### `_DIVIDER_BOX` (custom `rich.box.Box`)

```
        (no top border)
  │     (head rows: no outer edges, │ between columns)
 ─┼     (header separator: ─ fill, ┼ at column crossings, no outer edges)
  │     (data rows: same as head)
        (no row separators)
        (no foot row separator)
  │     (foot rows)
        (no bottom border)
```

Each position is 4 characters: `[left_edge, fill, divider, right_edge]`.

### Two-line column headers

`_col_headers()` returns `\n`-separated strings instead of space-separated:

| Column | Old header | New header |
|--------|-----------|------------|
| raw score col | `hw1 (10 pts)` | `hw1\n(10 pts)` |
| `*_pct` col | `homework_pct (20 pts)` | `homework_pct\n(20 pts)` |
| `Final Score` | `Final Score (100 pts)` | `Final Score\n(100 pts)` |
| `Coursework Total` | `Coursework Total (30 pts)` | `Coursework Total\n(30 pts)` |

Rich renders the `\n` as a genuine line break in the column header row, so each
column is only as wide as its widest single line (col name or annotation), not the
full concatenated string.

### Visual result (summary table)

```
 Student ID  Name   homework_pct  Coursework Total  midterm_pct  Final Score  Grade
                    (20 pts)      (20 pts)          (30 pts)     (100 pts)
 ──────────────────────────────┼─────────────────┼────────────┼────────────┼──────
 1001        Alice       17    │       17         │     25     │     87     │  A
 1002        Bob         15    │       15         │     18     │     73     │  B
```

### Pager behavior

- **Summary table**: `console.print()` — inline, no pager. Multi-line headers reduce
  column widths enough to fit a standard ≥80-char terminal.
- **Raw scores table**: `_print_wide()` — renders at 500-char width, piped through
  `less -SR`. Falls back to `console.print()` if `less` is unavailable.

---

## Decisions Made

| Decision | Choice |
|---|---|
| Wide table overflow | Wrap/truncate to terminal width (Rich default) for summary; pager for raw scores |
| Weighted toggle | Interactive `Confirm.ask` every run, never a CLI flag |
| Per-loop settings | Re-prompt weighted toggle on each new course |
| Grade chart order | F at top, A at bottom (matches bar-chart reading convention) |
| Course pre-selection | Always interactive — no CLI arg to skip menu |
| Summary table column headers | Two-line: name on line 1, `(X pts)` on line 2 |
| Column dividers | Custom box with `│` inner dividers, `─┼` header separator, no outer border |
| Summary table pager | Removed — inline print only |
| Raw scores table pager | Kept — `less -SR` for horizontal scrolling |

---

## Out of Scope

- Live/reactive updates (no `textual`, no `curses`, no `Live` render loop).
- Keyboard navigation within tables (terminal scroll only).
- Persistent user preferences across sessions.
- Multi-course comparison or side-by-side views.
- Any new features not present in the original Streamlit dashboard.

---

## End-to-End Verification

```bash
# 1. Install dependencies
pip install -r requirements.txt
# Confirm: no streamlit, rich>=13 installed

# 2. Launch from project root
python grader.py dashboard

# 3. Expected terminal flow:
#    - Numbered course list appears
#    - Entering "1" (or course name) loads the course
#    - "Show weighted scores? [Y/n]" prompt appears
#    - After Enter: rule line, metrics table, round-up panel, student tables, bar chart
#    - Summary table prints inline with two-line headers and │ column dividers
#    - "Show raw assignment scores? [y/N]" — answering y opens less pager; q to exit
#    - "Export final report to CSV? [y/N]" — answering y writes reports/
#    - "View another course? [y/N]" — answering n exits cleanly

# 4. Check summary table fits terminal
#    Terminal width: tput cols  (typically 80–200)
#    Summary table should not truncate any column name or value

# 5. Verify export output
ls courses/<course>/reports/
# Should contain: final_grades.csv  copy_friendly_scores.csv
```
