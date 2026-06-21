#!/usr/bin/env python3
"""
🎓 Excel/CSV Grade Cleaner Tool
Preprocesses and normalizes external student grade sheets (.xlsx, .xls, .csv)
and exports them cleanly into a grade dashboard course data folder.
"""

import os
import re
import sys
import argparse
from pathlib import Path
import pandas as pd
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm, IntPrompt

console = Console()

def get_projects_and_courses():
    """Scans the parent directory to locate courses and projects."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    courses_dir = project_root / "courses"
    
    if not courses_dir.exists() or not courses_dir.is_dir():
        # Fallback to current directory or prompt
        courses_dir = script_dir / "courses"
        
    if courses_dir.exists() and courses_dir.is_dir():
        courses = [d.name for d in courses_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        return courses_dir, sorted(courses)
    return None, []

def clean_student_id(val) -> str:
    """Standardizes Student ID to a clean string, stripping Excel float .0 formatting."""
    if pd.isna(val):
        return ""
    val_str = str(val).strip()
    # Check if it has a decimal point from Excel representation (e.g. 12345.0)
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    # Remove any scientific notation or other float representation if integer-like
    if re.match(r'^\d+\.0+$', val_str):
        val_str = val_str.split('.')[0]
    return val_str

def preview_file_rows(file_path: Path, num_rows: int = 8) -> pd.DataFrame:
    """Reads the top rows of a file for previewing header selection."""
    if file_path.suffix.lower() == '.csv':
        return pd.read_csv(file_path, nrows=num_rows, header=None)
    else:
        return pd.read_excel(file_path, nrows=num_rows, header=None)

def load_file_with_header(file_path: Path, header_row: int) -> pd.DataFrame:
    """Loads the file using the selected row as header, discarding preceding rows."""
    if file_path.suffix.lower() == '.csv':
        df = pd.read_csv(file_path, header=header_row)
    else:
        df = pd.read_excel(file_path, header=header_row)
    
    # Strip whitespace from headers
    df.columns = df.columns.astype(str).str.strip()
    return df

def find_best_column_matches(columns: list[str]) -> tuple[str | None, str | None]:
    """Finds best guesses for Student ID and Name columns based on regex patterns."""
    id_regexes = [
        r'^(student\s*)?id$', r'^student\s*number$', r'^std\s*id$', 
        r'^code$', r'^sid$', r'^uid$', r'^student\s*code$'
    ]
    name_regexes = [
        r'^name$', r'^student\s*name$', r'^full\s*name$', 
        r'^fname$', r'^first\s*name$', r'^last\s*name$', r'^lname$'
    ]
    
    detected_id = None
    detected_name = None
    
    # Try case-insensitive exact or prefix matches
    for col in columns:
        col_lower = col.lower().strip()
        
        # Check IDs
        if not detected_id:
            for pattern in id_regexes:
                if re.search(pattern, col_lower) or col_lower == 'id':
                    detected_id = col
                    break
        
        # Check Names
        if not detected_name:
            for pattern in name_regexes:
                if re.search(pattern, col_lower):
                    detected_name = col
                    break
                    
    # Broad fallback checks if not found
    if not detected_id:
        for col in columns:
            if 'id' in col.lower() or 'code' in col.lower() or 'std' in col.lower():
                detected_id = col
                break
                
    if not detected_name:
        for col in columns:
            if 'name' in col.lower() or 'student' in col.lower():
                # Avoid assigning the same column to both ID and Name
                if col != detected_id:
                    detected_name = col
                    break
                    
    return detected_id, detected_name

def select_target_course(courses_dir: Path, courses: list[str]) -> Path:
    """Interactively prompts user to select a course directory or enter a path."""
    console.print("\n[bold cyan]Select target course from local project:[/bold cyan]")
    for i, c in enumerate(courses, 1):
        console.print(f"  {i}. {c}")
    console.print(f"  {len(courses) + 1}. [italic]Enter custom directory path[/italic]")
    
    choice = IntPrompt.ask("Choose course option", choices=[str(i) for i in range(1, len(courses) + 2)], default=1)
    
    if choice <= len(courses):
        return courses_dir / courses[choice - 1]
    else:
        path_str = Prompt.ask("Enter custom absolute or relative path to course directory")
        custom_path = Path(path_str).resolve()
        if not custom_path.exists():
            console.print(f"[red]❌ Path '{custom_path}' does not exist![/red]")
            sys.exit(1)
        return custom_path

def main():
    parser = argparse.ArgumentParser(description="🎓 Excel/CSV Grade Cleaner Tool for Dashboard")
    parser.add_argument("-i", "--input", help="Path to raw excel/csv file")
    parser.add_argument("-c", "--course-dir", help="Path to course grading directory")
    parser.add_argument("-o", "--output", help="Name of output CSV (e.g. cleaned_grades.csv)")
    parser.add_argument("--header", type=int, help="Header row index (0-based)")
    parser.add_argument("--id-col", help="Column name containing Student IDs")
    parser.add_argument("--name-col", help="Column name containing Names")
    
    args = parser.parse_args()
    
    console.print(Panel.fit("[bold green]🎓 Excel/CSV Grade Cleaner[/bold green]\nClean, structure, and export student grades.", border_style="green"))

    # Resolve input file
    input_file_str = args.input
    if not input_file_str:
        # Interactively scan current directory for excel/csv files to help selection
        cwd_files = [f.name for f in Path('.').iterdir() if f.is_file() and f.suffix.lower() in ['.xlsx', '.xls', '.csv']]
        if cwd_files:
            console.print("\n[bold cyan]Files found in current directory:[/bold cyan]")
            for i, f in enumerate(cwd_files, 1):
                console.print(f"  {i}. {f}")
            console.print(f"  {len(cwd_files) + 1}. [italic]Enter other file path[/italic]")
            
            file_choice = IntPrompt.ask("Select file to clean", choices=[str(i) for i in range(1, len(cwd_files) + 2)], default=1)
            if file_choice <= len(cwd_files):
                input_file_str = cwd_files[file_choice - 1]
            else:
                input_file_str = Prompt.ask("Enter path to file")
        else:
            input_file_str = Prompt.ask("Enter path to file (.xlsx/.xls/.csv)")

    input_path = Path(input_file_str).resolve()
    if not input_path.exists():
        console.print(f"[bold red]❌ File not found at: {input_path}[/bold red]")
        sys.exit(1)
        
    console.print(f"[green]✓ Found input file: [bold]{input_path.name}[/bold][/green]")

    # 1. Preview file to decide header row
    preview_df = preview_file_rows(input_path, 8)
    
    preview_table = Table(title=f"First 8 lines of {input_path.name} (unparsed)", show_lines=True)
    preview_table.add_column("Row Index (0-based)", style="dim", justify="center")
    for col_idx in range(preview_df.shape[1]):
        preview_table.add_column(f"Col {col_idx}", overflow="ellipsis")
        
    for row_idx, row_values in preview_df.iterrows():
        str_vals = [str(x) if not pd.isna(x) else "" for x in row_values]
        preview_table.add_row(str(row_idx), *str_vals)
        
    console.print(preview_table)

    # Resolve header row
    header_row = args.header
    if header_row is None:
        header_row = IntPrompt.ask(
            "Which row index contains the actual column headers? (Usually 0)",
            default=0
        )
        
    # Reload with header row
    try:
        df = load_file_with_header(input_path, header_row)
    except Exception as e:
        console.print(f"[bold red]❌ Error parsing file with header row {header_row}: {e}[/bold red]")
        sys.exit(1)

    # 2. Match Columns
    columns = list(df.columns)
    detected_id, detected_name = find_best_column_matches(columns)
    
    # Resolve Student ID Column
    id_col = args.id_col
    if not id_col:
        if detected_id and Confirm.ask(f"Use detected Student ID column '[bold cyan]{detected_id}[/bold cyan]'?", default=True):
            id_col = detected_id
        else:
            console.print("\n[bold]Select the Student ID column:[/bold]")
            for i, col in enumerate(columns, 1):
                console.print(f"  {i}. {col}")
            id_idx = IntPrompt.ask("Select column index", choices=[str(i) for i in range(1, len(columns)+1)])
            id_col = columns[id_idx - 1]
            
    # Resolve Name Column
    name_col = args.name_col
    if not name_col:
        if detected_name and Confirm.ask(f"Use detected Name column '[bold cyan]{detected_name}[/bold cyan]'?", default=True):
            name_col = detected_name
        else:
            console.print("\n[bold]Select the Student Name column (or select 'None' if name is not in this file):[/bold]")
            console.print("  0. None")
            for i, col in enumerate(columns, 1):
                console.print(f"  {i}. {col}")
            name_idx = IntPrompt.ask("Select column index", choices=[str(i) for i in range(0, len(columns)+1)], default=0)
            name_col = columns[name_idx - 1] if name_idx > 0 else None

    # Resolve grading/assignment columns to import
    other_columns = [col for col in columns if col not in [id_col, name_col] and col.strip() != '']
    console.print("\n[bold cyan]Detected grading/assignment columns:[/bold cyan]")
    for i, col in enumerate(other_columns, 1):
        console.print(f"  {i}. {col}")
        
    selected_cols = []
    if Confirm.ask("Import ALL detected grading columns?", default=True):
        selected_cols = other_columns
    else:
        indices_str = Prompt.ask("Enter column indices to import (separated by commas, e.g. 1,2,4)")
        try:
            indices = [int(x.strip()) for x in indices_str.split(',') if x.strip().isdigit()]
            selected_cols = [other_columns[idx - 1] for idx in indices if 0 < idx <= len(other_columns)]
        except Exception:
            console.print("[yellow]⚠️ Invalid selection, importing all columns by default.[/yellow]")
            selected_cols = other_columns

    if not selected_cols:
        console.print("[red]❌ You must select at least one grading column to export![/red]")
        sys.exit(1)

    # 3. Choose target directory
    courses_dir, courses = get_projects_and_courses()
    course_path = None
    if args.course_dir:
        course_path = Path(args.course_dir).resolve()
    elif courses_dir and courses:
        course_path = select_target_course(courses_dir, courses)
    else:
        path_str = Prompt.ask("Enter path to course directory (e.g. ../courses/2026_S2_PHYS_grading)")
        course_path = Path(path_str).resolve()
        
    if not course_path.exists():
        console.print(f"[red]❌ Target course directory not found at: {course_path}[/red]")
        sys.exit(1)
        
    data_dir = course_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Resolve output filename
    output_name = args.output
    if not output_name:
        default_name = f"cleaned_{input_path.stem}.csv"
        output_name = Prompt.ask("Enter output file name (should end in .csv or .xlsx)", default=default_name)
        
    output_path = data_dir / output_name

    # 4. Clean Data
    console.print("\n[bold yellow]⚡ Cleaning and preparing data...[/bold yellow]")
    
    # Extract only needed columns
    keep_cols = [id_col]
    if name_col:
        keep_cols.append(name_col)
    keep_cols.extend(selected_cols)
    
    clean_df = df[keep_cols].copy()
    
    # Rename columns to standard Student ID and Name
    rename_dict = {id_col: 'Student ID'}
    if name_col:
        rename_dict[name_col] = 'Name'
    clean_df.rename(columns=rename_dict, inplace=True)
    
    # Clean student ID format
    clean_df['Student ID'] = clean_df['Student ID'].apply(clean_student_id)
    
    # Drop rows where Student ID is null, empty, or a typical title row element
    clean_df = clean_df.dropna(subset=['Student ID'])
    clean_df = clean_df[clean_df['Student ID'] != '']
    
    # Check for sentinel rows (Max / Max Score) and exclude them from sorting/string matching if they exist
    # But preserve them if they start with max
    sentinel_mask = clean_df['Student ID'].str.lower().isin(['max score', 'max', 'full score', 'full'])
    sentinels_df = clean_df[sentinel_mask]
    students_df = clean_df[~sentinel_mask].copy()
    
    # Warn about duplicates in Student IDs
    duplicates = students_df[students_df.duplicated(subset=['Student ID'], keep=False)]
    if not duplicates.empty:
        console.print(f"[bold yellow]⚠️ WARNING: Found duplicate Student IDs in import data![/bold yellow]")
        dup_table = Table(title="Duplicate Student IDs")
        dup_table.add_column("Student ID", style="red")
        if name_col:
            dup_table.add_column("Name")
        for _, row in duplicates.iterrows():
            row_vals = [row['Student ID']]
            if name_col:
                row_vals.append(str(row.get('Name', '')))
            dup_table.add_row(*row_vals)
        console.print(dup_table)
        if not Confirm.ask("Do you want to proceed with exporting duplicates?", default=True):
            console.print("[red]Aborted.[/red]")
            sys.exit(0)
            
    # Normalize grade columns to numeric
    for col in selected_cols:
        students_df[col] = pd.to_numeric(students_df[col], errors='coerce')
        
    # Reassemble df
    final_df = pd.concat([sentinels_df, students_df]).reset_index(drop=True)
    
    # 5. Export
    if output_path.suffix.lower() == '.csv':
        final_df.to_csv(output_path, index=False)
    else:
        final_df.to_excel(output_path, index=False)
        
    console.print(f"[bold green]✅ Successfully exported cleaned data to: {output_path}[/bold green]")
    
    # 6. Display configuration advice
    console.print(Panel(
        f"[bold green]Suggested config.yaml updates:[/bold green]\n"
        f"Copy the following assignment column names to your course config's [bold]data_mapping[/bold]:\n\n"
        f"data_mapping:\n"
        f"  # Add these column names under the appropriate weights categories (e.g. homework, midterm, final):\n"
        f"  homework: {list(selected_cols)}\n\n"
        f"Note: Ensure the exact column spelling matches in your YAML config file.",
        title="Config Helper"
    ))

if __name__ == "__main__":
    main()
