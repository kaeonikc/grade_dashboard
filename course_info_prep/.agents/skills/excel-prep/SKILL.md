---
name: excel-prep
description: Clean, structure, and import external student grade sheets (.xlsx, .xls, .csv) into the grade dashboard course data folder using the local excel_cleaner.py tool.
---
# 🎓 Excel Grade Preparation Skill

This skill provides a helper tool and guidelines for preprocessing and cleaning external grading spreadsheets (such as Canvas, Blackboard, or registrar exports) to format them correctly for the grade dashboard.

## Local Utility Tool

An interactive python script is provided at [excel_cleaner.py](file:///Users/chakkritk/myUniverse/workflow/10_Dev_Studio/Projects/grade_dashboard/course_info_prep/excel_cleaner.py) to manage the ingestion process.

It includes the following capabilities:
1. **Row-based Header Selection**: Identifies which row of the spreadsheet contains the actual column headers (skipping metadata rows).
2. **Column Matching**: Autodetects columns representing `Student ID` and `Name`, and allows custom overrides.
3. **Data Cleaning**:
   - Converts scientific or floating-point IDs from Excel (e.g., `2026001.0`) back to clean integer strings (e.g., `2026001`).
   - Normalizes score fields and removes empty/null rows.
   - Alerts users if duplicate Student IDs are present.
4. **Dashboard Ingestion**: Automatically exports clean outputs directly into the chosen course's `data/` folder.
5. **Config Assistant**: Outputs recommended code snippets to add to the target course's `config.yaml` to register the new score columns.

---

## How to Run

Navigate to the `course_info_prep` directory and run:

```bash
python3 excel_cleaner.py [options]
```

### Options:
- `-i`, `--input`: Path to the raw Excel/CSV file.
- `-c`, `--course-dir`: Path to the target course grading folder.
- `-o`, `--output`: Output filename (e.g. `cleaned_homework.csv`).
- `--header`: The 0-based index of the row containing column headers.
- `--id-col`: Column name of the Student ID.
- `--name-col`: Column name of the student Name.

### Interactive Mode:
If run without any arguments:
```bash
python3 excel_cleaner.py
```
The tool will automatically scan the current directory for `.xlsx`, `.xls`, or `.csv` files, guide you through a visual selection of header lines, let you confirm the detected IDs/Names, and prompt you to choose the target course.

---

## Expected Data Flow

```
Raw Grade Sheet (.xlsx/.xls/.csv)
        │
        ▼ (Run excel_cleaner.py)
   Clean Student IDs & Parse Scores
        │
        ▼ (Auto-export)
courses/<course_folder>/data/<output_name>.csv
        │
        ▼ (Run dashboard / grader)
Integrated Student grade reports & terminal view
```
