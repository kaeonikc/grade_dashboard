# Architecture: Grade Dashboard

## Overview

A local grading tool for university courses. Instructors drop CSV/XLSX score sheets into a course folder, define weights and grade boundaries in a YAML config, and launch either a Streamlit web dashboard or a Rust terminal UI (TUI) to review grade distributions, inspect round-up effects, edit scores, and export reports.

The design is deliberately flat: no database, no server, no framework beyond Streamlit. Data is read fresh on every load from plain files in the `courses/` directory tree. The Rust TUI shares the same Python calculation backend via a JSON-over-subprocess bridge, keeping all grading logic in one place.

## Entry Points

| Command / Trigger | File:Line | Description |
|---|---|---|
| `python grader.py init --course X --term Y` | `grader.py:14` | Scaffolds a new course directory with a template `config.yaml` |
| `python grader.py dashboard` | `grader.py:51` | Launches the Streamlit dashboard via subprocess |
| `streamlit run src/dashboard.py` | `src/dashboard.py:1` | Starts the web UI directly (bypasses CLI wrapper) |
| `./rust_tui/target/release/rust_tui` | `rust_tui/src/main.rs:19` | Launches the Rust terminal UI (must run from project root) |
| `cargo run --manifest-path rust_tui/Cargo.toml` | `rust_tui/Cargo.toml` | Build + run the Rust TUI in one step (from project root) |

## Directory Structure

```
grade_dashboard/
├── grader.py                   # CLI entry point (init + dashboard subcommands)
├── requirements.txt            # Python dependencies
├── theme.json.example          # Template for Rust TUI color theme override
├── src/
│   ├── data_loader.py          # Config + CSV/XLSX ingestion, max-score extraction, merging
│   ├── calculators.py          # Weighted grade computation, rules, letter grade assignment
│   ├── dashboard.py            # Streamlit UI (renders tables, charts, exports reports)
│   └── tui_api.py              # JSON-over-subprocess bridge for the Rust TUI
├── rust_tui/                   # Rust terminal UI (ratatui + tokio)
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs             # Terminal setup, tokio runtime, draw-event loop
│       ├── app.rs              # App state struct, AppEvent enum, all update logic
│       ├── bridge.rs           # Async subprocess callers → JSON deserialization
│       ├── types.rs            # Serde structs mirroring tui_api.py JSON shapes
│       ├── style.rs            # Theme struct, MONOKAI_PRO default, load_theme()
│       └── ui.rs               # Pure ratatui rendering (reads App, never writes it)
├── course_info_prep/           # One-off utilities: convert class lists to CSV format
│   ├── convert_student_info.py
│   └── excel_cleaner.py
└── courses/
    └── <term>_<name>/
        ├── course_info/
        │   └── <name>_config.yaml   # weights, data_mapping, grade_boundaries, rules
        ├── data/               # Input: any .csv or .xlsx files (merged on Student ID)
        └── reports/            # Output: final_grades.csv, copy_friendly_scores.csv
```

## Module Map

```
                    ┌──────────────────────────────────┐
                    │            grader.py              │
                    │   CLI: init | dashboard           │
                    └──────────────┬───────────────────┘
                                   │ subprocess
                                   ▼
              ┌────────────────────────────────────────────┐
              │             src/dashboard.py               │
              │   Streamlit UI — course selector,          │
              │   weighted toggle, round-up table,         │
              │   grade distribution chart, export btn     │
              └──────────┬──────────────────┬─────────────┘
                         │                  │
          ┌──────────────┘                  └──────────────────────┐
          │ load_config()                   calculate_final_grades()│
          │ load_course_data()                                      │
          ▼                                                         ▼
┌──────────────────────┐                        ┌──────────────────────────────┐
│  src/data_loader.py  │                        │     src/calculators.py       │
│                      │                        │                              │
│  load_config()       │─────(config dict)─────►│  calculate_final_grades()    │
│  load_course_data()  │─────(DataFrame,        │  assign_letter_grade()       │
│  parse_pts()         │      max_scores)───────►│  validate_scores()           │
│  parse_config_col()  │                        └──────────────────────────────┘
└──────────────────────┘
          ▲                          ▲
          │                          │ same Python stack, via JSON
          │ import                   │
          │                          │
┌─────────┴────────────────────────────────────────────────────────────┐
│                         src/tui_api.py                               │
│   JSON-over-subprocess bridge (CLI: get-courses | get-course-data |  │
│   update-score | update-config | export-reports)                     │
└─────────────────────────────────┬────────────────────────────────────┘
                                  ▲  stdout JSON
                                  │  python3 src/tui_api.py <cmd> [args]
                                  │
          ┌───────────────────────┴────────────────────────────────────┐
          │                    rust_tui/src/                           │
          │                                                            │
          │  main.rs ──► tokio runtime                                 │
          │               ├── key-poller task (50 ms poll)             │
          │               └── tick timer task (200 ms)                 │
          │                         │ AppEvent channel (mpsc)          │
          │                         ▼                                  │
          │  app.rs ◄──────── App::update(AppEvent)                   │
          │   (AppState: CourseSelect ↔ Dashboard)                     │
          │   (editing / editing_weights / editing_boundaries flags)   │
          │            │                                               │
          │            ├── bridge.rs  (async subprocess callers)       │
          │            │    get_courses() | get_course_data()          │
          │            │    update_score() | update_config()           │
          │            │    export_reports()                           │
          │            │                                               │
          │            └── ui.rs  (pure ratatui renderer)              │
          │                 draw() → draw_header / draw_course_select  │
          │                        / draw_dashboard / draw_footer      │
          │                        / overlays (loading/edit/settings)  │
          │                                                            │
          │  style.rs ── load_theme() → MONOKAI_PRO or theme.json     │
          │  types.rs ── Serde structs (CourseData, GradeStats, …)    │
          └────────────────────────────────────────────────────────────┘
```

