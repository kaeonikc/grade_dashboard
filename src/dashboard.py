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

from src.data_loader import load_config, load_course_data, get_course_file_prefix, backup_csv_before_write
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


def _fmt_pts(pts: float) -> str:
    """Bare integer when whole, else 1 decimal — matches rust_tui's pts_str formatting."""
    return str(int(pts)) if pts == int(pts) else f"{pts:.1f}"


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


def category_totals(df: pd.DataFrame, config: dict, max_scores: dict) -> dict:
    """{category: {student id: {raw, max, pct}}} for every score category (not attendance): the plain sum of the
    student's raw scores in the category's columns, the sum of their maxima, and raw/max in %."""
    out = {}
    if df is None or df.empty or "Student ID" not in df.columns:
        return out
    for cat, cols in (config.get("data_mapping") or {}).items():
        if cat == "attendance":
            continue
        present = [c for c in cols if c in df.columns]
        if not present:
            continue
        mx = float(sum(max_scores.get(c, 0.0) for c in present))
        raw = df[present].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
        out[cat] = {}
        for sid, r in zip(df["Student ID"].astype(str), raw):
            r = round(float(r), 2)
            out[cat][sid] = {"raw": r, "max": round(mx, 2), "pct": round(r / mx * 100, 1) if mx else 0.0}
    return out


def export_reports(final_df: pd.DataFrame, course_path: Path, config: dict, max_scores: dict, use_weighted: bool) -> Path:
    weights = config.get("weights", {})
    rename = {k: v.replace("\n", " ") for k, v in _col_headers(final_df, max_scores, config, use_weighted).items()}
    display_df = final_df.rename(columns=rename)

    report_dir = course_path / "reports"
    report_dir.mkdir(exist_ok=True)
    prefix = get_course_file_prefix(course_path)
    # Raw total, maximum and percentage per category (not weighted), e.g. final_raw 35, final_max 45, final_pct 77.8.
    for cat, totals in category_totals(final_df, config, max_scores).items():
        by_sid = {sid: t for sid, t in totals.items()}
        display_df[f"{cat}_raw"] = display_df["Student ID"].astype(str).map(lambda s: by_sid.get(s, {}).get("raw"))
        display_df[f"{cat}_max"] = display_df["Student ID"].astype(str).map(lambda s: by_sid.get(s, {}).get("max"))
        display_df[f"{cat}_pct"] = display_df["Student ID"].astype(str).map(lambda s: by_sid.get(s, {}).get("pct"))

    # Which exam/score columns hold "ขส" (absent) for each student.
    absent_by_sid = {}
    for sid, col in final_df.attrs.get("absences", []):
        absent_by_sid.setdefault(sid, []).append(col)
    if absent_by_sid and "Student ID" in display_df.columns:
        display_df["absent"] = display_df["Student ID"].astype(str).map(
            lambda sid: ", ".join(absent_by_sid.get(sid, [])))
    display_df.to_csv(report_dir / f"{prefix}_final_grades.csv", index=False)

    # Mirrors rust_tui's "For Submission" tab (tab [1]): Cumulative Scores / Midterm / Final
    # blocks in that fixed order, each with its own ID column, separated by a blank spacer.
    cw_weight = sum(w for c, w in weights.items() if c.lower() not in ["midterm", "final"])
    blocks = []
    if "Coursework Total" in final_df.columns:
        blocks.append(("Cumulative Scores", "Coursework Total", cw_weight * 100))
    if "midterm_pct" in final_df.columns:
        blocks.append(("Midterm", "midterm_pct", weights.get("midterm", 0) * 100))
    if "final_pct" in final_df.columns:
        blocks.append(("Final", "final_pct", weights.get("final", 0) * 100))

    if blocks:
        copy_parts = []
        for i, (label, key, pts) in enumerate(blocks):
            if i > 0:
                copy_parts.append(pd.DataFrame({"": [""] * len(final_df)}, index=final_df.index))
            part = final_df[["Student ID", key]].copy()
            part.columns = ["Student ID", f"{label} ({_fmt_pts(pts)} pts)"]
            copy_parts.append(part)
        copy_df = pd.concat(copy_parts, axis=1)
        copy_df.to_csv(report_dir / f"{prefix}_copy_friendly_scores.csv", index=False)

    return report_dir

def update_database_totals(course_path: Path, final_df: pd.DataFrame = None, data_mapping: dict = None,
                           max_scores: dict = None):
    """
    Refreshes the `total (Npts)` column of every score file (not attendance) from its cells:
    the plain sum of the columns data_mapping lists for that category (src/sync.py). A file is
    rewritten - after a history snapshot - only when a total actually changed. The extra
    arguments are ignored; they're kept so existing callers don't break.
    """
    from src.sync import sync_course
    try:
        sync_course(Path(course_path), tool="grade-tui", action="totals")
    except Exception as e:
        console.print(f"[yellow]⚠️ Warning: Failed to update totals: {e}[/yellow]")

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
                report_dir = export_reports(final_df, course_path, config, max_scores, use_weighted)
                console.print(f"[green]✓ Reports saved to {report_dir}[/green]")

        if not Confirm.ask("\nView another course?", default=False):
            break


if __name__ == "__main__":
    run()
