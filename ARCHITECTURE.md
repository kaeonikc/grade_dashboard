# Architecture: Grade Dashboard

## Overview

A local grading tool for university courses. Instructors drop CSV/XLSX score sheets into a course folder, define weights and grade boundaries in a YAML config, and launch either a Streamlit web dashboard or (per the planned migration) a Textual TUI to review grade distributions, inspect round-up effects, and export reports.

The design is deliberately flat: no database, no server, no framework beyond Streamlit. Data is read fresh on every dashboard load from plain files in the `courses/` directory tree.

## Entry Points

| Command / Trigger | File:Line | Description |
|---|---|---|
| `python grader.py init --course X --term Y` | `grader.py:14` | Scaffolds a new course directory with a template `config.yaml` |
| `python grader.py dashboard` | `grader.py:51` | Launches the Streamlit dashboard via subprocess |
| `streamlit run src/dashboard.py` | `src/dashboard.py:1` | Starts the UI directly (bypasses the CLI wrapper) |

## Directory Structure

```
grade_dashboard/
├── grader.py               # CLI entry point (init + dashboard subcommands)
├── requirements.txt        # Python dependencies
├── src/
│   ├── data_loader.py      # Config + CSV/XLSX ingestion, max-score extraction, merging
│   ├── calculators.py      # Weighted grade computation, rules, letter grade assignment
│   └── dashboard.py        # Streamlit UI (renders tables, charts, exports reports)
└── courses/
    └── <term>_<name>/
        ├── config.yaml     # weights, data_mapping, grade_boundaries, rules
        ├── data/           # Input: any .csv or .xlsx files (merged on Student ID)
        └── reports/        # Output: final_grades.csv, copy_friendly_scores.csv
```

## Module Map

```
┌─────────────────────────────────────────────┐
│                  grader.py                  │
│  CLI: subparsers(init | dashboard)          │
└────────────────────┬────────────────────────┘
                     │ subprocess / import
                     ▼
┌────────────────────────────────────────────────────────────────┐
│                       src/dashboard.py                         │
│  Streamlit UI — course selector, weighted toggle, export btn   │
└──────────┬─────────────────────────┬──────────────────────────┘
           │ load_config()           │ calculate_final_grades()
           │ load_course_data()      │
           ▼                         ▼
┌──────────────────────┐   ┌─────────────────────────────────────┐
│   src/data_loader.py │   │        src/calculators.py           │
│                      │   │                                     │
│  load_config()       │   │  calculate_final_grades()           │
│    reads config.yaml │   │    applies weights + rules          │
│                      │   │    applies ceil() rounding          │
│  load_course_data()  │   │    reconstructs Final Score         │
│    reads .csv/.xlsx  │   │                                     │
│    extracts max scores    │  assign_letter_grade()             │
│    merges on Student ID   │    threshold lookup                │
└──────────────────────┘   └─────────────────────────────────────┘
           │                         │
           ▼                         ▼
   (DataFrame, max_scores)    result DataFrame + Grade column
```

## Data Flow

```
courses/<term>_<name>/
  ├── config.yaml ──────────────────► load_config()
  │                                         │
  │                                         ▼
  │                                    config dict
  │                                  (weights, data_mapping,
  │                                   grade_boundaries, rules)
  │
  └── data/*.csv, *.xlsx ───────────► load_course_data()
        │  - strips whitespace from headers             │
        │  - extracts max scores                        │
        │    (a) column header: "col (40pts)"           │
        │    (b) sentinel row: Student ID = "Full Score"│
        │  - drops sentinel row from student data       │
        │  - merges all files on Student ID             │
        │  - coerces scores to numeric (NaN on failure) │
        │  - sorts by Student ID                        │
        └──────────────────────────────────────────────►│
                                             (DataFrame, max_scores dict)
                                                        │
                                                        ▼
                                          calculate_final_grades()
                                            1. filter to mapped cols only
                                            2. fillna(0) on score cols
                                            3. per category:
                                               - apply drop_lowest_homework rule
                                               - compute category % (score/max)
                                               - apply weight → weighted pts
                                               - accumulate Coursework Total
                                            4. save Original Final Score + Grade
                                            5. ceil() on Coursework Total,
                                               midterm_pct, final_pct
                                            6. recompute Final Score from
                                               rounded components
                                            7. assign letter grade
                                                        │
                              ┌─────────────────────────┘
                              │
                 ┌────────────┴─────────────────────────┐
                 ▼                                       ▼
         src/dashboard.py (Streamlit UI)         [Export button]
           - metrics: count, avg, high                   │
           - round-up summary table                      ▼
           - full student DataTable           courses/<name>/reports/
           - grade distribution bar chart       final_grades.csv
                                                copy_friendly_scores.csv
```

