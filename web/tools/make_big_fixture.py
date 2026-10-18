"""
Writes a synthetic 300-student x 80-column course for the S2.5/S8.9 payload proxy and the manual speed checks.

    python3 web/tools/make_big_fixture.py [--out DIR]   (default web/out/, git-ignored)

Seeded, so every run writes the same bytes. Fake data only: invented Thai-looking names, IDs starting 99.
Every total cell already follows the total rule (attendance: attendance.att_total), so loading it changes nothing.
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.attendance import att_total, fmt_total  # noqa: E402
from src.csvio import fmt_value  # noqa: E402

FOLDER = "9_ใหญ่จำลอง_grading"
PREFIX = "9_ใหญ่จำลอง"
STUDENTS = 300
COUNTS = {"attendance": 15, "homework": 20, "lab": 25, "quiz": 18, "midterm": 1, "final": 1}
WEIGHTS = {"attendance": 0.1, "homework": 0.2, "lab": 0.15, "quiz": 0.15, "midterm": 0.2, "final": 0.2}
FIRST = ["สมมติ", "ทดลอง", "ตัวอย่าง", "จำลอง", "สมสม", "ใจดี", "มีชื่อ", "ลองดู"]
LAST = ["ทดสอบ", "สมมุติ", "ใจเย็น", "ว่างเปล่า", "ครบชุด", "ตัวอย่าง", "ลองใจ", "นามสกุล"]


def columns(cat: str) -> list[str]:
    if cat == "attendance":
        first = date(2027, 1, 13)
        return [f"{d.day} {d:%b %Y}" for d in (first + timedelta(weeks=i) for i in range(COUNTS[cat]))]
    if cat in ("midterm", "final"):
        return [f"{cat}_exam"]
    return [f"{cat}{i}" for i in range(1, COUNTS[cat] + 1)]


def header(cat: str, col: str) -> str:
    return col if cat in ("attendance", "lab") else f"{col} (10pts)"  # lab: built-in default 10, bare header


def config_text() -> str:
    lines = ["course_id: BIG", "course_name: ใหญ่จำลอง", "term: 2027_S1", "term_start_date: 2027-01-13",
             "weights: {" + ", ".join(f"{c}: {w}" for c, w in WEIGHTS.items()) + "}", "data_mapping:"]
    for cat in COUNTS:
        cols = columns(cat)
        lines.append(f"  {cat}: [" + ", ".join(c if cat in ("attendance", "lab") else f"{c}: 10" for c in cols) + "]")
    lines += ["grade_boundaries: {A: 80, B+: 75, B: 70, C+: 65, C: 60, D+: 55, D: 50}",
              "rules: {drop_lowest_homework: true}"]
    return "\n".join(lines) + "\n"


def cell(rng: random.Random, cat: str) -> str:
    if cat == "attendance":
        return rng.choice(["P", "P", "P", "L", "A", "X", "EA", ""])
    if rng.random() < 0.05:
        return ""
    return fmt_value(round(rng.uniform(0, 10), 1))


def write(out: Path) -> Path:
    rng = random.Random(20270113)
    course = out / FOLDER
    (course / "course_info").mkdir(parents=True, exist_ok=True)
    (course / "data").mkdir(exist_ok=True)
    (course / "course_info" / f"{PREFIX}_config.yaml").write_text(config_text(), encoding="utf-8")
    students = [(f"99{10000000 + i}", f"{rng.choice(['นาย', 'นางสาว'])}{rng.choice(FIRST)} {rng.choice(LAST)}")
                for i in range(STUDENTS)]
    roster = ["Student ID,Name,Class Group"] + [f"{sid},{name},SEC{1 + i % 2}" for i, (sid, name) in
                                                enumerate(students)]
    (course / "course_info" / f"{PREFIX}_student_info.csv").write_text("\n".join(roster) + "\n", encoding="utf-8")
    for cat in COUNTS:
        cols = columns(cat)
        pts = len(cols) if cat == "attendance" else 10 * len(cols)
        lines = [",".join(["Student ID", "Name"] + [header(cat, c) for c in cols] + [f"total ({pts}pts)"])]
        for sid, name in students:
            cells = [cell(rng, cat) for _ in cols]
            if cat == "attendance":
                total = fmt_total(att_total(cells))
            else:
                total = fmt_value(round(sum(float(c) for c in cells if c), 2))
            lines.append(",".join([sid, name] + cells + [total]))
        (course / "data" / f"{PREFIX}_{cat}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return course


def main() -> int:
    ap = argparse.ArgumentParser(description="Write a synthetic 300-student x 80-column course (fake data).")
    ap.add_argument("--out", default=str(ROOT / "web" / "out"), help="folder to write into (default web/out/)")
    args = ap.parse_args()
    print(f"  ✍️  {write(Path(args.out))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
