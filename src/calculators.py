import math
import pandas as pd

def validate_scores(df: pd.DataFrame, config: dict, max_scores: dict) -> list[str]:
    """
    Checks every mapped assignment column for scores that exceed their defined maximum.
    Returns a list of human-readable warning strings, one per offending (student, column) pair.
    """
    warnings = []
    data_mapping = config.get('data_mapping', {})

    for category, columns in data_mapping.items():
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
    
    # Treat missing assignments as 0, but only for numeric columns
    numeric_cols = [col for col in result_df.columns if col not in ['Student ID', 'Name']]
    result_df[numeric_cols] = result_df[numeric_cols].fillna(0)
    
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
        
        if category == 'homework' and rules.get('drop_lowest_homework') and len(valid_cols) > 1:
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
