#!/usr/bin/env python3
import argparse
import copy
import sys
import shutil
import yaml
import pandas as pd
import datetime
import random
import re
from pathlib import Path

# Ensure src module can be imported, even if run from a softlink
script_path = Path(__file__).resolve()
sys.path.insert(0, str(script_path.parent))

from src.data_loader import load_config, load_course_data, get_course_file_prefix, backup_csv_before_write
from src.calculators import calculate_final_grades
from src.points import category_default, fmt_pts, header_for, resolve

_UNSAFE_PATH_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
_WHITESPACE_RUN = re.compile(r'\s+')

def sanitize_for_path(name: str) -> str:
    """Make a course_name safe to embed in a folder/file name, preserving non-ASCII text."""
    cleaned = _UNSAFE_PATH_CHARS.sub('', name or '')
    cleaned = _WHITESPACE_RUN.sub('_', cleaned.strip())
    return cleaned

_ABBR = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,29}$')
_CLASSLIST_ABBR = re.compile(r'^repclasslist_(.+)\.(xls|xlsx|csv)$', re.IGNORECASE)
# repclasslist_<abbr>_sec<N>.xls: one section's class list of a course with section folders (SPEC_section_folders.md)
_CLASSLIST_SEC = re.compile(r'^repclasslist_(.+?)[_-]sec(\d+)\.(xls|xlsx|csv)$', re.IGNORECASE)


def _name_section(path) -> str | None:
    """The section number in a class list's file name (`repclasslist_Astro_sec51.xls` → '51'), or None."""
    m = _CLASSLIST_SEC.match(Path(path).name)
    return m.group(2) if m else None

def _resolve_abbr(abbr, input_file, course_id, course_name, sec_num) -> tuple[str, str]:
    """
    The short ASCII name that `grader init` puts in the folder and file names (SPEC.md Part B), with where it came
    from: --abbr, else <ABBR> of repclasslist_<ABBR>.xls, else asked on a terminal (default: the course ID), else
    the course ID. An invalid --abbr exits before anything is created.
    """
    from_file = None
    inputs = [input_file] if isinstance(input_file, str) else list(input_file or [])
    found = []
    for one in inputs:
        name = Path(one).name
        m = _CLASSLIST_ABBR.match(name)
        sec = _CLASSLIST_SEC.match(name)
        if sec and _ABBR.match(sec.group(1)):
            found.append(sec.group(1))  # repclasslist_Astro_sec51.xls → Astro
        elif m and _ABBR.match(m.group(1)):
            found.append(m.group(1))
        elif m:
            print(f"⚠️ '{name}': '{m.group(1)}' can't be an abbreviation (ASCII letters, digits, _ and - only); ignoring it.")
    if len(inputs) == 1 and found:
        from_file = found[0]
    elif len(inputs) > 1 and len(found) == len(inputs):
        # one class list per section: repclasslist_Astro51.xls + repclasslist_Astro52.xls → Astro (SPEC_sections.md)
        stems = {re.sub(r'[_-]*(sec)?[_-]*\d+$', '', f, flags=re.IGNORECASE) or f for f in found}
        if len(stems) == 1 and _ABBR.match(next(iter(stems))):
            from_file = next(iter(stems))
        else:
            print(f"⚠️ the class lists' names don't share an abbreviation ({', '.join(found)}); ignoring them.")
    if abbr is not None:
        if not _ABBR.match(abbr):
            print(f"❌ --abbr '{abbr}': use 1–30 ASCII letters, digits, _ or -, starting with a letter or digit (e.g. ModPhys).")
            sys.exit(1)
        if from_file and from_file != abbr:
            print(f"ℹ️  --abbr {abbr} overrides {from_file} from the file name")
        return abbr, "--abbr"
    if from_file:
        return from_file, "file name"
    default = re.sub(r'[^A-Za-z0-9_-]', '-', str(course_id or '')).strip('-_')[:30] or "course"
    if not sys.stdin.isatty():
        print(f"⚠️ no abbreviation given (--abbr or repclasslist_<ABBR>.xls); using the course ID {default}")
        return default, "course ID"
    sec = f", SEC {sec_num}" if sec_num else ""
    print(f"Course {course_id} {course_name}{sec}")
    while True:
        answer = input(f"Abbreviation for folder/file names [{default}]: ").strip() or default
        if _ABBR.match(answer):
            return answer, "asked"
        print("   ASCII letters, digits, _ and - only, e.g. ModPhys")

def _same_course(cfg: dict, term_name, course_id, course_name) -> bool:
    """
    A config is this class list's course: same term, and the same course ID with spaces ignored ("SC 2202" ==
    "SC2202"). A course made before the ID parse fix (course_id "SC", course_name "2202 ดาราศาสตร์…") matches too:
    its ID + name, spaces removed, equals the class list's (SPEC_sections.md).
    """
    from src.sections import same_course_id
    if str(cfg.get('term', '')) != str(term_name):
        return False
    return same_course_id(cfg.get('course_id'), cfg.get('course_name'), course_id, course_name)

def _config_sections(cfg: dict) -> set[str]:
    secs = {str(k) for k in (cfg.get('sections') or {})}
    if cfg.get('sec_num') not in (None, ''):
        secs.add(str(cfg['sec_num']))
    return secs