## Key Interfaces

| Symbol | Signature | Notes |
|---|---|---|
| `load_config` | `(course_path: str) -> dict` | Raises `FileNotFoundError` if `config.yaml` missing |
| `load_course_data` | `(course_path: str) -> tuple[DataFrame, dict]` | Returns empty DataFrame + `{}` if `data/` is missing or empty |
| `calculate_final_grades` | `(df, config, max_scores, use_weighted_scores=True) -> DataFrame` | Adds `*_pct`, `Coursework Total`, `Final Score`, `Grade`, `Original *` columns |
| `assign_letter_grade` | `(score: float, boundaries: dict) -> str` | Returns `"F"` if score is below all thresholds |
| `grader.py init` | `--course NAME --term TERM` | Creates `courses/<TERM>_<NAME>/` skeleton |
| `grader.py dashboard` | _(no args)_ | Delegates to `streamlit run src/dashboard.py` via subprocess |

**config.yaml keys:**

| Key | Type | Purpose |
|---|---|---|
| `weights` | `dict[str, float]` | Category multipliers; should sum to 1.0 |
| `data_mapping` | `dict[str, list[str]]` | Maps category name → CSV column names |
| `grade_boundaries` | `dict[str, float]` | Letter grade thresholds, highest to lowest |
| `rules.drop_lowest_homework` | `bool` | Drops worst homework per-student (requires ≥2 homework cols) |

## External Dependencies

| Package | Purpose | Configured in |
|---|---|---|
| `streamlit` | Web dashboard UI | `requirements.txt` |
| `pandas` | DataFrame ingestion, merging, numeric coercion | `requirements.txt` |
| `pyyaml` | Parses `config.yaml` | `requirements.txt` |
| `openpyxl` | Reads `.xlsx` files via pandas | `requirements.txt` |
| `altair` | Grade distribution bar chart (imported inside `dashboard.py`) | bundled with streamlit |

## Known Constraints & Design Decisions

- **CWD-relative course discovery**: `dashboard.py` resolves `courses/` relative to the process working directory. The dashboard must be launched from the project root, not from `src/`.
- **Two max-score formats, column header takes precedence**: Column header notation (`"col (40pts)"`) is processed first; the sentinel row (`Full Score`) is a fallback and will not overwrite a header-extracted max.
- **Scores exceeding their max are silently accepted**: No validation currently prevents a student score from exceeding its defined maximum. This causes category percentages > 100 % and a final score above the intended scale, but the grade assignment still works (returns the highest grade letter). A validation pass is needed (see `validate_scores` in `calculators.py`).
- **Ceil rounding is intentional**: `math.ceil()` is applied to `Coursework Total`, `midterm_pct`, and `final_pct` before the final score is summed. This is a deliberate pro-student rounding policy, not a bug. The `Original Final Score` / `Original Grade` fields preserve the pre-rounding values for comparison.
- **Ceil rounding changes the total**: The `Final Score` is reconstructed from the rounded components rather than rounding the raw total. If a course has categories beyond homework/quizzes/reports/midterm/final, those extra weighted contributions may be omitted from the reconstructed total.
- **Empty CSV rows produce ghost students**: A trailing blank row in a CSV becomes a student with an empty `Student ID` and all-zero scores after `fillna(0)`. This row appears in the dashboard table.
- **No tests**: There are no automated tests. Validation must be done manually by inspecting dashboard output.
