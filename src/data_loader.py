import os
import re
import sys
import yaml
import pandas as pd
from pathlib import Path

def parse_pts(col_name: str) -> tuple[str, float | None]:
    """
    Parses a column name to see if it already contains points notation.
    Returns (clean_name, pts_value) or (col_name, None).
    """
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

def sync_attendance_xlsx_to_csv(xlsx_path: Path, csv_path: Path):
    """
    Reads the attendance Excel file and saves it as a CSV file.
    Ensures the CSV acts as the database for calculations/TUI.
    """
    try:
        df = pd.read_excel(xlsx_path)
        df.columns = df.columns.astype(str).str.strip()
        # Clean Student ID and Name columns
        if 'Student ID' in df.columns:
            df['Student ID'] = df['Student ID'].astype(str).str.strip()
        if 'Name' in df.columns:
            df['Name'] = df['Name'].astype(str).str.strip()
            
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
        print(f"✅ Synced attendance database CSV at: {csv_path.name}", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ Error syncing attendance XLSX to CSV: {e}", file=sys.stderr)

def check_and_sync_attendance(course_path: Path):
    data_dir = course_path / "data"
    if not data_dir.exists() or not data_dir.is_dir():
        return
    xlsx_files = [f for f in data_dir.iterdir() if f.is_file() and f.name.endswith("attendance.xlsx")]
    for xlsx_file in xlsx_files:
        csv_file = xlsx_file.with_suffix(".csv")
        # Sync if CSV doesn't exist or Excel is newer
        if not csv_file.exists() or xlsx_file.stat().st_mtime > csv_file.stat().st_mtime:
            sync_attendance_xlsx_to_csv(xlsx_file, csv_file)

def load_config(course_path: str) -> dict:
    """Reads the <term>_<course_id>_config.yaml under course_info/ for a given course."""
    path = Path(course_path)
    check_and_sync_attendance(path)
    info_dir = path / "course_info"
    if not info_dir.is_dir():
        raise FileNotFoundError(f"course_info directory not found under {course_path}")
        
    config_files = [f for f in info_dir.iterdir() if f.is_file() and f.name.endswith("_config.yaml")]
    if not config_files:
        raise FileNotFoundError(f"No *_config.yaml file found in {info_dir}")
        
    config_file = config_files[0]
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
        
    # Auto-detect attendance columns if attendance is in weights but missing in data_mapping
    if 'weights' in config and 'attendance' in config['weights']:
        if 'data_mapping' not in config:
            config['data_mapping'] = {}
        if 'attendance' not in config['data_mapping'] or not config['data_mapping']['attendance']:
            data_dir = Path(course_path) / "data"
            attendance_cols = []
            if data_dir.exists() and data_dir.is_dir():
                att_files = [f for f in data_dir.iterdir() if f.is_file() and (f.name.endswith("attendance.csv") or f.name.endswith("attendance.xlsx"))]
                if att_files:
                    try:
                        # Prefer CSV if it exists
                        att_file = next((f for f in att_files if f.name.endswith("attendance.csv")), att_files[0])
                        if att_file.suffix == '.csv':
                            df_att_headers = pd.read_csv(att_file, nrows=0)
                        else:
                            df_att_headers = pd.read_excel(att_file, nrows=0)
                        for col in df_att_headers.columns:
                            col_str = str(col).strip()
                            if col_str not in ['Student ID', 'Name'] and not col_str.lower().startswith('total') and not col_str.startswith('=') and 'unnamed' not in col_str.lower():
                                attendance_cols.append(col_str)
                    except Exception as e:
                        print(f"⚠️ Warning: Could not auto-detect attendance headers: {e}", file=sys.stderr)
            config['data_mapping']['attendance'] = attendance_cols

    # Clean data_mapping columns
    config['total_pts'] = {}
    if 'data_mapping' in config:
        new_mapping = {}
        for category, columns in config['data_mapping'].items():
            if isinstance(columns, dict) and 'columns' in columns:
                try:
                    config['total_pts'][category] = float(columns.get('total_pts', 0.0))
                except (ValueError, TypeError):
                    pass
                cols_list = columns.get('columns', [])
            else:
                cols_list = columns
                
            if isinstance(cols_list, list):
                new_columns = []
                for col in cols_list:
                    clean_name, _ = parse_config_col(col)
                    new_columns.append(clean_name)
                new_mapping[category] = new_columns
            else:
                new_mapping[category] = cols_list
        config['data_mapping'] = new_mapping
        
    return config

def load_course_data(course_path: str) -> tuple[pd.DataFrame, dict]:
    """
    Reads all .csv and .xlsx files in the course's data/ directory
    as well as any *_student_info.csv in the course_info/ directory.
    Extracts max scores if a row has 'Student ID' as 'Full Score', 'Max Score', or 'Max'.
    Assumes all files have a 'Student ID' and 'Name' column to merge on.
    """
    path = Path(course_path)
    check_and_sync_attendance(path)
    all_dfs = []
    max_scores = {}
    attendance_cols = set()
    
    # Load default max scores from config's data_mapping point annotations
    try:
        cfg_dir = Path(course_path) / "course_info"
        config_files = [f for f in cfg_dir.iterdir() if f.is_file() and f.name.endswith("_config.yaml")]
        if config_files:
            with open(config_files[0], 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f) or {}
            config_dm = raw_config.get('data_mapping', {})
            for category, columns in config_dm.items():
                cols_list = columns.get('columns', []) if isinstance(columns, dict) else columns
                if isinstance(cols_list, list):
                    for col in cols_list:
                        clean_name, pts = parse_config_col(col)
                        if pts is not None:
                            max_scores[clean_name] = pts
    except Exception:
        pass
    
    # 1. Load student_info.csv from course_info if it exists
    info_dir = Path(course_path) / "course_info"
    if info_dir.is_dir():
        for file in info_dir.iterdir():
            if file.is_file() and file.name.endswith("_student_info.csv"):
                try:
                    df = pd.read_csv(file)
                    df.columns = df.columns.astype(str).str.strip()
                    if 'Student ID' in df.columns:
                        df = df.dropna(subset=['Student ID'])
                        df = df[df['Student ID'].astype(str).str.strip() != '']
                        all_dfs.append(df)
                except Exception as e:
                    print(f"⚠️ Error reading student info file {file.name}: {e}", file=sys.stderr)
                    
    # 2. Load other CSV/Excel files from data/ directory
    data_dir = Path(course_path) / "data"
    if data_dir.exists() and data_dir.is_dir():
        for file in data_dir.iterdir():
            # Skip Excel attendance file since we load the synced CSV version instead
            if file.name.endswith("attendance.xlsx"):
                continue
                
            if file.suffix in ['.csv', '.xlsx']:
                try:
                    if file.suffix == '.csv':
                        df = pd.read_csv(file)
                    else:
                        df = pd.read_excel(file)
                        
                    df.columns = df.columns.astype(str).str.strip() # Strip whitespace from headers
                    
                    # Ignore 'total' and formula/unnamed placeholder columns
                    total_cols = [col for col in df.columns if str(col).lower().strip().startswith('total') or str(col).startswith('=') or 'unnamed' in str(col).lower()]
                    if total_cols:
                        df.drop(columns=total_cols, inplace=True)
                    
                    if 'Student ID' in df.columns:
                        df = df.dropna(subset=['Student ID'])
                        df = df[df['Student ID'].astype(str).str.strip() != '']
                    
                    is_attendance = "attendance" in file.name
                    
                    # Extract max scores directly from column names, e.g., "final_exam (30pts)"
                    new_columns = {}
                    for col in df.columns:
                        if col in ['Student ID', 'Name']:
                            new_columns[col] = col
                            continue
                        
                        if is_attendance:
                            attendance_cols.add(col)
                            new_columns[col] = col
                            continue
                            
                        clean_col, pts = parse_pts(col)
                        if pts is not None:
                            max_scores[clean_col] = pts
                            new_columns[col] = clean_col
                        else:
                            new_columns[col] = col
                    
                    df.rename(columns=new_columns, inplace=True)
                    
                    # Fallback: Check for max score row if someone still uses it, but don't overwrite header maxes
                    if len(df) > 0 and str(df.iloc[0].get('Student ID', '')).lower().strip() in ['max score', 'max', 'full score', 'full']:
                        max_row = df.iloc[0]
                        df = df.iloc[1:].copy()
                        for col in df.columns:
                            if col not in ['Student ID', 'Name'] and col not in max_scores:
                                try:
                                    max_scores[col] = float(max_row[col])
                                except (ValueError, TypeError):
                                    pass
                    
                    all_dfs.append(df)
                except Exception as e:
                    print(f"⚠️ Error reading data file {file.name}: {e}", file=sys.stderr)

    if not all_dfs:
        return pd.DataFrame(), {}

    # Before merging, let's extract all available names to a master mapping
    # and remove the 'Name' column from all dataframes so they merge cleanly on 'Student ID'
    master_names = {}
    for curr_df in all_dfs:
        if 'Student ID' in curr_df.columns:
            # Safely cast Student ID to string
            curr_df['Student ID'] = curr_df['Student ID'].astype(str).str.strip()
            
            if 'Name' in curr_df.columns:
                # Add names to our master dictionary if they exist
                curr_df['Name'] = curr_df['Name'].astype(str).str.strip().replace('nan', '')
                for _, row in curr_df.iterrows():
                    sid = row['Student ID']
                    name = row['Name']
                    if name and sid not in master_names:
                        master_names[sid] = name
                
                # Drop Name column so it doesn't cause Name_x / Name_y conflicts
                curr_df.drop(columns=['Name'], inplace=True)

    # Merge all dataframes cleanly on 'Student ID' alone using outer join
    merged_df = all_dfs[0]
    for curr_df in all_dfs[1:]:
        if 'Student ID' in curr_df.columns:
            merged_df = pd.merge(merged_df, curr_df, on='Student ID', how='outer')

    # Convert numeric columns where possible
    for col in merged_df.columns:
        if col != 'Student ID' and col not in attendance_cols:
            merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')

    # Now that merging is done, put the Name column back in!
    # Map the Student ID to our master list of names, fallback to NaN if not found
    if 'Student ID' in merged_df.columns:
        merged_df.insert(1, 'Name', merged_df['Student ID'].map(master_names))
        merged_df['Name'] = merged_df['Name'].fillna('')
        
        # Force string type for Student ID and Name to avoid serialization issues
        merged_df['Student ID'] = merged_df['Student ID'].astype(str)
        merged_df['Name'] = merged_df['Name'].astype(str)
        
        # Ensure the final DataFrame is sorted by Student ID
        merged_df = merged_df.sort_values(by='Student ID').reset_index(drop=True)

    return merged_df, max_scores