## Data Flow

### Streamlit path

```
courses/<term>_<name>/
  ├── course_info/<name>_config.yaml ──► load_config() → config dict
  │                                             │
  └── data/*.csv, *.xlsx ──────────────► load_course_data()
        │  - strips whitespace from headers         │
        │  - extracts max scores                    │
        │    (a) column header: "col (40pts)"       │
        │    (b) sentinel row: Student ID="Full Score"
        │  - merges all files on Student ID         │
        │  - coerces scores to numeric (NaN→0)      │
        └───────────────────────────────────────────┘
                                                    │
                                                    ▼
                                    calculate_final_grades()
                                      1. filter to mapped cols
                                      2. fillna(0) on score cols
                                      3. per category:
                                         - drop_lowest_homework rule
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
             ┌────────────┴───────────────────────────┐
             ▼                                         ▼
    src/dashboard.py (Streamlit UI)           [Export button]
      - metrics: count, avg, high                      │
      - round-up summary table                         ▼
      - full student DataTable           courses/<name>/reports/
      - grade distribution bar chart      final_grades.csv
                                          copy_friendly_scores.csv
```

### Rust TUI path

```
User keypress / tick
        │
        ▼
rust_tui/src/main.rs  (tokio event loop)
        │  AppEvent::Key | Tick | Resize
        ▼
rust_tui/src/app.rs  App::update()
        │
        ├─ AppState::CourseSelect + Enter
        │         │
        │         ▼
        │   bridge::get_course_data()
        │         │  tokio::process::Command
        │         │  "python3 src/tui_api.py get-course-data <path> <weighted>"
        │         │
        │         ▼  stdout JSON
        │   serde_json → types::CourseData
        │         │  AppEvent::CourseDataLoaded
        │         ▼
        │   App.course_data = Some(CourseData)
        │   AppState → Dashboard
        │
        ├─ Enter on Raw Details cell  →  bridge::update_score()
        │         │  "python3 src/tui_api.py update-score <path> <id> <col> <val>"
        │         │  updates CSV/XLSX in place
        │         └─ AppEvent::ScoreUpdated → reload course data
        │
        ├─ 'w' key  →  weight editor overlay  →  bridge::update_config()
        │         │  "python3 src/tui_api.py update-config <path> <weights_json> null"
        │         └─ rewrites course_info/<name>_config.yaml → reload
        │
        ├─ 'b' key  →  boundary editor overlay  →  bridge::update_config()
        │         └─  same as above but null <weights_json> and <boundaries_json>
        │
        └─ 'e' key  →  bridge::export_reports()
                  │  "python3 src/tui_api.py export-reports <path> <weighted>"
                  └─  writes courses/<name>/reports/*.csv
                              │
                              ▼
                rust_tui/src/ui.rs  draw()
                  [Header] [Tab bar] [Table/Chart] [Footer] [Overlay]
                  all reads from App state, no writes back
```

## Key Interfaces

### Python

| Symbol | Signature | Notes |
|---|---|---|
| `load_config` | `(course_path: Path) -> dict` | Reads `course_info/<name>_config.yaml`; raises if missing |
| `load_course_data` | `(course_path: Path) -> tuple[DataFrame, dict]` | Returns empty DataFrame + `{}` if `data/` is missing |
| `calculate_final_grades` | `(df, config, max_scores, use_weighted=True) -> DataFrame` | Adds `*_pct`, `Coursework Total`, `Final Score`, `Grade`, `Original *` cols |
| `assign_letter_grade` | `(score: float, boundaries: dict) -> str` | Returns `"F"` if below all thresholds |
| `grader.py init` | `--course NAME --term TERM` | Creates `courses/<TERM>_<NAME>/` skeleton |
| `grader.py dashboard` | _(no args)_ | Delegates to `streamlit run src/dashboard.py` |

### tui_api.py subcommands (JSON protocol)

