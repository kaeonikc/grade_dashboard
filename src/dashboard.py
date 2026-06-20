import streamlit as st
import pandas as pd
from pathlib import Path
import sys
import os

# Ensure src module can be imported
script_path = Path(__file__).resolve()
sys.path.insert(0, str(script_path.parent.parent))

from src.data_loader import load_config, load_course_data
from src.calculators import calculate_final_grades

st.set_page_config(page_title="Grade Dashboard", layout="wide")

st.title("🎓 Grade Dashboard")

# Find all courses
current_dir = Path(".")
courses_dir = current_dir / "courses"

potential_course_paths = []
# Look in current directory
potential_course_paths.extend([d for d in current_dir.iterdir() if d.is_dir()])
# Look in 'courses' directory if it exists
if courses_dir.exists() and courses_dir.is_dir():
    potential_course_paths.extend([d for d in courses_dir.iterdir() if d.is_dir()])

# Filter only those that have config.yaml
course_map = {d.name: d for d in potential_course_paths if (d / "config.yaml").exists()}

if not course_map:
    st.warning("No course directories found (looking for folders containing config.yaml in the current directory or 'courses/' folder).")
    st.stop()

st.sidebar.title("Select Course")
selected_course_name = st.sidebar.selectbox("Course", sorted(course_map.keys()))

course_path = course_map[selected_course_name]

try:
    config = load_config(course_path)
    st.sidebar.success(f"Loaded config for {config.get('course', selected_course_name)}")
except Exception as e:
    st.error(f"Failed to load config for {selected_course_name}: {e}")
    st.stop()

# Load Data
raw_df, max_scores = load_course_data(course_path)
if raw_df.empty:
    st.info(f"No student data found in {course_path / 'data'}")
    st.stop()

st.header(f"{config.get('course', selected_course_name)} - {config.get('term', '')}")

use_weighted_scores = st.checkbox("Show weighted scores (uncheck to show raw 100% scores)", value=True)

with st.spinner("Calculating grades..."):
    final_df = calculate_final_grades(raw_df, config, max_scores, use_weighted_scores)

col1, col2, col3 = st.columns(3)
col1.metric("Total Students", len(final_df))
avg_score = final_df['Final Score'].mean()
col2.metric("Average Score", f"{avg_score:.2f}%")
highest_score = final_df['Final Score'].max()
col3.metric("Highest Score", f"{highest_score:.2f}%")

st.subheader("Student Grades")

# --- Round-up Summary (Thick Box) ---
st.markdown("### 📊 Round-up Score Grade Summary")
with st.container(border=True):
    col_a, col_b = st.columns([1, 2])
    
    # Calculate grade changes
    # Ensure Original Grade and Grade columns exist from calculators.py
    if 'Original Grade' in final_df.columns:
        improved_students = final_df[final_df['Grade'] != final_df['Original Grade']]
        improved_count = len(improved_students)
        
        col_a.metric("Grades Improved", improved_count, help="Number of students whose letter grade increased due to rounding up Coursework, Midterm, and Final scores.")
        
        # Grade Order for comparison table
        grade_order = list(config.get('grade_boundaries', {}).keys()) + ["F"]
        
        orig_counts = final_df['Original Grade'].value_counts().reindex(grade_order, fill_value=0)
        new_counts = final_df['Grade'].value_counts().reindex(grade_order, fill_value=0)
        
        comp_df = pd.DataFrame({
            'Grade': grade_order,
            'Original': orig_counts.values,
            'Rounded': new_counts.values
        })
        comp_df['Change'] = comp_df['Rounded'] - comp_df['Original']
        
        # Only show grades that have students
        comp_df = comp_df[(comp_df['Original'] > 0) | (comp_df['Rounded'] > 0)]
        
        col_b.write("**Grade Distribution Comparison**")
        col_b.dataframe(comp_df, hide_index=True, use_container_width=True)
        
        if improved_count > 0:
            with st.expander("View students with improved grades"):
                st.write(improved_students[['Student ID', 'Name', 'Original Final Score', 'Final Score', 'Original Grade', 'Grade']])
    else:
        st.info("Original grade data not available for comparison.")
