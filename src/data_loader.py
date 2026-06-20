import os
import yaml
import pandas as pd
from pathlib import Path

def load_config(course_path: str) -> dict:
    """Reads the config.yaml for a given course."""
    config_file = Path(course_path) / "config.yaml"
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_course_data(course_path: str) -> tuple[pd.DataFrame, dict]:
    """
    Reads all .csv and .xlsx files in the course's data/ directory.
    Extracts max scores if a row has 'Student ID' as 'Full Score', 'Max Score', or 'Max'.
    Assumes all files have a 'Student ID' and 'Name' column to merge on.
    """
    data_dir = Path(course_path) / "data"
    if not data_dir.exists() or not data_dir.is_dir():
        return pd.DataFrame(), {}

    all_dfs = []
    max_scores = {}
    
    for file in data_dir.iterdir():
        if file.suffix in ['.csv', '.xlsx']:
            if file.suffix == '.csv':
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
                
            df.columns = df.columns.astype(str).str.strip() # Strip whitespace from headers
            
            # Extract max scores directly from column names, e.g., "final_exam (30pts)"
            import re
            new_columns = {}
            for col in df.columns:
                if col in ['Student ID', 'Name']:
                    new_columns[col] = col
                    continue
                
                # Look for "(XX)" or "(XXpts)" or "(XX points)"
                match = re.search(r'\(\s*([\d.]+)\s*(?:pts|points)?\s*\)', col, re.IGNORECASE)
                if match:
                    try:
                        max_score = float(match.group(1))
                        clean_col = re.sub(r'\s*\(\s*[\d.]+\s*(?:pts|points)?\s*\)', '', col, flags=re.IGNORECASE).strip()
                        max_scores[clean_col] = max_score
                        new_columns[col] = clean_col
                    except ValueError:
                        new_columns[col] = col
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
        if col != 'Student ID':
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