| Subcommand | Args | Response keys |
|---|---|---|
| `get-courses` | — | `status`, `courses[]` (`name`, `path`) |
| `get-course-data` | `<path> <weighted>` | `status`, `course_id`, `weights`, `grade_boundaries`, `student_grades[]`, `raw_scores[]`, `grade_distribution`, `roundup_summary` |
| `update-score` | `<path> <student_id> <col> <value>` | `status`, `message` |
| `update-config` | `<path> <weights_json\|null> <boundaries_json\|null>` | `status`, `message` |
| `export-reports` | `<path> <weighted>` | `status`, `message` |

### Rust TUI key bindings

| Key | State | Action |
|---|---|---|
| `↑ / k`, `↓ / j` | Both | Navigate list / table rows |
| `← / h`, `→ / l` | Dashboard | Navigate table columns |
| `Enter` | CourseSelect | Load selected course |
| `Enter` | Dashboard Raw Details | Open cell editor |
| `Tab / Shift+Tab` | Dashboard | Cycle tabs (Summary / Raw Details / Distribution / Roundup) |
| `c` | Dashboard | Toggle weighted ↔ raw mode |
| `w` | Dashboard | Open weight editor overlay |
| `b` | Dashboard | Open grade boundary editor overlay |
| `e` | Dashboard | Export reports |
| `Esc` | Dashboard | Return to course select |
| `q` / `Ctrl+C` | Both | Quit |

**config.yaml keys:**

| Key | Type | Purpose |
|---|---|---|
| `weights` | `dict[str, float]` | Category multipliers; should sum to 1.0 |
| `data_mapping` | `dict[str, list[str]]` | Maps category name → CSV column names |
| `grade_boundaries` | `dict[str, float]` | Letter grade thresholds, highest to lowest |
| `rules.drop_lowest_homework` | `bool` | Drops worst homework per-student (requires ≥2 cols) |

## External Dependencies

| Package | Purpose | Configured in |
|---|---|---|
| `streamlit` | Web dashboard UI | `requirements.txt` |
| `pandas` | DataFrame ingestion, merging, numeric coercion | `requirements.txt` |
| `pyyaml` | Parses `config.yaml` | `requirements.txt` |
| `openpyxl` | Reads/writes `.xlsx` files | `requirements.txt` |
| `altair` | Grade distribution bar chart | bundled with streamlit |
| `ratatui` | Terminal UI rendering | `rust_tui/Cargo.toml` |
| `crossterm` | Cross-platform terminal input/output | `rust_tui/Cargo.toml` |
| `tokio` | Async runtime for background tasks | `rust_tui/Cargo.toml` |
| `serde` / `serde_json` | JSON deserialization of Python bridge output | `rust_tui/Cargo.toml` |
| `tui-textarea` | In-cell text editing widget | `rust_tui/Cargo.toml` |

## Known Constraints & Design Decisions

- **CWD-relative course discovery (both UIs)**: `dashboard.py` and `tui_api.py` resolve `courses/` relative to the process working directory. Both must be launched from the project root.
- **Rust TUI bridge path resolution**: `bridge.rs::resolve_tui_api_path()` searches CWD → exe ancestor dirs → absolute fallback. If the binary is moved, the absolute fallback path will point to the original build machine.
- **Two max-score formats, column header takes precedence**: Column header notation (`"col (40pts)"`) is processed first; the sentinel row (`Full Score`) is a fallback and will not overwrite a header-extracted max.
- **Score edits write to the source CSV/XLSX in place**: `tui_api.py::update_student_score()` locates the file that contains the column and patches it. The Rust TUI auto-reloads after every successful edit to keep the display consistent.
- **Config writes round-trip via YAML dump**: `update_course_config()` reads the full YAML, updates the relevant keys, and rewrites the whole file with `yaml.dump()`. YAML comments and key order are not preserved.
- **Ceil rounding is intentional**: `math.ceil()` is applied to `Coursework Total`, `midterm_pct`, and `final_pct` before the final score is summed. This is a deliberate pro-student rounding policy. The `Original Final Score` / `Original Grade` fields preserve pre-rounding values.
- **Ceil rounding changes the total**: `Final Score` is reconstructed from the rounded components. Categories beyond the standard set may be omitted from the reconstruction if not explicitly handled.
- **Rust TUI tabs 0–3**: Summary (0), Raw Details (1), Distribution (2), Roundup (3). Cell editing is only allowed in tab 1 (Raw Details); attempting it in tab 0 shows an info message.
- **Theme is compile-time default + optional JSON override**: `load_theme()` checks `<exe_dir>/theme.json` then `~/.config/grade_dashboard/theme.json`. Missing or invalid keys fall back to `MONOKAI_PRO` silently.
- **Empty CSV rows produce ghost students**: A trailing blank row in a CSV becomes a student with an empty `Student ID` and all-zero scores after `fillna(0)`. This row appears in both UIs.
- **No automated tests**: Validation must be done manually by inspecting dashboard output or TUI display.
