#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

# Ensure src module can be imported, even if run from a softlink
script_path = Path(__file__).resolve()
sys.path.insert(0, str(script_path.parent))

from src.data_loader import load_config, load_course_data
from src.calculators import calculate_final_grades

def init_course(course_name: str, term_name: str):
    folder_name = f"{term_name}_{course_name}"
    base_dir = Path(folder_name)
    data_dir = base_dir / "data"
    reports_dir = base_dir / "reports"
    
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    config_path = base_dir / "config.yaml"
    if not config_path.exists():
        with open(config_path, "w") as f:
            f.write(f"""course: "{course_name}"
term: "{term_name}"

weights:
  homework: 0.20
  midterm: 0.30
  final: 0.50

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

def run_dashboard():
    dashboard_path = script_path.parent / "src" / "dashboard.py"
    print(f"💡 Starting dashboard... (Running: streamlit run {dashboard_path.name})")
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(dashboard_path.resolve())]))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🎓 Grading System Dashboard & Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    parser_init = subparsers.add_parser("init", help="Initialize a new course grading directory")
    parser_init.add_argument("--course", required=True, help="Course short name (e.g. 'GR2')")
    parser_init.add_argument("--term", required=True, help="The term for the course (e.g. '2026_S2')")

    # Dashboard command
    parser_dashboard = subparsers.add_parser("dashboard", help="Launch the Streamlit dashboard")

    args = parser.parse_args()

    if args.command == "init":
        init_course(args.course, args.term)
    elif args.command == "dashboard":
        run_dashboard()
    else:
        # Default behavior: show help
        parser.print_help()
        sys.exit(1)
