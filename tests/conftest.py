import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PREFIX = "2026_S1_Test_SEC_51"
CONFIG = """course_id: PHYS1120
course_name: Test
term: 2026_S1
sec_num: '51'
weights:
  homework: 0.3
  midterm: 0.3
  final: 0.4
data_mapping:
  homework:
  - hw1
  midterm:
  - midterm_mcq: 35
  - midterm_showsol: 5
  final:
  - final_exam
grade_boundaries:
  A: 80
  B: 70
  C: 60
  D: 50
"""


def write(path: Path, text: str, bom=False, crlf=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if crlf:
        text = text.replace("\n", "\r\n")
    data = text.encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


@pytest.fixture
def course(tmp_path) -> Path:
    """A small grade_dashboard course folder in the real on-disk format."""
    c = tmp_path / f"{PREFIX}_grading"
    write(c / "course_info" / f"{PREFIX}_config.yaml", CONFIG)
    write(c / "course_info" / f"{PREFIX}_student_info.csv",
          "Student ID,Name,Class Group\n"
          "69000001,นาย ก  หนึ่ง,G1\n69000002,นาย ข  สอง,G1\n69000003,นาย ค  สาม,G1\n")
    write(c / "data" / f"{PREFIX}_homework.csv",
          "Student ID,Name,hw1 (30pts),total (30pts)\n"
          "69000001,นาย ก  หนึ่ง,30,30.0\n69000002,นาย ข  สอง,15,15.0\n69000003,นาย ค  สาม,,0.0\n")
    write(c / "data" / f"{PREFIX}_midterm.csv",
          "Student ID,Name,midterm_mcq (35pts),midterm_showsol (5pts),total (40pts)\n"
          "69000001,นาย ก  หนึ่ง,35,5,40.0\n69000002,นาย ข  สอง,ขส,,0.0\n69000003,นาย ค  สาม,abs,2,2.0\n",
          bom=True, crlf=True)
    write(c / "data" / f"{PREFIX}_final.csv",
          "Student ID,Name,final_exam (40pts),total (40pts)\n"
          "69000001,นาย ก  หนึ่ง,40,40.0\n69000002,นาย ข  สอง,20,20.0\n69000003,นาย ค  สาม,ขส,0.0\n")
    return c
