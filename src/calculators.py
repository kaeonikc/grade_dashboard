import math
import pandas as pd

def validate_scores(df: pd.DataFrame, config: dict, max_scores: dict) -> list[str]:
    """
    Checks every mapped assignment column for scores that exceed their defined maximum.
    Also validates that manually specified totals match column sums in the database.
    Returns a list of human-readable warning strings.
    """
    warnings = []
    data_mapping = config.get('data_mapping', {})
    total_pts_config = config.get('total_pts', {})

    # Check for manual total points mismatch warnings
    for category, columns in data_mapping.items():
        if category in total_pts_config:
            target_total = total_pts_config[category]
            cat_max_scores = {col: max_scores.get(col, 100.0) for col in columns if col in df.columns}
            actual_total = sum(cat_max_scores.values())
            if not math.isclose(actual_total, target_total, abs_tol=1e-2):
                warnings.append(
                    f"[{category}] Warning: Manual total score is determined as {target_total}pts, "
                    f"but the sum of parts in database is {actual_total}pts."
                )

    # Check for scores exceeding max score
    for category, columns in data_mapping.items():
        if category == 'attendance':
            valid_codes = {'P', 'A', 'L', 'EA', 'X', '', 'nan'}
            for col in columns:
                if col not in df.columns:
                    continue
                invalid_mask = ~df[col].astype(str).str.strip().replace('nan', '').isin(valid_codes)
                offenders = df[invalid_mask]
                for _, row in offenders.iterrows():
                    val = row[col]
                    student_id = str(row.get('Student ID', '?')).strip()
                    name = str(row.get('Name', '')).strip()
                    label = f"{student_id} ({name})" if name else student_id
                    warnings.append(
                        f"[{category}] Column '{col}': student {label} "
                        f"has invalid attendance code '{val}' (must be P, A, L, EA, or X)."
                    )
            continue

        for col in columns:
            if col not in df.columns:
                continue
            max_val = max_scores.get(col, 100.0)
            numeric_col = pd.to_numeric(df[col], errors='coerce')
            offenders = df[numeric_col > max_val]
            for _, row in offenders.iterrows():
                score = numeric_col.loc[row.name]
                student_id = str(row.get('Student ID', '?')).strip()
                name = str(row.get('Name', '')).strip()
                label = f"{student_id} ({name})" if name else student_id
                warnings.append(
                    f"[{category}] Column '{col}': student {label} "
                    f"has score {score} which exceeds the max of {max_val}."
                )

    return warnings


def assign_letter_grade(score: float, boundaries: dict) -> str:
    """Assigns a letter grade based on the score and defined boundaries."""
    # Convert boundaries dict to a sorted list of tuples: [('A', 80), ('B+', 75), ...]
    sorted_bounds = sorted(boundaries.items(), key=lambda item: item[1], reverse=True)
    
    for grade, threshold in sorted_bounds:
        if score >= threshold:
            return grade
    return "F"

