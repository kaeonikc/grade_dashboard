#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# Ensure src module can be imported, even if run from a softlink
script_path = Path(__file__).resolve()
sys.path.insert(0, str(script_path.parent))

from src.data_loader import load_config, load_course_data
from src.calculators import calculate_final_grades

def init_course(course_name: str, term_name: str, course_id: str):
    folder_name = f"{term_name}_{course_id}_grading"
    base_dir = Path(folder_name)

    if base_dir.exists():
        print(f"❌ Directory '{base_dir}' already exists. Aborting to avoid overwriting existing files.")
        sys.exit(1)

    course_info_dir = base_dir / "course_info"
    data_dir = base_dir / "data"
    reports_dir = base_dir / "reports"
    
    course_info_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    config_filename = f"{term_name}_{course_id}_config.yaml"
    config_path = course_info_dir / config_filename
    
    with open(config_path, "w") as f:
        f.write(f"""course_id: "{course_id}"
course_name: "{course_name}"
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
    from src.dashboard import run
    run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🎓 Grading System Dashboard & Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    parser_init = subparsers.add_parser("init", help="Initialize a new course grading directory")
    parser_init.add_argument("--course_name", required=True, help="Course display/short name (e.g. 'General Relativity')")
    parser_init.add_argument("--term", required=True, help="The term for the course (e.g. '2026_S2')")
    parser_init.add_argument("--course_id", required=True, help="The course ID (e.g. 'PHYS1102')")

    # Dashboard command
    parser_dashboard = subparsers.add_parser("dashboard", help="Launch the grade dashboard")

    args = parser.parse_args()

    if args.command == "init":
        init_course(args.course_name, args.term, args.course_id)
    elif args.command == "dashboard":
        run_dashboard()
    else:
        # Default behavior: show help
        parser.print_help()
        sys.exit(1)