# ------------------------------------

display_df = final_df.copy()
rename_dict = {}
weights = config.get('weights', {})

for col in display_df.columns:
    if col in max_scores:
        rename_dict[col] = f"{col}\n({max_scores[col]:g} pts)"
    elif col.endswith('_pct'):
        category = col.replace('_pct', '')
        weight = weights.get(category, 0)
        if use_weighted_scores:
            max_cat_pts = weight * 100
            rename_dict[col] = f"{col}\n({max_cat_pts:g} pts)"
        else:
            rename_dict[col] = f"{col}\n(100%)"
    elif col == 'Final Score':
        rename_dict[col] = f"{col}\n(100 pts)" if use_weighted_scores else f"{col}\n(100%)"
    elif col == 'Coursework Total':
        # Automatically calculate the total weight for non-exam coursework
        cw_weight = sum(w for c, w in weights.items() if c.lower() not in ['midterm', 'final'])
        if use_weighted_scores:
            max_cw_pts = cw_weight * 100
            rename_dict[col] = f"{col}\n({max_cw_pts:g} pts)"
        else:
            rename_dict[col] = f"{col}\n(100%)"

display_df.rename(columns=rename_dict, inplace=True)
st.dataframe(display_df, use_container_width=True)

import altair as alt

st.subheader("Grade Distribution")
# Reversing the order so 'F' is on the left and 'A' is on the right
# The grade_boundaries in config.yaml are ordered highest to lowest ('A', 'B+', ...)
grade_order = list(config.get('grade_boundaries', {}).keys()) + ["F"] # ['A', 'B+', ..., 'F']
grade_order.reverse() # Now it is ['F', 'D', 'D+', ...]

grade_counts = final_df['Grade'].value_counts().reindex(grade_order, fill_value=0).reset_index()
grade_counts.columns = ['Grade', 'Count']

chart = alt.Chart(grade_counts).mark_bar().encode(
    x=alt.X('Grade', sort=grade_order),
    y='Count'
)
st.altair_chart(chart, use_container_width=True)

# Export
st.sidebar.markdown("---")
st.sidebar.subheader("Export")
if st.sidebar.button("Export Final Report to CSV"):
    report_dir = course_path / "reports"
    report_dir.mkdir(exist_ok=True)
    
    # Export full final grades (using the display DataFrame so headers have max points)
    report_path = report_dir / "final_grades.csv"
    display_df.to_csv(report_path, index=False)
    
    # Export copy-friendly files
    weights = config.get('weights', {})
    data_mapping = config.get('data_mapping', {})
    copy_parts = []
    
    # Extract Coursework Total
    for col in display_df.columns:
        if col.startswith('Coursework Total'):
            part_df = display_df[['Student ID', col]].copy()
            # E.g. "Coursework Total\n(30 pts)" -> "Coursework Total (30 pts)"
            part_df.columns = ['Student ID', col.replace('\n', ' ')]
            copy_parts.append(part_df)
            break
            
    # Extract Exams (Midterm and Final)
    for exam in ['midterm', 'final']:
        for col in display_df.columns:
            # We must look for the _pct calculated column, not the raw score column
            if col.startswith(f"{exam}_pct"):
                part_df = display_df[['Student ID', col]].copy()
                
                # Use the mapped column name from the config (e.g., 'midterm_score', 'final_exam')
                mapped_name = data_mapping.get(exam, [exam])[0]
                max_pts = weights.get(exam, 0) * 100
                
                part_df.columns = ['Student ID', f"{mapped_name} ({max_pts:g} pts)"]
                copy_parts.append(part_df)
                break
            
    if copy_parts:
        import pandas as pd
        copy_df = pd.concat(copy_parts, axis=1)
        
        copy_path = report_dir / "copy_friendly_scores.csv"
        copy_df.to_csv(copy_path, index=False)
            
    st.sidebar.success(f"Saved reports and copy-friendly extracts to {report_dir}")
