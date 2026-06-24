#!/usr/bin/env python3
"""
converts repclasslist.xls to <term>_<course_id>_SEC_<sec_num>_student_info.csv
and extracts metadata to a corresponding .yaml file using keyword searching.
"""

import os
import re
import sys
from pathlib import Path
import pandas as pd
import yaml

def extract_metadata(df: pd.DataFrame) -> dict:
    """
    Extracts structured metadata from the first 15 rows of the dataframe
    by scanning for specific keywords rather than relying on exact cells.
    """
    metadata = {
        'university': '',
        'campus': '',
        'term_raw': '',
        'term': '',
        'program': '',
        'course_id': '',
        'sec_num': '',
        'credits': '',
        'course_name': '',
        'teacher': '',
        'class_schedule': {
            'day': '',
            'time': '',
            'classroom': ''
        },
        'exam_schedule': ''
    }
    
    # Iterate through first 15 rows and all columns to search for keywords
    limit_rows = min(15, len(df))
    for r in range(limit_rows):
        for c in range(df.shape[1]):
            val = df.iloc[r, c]
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if not val_str:
                continue
            
            # 1. University Name
            if 'มหาวิทยาลัย' in val_str or 'ราชภัฏ' in val_str:
                if not metadata['university']:
                    metadata['university'] = val_str
            
            # 2. Campus & Term
            if 'ภาคการศึกษา' in val_str or 'วิทยาเขต' in val_str:
                if not metadata.get('campus_and_term_raw'):
                    metadata['campus_and_term_raw'] = val_str
                    if 'ภาคการศึกษา' in val_str:
                        parts = val_str.split('ภาคการศึกษา')
                        metadata['campus'] = parts[0].strip()
                        term_raw = parts[1].strip()
                        metadata['term_raw'] = term_raw
                        match = re.search(r'(\d+)/(\d+)', term_raw)
                        if match:
                            sem, year_th = match.groups()
                            year_ad = int(year_th) - 543
                            metadata['term'] = f"{year_ad}_S{sem}"
                    else:
                        match = re.search(r'(\d)/(\d{4})', val_str)
                        if match:
                            sem, year_th = match.groups()
                            year_ad = int(year_th) - 543
                            metadata['term'] = f"{year_ad}_S{sem}"
            
            # 3. Program/Degree type
            if 'ปริญญา' in val_str or 'ภาคปกติ' in val_str or 'ภาคพิเศษ' in val_str:
                if not metadata['program'] and 'รหัสวิชา' not in val_str:
                    metadata['program'] = val_str
            
            # 4. Course Details (Course ID, Section Number, Name, Credits)
            if 'รหัสวิชา' in val_str:
                if not metadata.get('course_details_raw'):
                    metadata['course_details_raw'] = val_str
                    
                    # Match Course ID
                    match_id = re.search(r'รหัสวิชา\s*([A-Za-z0-9_.-]+)', val_str)
                    if match_id:
                        metadata['course_id'] = match_id.group(1).strip()
                    
                    # Match Section Number
                    match_sec = re.search(r'Sec\s*(\d+)', val_str)
                    if match_sec:
                        metadata['sec_num'] = match_sec.group(1).strip()
                    
                    # Match Credits
                    match_credits = re.search(r'หน่วยกิต\s*(\S+)', val_str)
                    if match_credits:
                        metadata['credits'] = match_credits.group(1).strip()
                    
                    # Extract Course Name
                    if 'หน่วยกิต' in val_str:
                        try:
                            part_id_name = val_str.split('รหัสวิชา')[1].split('หน่วยกิต')[0].strip()
                            if 'course_id' in metadata and metadata['course_id']:
                                metadata['course_name'] = part_id_name.replace(metadata['course_id'], '').strip()
                            else:
                                metadata['course_name'] = part_id_name
                        except Exception:
                            pass
            
            # 5. Teacher
            if 'ผู้สอน' in val_str or 'อาจารย์' in val_str:
                if 'รหัสวิชา' not in val_str:
                    if not metadata['teacher']:
                        metadata['teacher'] = val_str.replace('ผู้สอน', '').strip()
            
            # 6. Class Schedule
            if 'วันเวลาเรียน' in val_str or 'วันและเวลาเรียน' in val_str:
                if not metadata.get('class_schedule_raw'):
                    metadata['class_schedule_raw'] = val_str
                    val_clean = val_str.replace('วันเวลาเรียน', '').replace('วันและเวลาเรียน', '').strip()
                    parts = val_clean.split()
                    day = parts[0] if len(parts) >= 1 else ""
                    time_range = parts[1] if len(parts) >= 2 else ""
                    classroom = parts[2] if len(parts) >= 3 else ""
                    metadata['class_schedule'] = {
                        'day': day,
                        'time': time_range,
                        'classroom': classroom
                    }
            
            # 7. Exam Schedule
            if 'วันเวลาสอบ' in val_str or 'วันและเวลาสอบ' in val_str:
                if not metadata['exam_schedule']:
                    raw_exam = val_str.replace('วันเวลาสอบ', '').replace('วันและเวลาสอบ', '').strip()
                    
                    # Convert DD/MM/YY format to d mmm yyyy (e.g. 7 Aug 2026)
                    MONTH_ABBRS = {
                        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                        7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
                    }
                    def replace_date(match):
                        date_str = match.group(0)
                        try:
                            d, m, y = date_str.split('/')
                            day = int(d)
                            month = int(m)
                            year = 2000 + int(y)
                            if month in MONTH_ABBRS:
                                return f"{day} {MONTH_ABBRS[month]} {year}"
                        except Exception:
                            pass
                        return date_str
                    
                    metadata['exam_schedule'] = re.sub(r'\b\d{2}/\d{2}/\d{2,4}\b', replace_date, raw_exam)
                    
    # Check defaults and print warnings for missing fields
    required_fields = {
        'university': 'University Name',
        'term': 'Term (Semester/Year)',
        'course_id': 'Course ID',
        'sec_num': 'Section Number',
        'course_name': 'Course Name',
        'teacher': 'Teacher Name',
        'program': 'Program/Degree'
    }
    
    for key, display_name in required_fields.items():
        if not metadata.get(key):
            print(f"⚠️ Warning: Missing metadata field '{display_name}' - could not find keyword.")
            metadata[key] = f"Unknown_{key.upper()}"
            
    return metadata

