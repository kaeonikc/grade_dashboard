import io
import subprocess
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.rule import Rule
from rich.text import Text
from rich import box

script_path = Path(__file__).resolve()
sys.path.insert(0, str(script_path.parent.parent))

from src.data_loader import load_config, load_course_data
from src.calculators import calculate_final_grades, validate_scores

console = Console()

# │ between columns, ─┼ under header, no outer border
_DIVIDER_BOX = box.Box("    \n  │ \n ─┼ \n  │ \n    \n    \n  │ \n    \n")


def find_courses() -> dict:
    current_dir = Path(".")
    courses_dir = current_dir / "courses"
    potential = []
    potential.extend([d for d in current_dir.iterdir() if d.is_dir()])
    if courses_dir.is_dir():
        potential.extend([d for d in courses_dir.iterdir() if d.is_dir()])
        
    course_map = {}
    for d in potential:
        info_dir = d / "course_info"
        if info_dir.is_dir():
            config_files = [f for f in info_dir.iterdir() if f.is_file() and f.name.endswith("_config.yaml")]
            if config_files:
                course_map[d.name] = d
    return course_map


def select_course(course_map: dict) -> tuple[str, Path]:
    names = sorted(course_map.keys())
    console.print("\n[bold]Available Courses:[/bold]")
    for i, name in enumerate(names, 1):
        console.print(f"  [cyan]{i}.[/cyan] {name}")
    while True:
        choice = Prompt.ask("Select course", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(names):
                return names[idx], course_map[names[idx]]
        except ValueError:
            if choice in course_map:
                return choice, course_map[choice]
        console.print(f"[red]Invalid. Enter a number 1–{len(names)} or a course name.[/red]")


def show_warnings(warnings: list) -> None:
    if not warnings:
        return
    lines = "\n".join(f"  • {w}" for w in warnings)
    console.print(Panel(
        Text(lines, style="yellow"),
        title=f"[bold yellow]⚠  {len(warnings)} Score Validation Warning(s)[/bold yellow]",
        border_style="yellow",
    ))


def show_metrics(final_df: pd.DataFrame) -> None:
    tbl = Table(box=box.ROUNDED, show_header=True)
    tbl.add_column("Total Students", style="cyan", justify="center", min_width=16)
    tbl.add_column("Average Score", style="green", justify="center", min_width=16)
    tbl.add_column("Highest Score", style="bold green", justify="center", min_width=16)
    avg = final_df["Final Score"].mean()
    high = final_df["Final Score"].max()
    tbl.add_row(str(len(final_df)), f"{avg:.2f}%", f"{high:.2f}%")
    console.print(tbl)


def show_roundup_summary(final_df: pd.DataFrame, config: dict) -> None:
    if "Original Grade" not in final_df.columns:
        return

    grade_order = list(config.get("grade_boundaries", {}).keys()) + ["F"]
    orig_counts = final_df["Original Grade"].value_counts().reindex(grade_order, fill_value=0)
    new_counts = final_df["Grade"].value_counts().reindex(grade_order, fill_value=0)

    dist_tbl = Table(box=box.SIMPLE, show_header=True)
    dist_tbl.add_column("Grade", style="bold")
    dist_tbl.add_column("Original", justify="right")
    dist_tbl.add_column("Rounded", justify="right")
    dist_tbl.add_column("Change", justify="right")

    for grade in grade_order:
        orig = int(orig_counts[grade])
        rounded = int(new_counts[grade])
        if orig == 0 and rounded == 0:
            continue
        delta = rounded - orig
        change_text = Text(f"+{delta}" if delta > 0 else str(delta))
        if delta > 0:
            change_text.stylize("green")
        elif delta < 0:
            change_text.stylize("red")
        dist_tbl.add_row(grade, str(orig), str(rounded), change_text)

    improved = final_df[final_df["Grade"] != final_df["Original Grade"]]
    improved_count = len(improved)
    summary_line = Text()
    summary_line.append("Grades improved by rounding: ")
    summary_line.append(str(improved_count), style="bold green" if improved_count > 0 else "dim")

    console.print(Panel(
        Group(summary_line, dist_tbl),
        title="[bold]📊 Round-up Score Grade Summary[/bold]",
        border_style="blue",
    ))

    if improved_count > 0 and Confirm.ask("Show students with improved grades?", default=False):
        imp_tbl = Table(box=box.SIMPLE, show_header=True)
        for col in ["Student ID", "Name", "Original Final Score", "Final Score", "Original Grade", "Grade"]:
            imp_tbl.add_column(col)
        for _, row in improved.iterrows():
            imp_tbl.add_row(
                str(row.get("Student ID", "")),
                str(row.get("Name", "")),
                str(row.get("Original Final Score", "")),
                str(row.get("Final Score", "")),
                str(row.get("Original Grade", "")),
                str(row.get("Grade", "")),
            )
        console.print(imp_tbl)


def _col_headers(final_df: pd.DataFrame, max_scores: dict, config: dict, use_weighted: bool) -> dict:
    """Maps original column names to two-line display headers (name / annotation)."""
    weights = config.get("weights", {})
    rename = {}
    for col in final_df.columns:
        if col in max_scores:
            rename[col] = f"{col}\n({max_scores[col]:g}pts)"
        elif col.endswith("_pct"):
            category = col.replace("_pct", "")
            weight = weights.get(category, 0)
            rename[col] = f"{category.title()} Grade\n({weight * 100:g}pts)" if use_weighted else f"{category.title()} Grade\n(100%)"
        elif col == "Final Score":
            rename[col] = "Final Score\n(100pts)" if use_weighted else "Final Score\n(100%)"
        elif col == "Coursework Total":
            cw_weight = sum(w for c, w in weights.items() if c.lower() not in ["midterm", "final"])
            rename[col] = f"Coursework Total\n({cw_weight * 100:g}pts)" if use_weighted else f"Coursework Total\n(100%)"
    return rename


def _fmt(v) -> str:
    if not isinstance(v, str) and pd.isna(v):
        return ""
    return str(v)


def _print_wide(renderable) -> None:
    """Render at full width (500 cols) and display in 'less -SR' for horizontal scrolling."""
    buf = io.StringIO()
    wide = Console(file=buf, width=500, force_terminal=True, color_system="256")
    wide.print(renderable)
    content = buf.getvalue()
    try:
        proc = subprocess.Popen(["less", "-SR"], stdin=subprocess.PIPE)
        proc.communicate(input=content.encode("utf-8", errors="replace"))
    except (FileNotFoundError, BrokenPipeError):
        console.print(renderable)


def show_student_table(final_df: pd.DataFrame, max_scores: dict, config: dict, use_weighted: bool) -> None:
    rename = _col_headers(final_df, max_scores, config, use_weighted)

    data_mapping = config.get("data_mapping", {})
    raw_assignment_cols = {col for cols in data_mapping.values() for col in cols}

    # Summary: calculated columns only — exclude raw assignment scores and Original* audit columns
    exclude = raw_assignment_cols | {"Original Final Score", "Original Grade"}
    summary_cols = [c for c in final_df.columns if c not in exclude]

    summary_tbl = Table(box=_DIVIDER_BOX, show_header=True, title="[bold]Student Grades — Summary[/bold]")
    for col in summary_cols:
        summary_tbl.add_column(rename.get(col, col))
    for _, row in final_df[summary_cols].iterrows():
        summary_tbl.add_row(*[_fmt(v) for v in row])
    console.print(summary_tbl)

    # Raw assignment scores — only offer if there are any mapped columns in the data
    raw_cols_present = [c for c in final_df.columns if c in raw_assignment_cols]
    if raw_cols_present and Confirm.ask("Show raw assignment scores?", default=False):
        raw_display_cols = ["Student ID", "Name"] + raw_cols_present
        raw_tbl = Table(box=_DIVIDER_BOX, show_header=True, title="[bold]Raw Assignment Scores[/bold]")
        for col in raw_display_cols:
            raw_tbl.add_column(rename.get(col, col), no_wrap=True)
        for _, row in final_df[raw_display_cols].iterrows():
            raw_tbl.add_row(*[_fmt(v) for v in row])
        console.print("[dim]← → to scroll  ·  q to exit[/dim]")
        _print_wide(raw_tbl)


def show_grade_distribution(final_df: pd.DataFrame, config: dict) -> None:
    grade_order = list(config.get("grade_boundaries", {}).keys()) + ["F"]
    counts = final_df["Grade"].value_counts()
    total = len(final_df)
    max_count = max((counts.get(g, 0) for g in grade_order), default=1)
    bar_width = 30

    console.print(Rule("[bold]Grade Distribution[/bold]"))
    for grade in reversed(grade_order):
        count = counts.get(grade, 0)
        filled = int(bar_width * count / max_count) if max_count > 0 else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = count / total * 100 if total > 0 else 0
        console.print(f"  [bold]{grade:<4}[/bold] [blue]{bar}[/blue]  {count} ({pct:.1f}%)")
    console.print()


def export_reports(final_df: pd.DataFrame, course_path: Path, config: dict, max_scores: dict, use_weighted: bool) -> None:
    weights = config.get("weights", {})
    data_mapping = config.get("data_mapping", {})
    rename = {k: v.replace("\n", " ") for k, v in _col_headers(final_df, max_scores, config, use_weighted).items()}
    display_df = final_df.rename(columns=rename)

    report_dir = course_path / "reports"
    report_dir.mkdir(exist_ok=True)
    display_df.to_csv(report_dir / "final_grades.csv", index=False)

    copy_parts = []
    if "Coursework Total" in final_df.columns:
        disp_name = rename.get("Coursework Total", "Coursework Total")
        if disp_name in display_df.columns:
            copy_parts.append(display_df[["Student ID", disp_name]].copy())

    for exam in ["midterm", "final"]:
        pct_col = f"{exam}_pct"
        if pct_col in final_df.columns:
            disp_name = rename.get(pct_col, pct_col)
            if disp_name in display_df.columns:
                part = display_df[["Student ID", disp_name]].copy()
                mapped_name = data_mapping.get(exam, [exam])[0]
                max_pts = weights.get(exam, 0) * 100
                part.columns = ["Student ID", f"{mapped_name} ({max_pts:g}pts)"]
                copy_parts.append(part)

    if copy_parts:
        for i in range(1, len(copy_parts)):
            copy_parts[i] = copy_parts[i].drop(columns=["Student ID"])
        copy_df = pd.concat(copy_parts, axis=1)
        copy_df.to_csv(report_dir / "copy_friendly_scores.csv", index=False)

    console.print(f"[green]✓ Reports saved to {report_dir}[/green]")

def update_database_totals(course_path: Path, final_df: pd.DataFrame, data_mapping: dict, max_scores: dict):
    data_dir = course_path / "data"
    if not data_dir.is_dir():
        return
    for category, columns in data_mapping.items():
        if category == 'attendance':
            csv_files = [f for f in data_dir.iterdir() if f.is_file() and f.name.endswith("attendance.csv")]
            csv_path = csv_files[0] if csv_files else None
        else:
            csv_path = data_dir / f"{category}.csv"
            
        if csv_path and csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                df.columns = df.columns.astype(str).str.strip()
                
                # Check for Student ID column
                if 'Student ID' not in df.columns:
                    continue
                    
                df['Student ID'] = df['Student ID'].astype(str).str.strip()
                
                # Determine total points
                cat_max_scores = {col: max_scores.get(col, 100.0) for col in columns}
                total_pts = sum(cat_max_scores.values())
                total_pts_str = str(int(total_pts)) if total_pts.is_integer() else str(total_pts)
                total_header = f"total ({total_pts_str}pts)"
                
                # Find if any existing total column exists
                existing_total_col = None
                for col in df.columns:
                    if str(col).lower().strip().startswith('total'):
                        existing_total_col = col
                        break
                        
                calc_col = f"{category.title()} Total"
                if calc_col in final_df.columns:
                    totals_map = final_df.set_index("Student ID")[calc_col].to_dict()
                    target_col = existing_total_col if existing_total_col else total_header
                    
                    # Fill the total column only for rows that are not 'Max' / sentinel rows
                    max_mask = df['Student ID'].str.lower().isin(['max', 'max score', 'full score', 'full'])
                    
                    # For student rows, map totals from final_df
                    df.loc[~max_mask, target_col] = df.loc[~max_mask, 'Student ID'].map(totals_map)
                    
                    # For Max row, put Z
                    df.loc[max_mask, target_col] = total_pts
                    
                    if target_col != total_header:
                        df.rename(columns={target_col: total_header}, inplace=True)
                        
                    # Save back
                    df.to_csv(csv_path, index=False)
            except Exception as e:
                console.print(f"[yellow]⚠️ Warning: Failed to update total in {csv_path.name}: {e}[/yellow]")

def run() -> None:
    while True:
        course_map = find_courses()
        if not course_map:
            console.print("[red]No course directories found (looking for folders with config.yaml in current dir or 'courses/').[/red]")
            sys.exit(1)

        course_name, course_path = select_course(course_map)

        try:
            config = load_config(course_path)
        except Exception as e:
            console.print(f"[red]Failed to load config: {e}[/red]")
            if not Confirm.ask("Try another course?", default=True):
                break
            continue

        raw_df, max_scores = load_course_data(course_path)
        if raw_df.empty:
            console.print(f"[yellow]No student data found in {course_path / 'data'}[/yellow]")
        else:
            show_warnings(validate_scores(raw_df, config, max_scores))
            use_weighted = Confirm.ask("Show weighted scores?", default=True)
            final_df = calculate_final_grades(raw_df, config, max_scores, use_weighted)
            
            # Automatically calculate and write totals back to the raw CSV database files
            update_database_totals(course_path, final_df, config.get("data_mapping", {}), max_scores)

            console.print()
            console.print(Rule(f"[bold]{config.get('course_name', course_name)} — {config.get('term', '')}[/bold]"))
            console.print()

            show_metrics(final_df)
            console.print()
            show_roundup_summary(final_df, config)
            console.print()
            show_student_table(final_df, max_scores, config, use_weighted)
            console.print()
            show_grade_distribution(final_df, config)

            if Confirm.ask("Export final report to CSV?", default=False):
                export_reports(final_df, course_path, config, max_scores, use_weighted)

        if not Confirm.ask("\nView another course?", default=False):
            break


if __name__ == "__main__":
    run()