def find_course_dir(term_name: str, course_id: str, sec_num, course_name: str = None) -> Path:
    """
    Locate an existing course directory by matching term/course_id inside its config.yaml, rather than guessing the
    folder name (folders are named after course_name, which can drift or be re-sanitized between spreadsheet
    re-uploads). One folder holds every section of a course (SPEC_sections.md): when several folders are this course,
    the one that already has section sec_num wins. Mirrors src/dashboard.py:find_courses' directory discovery
    (cwd + cwd's immediate subdirs + courses/*).
    """
    current_dir = Path(".")
    courses_dir = current_dir / "courses"
    candidates = [d for d in current_dir.iterdir() if d.is_dir()]
    if courses_dir.is_dir():
        candidates.extend([d for d in courses_dir.iterdir() if d.is_dir()])

    matches = {}
    for d in candidates:
        info_dir = d / "course_info"
        if not info_dir.is_dir():
            continue
        config_files = [f for f in info_dir.iterdir() if f.is_file() and f.name.endswith("_config.yaml") and not f.name.endswith(".bak")]
        for cfg_file in config_files:
            try:
                with open(cfg_file, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception:
                continue
            if _same_course(cfg, term_name, course_id, course_name):
                matches.setdefault(d.resolve(), str(sec_num) in _config_sections(cfg))
                break

    if len(matches) > 1:
        with_sec = [m for m, has in matches.items() if has]
        if len(with_sec) == 1:
            return with_sec[0]
        print("❌ Error: Multiple course directories match this term/course_id:")
        for m in matches:
            print(f"   - {m}")
        print("Run grader update from inside the one you mean, or remove the duplicates.")
        sys.exit(1)
    return next(iter(matches), None)

def create_merged_config(metadata: dict, output_path: Path):
    config_data = {
        'course_id': metadata.get('course_id'),
        'course_name': metadata.get('course_name'),
        'term': metadata.get('term'),
        'sec_num': metadata.get('sec_num'),
        'teacher': metadata.get('teacher'),
        'credits': metadata.get('credits'),
        'university': metadata.get('university'),
        'campus': metadata.get('campus'),
        'program': metadata.get('program'),
        'class_schedule': metadata.get('class_schedule'),
        'exam_schedule': metadata.get('exam_schedule'),
        'term_start_date': '',
        'weights': {
            'attendance': 0.10,
            'homework': 0.20,
            'midterm': 0.30,
            'final': 0.40
        },
        'data_mapping': {
            'homework': ['hw1', 'hw2'],
            'midterm': ['midterm_score'],
            'final': ['final_exam']
        },
        'grade_boundaries': {
            'A': 80,
            'B+': 75,
            'B': 70,
            'C+': 65,
            'C': 60,
            'D+': 55,
            'D': 50
        }
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

THAI_WEEKDAY_MAP = {
    'จ.': 0,    # Monday
    'อ.': 1,    # Tuesday
    'พ.': 2,    # Wednesday
    'พฤ.': 3,   # Thursday
    'ศ.': 4,    # Friday
    'ส.': 5,    # Saturday
    'อา.': 6    # Sunday
}

MONTH_ABBRS = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
}

def parse_midterm_date(exam_schedule_str: str) -> datetime.date | None:
    if not exam_schedule_str or not isinstance(exam_schedule_str, str):
        return None
    parts = exam_schedule_str.split(',')
    for part in parts:
        part = part.strip()
        if not re.search(r'\bM\b', part):
            continue
        
        # Try matching "d mmm yyyy" format: e.g., 7 Aug 2026
        match_new = re.search(r'\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\b', part)
        if match_new:
            day = int(match_new.group(1))
            month_str = match_new.group(2)
            year = int(match_new.group(3))
            
            MONTH_MAP = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            m_num = MONTH_MAP.get(month_str.lower())
            if m_num:
                try:
                    return datetime.date(year, m_num, day)
                except ValueError:
                    pass
                    
        # Try matching "DD/MM/YY" format
        match_old = re.search(r'\b(\d{2})/(\d{2})/(\d{2,4})\b', part)
        if match_old:
            try:
                d = int(match_old.group(1))
                m = int(match_old.group(2))
                y_str = match_old.group(3)
                year = 2000 + int(y_str) if len(y_str) == 2 else int(y_str)
                return datetime.date(year, m, d)
            except ValueError:
                pass
    return None

def calculate_class_dates(term_start_date_str: str, weekday_str: str, exam_schedule_str: str, num_classes: int = 15) -> list[str]:
    """
    Calculates class dates based on term start date, weekday of the class,
    and skips the week of the midterm exam.
    Returns list of formatted date strings "d mmm yyyy" (e.g. "7 Aug 2026").
    """
    if not term_start_date_str:
        return [f"a{i}" for i in range(1, num_classes + 1)]
        
    try:
        start_date = datetime.datetime.strptime(term_start_date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return [f"a{i}" for i in range(1, num_classes + 1)]
        
    weekday_int = THAI_WEEKDAY_MAP.get(weekday_str.strip(), 0)
    
    days_ahead = weekday_int - start_date.weekday()
    if days_ahead < 0:
        days_ahead += 7
    first_class_date = start_date + datetime.timedelta(days=days_ahead)
    
    midterm_date = parse_midterm_date(exam_schedule_str)
    midterm_iso_week = None
    midterm_year = None
    if midterm_date:
        midterm_year, midterm_iso_week, _ = midterm_date.isocalendar()
        
    class_dates = []
    curr_date = first_class_date
    while len(class_dates) < num_classes:
        curr_year, curr_iso_week, _ = curr_date.isocalendar()
        
        if midterm_iso_week is not None and curr_iso_week == midterm_iso_week and curr_year == midterm_year:
            curr_date += datetime.timedelta(days=7)
            continue
            
        formatted = f"{curr_date.day} {MONTH_ABBRS[curr_date.month]} {curr_date.year}"
        class_dates.append(formatted)
        curr_date += datetime.timedelta(days=7)
        
    return class_dates

def save_attendance_excel(excel_path: Path, student_registry: pd.DataFrame, columns: list[str]):
    """
    Creates or updates the attendance spreadsheet using openpyxl.
    Maintains existing scores if they exist.
    Applies dropdown data validations, conditional colors, rotated headers, and compact layout.
    """
    import openpyxl
    from openpyxl.styles import Alignment, PatternFill, Font, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.utils import get_column_letter

    existing_df = None
    if excel_path.exists():
        try:
            existing_df = pd.read_excel(excel_path)
            existing_df.columns = existing_df.columns.astype(str).str.strip()
        except Exception as e:
            print(f"⚠️ Warning: Could not read existing attendance file: {e}")

    # Build header formulas. We keep using the static value for the maximum score (total number of class sessions).
    if len(columns) > 0:
        header_formula = f"total ({len(columns)}pts)"
    else:
        header_formula = "total (0pts)"
    
    headers = ['Student ID', 'Name'] + columns + [header_formula]
    
    df_new = pd.DataFrame(columns=headers)
    df_new['Student ID'] = student_registry['Student ID'].astype(str).str.strip()
    df_new['Name'] = student_registry['Name'].astype(str).str.strip()
    
    # Merge existing data if available
    if existing_df is not None and 'Student ID' in existing_df.columns:
        existing_df['Student ID'] = existing_df['Student ID'].astype(str).str.strip()
        old_cols = [c for c in existing_df.columns if c not in ['Student ID', 'Name', 'Sec'] and not c.lower().startswith('total') and not c.startswith('=') and 'unnamed' not in c.lower()]
        new_cols = columns
        
        student_rows = {sid: idx for idx, sid in enumerate(df_new['Student ID'])}
        
        for idx, sid in enumerate(existing_df['Student ID']):
            if sid in student_rows:
                target_idx = student_rows[sid]
                for pos, old_col in enumerate(old_cols):
                    if pos < len(new_cols):
                        new_col = new_cols[pos]
                        if old_col in new_cols:
                            val = existing_df.loc[idx, old_col]
                            if pd.notna(val):
                                if isinstance(val, str) and val.strip() == "EA":
                                    val = "X"
                                df_new.loc[target_idx, old_col] = val
                        else:
                            val = existing_df.loc[idx, old_col]
                            if pd.notna(val):
                                if isinstance(val, str) and val.strip() == "EA":
                                    val = "X"
                                df_new.loc[target_idx, new_col] = val

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.views.sheetView[0].showGridLines = True
    
    ws.append(headers)
    for r_idx, row in df_new.iterrows():
        ws.append(row.tolist())
        
    num_students = len(df_new)
    # Date columns start at column 3 (C) and end at column len(columns)+2 (e.g. Q)
    # Date columns start at column 3 (C) and end at column len(columns)+2 (e.g. Q)
    # The total column is at column len(columns)+3
    if len(columns) > 0:
        start_col_letter = get_column_letter(3)
        end_col_letter = get_column_letter(len(columns) + 2)
        total_col_idx = len(columns) + 3
        for r in range(2, num_students + 2):
            formula = f'=COUNTIF({start_col_letter}{r}:{end_col_letter}{r}, "P") + COUNTIF({start_col_letter}{r}:{end_col_letter}{r}, "L")*0.8 + COUNTIF({start_col_letter}{r}:{end_col_letter}{r}, "X")'
            ws.cell(row=r, column=total_col_idx, value=formula)
        
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    ws.row_dimensions[1].height = 75
    header_font = Font(name='Segoe UI', size=11, bold=True)
    normal_font = Font(name='Segoe UI', size=11)
    
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.border = thin_border
        
        if col_idx > 2 and col_idx < len(headers):
            # Rotated for date/placeholder columns only
            cell.alignment = Alignment(textRotation=90, horizontal='center', vertical='center', wrap_text=True)
        elif col_idx == len(headers):
            # Total header is not rotated
            cell.alignment = Alignment(horizontal='center', vertical='center')
        else:
            cell.alignment = Alignment(horizontal='left', vertical='center')
            
    for r in range(2, num_students + 2):
        ws.row_dimensions[r].height = 20
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = normal_font
            cell.border = thin_border
            if c == len(headers):
                cell.font = Font(name='Segoe UI', size=11, bold=True)
                cell.alignment = Alignment(horizontal='center', vertical='center')
            elif c > 2:
                cell.alignment = Alignment(horizontal='center', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='left', vertical='center')
                
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 25
    for c in range(3, len(headers)):
        col_letter = get_column_letter(c)
        ws.column_dimensions[col_letter].width = 6
    total_col_letter = get_column_letter(len(headers))
    ws.column_dimensions[total_col_letter].width = 14
        
    dv = DataValidation(type="list", formula1='"P,A,L,X"', allow_blank=True)
    dv.error ='Your entry is not in the list (P, A, L, X)'
    dv.errorTitle = 'Invalid Entry'
    dv.prompt = 'Please select from: P, A, L, X'
    dv.promptTitle = 'Select attendance'
    
    ws.add_data_validation(dv)
    
    if len(columns) > 0 and num_students > 0:
        start_col_letter = get_column_letter(3)
        end_col_letter = get_column_letter(len(columns) + 2)
        validation_range = f"{start_col_letter}2:{end_col_letter}{num_students + 1}"
        dv.add(validation_range)
        
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    green_font = Font(color="006100", name='Segoe UI', size=11)
    
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    red_font = Font(color="9C0006", name='Segoe UI', size=11)
    
    orange_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    orange_font = Font(color="9C6500", name='Segoe UI', size=11)
    
    yellow_fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")
    yellow_font = Font(color="808000", name='Segoe UI', size=11)
    
    if len(columns) > 0 and num_students > 0:
        cf_range = f"{start_col_letter}2:{end_col_letter}{num_students + 1}"
        ws.conditional_formatting.add(cf_range, CellIsRule(operator='equal', formula=['"P"'], fill=green_fill, font=green_font))
        ws.conditional_formatting.add(cf_range, CellIsRule(operator='equal', formula=['"A"'], fill=red_fill, font=red_font))
        ws.conditional_formatting.add(cf_range, CellIsRule(operator='equal', formula=['"L"'], fill=orange_fill, font=orange_font))
        ws.conditional_formatting.add(cf_range, CellIsRule(operator='equal', formula=['"X"'], fill=yellow_fill, font=yellow_font))

    excel_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(excel_path)
    print(f"✅ Generated and formatted attendance sheet at: {excel_path.name}")

def _attendance_csv(course_dir: Path, entry=None) -> None:
    """The csv copy of a freshly made attendance xlsx, and the first sync baseline (src/attendance.py)."""
    from src.attendance import make_csv
    try:
        make_csv(course_dir, entry)
    except Exception as e:
        print(f"⚠️ Warning: could not write the attendance csv: {e}")


def _attendance_rows(course_dir: Path, att_path: Path, registry: pd.DataFrame, class_cols: list[str],
                     entry=None) -> None:
    """
    `grader update`: an existing attendance sheet keeps its session columns (the ones you deleted stay deleted);
    only its rows follow the roster, in the xlsx and the csv alike. Without a sheet, a new one is made.
    """
    from src.attendance import align_rows
    if not att_path.exists():
        if entry is not None:
            entry.capture(att_path)
        save_attendance_excel(att_path, registry, class_cols)
        _attendance_csv(course_dir, entry)
        print(f"✅ Created attendance sheet: {att_path.name}")
        return
    done = align_rows(course_dir, entry=entry, class_dates=class_cols)
    for name, n in done.items():
        print(f"  ✍️  {name}: rows follow the roster ({n} change(s)); session columns kept")
    if not done:
        print(f"✅ {att_path.name}: already follows the roster")


def parse_pts(col_name: str) -> tuple[str, float | None]:
    """
    Parses a column name to see if it already contains points notation.
    Returns (clean_name, pts_value) or (col_name, None).
    """
    import re
    match = re.search(r'\(\s*([\d.]+)\s*(?:pts|points)?\s*\)', col_name, re.IGNORECASE)
    if match:
        try:
            val = float(match.group(1))
            clean_name = re.sub(r'\s*\(\s*[\d.]+\s*(?:pts|points)?\s*\)', '', col_name, flags=re.IGNORECASE).strip()
            return clean_name, val
        except ValueError:
            pass
    return col_name, None

def parse_config_col(col) -> tuple[str, float | None]:
    """
    Parses a column item from config file (can be a string or a dictionary).
    Returns (clean_name, pts_value) or (col_name_str, None).
    """
    if isinstance(col, dict):
        if len(col) == 1:
            key = list(col.keys())[0]
            val = col[key]
            try:
                return str(key).strip(), float(val)
            except (ValueError, TypeError):
                return str(key).strip(), None
        return str(col), None
    else:
        col_str = str(col).strip()
        return parse_pts(col_str)

def parse_category_mapping(category_mapping) -> tuple[float | None, list]:
    """
    Parses a category mapping from the configuration.
    It can be a list of columns, or a dictionary with 'total_pts' and 'columns'.
    Returns (total_pts, columns_list).
    """
    if isinstance(category_mapping, dict):
        total_pts = category_mapping.get('total_pts')
        if total_pts is not None:
            try:
                total_pts = float(total_pts)
            except (ValueError, TypeError):
                total_pts = None
        columns_list = category_mapping.get('columns', [])
        return total_pts, columns_list
    else:
        return None, category_mapping

def normalize_col_key(name: str) -> str:
    """
    Normalizes a cleaned column base-name for matching a CSV header against a
    config column, so cosmetic differences (case, extra spaces, underscores
    vs spaces) don't make an existing scored column look "missing" and get
    silently duplicated/blanked during `grader update`.
    """
    return re.sub(r'[\s_]+', ' ', str(name).strip()).casefold()

def create_empty_category_csv(category: str, columns: list, student_registry: pd.DataFrame, csv_path: Path,
                              default_max: float = 100.0, default: float | None = None):
    """`default` is the category's default points (pts_each / lab's 10): columns at it get a bare header."""
    headers = ['Student ID', 'Name']
    total_pts = 0.0
    for col in columns:
        clean_name, pts = parse_config_col(col)
        pts_val = float(resolve(pts, default) if resolve(pts, default) is not None else default_max)
        total_pts += pts_val
        headers.append(header_for(clean_name, pts_val, default))
        
    # Append the total column header
    total_pts_str = str(int(total_pts)) if total_pts.is_integer() else str(total_pts)
    headers.append(f"total ({total_pts_str}pts)")
    
    student_rows = student_registry.copy()
    for col in headers:
        if col not in student_rows.columns:
            student_rows[col] = ""
    student_rows = student_rows[headers]
    
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    student_rows.to_csv(csv_path, index=False)

def init_course(course_name: str, term_name: str, course_id: str, input_file=None, abbr: str = None):
    if isinstance(input_file, (list, tuple)):
        files = list(input_file)
        # several class lists, or one named repclasslist_<abbr>_sec<N>: a course with section folders
        if len(files) > 1 or (files and _name_section(files[0])):
            return _init_sections(course_name, term_name, course_id, files, abbr)
        input_file = files[0] if files else None
    elif input_file and _name_section(input_file):
        return _init_sections(course_name, term_name, course_id, [input_file], abbr)
    if input_file:
        input_path = Path(input_file)
        if not input_path.exists():
            print(f"❌ Input file not found: {input_path}")
            sys.exit(1)
        try:
            # Check file type and read
            if input_path.suffix.lower() == '.csv':
                df_raw = pd.read_csv(input_path, header=None)
            else:
                df_raw = pd.read_excel(input_path, header=None)
        except Exception as e:
            print(f"❌ Error reading raw file: {e}")
            sys.exit(1)
        
        from course_info_prep.convert_student_info import extract_metadata
        metadata = extract_metadata(df_raw)
        
        term_name = term_name if term_name else metadata.get('term')
        course_id = course_id if course_id else metadata.get('course_id')
        course_name = course_name if course_name else metadata.get('course_name')
        sec_num = metadata.get('sec_num', 'Unknown')
        abbr, source = _resolve_abbr(abbr, input_file, course_id, course_name, sec_num)
        prefix = f"{term_name}_{abbr}_SEC_{sec_num}"
    else:
        abbr, source = _resolve_abbr(abbr, None, course_id, course_name, None)
        prefix = f"{term_name}_{abbr}"
        sec_num = None
    folder_name = prefix  # the file prefix too; the Thai course_name stays in config.yaml

    base_dir = Path(folder_name)
    if base_dir.exists():
        if input_file:
            print(f"❌ Directory '{base_dir}' already exists. Use 'grader update -i {input_file}' to update it.")
        else:
            print(f"❌ Directory '{base_dir}' already exists. Aborting to avoid overwriting existing files.")
        sys.exit(1)

    course_info_dir = base_dir / "course_info"
    data_dir = base_dir / "data"
    reports_dir = base_dir / "reports"
    
    course_info_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    if input_file:
        config_path = course_info_dir / f"{prefix}_config.yaml"
        csv_path = course_info_dir / f"{prefix}_student_info.csv"

        temp_yaml_path = course_info_dir / "temp_metadata.yaml"
        from course_info_prep.convert_student_info import convert_excel_to_csv_and_yaml
        metadata, clean_df = convert_excel_to_csv_and_yaml(input_path, csv_path=csv_path, yaml_path=temp_yaml_path)

        create_merged_config(metadata, config_path)
        if temp_yaml_path.exists():
            temp_yaml_path.unlink()

        # Generate initial attendance spreadsheet with placeholders
        att_filename = f"{get_course_file_prefix(base_dir)}_attendance.xlsx"
        att_path = data_dir / att_filename
        class_cols = calculate_class_dates('', '', '')
        save_attendance_excel(att_path, clean_df, class_cols)
        _attendance_csv(base_dir)
        
        note = f"   (abbreviation {abbr} from the file name)" if source == "file name" else ""
        print(f"✅ Successfully created course structure at: {base_dir}{note}")
        print(f"✅ Generated student list at: {csv_path}")
        print(f"✅ Generated config at: {config_path}")
        print(f"✅ Generated initial attendance sheet at: {att_path}")
    else:
        config_path = course_info_dir / f"{prefix}_config.yaml"

        with open(config_path, "w") as f:
            f.write(f"""course_id: "{course_id}"
course_name: "{course_name}"
term: "{term_name}"
term_start_date: ""

weights:
  attendance: 0.10
  homework: 0.20
  midterm: 0.30
  final: 0.40

data_mapping:
  homework: ["hw1", "hw2"]
  midterm: ["midterm_score"]
  final: ["final_exam"]

grade_boundaries:
  A: 80
  B+: 75
  B: 70
  C+: 65
  C: 60
  D+: 55
  D: 50
""")
        print(f"✅ Successfully created course structure at: {base_dir}")
        print(f"Modify the '{config_path}' file to set up your rules!")

def _init_sections(course_name, term_name, course_id, input_files: list[str], abbr: str = None):
    """
    `grader init -i a_sec51.xls -i a_sec52.xls`: one course folder <term>_<abbr>/ with the shared config, and a
    sub-folder sec<N>/ per class list holding that section's roster, score files and attendance sheet
    (SPEC_section_folders.md).
    """
    from src.sections import norm_id, sort_sections
    from src.split import layout_config
    lists = [_read_class_list(f) for f in input_files]
    first_path, first, _ = lists[0]
    for path, meta, _ in lists[1:]:
        if str(meta.get('term')) != str(first.get('term')) or norm_id(meta.get('course_id')) != norm_id(first.get('course_id')):
            print(f"❌ {path.name} is {meta.get('course_id')} ({meta.get('term')}), but {first_path.name} is "
                  f"{first.get('course_id')} ({first.get('term')}): one course's sections only. Nothing was created.")
            sys.exit(1)
    secs = [str(meta.get('sec_num')) for _, meta, _ in lists]
    for path, meta, _ in lists:
        sec = str(meta.get('sec_num'))
        if sec.startswith('Unknown_'):
            print(f"❌ {path.name}: no section number (Sec NN) found. Nothing was created.")
            sys.exit(1)
        named = _name_section(path)
        if named is not None and named != sec:
            print(f"❌ {path.name} says sec{named} in its name, but the class list inside is Sec {sec}. Rename the "
                  "file or check you have the right one. Nothing was created.")
            sys.exit(1)
    if len(set(secs)) < len(secs):
        dup = next(s for s in secs if secs.count(s) > 1)
        print(f"❌ Two class lists are section {dup}. Nothing was created.")
        sys.exit(1)

    sections = sort_sections(secs)
    ordered = sorted(lists, key=lambda t: sections.index(str(t[1].get('sec_num'))))
    head = ordered[0][1]
    term_name = term_name or head.get('term')
    course_id = course_id or head.get('course_id')
    course_name = course_name or head.get('course_name')
    abbr, source = _resolve_abbr(abbr, input_files, course_id, course_name, ", ".join(sections))
    prefix = f"{term_name}_{abbr}"
    base_dir = Path(prefix)
    if base_dir.exists():
        print(f"❌ Directory '{base_dir}' already exists. Use 'grader update -i <class list>' to update it.")
        sys.exit(1)

    for d in ("course_info", "history", "reports"):
        (base_dir / d).mkdir(parents=True)
    config_path = base_dir / "course_info" / f"{prefix}_config.yaml"
    create_merged_config({**head, 'term': term_name, 'course_id': course_id, 'course_name': course_name}, config_path)
    flat = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    flat['sections'] = {str(m.get('sec_num')): {k: copy.deepcopy(m.get(k)) for k in ('class_schedule', 'exam_schedule')}
                        for _, m, _ in ordered}
    from src.split import dump_yaml
    dump_yaml(config_path, layout_config(flat, sections))

    made = []
    for _, meta, students in ordered:
        sec = str(meta.get('sec_num'))
        n = _make_section(base_dir, sec, students)
        made.append(f"sec{sec} ({n} students)")

    note = f"   (abbreviation {abbr} from the file names)" if source == "file name" else ""
    print(f"✅ {base_dir}/: {', '.join(made)}{note}")
    print(f"✅ Shared config: {config_path}")


def _make_section(root: Path, sec: str, students: pd.DataFrame, entry=None) -> int:
    """
    A section's folder in a course with section folders: its roster, empty score files from the shared config, and
    an attendance sheet with dates from its own schedule. The config must list the section already. Returns the
    number of students.
    """
    from src.course import at, config_for
    section = at(root).section(sec)
    unit, sp = section.path, section.prefix
    for d in ("course_info", "data", "reports"):
        (unit / d).mkdir(parents=True, exist_ok=True)
    roster = students.copy()
    roster['Student ID'] = roster['Student ID'].astype(str).str.strip()
    for col in ('Name', 'Class Group'):
        if col not in roster.columns:
            roster[col] = ''
    roster = roster[['Student ID', 'Name', 'Class Group']].drop_duplicates('Student ID', keep='last')
    roster = roster.sort_values('Student ID').reset_index(drop=True)
    roster.to_csv(unit / "course_info" / f"{sp}_student_info.csv", index=False)
    _mkdb_unit(unit, quiet=True)
    cfg = config_for(unit)
    sch = cfg.get('class_schedule') if isinstance(cfg.get('class_schedule'), dict) else {}
    class_cols = calculate_class_dates(cfg.get('term_start_date', '') or '', sch.get('day', ''), cfg.get('exam_schedule', '') or '')
    att_path = unit / "data" / f"{sp}_attendance.xlsx"
    save_attendance_excel(att_path, roster, class_cols)
    _attendance_csv(unit, entry)
    return len(roster)

def mkdb_course(config_file: str = None, input_alias: str = None):
    cfg_path = _config_here(config_file or input_alias)
    if not cfg_path or not cfg_path.exists():
        print("❌ Error: Configuration file not specified or not found.")
        print("Please provide the path to the config file or run the command from inside the course directory.")
        sys.exit(1)
    from src.course import at
    course = at(cfg_path)
    for section in course.sections:  # every section folder (SPEC_section_folders.md), or the flat course
        if course.layout:
            print(f"── sec {section.num} ({section.path.name}/) ──")
        _mkdb_unit(section.path)


def _mkdb_unit(course_dir: Path, quiet: bool = False):
    """`grader mkdb` for one folder of rosters and data/: the config's score files that don't exist yet."""
    say = (lambda *a, **k: None) if quiet else print
    course_dir = Path(course_dir).resolve()
    info_dir = course_dir / "course_info"
    data_dir = course_dir / "data"
    from src.course import config_for
    config = config_for(course_dir)
    data_mapping = config.get("data_mapping", {})
    if not data_mapping:
        say("⚠️ Warning: 'data_mapping' not found or empty in the config.")
        return
        
    # Locate student info CSV
    student_info_files = [f for f in info_dir.iterdir() if f.is_file() and f.name.endswith("_student_info.csv") and not f.name.endswith(".bak")]
    if not student_info_files:
        print(f"❌ Error: Student registry (*_student_info.csv) not found under {info_dir}")
        sys.exit(1)
        
    student_info_path = student_info_files[0]
    try:
        student_df = pd.read_csv(student_info_path)
        student_df.columns = student_df.columns.astype(str).str.strip()
    except Exception as e:
        print(f"❌ Error reading student registry: {e}")
        sys.exit(1)
        
    if 'Student ID' not in student_df.columns or 'Name' not in student_df.columns:
        print(f"❌ Error: Registry must contain 'Student ID' and 'Name' columns.")
        sys.exit(1)
        
    # Clean registry
    student_registry = student_df[['Student ID', 'Name']].copy()
    student_registry['Student ID'] = student_registry['Student ID'].astype(str).str.strip()
    student_registry['Name'] = student_registry['Name'].astype(str).str.strip()
    
    data_dir.mkdir(parents=True, exist_ok=True)
    prefix = get_course_file_prefix(course_dir)

    for category, mapping_item in data_mapping.items():
        total_pts, columns = parse_category_mapping(mapping_item)
        if not isinstance(columns, list):
            continue
        default = category_default(category, mapping_item)
        csv_path = data_dir / f"{prefix}_{category}.csv"
        if csv_path.exists():
            # mkdb is for scaffolding brand-new databases; a file already
            # existing here may hold scores someone entered by hand or via
            # grade-tui, so never blindly overwrite it with a blank template.
            # Realigning an existing database to config changes is `update`'s
            # job, not mkdb's.
            say(f"⏭️  {csv_path.name} already exists; leaving it as-is (use `grader update` to realign it with config changes).")
            continue
        say(f"🛠️ Creating empty score database: {csv_path.name}...")

        # Calculate target_total based on category weight or manual total_pts
        weights = config.get("weights", {})
        weight = weights.get(category, None)
        weight_points = weight * 100.0 if weight is not None else 100.0
        
        target_total = total_pts if total_pts is not None else weight_points
        
        specified_total = 0.0
        unspecified_cols = 0
        for col in columns:
            _, pts = parse_config_col(col)
            pts = resolve(pts, default)
            if pts is not None:
                specified_total += pts
            else:
                unspecified_cols += 1
                
        if unspecified_cols > 0:
            remaining = target_total - specified_total
            if remaining <= 0:
                default_max = 10.0 # Fallback default
            else:
                default_max = round(remaining / unspecified_cols, 2)
        else:
            default_max = 100.0
            # Warning check
            import math
            if total_pts is not None and not math.isclose(specified_total, target_total, abs_tol=1e-2):
                print(f"⚠️ WARNING: [{category}] Manual total score is determined as {target_total}pts, "
                      f"but the sum of specified columns is {specified_total}pts.")
        
        try:
            create_empty_category_csv(category, columns, student_registry, csv_path, default_max, default)
            say(f"✅ Created {csv_path.name} successfully with default max score {default_max}.")
        except Exception as e:
            print(f"❌ Error writing {csv_path.name}: {e}")
            
    from src.columns import save_base
    save_base(course_dir)
    _refresh_totals(course_dir, "mkdb")
    say("🚀 All databases created successfully!")

def _read_class_list(input_file: str):
    """(path, metadata, students) of a class list, or exit with the reason."""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)
    try:
        if input_path.suffix.lower() == '.csv':
            df_raw = pd.read_csv(input_path, header=None)
        else:
            df_raw = pd.read_excel(input_path, header=None)
    except Exception as e:
        print(f"❌ Error reading raw file: {e}")
        sys.exit(1)
    from course_info_prep.convert_student_info import extract_metadata, convert_excel_to_csv_and_yaml
    metadata = extract_metadata(df_raw)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _, students = convert_excel_to_csv_and_yaml(input_path, csv_path=Path(tmp) / "students.csv",
                                                    yaml_path=Path(tmp) / "metadata.yaml")
    students['Student ID'] = students['Student ID'].astype(str).str.strip()
    return input_path, metadata, students

def _read_course_config(course_dir: Path) -> dict:
    """The course's config.yaml as written ({} without one); no attendance sync, unlike load_config."""
    for f in sorted((course_dir / "course_info").glob("*_config.yaml")):
        try:
            return yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}

