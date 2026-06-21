# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the grade dashboard (must be run from project root)
python grader.py dashboard

# Scaffold a new course directory and config.yaml
python grader.py init --course "GR2" --term "2026_S2"
```

The dashboard resolves course paths relative to CWD, so it must be launched from the project root where the `courses/` directory lives.

## Architecture

```
grader.py           # CLI entry point (subcommands: init, dashboard)
src/
  data_loader.py    # Config + CSV/XLSX ingestion, max score extraction, merging
  calculators.py    # Weighted grade calculation, rules, letter grade assignment
  dashboard.py      # Streamlit UI (actual dashboard target; grader.py delegates here)
courses/
  <term>_<name>/
    config.yaml     # Per-course weights, data_mapping, grade_boundaries, rules
    data/           # Drop CSV or XLSX files here; all files are auto-merged on Student ID
    reports/        # Export destination (final_grades.csv, copy_friendly_scores.csv)
```

**Data flow:** `grader.py dashboard` → `streamlit run src/dashboard.py` → `load_config` + `load_course_data` → `calculate_final_grades` → UI render / CSV export.

### Max score detection (data_loader.py)
Two supported formats — the loader tries the column-header format first, then falls back to the row-based format:
1. **Column header notation** (preferred): `"column_name (100pts)"` — the parser strips the suffix and registers the max.
2. **Sentinel row** (legacy): a row where `Student ID` is `Full Score`, `Max`, or `Max Score`.

If no max is found for a column, it defaults to 100.

### Grade calculation (calculators.py)
1. Each category's raw scores are summed and divided by the possible max (respecting `drop_lowest_homework` rule if set) to produce a percentage.
2. The percentage is multiplied by the category weight × 100 to get weighted points.
3. Categories other than `midterm` and `final` accumulate into `Coursework Total`.
4. `ceil()` is applied to `Coursework Total`, `midterm_pct`, and `final_pct` before the final letter grade is assigned — this is intentional rounding-up behaviour (not a bug).
5. Letter grades are assigned by iterating `grade_boundaries` from highest threshold to lowest; anything below the lowest threshold is `F`.

### config.yaml structure
```yaml
weights:          # Category multipliers that must sum to 1.0
data_mapping:     # Maps category names → list of CSV column names
grade_boundaries: # Letter grade thresholds (highest first, e.g. A: 80)
rules:
  drop_lowest_homework: true   # Only supported rule; requires ≥2 homework columns
```
