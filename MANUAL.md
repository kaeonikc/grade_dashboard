# Grading System Manual

## Starting the Dashboard
To start the Grade Dashboard locally and view your courses:
```bash
streamlit run grader.py
```
This automatically opens the graphical interface in your browser where you can view aggregate statistics, review grade distributions across categories, and export finished reports.

---

## 🏗️ Managing Courses

### Creating a New Course
You can auto-generate the necessary folder structure and configuration template for a new course via the CLI. Both the course name and term are required:
```bash
python grader.py --course "GR2" --term "2026_S2"
```
This creates a combined directory:
- `courses/2026_S2_GR2/`
- `courses/2026_S2_GR2/data/` (Drop your CSVs here)
- `courses/2026_S2_GR2/reports/` (Exported results will save here)
- `courses/2026_S2_GR2/config.yaml` (Edit this to define weights and cutoffs)

### Configuring a Course (`config.yaml`)
Every course utilizes a purely customizable `config.yaml`:
- **`weights`**: Defines the categorical multiplier out of 1.0 (e.g., `homework: 0.3`).
- **`data_mapping`**: Maps the exact column names present in your CSV files mathematically to their specific weight category.
- **`grade_boundaries`**: Dictates the exact numerical boundary where a letter grade is earned (e.g., `B+: 75`).
- **`rules`**: Enable specific operations (e.g., `drop_lowest_homework: true`).

---

## 🧮 How to Format CSV Data

All data parsing works simply by placing any `.csv` or `.xlsx` file inside the `courses/<Your_Course>/data/` folder. The system will auto-merge every file using the **`Student ID`**.

To define the *maximum points* achievable on an assignment:
Add an auxiliary row near the top of your data file where the `Student ID` column is explicitly named **`Full Score`**, **`Max`**, or **`Max Score`**.
*Example Format:*
```csv
Student ID, Name, midterm_score, final_exam
Full Score, Max, 100, 150
123456, Alice, 82, 131
```
The program will dynamically read that 100 and 150 points were the respective maximums and calculate the percentage scores using the configured category weights.

---

## 📊 Exporting Reports

When ready, click "Export Final Report to CSV" in the sidebar menu.
This will save:
1. `final_grades.csv` - The complete dataset containing every student, every normalized categorical score, and their final letter grade.
2. `copy_friendly_scores.csv` - An optimally formatted extract linking each *Student ID* immediately adjacent to specific assignment totals (e.g., Midterm, Final, Coursework Total), mathematically ready to highlight and paste directly into your university submission portal.