def _update_roster(input_file: str, yes: bool = False):
    """
    `grader update -i <class list>`: merge one section's class list into its course. A course with section folders
    gets it in that section's folder (a new section: a new folder, after asking); a flat course merges it as before,
    or, for another section, moves into section folders first (SPEC_section_folders.md).
    """
    from src.course import at
    from src.sections import section_column, sections_of
    input_path, metadata, new_df = _read_class_list(input_file)
    term_name = metadata.get('term')
    course_id = metadata.get('course_id')
    course_name = metadata.get('course_name')
    sec_num = metadata.get('sec_num')

    if not term_name or not course_id or not sec_num or str(sec_num).startswith('Unknown_'):
        print("❌ Error: Could not parse required metadata (term, course_id, sec_num) from input file.")
        sys.exit(1)
    sec_num = str(sec_num)
    named = _name_section(input_path)
    if named is not None and named != sec_num:
        print(f"❌ {input_path.name} says sec{named} in its name, but the class list inside is Sec {sec_num}. "
              "Nothing changed.")
        sys.exit(1)

    # The course: the one we're in (a section folder counts), else found by term + course ID
    if Path("course_info").is_dir():
        course = at(Path("."))
        print("🔍 Detected running from inside a course grading directory.")
        cfg_here = course.config() if course else {}
        if cfg_here and not _same_course(cfg_here, term_name, course_id, course_name):
            print(f"❌ {input_path.name} is {course_id} {course_name} ({term_name}), but this folder is "
                  f"{cfg_here.get('course_id')} {cfg_here.get('course_name')} ({cfg_here.get('term')}). Nothing changed.")
            print("   Run grader update -i from the course folder it belongs to (or from its term folder).")
            sys.exit(1)
    else:
        found = find_course_dir(term_name, course_id, sec_num, course_name)
        course = at(found) if found else None
    if course is None:
        print(f"❌ Target grading directory for term={term_name}, course_id={course_id}, sec_num={sec_num} does not exist.")
        print(f"Please run 'grader init -i {input_file}' first to initialize the course.")
        sys.exit(1)

    if course.layout:
        return _update_section_roster(course, input_path, metadata, new_df, sec_num, input_file, yes)

    # A flat course
    column = section_column(course.root)
    if len(sections_of(column)) >= 2:
        print(f"❌ {course.root.name} keeps several sections in one folder (its roster's Section column). "
              "Run grader split first, then grader update -i again. Nothing changed.")
        sys.exit(1)
    flat_sec = str(course.config().get('sec_num') or '').strip()
    if flat_sec and flat_sec != sec_num:
        from src.split import layout_name
        new_name = layout_name(course.root.name, [flat_sec, sec_num]) or "<term>_<abbr>"
        print(f"🔍 {course.root.name} is {course_id} {course_name}, section {flat_sec}")
        print(f"   Adding section {sec_num} moves it into section folders: {new_name}/sec{flat_sec}/ and sec{sec_num}/")
        if not _confirm_add(f"Add section {sec_num} ({len(new_df)} students) to this course?", yes, sec_num,
                            course.root.name, input_file):
            return
        from src import split
        roster_ids = set(pd.read_csv(next((course.root / "course_info").glob("*_student_info.csv")), dtype=str,
                                     keep_default_na=False)['Student ID'].astype(str).str.strip())
        try:
            new_root = split.split(course.root, secmap={sid: flat_sec for sid in roster_ids if sid})
        except split.Refused as e:
            print(e)
            sys.exit(1)
        print(f"📁 {course.root.name} → {new_root.name}/sec{flat_sec}/ (the old folder is {course.root.name}{split.BEFORE})")
        print(f"   Your shell is still in the old path: cd {new_root}")
        return _update_section_roster(at(new_root), input_path, metadata, new_df, sec_num, input_file, yes=True)
    return _update_flat_roster(course.root, input_path, metadata, new_df, sec_num)


