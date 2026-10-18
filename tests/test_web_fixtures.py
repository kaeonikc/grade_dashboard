"""Fixture integrity for grade_web (web/SPEC.md "Fixtures"): fake data only, UTF-8, totals already current."""
import csv
import io
import json
import shutil

import pytest

from src import tui_api
from webtools import FIXTURES, tree_sha

COURSES = ["9_ฟิสิกส์จำลอง_grading", "9_กลศาสตร์ทดลอง_grading", "9_ไฟฟ้าจำลอง_grading", "9_ดาราศาสตร์จำลอง_grading"]
SENTINELS = {"full score", "max", "max score", "full"}


def all_files():
    return [p for p in sorted(FIXTURES.rglob("*")) if p.is_file()]


def test_every_course_fixture_exists():
    for name in COURSES:
        assert (FIXTURES / name / "course_info").is_dir(), name
        assert list((FIXTURES / name / "data").glob("*.csv")), name


def test_every_file_is_strict_utf8():
    for p in all_files():
        p.read_bytes().decode("utf-8")  # raises on anything else


def test_no_history_xlsx_or_real_cohort_ids():
    for p in all_files():
        rel = p.relative_to(FIXTURES).as_posix()
        assert "history/" not in rel + "/", rel
        assert p.suffix.lower() not in (".xlsx", ".xls"), rel
        assert b"6920" not in p.read_bytes(), f"{rel} holds a 6920… (real-looking cohort) number"


def test_every_student_id_starts_99():
    for p in all_files():
        if p.suffix == ".csv":
            rows = list(csv.reader(io.StringIO(p.read_bytes().decode("utf-8-sig"), newline="")))
            i = [h.strip() for h in rows[0]].index("Student ID")
            for r in rows[1:]:
                sid = r[i].strip()
                if sid and sid.lower() not in SENTINELS:
                    assert sid.startswith("99") and sid.isdigit() and len(sid) in (10, 11), (p.name, sid)
        elif p.suffix == ".jsonl":
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if "student_id" in o:
                    assert str(o["student_id"]).startswith("99"), (p.name, o["student_id"])


@pytest.mark.parametrize("name", COURSES)
def test_loading_a_copy_changes_no_data_byte(tmp_path, name):
    """grade-tui writes totals on open: the fixture's stored totals must already follow the total rule."""
    c = tmp_path / name
    shutil.copytree(FIXTURES / name, c)
    before = tree_sha(c / "data")
    r = tui_api.get_course_data(c)
    assert r["status"] == "success", r.get("message")
    assert tree_sha(c / "data") == before