def convert_excel_to_csv_and_yaml(input_path: Path, csv_path: Path = None, yaml_path: Path = None) -> tuple[dict, pd.DataFrame]:
    print(f"Loading {input_path.name}...")
    try:
        df_raw = pd.read_excel(input_path, header=None)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    # Extract all metadata dynamically
    metadata = extract_metadata(df_raw)
    
    term_str = metadata['term']
    course_id = metadata['course_id']
    sec_num = metadata['sec_num']
    
    # Output file paths
    base_name = f"{term_str}_{course_id}_SEC_{sec_num}_student_info"
    if csv_path is None:
        csv_path = input_path.parent / f"{base_name}.csv"
    if yaml_path is None:
        yaml_path = input_path.parent / f"{base_name}.yaml"

    print(f"Parsed metadata details:")
    for k, v in metadata.items():
        if not isinstance(v, dict):
            print(f"  - {k}: {v}")
            
    print(f"File Output Destination:")
    print(f"  - CSV: {csv_path.name}")
    print(f"  - YAML: {yaml_path.name}")

    # Find the header row (containing 'รหัสประจำตัว' or 'ชื่อ')
    header_idx = None
    for idx, row in df_raw.iterrows():
        row_str = [str(x).strip() for x in row]
        if 'รหัสประจำตัว' in row_str or 'ชื่อ' in row_str:
            header_idx = idx
            break

    if header_idx is None:
        print("❌ Error: Could not find student list header row containing 'รหัสประจำตัว' or 'ชื่อ'")
        sys.exit(1)

    # Set column headers
    headers = [str(x).strip() if not pd.isna(x) else "" for x in df_raw.iloc[header_idx]]
    
    # Map headers to index positions
    id_col_idx = None
    name_col_idx = None
    group_col_idx = None

    for i, h in enumerate(headers):
        if 'รหัสประจำตัว' in h:
            id_col_idx = i
        elif 'ชื่อ' in h:
            name_col_idx = i
        elif 'หมู่เรียน' in h:
            group_col_idx = i

    if id_col_idx is None or name_col_idx is None:
        print(f"❌ Error: Required columns not found. Headers parsed: {headers}")
        sys.exit(1)

    # Extract student data rows (skip subheader row)
    student_rows = []
    start_row = header_idx + 2
    for idx in range(start_row, len(df_raw)):
        row = df_raw.iloc[idx]
        
        row_val_0 = str(row.iloc[0]).strip()
        if 'พิมพ์ ณ วันที่' in row_val_0 or pd.isna(row.iloc[id_col_idx]):
            continue
            
        std_id = str(row.iloc[id_col_idx]).strip()
        if std_id.endswith('.0'):
            std_id = std_id[:-2]
            
        if not std_id or not std_id.isdigit():
            continue
            
        name = str(row.iloc[name_col_idx]).strip()
        group = str(row.iloc[group_col_idx]).strip() if group_col_idx is not None else ""
        
        student_rows.append({
            'Student ID': std_id,
            'Name': name,
            'Class Group': group
        })

    # Create cleaned DataFrame
    clean_df = pd.DataFrame(student_rows)
    clean_df = clean_df.sort_values(by='Student ID').reset_index(drop=True)

    # Save to CSV
    clean_df.to_csv(csv_path, index=False)
    
    # Save metadata to YAML (with Thai characters readable)
    try:
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(metadata, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"❌ Error writing YAML file: {e}")
        sys.exit(1)

    print(f"✅ Successfully converted and exported {len(clean_df)} student rows to CSV!")
    print(f"✅ Successfully wrote structured metadata to YAML!")
    return metadata, clean_df

if __name__ == '__main__':
    script_dir = Path(__file__).resolve().parent
    excel_file = script_dir / 'repclasslist.xls'
    if not excel_file.exists():
        print(f"❌ Could not find {excel_file.name} in current directory!")
        sys.exit(1)
        
    convert_excel_to_csv_and_yaml(excel_file)