def _confirm_add(question: str, yes: bool, sec_num: str, folder: str, input_file: str) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print(f"❌ Section {sec_num} isn't in {folder} yet, and there's no terminal to ask on. Nothing changed.")
        print(f"   To add it: grader update -i {input_file} -y")
        sys.exit(1)
    if input(f"❓ {question} [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return False
    return True


COURSE_KEYS = ('course_id', 'course_name', 'term', 'teacher', 'credits', 'university', 'campus', 'program')


def _merge_roster(old_csv: Path, new_df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, int]:
    """The roster at old_csv with new_df's students merged in (nobody removed; the class list wins); (roster, old size)."""
    if old_csv.exists():
        old_df = pd.read_csv(old_csv, dtype=str, keep_default_na=False)
        old_df.columns = old_df.columns.astype(str).str.strip()
    else:
        old_df = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in old_df.columns:
            old_df[c] = ''
        if c not in new_df.columns:
            new_df[c] = ''
    old_df['Student ID'] = old_df['Student ID'].astype(str).str.strip()
    merged = pd.merge(old_df[cols], new_df[cols], on='Student ID', how='outer', suffixes=('_old', '_new'))
    for c in cols[1:]:
        merged[c] = merged[f'{c}_new'].fillna(merged[f'{c}_old']).fillna('')
    merged = merged[cols].sort_values(by='Student ID').reset_index(drop=True)
    return merged, len(old_df)


def _update_section_roster(course, input_path: Path, metadata: dict, new_df: pd.DataFrame, sec_num: str,
                           input_file: str, yes: bool = False):
    """`update -i` into a course with section folders: that section's roster, or a new section folder."""
    from src.course import at, config_for
    from src.history import Entry
    from src.sections import counts, roster_sections
    from src.split import dump_yaml, move_students
    root = course.root
    section = course.section(sec_num)
    added = section is None
    if added:
        print(f"🔍 {root.name} is {metadata.get('course_id')} {metadata.get('course_name')}, sections: "
              f"{', '.join(s.num for s in course.sections)}")
        if not _confirm_add(f"Add section {sec_num} ({len(new_df)} students) to {root.name}?", yes, sec_num,
                            root.name, input_file):
            return

    entry = Entry(root, "grader", "update-roster", note=str(input_path.name))
    entry.capture(course.config_path)
    cfg = course.config()
    for key in COURSE_KEYS:
        if key in metadata:
            cfg[key] = metadata[key]
    secs = {str(k): v for k, v in (cfg.get('sections') or {}).items()}
    mine = dict(secs.get(sec_num) or {})
    mine.setdefault('folder', f"sec{sec_num}")
    for key in ('class_schedule', 'exam_schedule'):
        if metadata.get(key) is not None:
            mine[key] = copy.deepcopy(metadata[key])
    secs[sec_num] = mine
    from src.sections import sort_sections
    cfg['sections'] = {s: secs[s] for s in sort_sections(secs)}
    dump_yaml(course.config_path, cfg)

    # Students found in another section's roster move here, with their scores and marks (the class list wins)
    before = roster_sections(root)
    new_ids = set(new_df['Student ID'].astype(str).str.strip())
    movers = {}
    for sid in sorted(new_ids):
        if before.get(sid) and before[sid] != sec_num:
            movers.setdefault(before[sid], []).append(sid)

    course = at(root)
    unit = course.section(sec_num)
    if added and not (unit.path / "course_info").is_dir():
        n = _make_section(root, sec_num, new_df, entry)
        print(f"✅ Created {unit.path.name}/: {n} students, score files and an attendance sheet")
    else:
        csv_path = unit.path / "course_info" / f"{unit.prefix}_student_info.csv"
        att_files = sorted((unit.path / "data").glob("*attendance.*")) if (unit.path / "data").is_dir() else []
        for f in [csv_path, *att_files]:
            entry.capture(f)
        merged, old_n = _merge_roster(csv_path, new_df.copy(), ['Student ID', 'Name', 'Class Group'])
        merged.to_csv(csv_path, index=False)
        print(f"✅ Merged sec {sec_num} roster: {len(merged)} students (added {len(merged) - old_n})")
        cfg_unit = config_for(unit.path)
        sch = cfg_unit.get('class_schedule') if isinstance(cfg_unit.get('class_schedule'), dict) else {}
        class_cols = calculate_class_dates(cfg_unit.get('term_start_date', '') or '', sch.get('day', ''),
                                           cfg_unit.get('exam_schedule', '') or '')
        att_path = unit.path / "data" / f"{unit.prefix}_attendance.xlsx"
        try:
            _attendance_rows(unit.path, att_path, merged, class_cols, entry)
        except Exception as e:
            print(f"⚠️ Warning: Could not update attendance spreadsheet: {e}")
    for old_sec, sids in movers.items():
        src_unit = course.section(old_sec)
        moved = move_students(src_unit.path, unit.path, sids, entry)
        for sid in sids:
            print(f"⚠️ {sid} moves sec {old_sec} → {sec_num} ({input_path.name}; {moved.get(sid, 0)} score/mark cells moved)")
    entry.close()
    print(f"✅ Roster: {sum(1 for _ in roster_sections(root))} students ({counts(roster_sections(root))})")
    if added:
        print(f"✅ config.yaml sections: {', '.join(s.num for s in at(root).sections)}")
    print("🚀 Course update completed successfully!")
    from src import rename
    if not all(_score_files_complete(s.path) for s in at(root).sections):
        print("ℹ️  Run grader update (no -i) to add the new students' rows to the score files"
              " (it then offers to push to the web copy).")
    elif added or movers:
        rename.offer_push(root, yes, f"section {sec_num} added" if added else "students moved")


def _update_flat_roster(target_dir: Path, input_path: Path, metadata: dict, new_df: pd.DataFrame, sec_num: str):
    """`update -i` into a flat one-section course: its roster merged, as before section folders."""
    from src.history import Entry
    info_dir = target_dir / "course_info"
    config_path = next(f for f in sorted(info_dir.glob("*_config.yaml")))
    csv_path = info_dir / f"{get_course_file_prefix(target_dir)}_student_info.csv"
    entry = Entry(target_dir, "grader", "update-roster", note=str(input_path.name))
    attendance_files = sorted((target_dir / "data").glob("*attendance.*")) if (target_dir / "data").is_dir() else []
    for f in [config_path, csv_path, *attendance_files]:
        entry.capture(f)
    shutil.copy2(config_path, config_path.with_suffix(".yaml.bak"))
    print(f"📦 Backed up configuration to: {config_path.with_suffix('.yaml.bak').name}")
    cols = ['Student ID', 'Name', 'Class Group']
    if csv_path.exists():
        shutil.copy2(csv_path, csv_path.with_suffix(".csv.bak"))
        print(f"📦 Backed up student info to: {csv_path.with_suffix('.csv.bak').name}")
        head = pd.read_csv(csv_path, nrows=0).columns.astype(str).str.strip()
        if 'Section' in head:  # a roster written with a Section column keeps it (one value)
            cols.append('Section')
            new_df['Section'] = sec_num
    merged_df, old_n = _merge_roster(csv_path, new_df, cols)
    merged_df.to_csv(csv_path, index=False)
    print(f"✅ Merged student list. Total students now: {len(merged_df)} (Added {len(merged_df) - old_n} new students)")

    existing_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    for key in COURSE_KEYS + ('sec_num', 'class_schedule', 'exam_schedule'):
        if key in metadata and metadata[key] is not None:
            existing_config[key] = metadata[key]
    existing_config.pop('sections', None)  # a one-section course has no sections: list
    existing_config.setdefault('term_start_date', '')
    if 'weights' not in existing_config:
        existing_config['weights'] = {'attendance': 0.10, 'homework': 0.20, 'midterm': 0.30, 'final': 0.40}
    elif 'attendance' not in existing_config['weights']:
        existing_config['weights']['attendance'] = 0.10
        if 'final' in existing_config['weights']:
            existing_config['weights']['final'] = round(existing_config['weights']['final'] - 0.10, 2)
    existing_config.setdefault('data_mapping', {'homework': ['hw1', 'hw2'], 'midterm': ['midterm_score'], 'final': ['final_exam']})
    existing_config.setdefault('grade_boundaries', {'A': 80, 'B+': 75, 'B': 70, 'C+': 65, 'C': 60, 'D+': 55, 'D': 50})
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(existing_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"✅ Merged metadata into configuration at: {config_path.name}")
    try:
        att_path = target_dir / "data" / f"{get_course_file_prefix(target_dir)}_attendance.xlsx"
        sch = existing_config.get('class_schedule', {})
        weekday = sch.get('day', '') if isinstance(sch, dict) else ''
        class_cols = calculate_class_dates(existing_config.get('term_start_date', ''), weekday,
                                           existing_config.get('exam_schedule', ''))
        _attendance_rows(target_dir, att_path, merged_df, class_cols, entry)
    except Exception as e:
        print(f"⚠️ Warning: Could not update attendance spreadsheet: {e}")
    entry.close()
    if len(merged_df) > old_n and any((target_dir / "data").glob("*.csv")):
        print("ℹ️  Run grader update (no -i) to add the new students' rows to the score files.")
    print(f"🚀 Course update completed successfully!")


def _score_files_complete(course_dir: Path) -> bool:
    """Every roster student has a row in every data/*.csv (so a push carries them all)."""
    from src.sections import roster_file
    from src.webpush import _students, data_csvs
    roster = roster_file(course_dir)
    if roster is None:
        return True
    ids = set(_students(roster, roster.name))
    try:
        return all(ids <= set(_students(p, p.name)) for p in data_csvs(course_dir))
    except Exception:
        return False

def update_course(input_file: str = None, config_file: str = None, purge_empty_orphans: bool = False,
                  yes: bool = False):
    # 1. Raw excel file update mode (if input_file is supplied)
    if input_file:
        _update_roster(input_file, yes)
        return

    # 2. Configuration file update mode (if config_file is supplied or auto-detected)
    cfg_path = _config_here(config_file)
    if not cfg_path or not cfg_path.exists():
        print("❌ Error: Configuration file not specified or not found.")
        print("Please provide the path to the config file or run update from inside a course grading directory.")
        sys.exit(1)

    # Every section of a course with section folders, each like a flat course (SPEC_section_folders.md)
    from src.course import at
    course = at(cfg_path)
    for section in course.sections:
        if course.layout:
            print(f"── sec {section.num} ({section.path.name}/) ──")
        if _update_unit(section.path, purge_empty_orphans, yes) is False:
            return
    if course.layout:
        print(f"🚀 All {len(course.sections)} sections updated.")
    from src import rename
    rename.offer_push(course.root, yes, "new students", only_if_counts_differ=True)


def _config_here(config_file: str = None) -> Path | None:
    """config_file, else the config of the course we're in (a section folder's is its course's)."""
    if config_file:
        return Path(config_file)
    from src.course import config_path
    found = config_path(Path(".")) if Path("course_info").is_dir() else None
    if found is not None:
        print(f"🔍 Auto-detected configuration file: {found}")
    return found


def _update_unit(course_dir: Path, purge_empty_orphans: bool = False, yes: bool = False):
    """`grader update` for one folder of rosters and data/ (a flat course, or one section folder)."""
    course_dir = Path(course_dir).resolve()
    info_dir = course_dir / "course_info"
    data_dir = course_dir / "data"

    # You changed pts_each while bare-header columns hold scores: ask before they count out of the new value.
    from src.columns import settle_default_changes
    from src.history import Entry
    pts_entry = Entry(course_dir, "grader", "update-points")
    settle_default_changes(course_dir, _ask, pts_entry, yes=yes)
    if pts_entry.close():
        print(f"  (undo with: grader undo {pts_entry.id})")
    
    # Load config yaml (a section folder's: the shared one with its own schedules)
    from src.course import config_path, config_for
    cfg_path = config_path(course_dir)
    try:
        config = config_for(course_dir) if cfg_path else {}
    except Exception as e:
        print(f"❌ Error loading config YAML: {e}")
        sys.exit(1)

    data_mapping = config.get("data_mapping", {})
    if not data_mapping:
        print(f"⚠️ Warning: 'data_mapping' not found or empty in {cfg_path.name if cfg_path else 'config.yaml'}.")
        return False

    # Locate student info CSV
    student_info_files = [f for f in info_dir.iterdir() if f.is_file() and f.name.endswith("_student_info.csv") and not f.name.endswith(".bak")]
    if not student_info_files:
        print(f"❌ Error: Student registry (*_student_info.csv) not found under {info_dir}")
        sys.exit(1)
        
    student_info_path = student_info_files[0]
    try:
        registry_df = pd.read_csv(student_info_path)
        registry_df.columns = registry_df.columns.astype(str).str.strip()
    except Exception as e:
        print(f"❌ Error reading student registry: {e}")
        sys.exit(1)
        
    if 'Student ID' not in registry_df.columns or 'Name' not in registry_df.columns:
        print(f"❌ Error: Registry must contain 'Student ID' and 'Name' columns.")
        sys.exit(1)
        
    # Clean registry
    student_registry = registry_df[['Student ID', 'Name']].copy()
    student_registry['Student ID'] = student_registry['Student ID'].astype(str).str.strip()
    student_registry['Name'] = student_registry['Name'].astype(str).str.strip()
    registry_ids = set(student_registry['Student ID'].tolist())
    
    data_dir.mkdir(parents=True, exist_ok=True)
    prefix = get_course_file_prefix(course_dir)
    from src.columns import points_side, save_base, settle_removed, unmapped
    removed_names: dict = {}  # taken out of config.yaml, or kept on purpose: no "added by hand?" note for these
    for u in unmapped(course_dir):
        if u.kind in ("removed", "kept"):
            removed_names.setdefault(u.category, set()).add(u.name)

    for category, mapping_item in data_mapping.items():
        total_pts, columns = parse_category_mapping(mapping_item)
        if not isinstance(columns, list):
            continue
        default = category_default(category, mapping_item)
        csv_path = data_dir / f"{prefix}_{category}.csv"

        # Calculate target_total based on category weight or manual total_pts
        weights = config.get("weights", {})
        weight = weights.get(category, None)
        weight_points = weight * 100.0 if weight is not None else 100.0
        
        target_total = total_pts if total_pts is not None else weight_points
        
        specified_total = 0.0
        unspecified_cols = 0
        for col in columns:
            _, pts = parse_config_col(col)
            pts = resolve(pts, default)
            if pts is not None:
                specified_total += pts
            else:
                unspecified_cols += 1
                
        if unspecified_cols > 0:
            remaining = target_total - specified_total
            if remaining <= 0:
                default_max = 10.0 # Fallback default
            else:
                default_max = round(remaining / unspecified_cols, 2)
        else:
            default_max = 100.0
            # Warning check
            import math
            if total_pts is not None and not math.isclose(specified_total, target_total, abs_tol=1e-2):
                print(f"⚠️ WARNING: [{category}] Manual total score is determined as {target_total}pts, "
                      f"but the sum of specified columns is {specified_total}pts.")
        
        # If database CSV doesn't exist, create it
        if not csv_path.exists():
            print(f"✨ Score database {csv_path.name} does not exist. Creating it...")
            create_empty_category_csv(category, columns, student_registry, csv_path, default_max, default)
            continue
            
        try:
            # As text: a column with blanks would otherwise come back as floats and be written as `9.0`.
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            df.columns = df.columns.astype(str).str.strip()
        except Exception as e:
            print(f"❌ Error reading {csv_path.name}: {e}. Skipping.")
            continue

        if 'Student ID' not in df.columns:
            print(f"❌ Error: {csv_path.name} is missing 'Student ID' column. Skipping.")
            continue

        # Separate Max/sentinel row from students (discard Max row if it exists)
        df['Student ID'] = df['Student ID'].astype(str).str.strip()
        max_mask = df['Student ID'].str.lower().isin(['max', 'max score', 'full score', 'full'])
        student_rows = df[~max_mask].copy()

        # Parse current headers to extract base names and original formatting.
        # Keyed by a normalized form (case/whitespace/underscore-insensitive)
        # so cosmetic header differences don't make a real, scored column
        # look "missing" and get silently duplicated/blanked below.
        csv_columns_info = {} # normalized_key -> (original_header, max_score)
        for col in df.columns:
            if col in ['Student ID', 'Name']:
                continue
            clean_name, pts = parse_pts(col)
            if clean_name.lower().strip() == 'total':
                continue
            key = normalize_col_key(clean_name)
            if pts is not None:
                csv_columns_info[key] = (col, pts)
            else:
                csv_columns_info[key] = (col, 100.0)

        # Determine the columns the current config expects
        desired_keys = []
        desired_base_mapping = {} # normalized_key -> (clean_name, original_config_col)
        for col in columns:
            clean_name, _ = parse_config_col(col)
            key = normalize_col_key(clean_name)
            desired_keys.append(key)
            desired_base_mapping[key] = (clean_name, col)

        # Columns present in the file but no longer referenced by config stay
        # here for now; after this loop, settle_removed() asks about the ones
        # you took out of the config (delete / rename / keep), src/columns.py.
        orphan_keys = [k for k in csv_columns_info.keys() if k not in desired_keys]
        orphan_headers = []
        for key in orphan_keys:
            orig_header = csv_columns_info[key][0]

            # --purge-empty-orphans only ever removes a column when every
            # single row's value is blank/NaN - a literal "0" is a real score
            # (a student who scored zero) and is never purged.
            if purge_empty_orphans and orig_header in student_rows.columns:
                col_data = student_rows[orig_header]
                blank_mask = col_data.isna() | (col_data.astype(str).str.strip() == '')
                is_empty = bool(blank_mask.all())
                if is_empty:
                    student_rows.drop(columns=[orig_header], inplace=True)
                    print(f"  🗑️ Removed empty orphan column '{orig_header}' from {csv_path.name} (--purge-empty-orphans).")
                    continue

            orphan_headers.append(orig_header)
            if parse_pts(orig_header)[0] not in removed_names.get(category, set()):
                print(f"  ℹ️ '{orig_header}' in {csv_path.name} isn't in config.yaml (added by hand?); left as-is. "
                      "`grader sync` offers to add it.")

        # Determine header mapping for desired columns. This only ever adds a
        # brand-new column or renames an existing one in place (both
        # value-preserving) - it never assigns into a column that already
        # holds data.
        final_headers = ['Student ID', 'Name']
        total_pts = 0.0
        shortened = []  # `4 (10pts)` → `4`: same points, at the category default (one line per file below)
        for key in desired_keys:
            clean_name, config_col_item = desired_base_mapping[key]
            _, pts = parse_config_col(config_col_item)
            pts = resolve(pts, default)
            pts_val = float(pts if pts is not None else default_max)
            total_pts += pts_val

            new_header = header_for(clean_name, pts_val, default)

            if key in csv_columns_info:
                # Column already exists (matched by normalized name).
                orig_header = csv_columns_info[key][0]
                orig_pts = resolve(parse_pts(orig_header)[1], default)  # a bare header holds the default
                if orig_header == new_header:
                    final_headers.append(orig_header)
                elif points_side(course_dir, category, clean_name, orig_pts, pts) == "file":
                    # You changed the points in the CSV header, not in the config: keep them; `grader sync` asks.
                    final_headers.append(orig_header)
                    print(f"  ℹ️ '{orig_header}': points changed in the file, not in config.yaml; kept. "
                          "Run `grader sync` to settle them.")
                elif new_header in student_rows.columns:
                    # Another column already occupies the desired header name;
                    # don't clobber it, keep this column under its old name.
                    final_headers.append(orig_header)
                else:
                    student_rows.rename(columns={orig_header: new_header}, inplace=True)
                    if orig_pts is not None and abs(orig_pts - pts_val) < 1e-9:
                        shortened.append((orig_header, new_header))
                    else:
                        print(f"  📝 Updated max points header for '{clean_name}' from '{orig_header}' to '{new_header}'")
                    final_headers.append(new_header)
            elif new_header in student_rows.columns:
                # A column with this exact name already exists even though it
                # wasn't matched above - keep it rather than overwrite its data.
                final_headers.append(new_header)
            else:
                # Genuinely new column - safe to add.
                student_rows[new_header] = ""
                final_headers.append(new_header)
                print(f"  ✚ Added new column '{new_header}' to {csv_path.name}")

        if shortened:
            (o, n), more = shortened[0], ", …" if len(shortened) > 1 else ""
            each = f": {fmt_pts(default)} pts each" if default is not None else ""
            print(f"  📝 [{category}] {len(shortened)} header(s) reshaped ('{o}' → '{n}'{more}){each}")

        # Keep orphaned columns in the file (just not part of the calculated
        # schema) rather than dropping them on the column reindex below.
        final_headers.extend(orphan_headers)

        # Handle the total column at the end
        total_pts_str = str(int(total_pts)) if total_pts.is_integer() else str(total_pts)
        total_header = f"total ({total_pts_str}pts)"

        # Locate if there is an existing total column in student_rows to rename/align
        existing_total_col = None
        for col in student_rows.columns:
            if str(col).lower().strip().startswith('total'):
                existing_total_col = col
                break

        if existing_total_col:
            if existing_total_col != total_header:
                student_rows.rename(columns={existing_total_col: total_header}, inplace=True)
                print(f"  📝 Updated max points header for total column from '{existing_total_col}' to '{total_header}'")
        else:
            student_rows[total_header] = ""

        final_headers.append(total_header)

        # Students in the file who are no longer in the registry: never
        # discard a row that still holds real data, only prune rows that are
        # already empty.
        csv_student_ids = student_rows['Student ID'].tolist()
        orphan_student_ids = [sid for sid in csv_student_ids if sid not in registry_ids]
        score_cols = [c for c in student_rows.columns if c not in ['Student ID', 'Name']]
        rows_to_drop = []

        for sid in orphan_student_ids:
            stud_row = student_rows[student_rows['Student ID'] == sid]
            has_scores = False
            for c in score_cols:
                val = stud_row.iloc[0][c]
                if pd.notna(val) and str(val).strip() != '' and str(val).strip() != '0' and val != 0:
                    has_scores = True
                    break

            student_name = stud_row.iloc[0].get('Name', 'Unknown')
            if has_scores:
                print(f"  ℹ️ Student '{sid}' ({student_name}) has scores in {csv_path.name} but is no longer in the registry; left as-is.")
            else:
                rows_to_drop.append(sid)

        if rows_to_drop:
            student_rows = student_rows[~student_rows['Student ID'].isin(rows_to_drop)]

        # Students to add
        students_to_add = [sid for sid in registry_ids if sid not in csv_student_ids]
        add_rows = []
        for sid in students_to_add:
            reg_row = student_registry[student_registry['Student ID'] == sid]
            name = reg_row.iloc[0]['Name'] if not reg_row.empty else ""
            new_row = {col: "" for col in final_headers}
            new_row['Student ID'] = sid
            new_row['Name'] = name
            add_rows.append(new_row)

        if add_rows:
            student_rows = pd.concat([student_rows, pd.DataFrame(add_rows)], ignore_index=True)

        # Order columns and sort students
        student_rows = student_rows[final_headers]
        student_rows = student_rows.sort_values(by='Student ID').reset_index(drop=True)

        # Skip touching the file entirely if nothing actually changed.
        needs_write = True
        try:
            original_aligned = df[~max_mask].copy()
            original_aligned = original_aligned.sort_values(by='Student ID').reset_index(drop=True)
            if (list(original_aligned.columns) == list(student_rows.columns)
                    and original_aligned.shape[0] == student_rows.shape[0]
                    and original_aligned.fillna('').astype(str).equals(student_rows.fillna('').astype(str))):
                needs_write = False
        except Exception:
            pass

        if not needs_write:
            print(f"✅ {csv_path.name} already up to date.")
            continue

        print(f"🔄 Aligning database score file: {csv_path.name}...")

        # Backup before writing
        backup_csv_before_write(csv_path, tool="grader", action="update")
        print(f"  📦 Backed up {csv_path.name} (history/ and {csv_path.with_suffix('.csv.bak').name})")

        # Save
        student_rows.to_csv(csv_path, index=False)
        print(f"  ✅ Successfully updated {csv_path.name}")
        
    # Align/update attendance sheet if attendance is in weights
    if 'weights' in config and 'attendance' in config['weights']:
        try:
            att_filename = f"{prefix}_attendance.xlsx"
            att_path = data_dir / att_filename
            
            sch = config.get('class_schedule', {})
            weekday = sch.get('day', '') if isinstance(sch, dict) else ''
            exam_sch = config.get('exam_schedule', '')
            term_start = config.get('term_start_date', '')
            
            class_cols = calculate_class_dates(term_start, weekday, exam_sch)
            _attendance_rows(course_dir, att_path, student_registry, class_cols)
        except Exception as e:
            print(f"⚠️ Warning: Could not update/align attendance spreadsheet: {e}")

    # Columns you took out of config.yaml that are still in a score file: delete / rename / keep.
    from src.history import Entry
    entry = Entry(course_dir, "grader", "update-columns")
    settled = settle_removed(course_dir, _ask, entry)
    entry_id = entry.close()
    if entry_id:
        print(f"  (undo with: grader undo {entry_id})")
    save_base(course_dir, kept=settled.kept)
    _refresh_totals(course_dir, "update")
    print("🚀 All databases updated successfully!")

def _find_bak_files(course_dir: Path) -> list[Path]:
    """
    Collects .bak files from every subdirectory `update_course` can write
    backups into - course_info/ (student roster + config) and data/
    (per-category score CSVs) - so `grader undo` can restore whichever one
    the last update actually touched.
    """
    bak_files = []
    for subdir_name in ("course_info", "data"):
        subdir = course_dir / subdir_name
        if subdir.is_dir():
            bak_files.extend(f for f in subdir.iterdir() if f.is_file() and f.name.endswith(".bak"))
    return bak_files

def _course_dirs_here() -> list[Path]:
    dirs = []
    for sp in (Path("."), Path("courses")):
        if sp.is_dir():
            dirs.extend(d for d in sp.iterdir() if d.is_dir() and (d / "course_info").is_dir())
    return dirs


def _resolve_course_for_history(course: str = None) -> Path | None:
    """--course DIR, else the course we're in, else the course under ./ or ./courses
    whose history (or .bak files) changed most recently."""
    from src.history import HISTORY, LOG
    if course:
        d = Path(course)
        if not (d / "course_info").is_dir():
            print(f"❌ {d} is not a course folder (no course_info/).")
            sys.exit(1)
        from src.history import root_of
        return root_of(d)
    if Path("course_info").is_dir():
        from src.history import root_of
        return root_of(Path("."))  # a section folder's history is its course's (SPEC_section_folders.md F6)
    best = []
    for d in _course_dirs_here():
        stamps = [f.stat().st_mtime for f in _find_bak_files(d)]
        log = d / HISTORY / LOG
        if log.exists():
            stamps.append(log.stat().st_mtime)
        if stamps:
            best.append((max(stamps), d))
    return max(best)[1] if best else None


def _describe_entry(e: dict) -> str:
    cells = f", {e['cells']} cell(s)" if e.get("cells") is not None else ""
    note = f" — {e['note']}" if e.get("note") else ""
    return f"{e['id']}  [{e.get('tool')} {e.get('action')}{cells}]  {', '.join(e.get('files', []))}{note}"


def _refresh_totals(course_dir, action: str) -> None:
    """Every score file's total column in step with its cells (src/sync.py); attendance is src/attendance.py."""
    from src.sync import sync_course
    try:
        done = sync_course(course_dir, tool="grader", action=action)
    except Exception as e:
        print(f"⚠️ Warning: could not refresh the total columns: {e}")
        return
    for name, n in done.items():
        print(f"  🔁 {name}: total column refreshed ({n} cell(s))")


def _ask(question: str, default: str = "") -> str:
    if not sys.stdin.isatty():
        return default
    ans = input(question + " ").strip()
    return ans or default


def sync_cmd(course: str = None, yes: bool = False):
    """
    `grader sync`: after editing score CSVs or the attendance sheet by hand. Refreshes every total column and settles
    what only you can decide: columns you added (add them to config.yaml?), points that differ between a header and
    the config, and the attendance xlsx ↔ csv (src/attendance.py: what changed in one file is copied to the other;
    conflicts, removing a session with marks and empty past sessions are asked). Everything it writes is one
    history entry (grader undo).
    """
    from src.csvio import read_csv_text, write_csv_text
    from src.history import Entry
    from src.sync import (_fmt_pts, category_items, config_file, data_files, find_changes, parse_item, parse_pts,
                          raw_config, set_category, sync_course)
    from src.points import at_default, defaults
    from src.csvio import atomic_write_bytes

    target_dir = _resolve_course_for_history(course)
    if not target_dir:
        print("❌ No course folder here (use --course DIR).")
        sys.exit(1)
    from src.course import at
    found = at(target_dir)
    for section in found.sections:  # each section folder in turn (SPEC_section_folders.md), or the flat course
        _sync_unit(section.path, yes, f"{found.root.name} · sec {section.num}" if found.layout else None)


def _sync_unit(target_dir: Path, yes: bool = False, title: str | None = None):
    """`grader sync` for one folder of rosters and data/ (a flat course, or one section folder)."""
    from src.csvio import read_csv_text, write_csv_text
    from src.history import Entry
    from src.sync import (_fmt_pts, category_items, config_file, data_files, find_changes, parse_item, parse_pts,
                          raw_config, set_category, sync_course)
    from src.points import at_default, defaults
    from src.csvio import atomic_write_bytes
    target_dir = Path(target_dir).resolve()
    from src import attendance
    from src.columns import save_base, settle_default_changes, settle_removed
    entry = Entry(target_dir, "grader", "sync")
    print(f"🔄 Sync: {title or target_dir.name}")
    # You changed pts_each while bare-header columns hold scores: ask first (it can put the old value back).
    settle_default_changes(target_dir, _ask, entry, yes=yes)
    ch = find_changes(target_dir)
    att = attendance.plan(target_dir)
    att_todo = att is not None and (att.has_changes() or att.empty_past or att.first_run)
    if ch.empty() and not att_todo:
        save_base(target_dir)
        if entry.close():
            print(f"✅ Synced. Undo with: grader undo {entry.id}")
            return
        print("✅ Everything is in sync: every total matches its cells, every column is in config.yaml"
              + (", and the attendance xlsx and csv agree." if att is not None else "."))
        return

    if ch.stale:
        print("Totals to refresh:")
        for name, n in ch.stale.items():
            print(f"  {name}: {n} cell(s)")
    if ch.missing:
        print("In config.yaml but not in the file (run `grader update` to add the column):")
        for cat, col in ch.missing:
            print(f"  [{cat}] {col}")
    for cat, col in ch.no_points:
        print(f"⚠️  [{cat}] '{col}' has no points in config.yaml or in its header: write `- {col}: N` in the config.")

    cfg = raw_config(target_dir)
    dm = cfg.get("data_mapping") or {}
    dflt = defaults(cfg)
    new_values: dict = {}
    header_fixes: list = []  # (category, column, points)

    # You edited config.yaml: the files follow it (src/columns.py tells which side changed).
    for cat, fname, col, hp, cp in ch.follow_config:
        print(f"  ✍️  {fname}: '{col}' {_fmt_pts(hp)} → {_fmt_pts(cp)} pts, as you set in config.yaml")
        header_fixes.append((cat, col, cp))
    settled = None
    if ch.removed:
        print("Taken out of config.yaml but still in a file:")
        settled = settle_removed(target_dir, _ask, entry, yes=yes)

    def items_of(cat):
        if cat not in new_values:
            import copy
            new_values[cat] = copy.deepcopy(dm.get(cat))
        return new_values[cat]

    def entry_for(cat, key, pts):
        return key if at_default(pts, dflt.get(cat)) else {key: pts}  # bare at the category default

    def set_points(cat, col, pts):
        value = items_of(cat)
        lst = value["columns"] if isinstance(value, dict) and "columns" in value else value
        for i, item in enumerate(lst):
            if parse_item(item)[0] == col:
                key = next(iter(item)) if isinstance(item, dict) else item  # keeps `5` a number in the YAML
                lst[i] = entry_for(cat, key, pts)
                return

    def add_column(cat, col, pts):
        value = items_of(cat)
        lst = value["columns"] if isinstance(value, dict) and "columns" in value else value
        key = int(col) if col.isdigit() and str(int(col)) == col else col  # lab `11`, like `1`…`10`
        lst.append(entry_for(cat, key, pts))

    if ch.unmapped:
        print("Columns in a file but not in config.yaml (they don't count yet):")
    for cat, fname, col, hp in ch.unmapped:
        pts = hp
        if pts is None:
            raw = _ask(f"  {fname}: '{col}' has no points in its header. Full score for it (empty = skip)?")
            try:
                pts = float(raw) if raw else None
            except ValueError:
                pts = None
            if pts is None:
                print(f"  ⏭  {col}: skipped")
                continue
        pts = int(pts) if float(pts).is_integer() else pts
        if yes or _ask(f"  {fname}: add '{col}: {_fmt_pts(pts)}' to [{cat}] in config.yaml so it counts? [y/N]",
                       "n").lower() in ("y", "yes"):
            add_column(cat, col, pts)
            print(f"  ➕ [{cat}] {col}: {_fmt_pts(pts)} (now counts)")
            if hp is None:
                header_fixes.append((cat, col, pts))
        else:
            print(f"  ⏭  {col}: left out (not counted)")

    if ch.conflicts:
        print("Points that differ between a file and config.yaml:")
    for cat, fname, col, hp, cp in ch.conflicts:
        ans = "s" if yes else _ask(f"  {fname}: '{col}' is {_fmt_pts(hp)} pts in the file, {_fmt_pts(cp)} in "
                                   f"config.yaml. Keep the file's [f] / the config's [c] / skip [s]?", "s").lower()
        if ans.startswith("f"):
            set_points(cat, col, int(hp) if float(hp).is_integer() else hp)
        elif ans.startswith("c"):
            header_fixes.append((cat, col, cp))
        else:
            print(f"  ⏭  {col}: left as it is")

    att_decisions = _attendance_questions(att, yes) if att_todo else None

    if att_decisions is not None and att_decisions.apply:
        try:
            for name, n in attendance.apply(att, att_decisions, entry).items():
                print(f"  ✍️  {name}: attendance synced")
        except attendance.Locked as e:
            print(f"  ❌ attendance not synced: {e}")
    if new_values:
        cfg_path = config_file(target_dir)
        entry.capture(cfg_path)
        for cat, value in new_values.items():
            atomic_write_bytes(cfg_path, set_category(cfg_path, cat, value).encode("utf-8"))
        print(f"  ✍️  {cfg_path.name}: data_mapping updated ({', '.join(new_values)})")
    files = data_files(target_dir)
    for cat, col, pts in header_fixes:
        path = files.get(cat)
        if not path:
            continue
        doc = read_csv_text(path)
        for i, h in enumerate(doc.header):
            if parse_pts(h)[0] == col and not h.strip().lower().startswith("total"):
                doc.header[i] = header_for(col, pts, dflt.get(cat))
        entry.capture(path)
        write_csv_text(path, doc)
        print(f"  ✍️  {path.name}: header of '{col}' set to {_fmt_pts(pts)} pts")
    # Same points, other form: `4 (10pts)` → `4` at the category default (or back, when the default is gone).
    reshaped: dict = {}
    for cat, fname, old, new in ch.reshape:
        path = files.get(cat)
        if path:
            reshaped.setdefault(path, []).append((old, new))
    for path, pairs in reshaped.items():
        doc = read_csv_text(path)
        for old, new in pairs:
            i = doc.col(old)
            if i is not None:
                doc.header[i] = new
        entry.capture(path)
        write_csv_text(path, doc)
        (o, n), more = pairs[0], ", …" if len(pairs) > 1 else ""
        print(f"  📝 {path.name}: {len(pairs)} header(s) reshaped ('{o}' → '{n}'{more})")
    done = sync_course(target_dir, entry=entry)
    for name, n in done.items():
        print(f"  🔁 {name}: total column refreshed ({n} cell(s))")
    save_base(target_dir, kept=settled.kept if settled else None)
    entry_id = entry.close(sum(done.values()) or None)
    print("✅ Synced." + (f" Undo with: grader undo {entry_id}" if entry_id else " Nothing needed writing."))


def _attendance_questions(att, yes: bool):
    """The attendance part of `grader sync`: preview, then the questions (SPEC.md decisions 1-3, 7, 8)."""
    from src.attendance import Decisions
    print(f"Attendance ({att.xlsx.name} ↔ {att.csv.name}):")
    for line in _att_lines(att):
        print(line)
    d = Decisions()
    if att.is_locked:
        print(f"  ❌ {att.xlsx.name} is open in Excel: close it, then run `grader sync` again.")
        d.apply = False
        return d
    for r in att.marked:
        other = "csv" if r.deleted_in == "xlsx" else "xlsx"
        ans = "n" if yes else _ask(f"  Session '{r.session}' is gone from the {r.deleted_in} but has {r.marks} mark(s) "
                                   f"in the {other}. Remove it from the {other} too? [y/N]", "n").lower()
        if ans not in ("y", "yes"):
            d.keep.add(r.session)
            print(f"  ↩️  '{r.session}' kept: put back into the {r.deleted_in}")
    from src.sections import roster_sections, tagger
    tag = tagger(roster_sections(att.course))
    for sid, f, x, c, b in att.conflicts:
        ans = "s" if yes else _ask(f"  {tag(sid)}{sid} {f}: xlsx {x or '—'} / csv {c or '—'}. Keep the xlsx's [x] / the csv's [c] "
                                   f"/ skip [s]?", "s").lower()
        if ans.startswith(("x", "c")):
            d.choose[(sid, f)] = ans[0]
        else:
            print(f"  ⏭  {tag(sid)}{sid} {f}: left different (asked again next time)")
    if att.empty_past:
        print(f"  Sessions before today with no mark for anyone: {', '.join(att.empty_past)}")
        ans = "n" if yes else _ask("  Remove them from both files (the attendance maximum drops to the sessions "
                                   "left)? [y/N]", "n").lower()
        d.drop_empty = ans in ("y", "yes")
    if att.first_run and (att.copies or att.removals or att.additions):
        d.apply = yes or _ask("  Apply these attendance changes (first sync)? [y/N]", "n").lower() in ("y", "yes")
        if not d.apply:
            print("  ⏭  attendance not synced")
    return d


def _att_lines(att):
    from src.attendance import describe
    return describe(att)


def split_cmd(course: str = None, yes: bool = False):
    """`grader split` (src/split.py, SPEC_section_folders.md F9)."""
    from src import split, webpush
    from src.webdrive import Refused
    folder = Path(course) if course else Path(".")
    try:
        p = split.plan(folder)
    except Refused as e:
        print(e)
        sys.exit(1)
    from src.sections import counts
    print(f"🔀 {p.course.name}: {len(p.secmap)} students ({counts(p.secmap)})")
    print(f"   → {p.target.name}/ with " + ", ".join(f"sec{s}/" for s in p.sections) +
          f"; the old folder is kept as {p.course.name}{split.BEFORE}")
    if not yes:
        if not sys.stdin.isatty():
            print("❌ No terminal to ask on. Nothing changed. To split: grader split -y")
            sys.exit(1)
        if input("❓ Split it? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing changed.")
            return
    try:
        new = split.apply(p)
    except Refused as e:
        print(e)
        sys.exit(1)
    print(f"✅ Split into {new}")
    print(f"   Your shell is still in the old path: cd {new}")
    print(f"   Delete {p.course.name}{split.BEFORE} once you're happy (grader undo puts it back until then).")
    if p.drive:
        root, mirror = p.drive
        print(f"   The old web copy {mirror.name} is no longer updated: delete it in Drive.")
        ask = yes or (sys.stdin.isatty() and input("❓ Push the new course to the web copy? [y/N] ").strip().lower()
                      in ("y", "yes"))
        if ask:
            try:
                webpush.push(new, root)
            except Refused as e:
                print(e)


def history_course(course: str = None, limit: int = 20):
    from src.history import list_entries
    target_dir = _resolve_course_for_history(course)
    if not target_dir:
        print("❌ No course folder with history found here (use --course DIR).")
        sys.exit(1)
    entries = list_entries(target_dir)
    print(f"🕘 History of {target_dir.resolve().name} ({len(entries)} entries, newest first)")
    if not entries:
        print("  (none yet)")
        return
    undone = {e.get("undoes") for e in entries if e.get("action") == "undo"}
    for e in list(reversed(entries))[:limit]:
        mark = "  (undone)" if e["id"] in undone else ""
        print(f"  {_describe_entry(e)}{mark}")
    print("Restore one with: grader undo <ID>   (no ID = newest one not undone yet)")


def _confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print("Not restored: no terminal to confirm on (pass --yes).")
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def undo_course(entry_id: str = None, course: str = None, yes: bool = False):
    from src.history import list_entries, latest_undoable, later_changes, restore
    target_dir = _resolve_course_for_history(course)
    if not target_dir:
        print("❌ No backup files found to undo.")
        sys.exit(1)

    entries = list_entries(target_dir)
    if entries or entry_id:
        if entry_id:
            entry = next((e for e in entries if e["id"] == entry_id), None)
            if entry is None:
                print(f"❌ No history entry {entry_id!r} in {target_dir.resolve().name} (see: grader history).")
                sys.exit(1)
        else:
            entry = latest_undoable(target_dir)
            if entry is None:
                print(f"❌ Nothing left to undo in {target_dir.resolve().name} (see: grader history).")
                sys.exit(1)
        print(f"🔄 Course: {target_dir.resolve().name}")
        print(f"   Restore: {_describe_entry(entry)}")
        from src import rename
        if entry.get("action") == "split":
            from src import split
            if not _confirm(f"Undo the split: remove {entry['to']}/ and give {entry['before']} its old name back?", yes):
                return
            try:
                old = split.undo(target_dir, entry)
            except split.Refused as e:
                print(e)
                sys.exit(1)
            print(f"✅ Back to {old.name}. Your shell is still in the removed folder: cd {old}")
            return
        if rename.is_rename(entry):
            if not _confirm(f"Rename the course back to {entry['from']}?", yes):
                return
            try:
                dest = rename.undo(target_dir, entry)
            except rename.Refused as e:
                print(e)
                sys.exit(1)
            for line in rename.done_lines(entry["to"], dest.name):
                print(line)
            rename.offer_push(dest, yes, "renamed")
            print("✅ Undo completed (redo it with: grader undo <ID of this undo>).")
            return
        later = later_changes(target_dir, entry["id"])
        if later:
            print(f"   ⚠️  {len(later)} later change(s) to the same file(s) will be lost too:")
            for e in later:
                print(f"      {_describe_entry(e)}")
        if not _confirm("Put these files back as they were before that change?", yes):
            return
        for rel in restore(target_dir, entry["id"]):
            print(f"  ⏪ Restored {rel}")
        print("✅ Undo completed (the versions it replaced are saved in history/ too).")
        return

    # No history yet: the old .bak behaviour.
    bak_files = _find_bak_files(target_dir)
    if not bak_files:
        print(f"❌ No backup files found in {target_dir}.")
        sys.exit(1)

    print(f"🔄 Found backup files in course: {target_dir.resolve().name}")
    if not _confirm(f"Restore {len(bak_files)} .bak file(s)?", yes):
        return
    for bak in bak_files:
        original_name = bak.name[:-4] # strip .bak
        original_path = bak.parent / original_name
        # Restore
        shutil.copy2(bak, original_path)
        bak.unlink()
        print(f"  ⏪ Restored {original_name} from backup")
    print("✅ Undo completed successfully!")

def mock_course():
    """
    Generates a complete, self-contained mock course under courses/ with a
    config, student roster, score data, and attendance sheet, seeded
    deterministically so grade-tui and the dashboard can be exercised end-to-end
    without needing real student data. Always wipes and regenerates that one
    hardcoded, unmistakably-fake course (identified by its fixed term/course_name).
    """
    mock_term = "0"
    name_for_path = "GenPhysMock"  # the abbreviation, as `grader init` names courses; course_name stays Thai

    # Made as one folder with a Section column, then split into section folders, as `grader split` does
    # (SPEC_section_folders.md): courses/0_GenPhysMock/sec51/, sec52/
    final_dir = Path("courses") / f"{mock_term}_{name_for_path}"
    base_dir = Path("courses") / f"{mock_term}_{name_for_path}_flat"
    for d in (final_dir, base_dir, base_dir.with_name(base_dir.name + "_before_split")):
        if d.exists():
            shutil.rmtree(d)

    course_info_dir = base_dir / "course_info"
    data_dir = base_dir / "data"
    reports_dir = base_dir / "reports"
    course_info_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    rng = random.Random(42)

    # --- Config ---
    config_path = course_info_dir / f"{mock_term}_{name_for_path}_config.yaml"
    config_path.write_text("""course_id: "MOCK"
course_name: "ฟิสิกส์ทั่วไป (ข้อมูลจำลอง)"
term: "0"
sec_num: "51"
teacher: "อาจารย์ตัวอย่าง"
credits: "3(3-0-6)"
university: "มหาวิทยาลัยตัวอย่าง"
campus: "วิทยาเขตตัวอย่าง"
program: "ปริญญาตรี (ข้อมูลจำลอง)"
class_schedule:
  day: "พ."
  time: "09:00-12:00"
  classroom: "MOCK-101"
exam_schedule: "M 15 Mar 2027 09:00-11:00, F 17 May 2027 09:00-12:00"
sections:
  "51":
    class_schedule: {day: "พ.", time: "09:00-12:00", classroom: "MOCK-101"}
    exam_schedule: "M 15 Mar 2027 09:00-11:00, F 17 May 2027 09:00-12:00"
  "52":
    class_schedule: {day: "พ.", time: "13:00-16:00", classroom: "MOCK-101"}
    exam_schedule: "M 15 Mar 2027 09:00-11:00, F 17 May 2027 09:00-12:00"
term_start_date: "2027-01-11"

weights:
  attendance: 0.1
  homework: 0.2
  midterm: 0.3
  final: 0.4

data_mapping:
  homework: ["hw1 (10pts)", "hw2 (10pts)", "hw3 (10pts)"]
  midterm: ["midterm_exam (30pts)"]
  final: ["final_exam (40pts)"]

rules:
  drop_lowest_homework: true

grade_boundaries:
  A: 80
  B+: 75
  B: 70
  C+: 65
  C: 60
  D+: 55
  D: 50
""", encoding="utf-8")

    # --- Student roster ---
    FIRST_NAMES = [
        "Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona", "George", "Hannah",
        "Ian", "Julia", "Kevin", "Laura", "Michael", "Nora", "Oscar", "Paula",
        "Quentin", "Rachel", "Steven", "Tina",
    ]
    LAST_NAMES = [
        "Smith", "Jones", "Brown", "Prince", "Taylor", "Anderson", "Clark", "Lewis",
        "Walker", "Young", "King", "Wright", "Scott", "Green", "Baker", "Adams",
        "Nelson", "Carter", "Mitchell", "Perez",
    ]
    name_pool = [f"{fn} {ln}" for fn in FIRST_NAMES for ln in LAST_NAMES]
    rng.shuffle(name_pool)

    num_students = 30
    num_sessions = 15
    student_names = name_pool[:num_students]
    student_ids = [f"69200{i + 1:03d}" for i in range(num_students)]
    # Two sections (SPEC_sections.md): 16 students in 51, 14 in 52; the cohorts (หมู่เรียน) cut across them
    class_groups = ["ว 69.ค.บ.4.1" if i % 2 == 0 else "ว 69.ค.บ.4.2" for i in range(num_students)]
    sections = ["51" if i < 16 else "52" for i in range(num_students)]

    student_registry = pd.DataFrame({
        "Student ID": student_ids,
        "Name": student_names,
        "Class Group": class_groups,
        "Section": sections,
    })
    student_registry.to_csv(course_info_dir / f"{mock_term}_{name_for_path}_student_info.csv", index=False)

    # --- Deterministic edge-case index selection ---
    at_risk_idxs = set(rng.sample(range(num_students), 4))
    remaining = [i for i in range(num_students) if i not in at_risk_idxs]
    hw2_overmax_idx = rng.choice(remaining)
    midterm_overmax_idx = rng.choice(remaining)
    hw3_blank_idxs = set(rng.sample(remaining, 3))
    final_blank_idxs = set(rng.sample(remaining, 2))
    attendance_invalid_idxs = rng.sample(remaining, 2)

    def clipped_gauss(mu, sigma):
        return max(0.0, min(1.0, rng.gauss(mu, sigma)))

    # --- Homework scores (hw1, hw2, hw3; 10pts each; drop_lowest_homework exercises this) ---
    hw_max = 10.0
    hw_rows = []
    for i in range(num_students):
        scale = 0.3 if i in at_risk_idxs else 1.0
        scores = [round(clipped_gauss(0.75, 0.15) * hw_max * scale, 1) for _ in range(3)]
        if i == hw2_overmax_idx:
            scores[1] = 12.0  # deliberately exceeds the 10pt max
        if i in hw3_blank_idxs:
            scores[2] = None  # deliberately ungraded/missing
        row_total = round(sum(s for s in scores if s is not None), 1)
        hw_rows.append({
            "Student ID": student_ids[i],
            "Name": student_names[i],
            "hw1 (10pts)": scores[0],
            "hw2 (10pts)": scores[1],
            "hw3 (10pts)": scores[2],
            "total (30pts)": row_total,
        })
    pd.DataFrame(hw_rows).to_csv(data_dir / f"{mock_term}_{name_for_path}_homework.csv", index=False)

    # --- Midterm scores (30pts) ---
    midterm_max = 30.0
    mid_rows = []
    for i in range(num_students):
        scale = 0.3 if i in at_risk_idxs else 1.0
        score = round(clipped_gauss(0.70, 0.18) * midterm_max * scale, 1)
        if i == midterm_overmax_idx:
            score = 35.0  # deliberately exceeds the 30pt max
        mid_rows.append({
            "Student ID": student_ids[i],
            "Name": student_names[i],
            "midterm_exam (30pts)": score,
            "total (30pts)": score,
        })
    pd.DataFrame(mid_rows).to_csv(data_dir / f"{mock_term}_{name_for_path}_midterm.csv", index=False)

    # --- Final scores (40pts) ---
    final_max = 40.0
    final_rows = []
    for i in range(num_students):
        scale = 0.3 if i in at_risk_idxs else 1.0
        score = round(clipped_gauss(0.72, 0.16) * final_max * scale, 1)
        if i in final_blank_idxs:
            score = None  # deliberately not-yet-graded
        final_rows.append({
            "Student ID": student_ids[i],
            "Name": student_names[i],
            "final_exam (40pts)": score,
            "total (40pts)": score if score is not None else 0.0,
        })
    pd.DataFrame(final_rows).to_csv(data_dir / f"{mock_term}_{name_for_path}_final.csv", index=False)

    # --- Attendance sheet ---
    class_cols = calculate_class_dates(
        "2027-01-11", "พ.",
        "M 15 Mar 2027 09:00-11:00, F 17 May 2027 09:00-12:00",
        num_sessions,
    )

    att_codes = ["P", "L", "A", "X"]
    att_weights = [75, 10, 10, 5]
    att_rows = []
    for i in range(num_students):
        row = {"Student ID": student_ids[i], "Name": student_names[i]}
        for c in class_cols:
            row[c] = rng.choices(att_codes, weights=att_weights, k=1)[0]
        att_rows.append(row)
    for i in attendance_invalid_idxs:
        session = rng.choice(class_cols)
        att_rows[i][session] = "Z"  # deliberately invalid attendance code

    att_path = data_dir / f"{mock_term}_{name_for_path}_attendance.xlsx"
    # Seed a raw prefilled workbook, then reuse the real production helper to
    # merge those values in and apply the standard styling/validation/formulas.
    pd.DataFrame(att_rows).to_excel(att_path, index=False)
    save_attendance_excel(att_path, student_registry, class_cols)
    _attendance_csv(base_dir)
    from src import split
    split.split(base_dir, say=lambda *_: None, name=final_dir.name)
    shutil.rmtree(base_dir.with_name(base_dir.name + split.BEFORE))
    base_dir = final_dir
    log = base_dir / "history" / "log.jsonl"  # a mock starts with no history (nothing to undo)
    for d in (base_dir / "history").glob("*_grader_split*"):
        shutil.rmtree(d)
    if log.exists():
        log.unlink()

    print(f"✅ Successfully generated mock course at: {base_dir} (sec51/: 16 students, sec52/: 14)")
    print(f"✅ {num_students} students, {num_sessions} attendance sessions.")
    print("✅ Seeded edge cases: over-max scores, missing scores, invalid attendance codes, at-risk students.")


def _web_course(sub, course: str = None) -> Path:
    """COURSE, else the folder we're in when it is a course folder, else a usage error (exit 2)."""
    if course is None:
        if not Path("course_info").is_dir():
            sub.error(f"no course folder here; give one, e.g. {sub.prog} courses/9_ฟิสิกส์จำลอง_grading")
        return Path.cwd()
    if not (Path(course) / "course_info").is_dir():
        print(f"❌ {course} is not a course folder (no course_info/).")
        sys.exit(1)
    return Path(course)


def web_push(sub, args):
    """`grader web-push` (src/webpush.py). A refusal prints its message and exits 1, having written nothing."""
    from src import webpush
    from src.webdrive import Refused, drive_root
    course = _web_course(sub, args.course)
    try:
        webpush.push(course, drive_root(args.drive_root), force=args.force, semester=args.semester)
    except Refused as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        if args.debug:
            import traceback
            traceback.print_exc()
        else:
            print(f"❌ Unexpected error: {e}. Run again with --debug for the details.")
        sys.exit(1)


def web_pull(sub, args):
    """`grader web-pull` (src/webpull.py). Preview unless --yes; a refusal prints its message and exits 1."""
    from src import webpull
    from src.webdrive import Refused, drive_root
    course = _web_course(sub, args.course)
    try:
        code = webpull.pull(course, drive_root(args.drive_root), yes=args.yes, semester=args.semester)
    except Refused as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        if args.debug:
            import traceback
            traceback.print_exc()
        else:
            print(f"❌ Unexpected error: {e}. Run again with --debug for the details.")
        sys.exit(1)
    sys.exit(code)


def run_dashboard():
    from src.dashboard import run
    run()

def build_parser() -> argparse.ArgumentParser:
    """All of grader's subcommands and options (also the source of the zsh completion, src/complete.py)."""
    parser = argparse.ArgumentParser(description="🎓 Grading System Dashboard & Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    parser_init = subparsers.add_parser("init", help="Initialize a new course grading directory")
    parser_init.add_argument("-i", "--input", action="append",
                             help="Path to raw excel/csv file to initialize from (e.g. repclasslist.xls); "
                                  "repeat it for a course with several sections (one class list each)")
    parser_init.add_argument("--course_name", help="Course display/short name (e.g. 'General Relativity')")
    parser_init.add_argument("--term", help="The term for the course (e.g. '2026_S2')")
    parser_init.add_argument("--course_id", help="The course ID (e.g. 'PHYS1102')")
    parser_init.add_argument("--abbr", help="Short ASCII name for the folder and file names (e.g. 'ModPhys'). "
                                            "Default: ABBR of repclasslist_ABBR.xls, else asked")

    # mkdb command
    parser_mkdb = subparsers.add_parser("mkdb", help="Create empty database files for all categories from config")
    parser_mkdb.add_argument("config_file", nargs="?", help="Path to course config YAML file")
    parser_mkdb.add_argument("-i", "--input", help="Alias for path to course config YAML file")

    # Update command
    parser_update = subparsers.add_parser("update", help="Update student list from raw file or update database files from config")
    parser_update.add_argument("-i", "--input", help="Path to raw excel/csv student list file (e.g. repclasslist.xls)")
    parser_update.add_argument("config_file", nargs="?", help="Path to course config YAML file")
    parser_update.add_argument("--purge-empty-orphans", action="store_true",
                                help="Remove category-CSV columns no longer referenced by config.yaml, "
                                     "but only when every student's value in that column is blank. "
                                     "Orphan columns holding any real score are always left alone.")
    parser_update.add_argument("-y", "--yes", action="store_true",
                               help="Don't ask; when you changed pts_each, keep the new value")

    # Undo / history commands
    parser_undo = subparsers.add_parser("undo", help="Restore files from history/ (newest change not undone yet, or ID)")
    parser_undo.add_argument("entry", nargs="?", help="History entry ID (see: grader history)")
    parser_undo.add_argument("--course", help="Course folder (default: the one you're in, or the most recently changed)")
    parser_undo.add_argument("-y", "--yes", action="store_true", help="Don't ask for confirmation")
    parser_sync = subparsers.add_parser("sync", help="After editing score CSVs or the attendance sheet by hand: "
                                        "refresh the total columns, add hand-made columns to config.yaml, and keep "
                                        "the attendance xlsx and csv in step (asks first)")
    parser_sync.add_argument("--course", help="Course folder (default: the one you're in, or the most recently changed)")
    parser_sync.add_argument("-y", "--yes", action="store_true", help="Add every new column and copy one-sided "
                                        "attendance changes without asking (conflicts, removing a session with "
                                        "marks and empty sessions are left alone)")
    parser_split = subparsers.add_parser("split", help="Turn a one-folder course with several sections (a Section "
                                         "column in its roster) into one sub-folder per section")
    parser_split.add_argument("course", nargs="?", metavar="COURSE",
                              help="The course folder (default: the one you're in)")
    parser_split.add_argument("-y", "--yes", action="store_true", help="Don't ask (also pushes when it has a web copy)")
    parser_history = subparsers.add_parser("history", help="List the saved versions in a course's history/")
    parser_history.add_argument("--course", help="Course folder (default: the one you're in, or the most recently changed)")
    parser_history.add_argument("-n", type=int, default=20, help="How many entries to show (default 20)")

    # Mock command
    parser_mock = subparsers.add_parser("mock", help="Generate a complete mock course under courses/ for testing grade-tui")

    # Dashboard command
    parser_dashboard = subparsers.add_parser("dashboard", help="Launch the grade dashboard")

    # grade_web (web/SPEC.md "Mac commands")
    parser_web_push = subparsers.add_parser(
        "web-push", help="Copy a course to Google Drive for the grade_web app (phone or browser)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Copy a course to Google Drive (My Drive/grade_courses/<semester>/<course folder>/, the semester\n"
                    "being the folder the course sits in on the Mac). The grade_web app lists it once My Drive/\n"
                    "grade_web/ has a shortcut to that semester folder. Reads the course and never writes into it.\n"
                    "Refuses while web edits are waiting to be pulled, so nothing made on the phone is lost.",
        epilog="examples:\n"
               "  grader web-push                                   # inside 9_ฟิสิกส์จำลอง_grading/\n"
               "  grader web-push courses/9_ฟิสิกส์จำลอง_grading\n"
               "  grader web-pull                                   # later: see what the web changed")
    parser_web_push.add_argument("--force", action="store_true",
                                 help="Push even if web edits are waiting to be pulled. They are kept in "
                                      "<course>/archive/ on Drive marked as discarded, never deleted")
    parser_web_push.add_argument("--semester", metavar="NAME",
                                 help="Semester folder on Drive (default: the name of the folder the course is in, "
                                      "e.g. 2569-1). The folder above it is $GRADE_WEB_COURSES, else grade_courses")
    parser_web_push.add_argument("--drive-root", metavar="DIR",
                                 help='Your "My Drive" folder (default: $GRADE_WEB_DRIVE_ROOT, else the Google '
                                      "Drive for Desktop folder of your @g.cmru.ac.th account)")
    parser_web_push.add_argument("--debug", action="store_true", help="Show the full traceback on unexpected errors")
    parser_web_push.add_argument("course", nargs="?", metavar="COURSE",
                                 help="Course folder (default: the folder you're in, if it has course_info/)")

    parser_web_pull = subparsers.add_parser(
        "web-pull", help="Bring grade_web edits back into the course (preview; --yes applies)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Bring the edits made in the grade_web app back into the course. Without --yes it only shows\n"
                    "what would change. Cells changed on the Mac since the push keep the Mac value (listed as\n"
                    "conflicts). Everything it writes is one history entry: grader undo puts it all back.",
        epilog="examples:\n"
               "  grader web-pull                 # preview, inside the course folder\n"
               "  grader web-pull --yes           # apply\n"
               "  grader undo                     # take the whole pull back")
    parser_web_pull.add_argument("-y", "--yes", action="store_true",
                                 help="Apply the changes (default: preview only, nothing written)")
    parser_web_pull.add_argument("--semester", metavar="NAME",
                                 help="Semester folder on Drive, as given to web-push (default: the name of the "
                                      "folder the course is in)")
    parser_web_pull.add_argument("--drive-root", metavar="DIR",
                                 help='Your "My Drive" folder (default: $GRADE_WEB_DRIVE_ROOT, else the Google '
                                      "Drive for Desktop folder of your @g.cmru.ac.th account)")
    parser_web_pull.add_argument("--debug", action="store_true", help="Show the full traceback on unexpected errors")
    parser_web_pull.add_argument("course", nargs="?", metavar="COURSE",
                                 help="Course folder (default: the folder you're in, if it has course_info/)")

    parser_completion = subparsers.add_parser(
        "completion", help="Print or install the zsh Tab completion for grader",
        description="zsh prints the completion script (_grader); install writes it where zsh finds it\n"
                    "(~/.oh-my-zsh/cache/completions/, or $GRADER_ZSH_COMPLETIONS). Once installed, grader keeps\n"
                    "it up to date by itself whenever grader.py changes.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser_completion.add_argument("what", nargs="?", choices=["zsh", "install"],
                                   help="zsh: print the script; install: write it for zsh to load")
    return parser


if __name__ == "__main__":
    from src import complete
    parser = build_parser()
    subs = complete._subcommands(parser)
    args = parser.parse_args()
    if args.command != "completion":
        complete.refresh_installed(parser)

    if args.command == "init":
        # Programmatic validation for init arguments
        if not args.input and (not args.course_name or not args.term or not args.course_id):
            parser.error("Either --input / -i, or all of (--course_name, --term, --course_id) must be specified.")
        init_course(args.course_name, args.term, args.course_id, args.input, args.abbr)
    elif args.command == "mkdb":
        mkdb_course(args.config_file, args.input)
    elif args.command == "update":
        if args.input:
            update_course(input_file=args.input, yes=args.yes)
        else:
            update_course(config_file=args.config_file, purge_empty_orphans=args.purge_empty_orphans,
                          yes=args.yes)
    elif args.command == "undo":
        undo_course(args.entry, args.course, args.yes)
    elif args.command == "sync":
        sync_cmd(args.course, args.yes)
    elif args.command == "split":
        split_cmd(args.course, args.yes)
    elif args.command == "history":
        history_course(args.course, args.n)
    elif args.command == "mock":
        mock_course()
    elif args.command == "dashboard":
        run_dashboard()
    elif args.command == "web-push":
        web_push(subs["web-push"], args)
    elif args.command == "web-pull":
        web_pull(subs["web-pull"], args)
    elif args.command == "completion":
        if args.what == "zsh":
            print(complete.zsh_script(parser), end="")
        elif args.what == "install":
            sys.exit(complete.install(parser))
        else:
            subs["completion"].print_help()
    else:
        # Default behavior: show help
        parser.print_help()
        sys.exit(1)