def calculate_final_grades(df: pd.DataFrame, config: dict, max_scores: dict, use_weighted_scores: bool = True) -> pd.DataFrame:
    """
    Calculates the final grades based on the data_mapping, dynamic max_scores, and weights.
    Applies rules such as drop_lowest_homework.
    """
    if df.empty:
        return df

    result_df = df.copy()
    
    # Filter the dataframe to only include 'Student ID', 'Name', and mapped columns
    data_mapping = config.get('data_mapping', {})
    allowed_cols = ['Student ID', 'Name']
    for cols in data_mapping.values():
        allowed_cols.extend(cols)
        
    cols_to_keep = [col for col in result_df.columns if col in allowed_cols]
    result_df = result_df[cols_to_keep]
    
    # Treat missing assignments as 0, but only for numeric columns (exclude attendance)
    attendance_cols = set(data_mapping.get('attendance', []))
    numeric_cols = [col for col in result_df.columns if col not in ['Student ID', 'Name'] and col not in attendance_cols]
    result_df[numeric_cols] = result_df[numeric_cols].fillna(0)
    
    # For attendance columns, fillna with empty string
    for col in attendance_cols:
        if col in result_df.columns:
            result_df[col] = result_df[col].fillna('')
    
    total_score = pd.Series(0.0, index=df.index)
    weights = config.get('weights', {})
    rules = config.get('rules', {})
    
    for category, weight in weights.items():
        columns = data_mapping.get(category, [])
        valid_cols = [col for col in columns if col in result_df.columns]
        
        if not valid_cols:
            result_df[f'{category}_pct'] = 0.0
            continue
            
        category_df = result_df[valid_cols]
        # Use dynamic max score from CSV, default to 100 if missing
        cat_max_scores = {col: max_scores.get(col, 100.0) for col in valid_cols}
        
        if category == 'attendance':
            # Map P/L/EA/A to numeric values
            mapping = {'P': 1.0, 'L': 0.8, 'EA': 1.0, 'X': 1.0, 'A': 0.0}
            
            numeric_category_df = category_df.copy()
            for col in valid_cols:
                numeric_category_df[col] = numeric_category_df[col].astype(str).str.strip().map(mapping).fillna(0.0)
            
            cat_sum = numeric_category_df[valid_cols].sum(axis=1)
            cat_max_scores = {col: 1.0 for col in valid_cols}
            
            # The total score (possible_max) is the static number of class columns
            possible_max = float(len(valid_cols))
        elif category == 'homework' and rules.get('drop_lowest_homework') and len(valid_cols) > 1:
            # We need to find the lowest percentage score to drop
            pct_df = pd.DataFrame()
            for col in valid_cols:
                pct_df[col] = category_df[col] / cat_max_scores[col]
            
            # Find the column to drop for each student
            min_col = pct_df.idxmin(axis=1)
            
            # Now sum up scores excluding the dropped col
            cat_sum = pd.Series(0.0, index=df.index)
            possible_max = pd.Series(0.0, index=df.index)
            for idx in df.index:
                drop_c = min_col[idx]
                c_sum = sum(category_df.loc[idx, c] for c in valid_cols if c != drop_c)
                p_max = sum(cat_max_scores[c] for c in valid_cols if c != drop_c)
                cat_sum[idx] = c_sum
                possible_max[idx] = p_max
        else:
            cat_sum = category_df.sum(axis=1)
            possible_max = sum(cat_max_scores.values())

        total_pts_config = config.get('total_pts', {})
        category_total_pts = total_pts_config.get(category)
        if category_total_pts is not None:
            if isinstance(possible_max, pd.Series):
                possible_max = possible_max.clip(lower=category_total_pts)
            else:
                possible_max = max(possible_max, category_total_pts)

        # Add raw category total points column, e.g., "Quiz Total" or "Homework Total"
        total_col_name = f"{category.title()} Total"
        result_df[total_col_name] = cat_sum.round(2)
        if isinstance(possible_max, pd.Series):
            max_scores[total_col_name] = float(possible_max.max())
        else:
            max_scores[total_col_name] = float(possible_max)

        # Calculate percentage for this category
        if isinstance(possible_max, pd.Series):
            category_pct = cat_sum / possible_max.replace(0, 1) # avoid div0
            category_pct[possible_max == 0] = 0.0
        else:
            category_pct = cat_sum / possible_max if possible_max > 0 else 0.0
            
        category_weighted = category_pct * 100 * weight
        if use_weighted_scores:
            result_df[f'{category}_pct'] = category_weighted.round(2)
        else:
            result_df[f'{category}_pct'] = (category_pct * 100).round(2)
        
        # Add to total weighted score
        total_score += category_weighted
        
        # Add to coursework total if not midterm or final
        if category.lower() not in ['midterm', 'final']:
            if 'Coursework Total' not in result_df.columns:
                result_df['Coursework Total'] = 0.0
            result_df['Coursework Total'] += category_weighted

    if 'Coursework Total' in result_df.columns:
        if not use_weighted_scores:
            cw_weight = sum(w for c, w in weights.items() if c.lower() not in ['midterm', 'final'])
            if cw_weight > 0:
                result_df['Coursework Total'] = (result_df['Coursework Total'] / cw_weight).round(2)
        else:
            result_df['Coursework Total'] = result_df['Coursework Total'].round(2)

    result_df['Final Score'] = total_score.round(2)
    
    boundaries = config.get('grade_boundaries', {})
    result_df['Grade'] = result_df['Final Score'].apply(lambda x: assign_letter_grade(x, boundaries))

    # Store original values for comparison in dashboard
    result_df['Original Final Score'] = result_df['Final Score'].copy()
    result_df['Original Grade'] = result_df['Grade'].copy()

    # Apply Round Up (Ceil) logic as requested
    # Rounding up "Coursework Total", "midterm_pct", and "final_pct"
    if 'Coursework Total' in result_df.columns:
        result_df['Coursework Total'] = result_df['Coursework Total'].apply(lambda x: int(math.ceil(x)))
    
    if 'midterm_pct' in result_df.columns:
        result_df['midterm_pct'] = result_df['midterm_pct'].apply(lambda x: int(math.ceil(x)))
        
    if 'final_pct' in result_df.columns:
        result_df['final_pct'] = result_df['final_pct'].apply(lambda x: int(math.ceil(x)))

    # Recalculate Final Score based on rounded values
    # Note: total_score was the sum of all weighted categories.
    # To be consistent with the rounded components, we recalculate it.
    new_total = pd.Series(0, index=df.index)
    if 'Coursework Total' in result_df.columns:
        new_total += result_df['Coursework Total']
    if 'midterm_pct' in result_df.columns:
        new_total += result_df['midterm_pct']
    if 'final_pct' in result_df.columns:
        new_total += result_df['final_pct']
    
    # If there are other categories not in Coursework Total, Midterm or Final, 
    # they would have been lost in this recalculation if we weren't careful.
    # But current logic defines Coursework Total as everything except midterm and final.
    
    result_df['Final Score'] = new_total.astype(int)
    result_df['Grade'] = result_df['Final Score'].apply(lambda x: assign_letter_grade(x, boundaries))
    
    return result_df
