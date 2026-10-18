"""Golden parity (S12) from the Python side: drift check, hazard coverage, S4.1 literals, S2.5 payload proxy."""
import json
import shutil
import subprocess
import sys

from src import tui_api
from webtools import F1, FIXTURES, ROOT

GOLDEN = ROOT / "web" / "tests" / "golden"
F2, F3, F4 = "9_กลศาสตร์ทดลอง_grading", "9_ไฟฟ้าจำลอง_grading", "9_ดาราศาสตร์จำลอง_grading"


def golden(name):
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


def student(g, sid, variant=None):
    rows = g["expected"] if variant is None else next(v for v in g["variants"] if v["name"] == variant)["expected"]
    return next(r for r in rows if r["student_id"] == sid)


def test_golden_files_match_grade_tui():
    r = subprocess.run([sys.executable, str(ROOT / "web" / "tools" / "make_golden.py"), "--check"], cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    for name in (F1, F2, F3, F4, "csv_rows", "canonical"):
        assert (GOLDEN / f"{name}.json").is_file(), name


def test_ac12_2_fixture_set_covers_hazards():
    g1, g2, g3, g4 = golden(F1), golden(F2), golden(F3), golden(F4)
    # drop_lowest on (F1, F3) / off (F2)
    assert g1["course"]["rules"]["drop_lowest_homework"] is True
    assert g3["course"]["rules"]["drop_lowest_homework"] is True
    assert g2["course"]["rules"]["drop_lowest_homework"] is False
    # total_pts raises homework's possible max: 4.5 / 50 x 20, not 4.5 / 5 x 20
    assert g3["course"]["total_pts"]["homework"] == 50
    assert student(g3, "9900000201")["pct"]["homework"] == 1.8
    # pts_each, built-in lab default, bare headers; header overrides config
    ms = g3["course"]["max_scores"]
    assert {str(i): ms[str(i)] for i in range(1, 13)} == {str(i): (20 if i == 5 else 10) for i in range(1, 13)}
    assert (ms["q1"], ms["q2"], ms["q3"], ms["q4"]) == (4, 4, 4, 6)
    assert ms["hw1"] == 15
    # no points anywhere: course.json leaves them out (the JS fills 5, 5, 2.5, 2.5 and 100)
    for col in ("p1", "p2", "hw2", "hw3", "x1"):
        assert col not in ms, col
    # attendance auto-detected
    assert g3["course"]["data_mapping"]["attendance"] == ["a1", "a2", "a3", "a4"]
    # x.xx5 rounding (numpy half-to-even), ceiling just above a whole number
    assert student(g2, "9900000103")["pct"]["project"] == 0.62
    s104 = student(g2, "9900000104")
    assert (s104["coursework_total"], s104["pct"]["midterm"], s104["pct"]["final"]) == (7, 25, 22)
    # boundary 80 -> A, 79 -> B+
    assert (student(g2, "9900000101")["final_score"], student(g2, "9900000101")["grade"]) == (80, "A")
    assert (student(g2, "9900000102")["final_score"], student(g2, "9900000102")["grade"]) == (79, "B+")
    # weights not summing to 1.0; category with weight but no columns
    assert abs(sum(g2["course"]["weights"].values()) - 1.05) < 1e-9
    assert student(g3, "9900000201")["pct"]["participation"] == 0
    # >= 9 columns in one category; 11-digit ID kept as text; roster-only and file-only students; sentinel row
    assert len(g3["course"]["data_mapping"]["lab"]) == 12
    assert "99000002061" in [r["student_id"] for r in g3["expected"]]
    ids2 = [r["student_id"] for r in g2["expected"]]
    assert "9900000108" in ids2 and "9900000109" in ids2
    assert [r["student_id"] for r in g4["expected"]] == ["9900000301", "9900000302", "9900000303"]
    assert (g4["course"]["max_scores"]["quiz1"], g4["course"]["max_scores"]["quiz2"]) == (10, 5)
    # names exactly as written (comma, doubled quotes)
    names2 = {r["student_id"]: r["name"] for r in g2["expected"]}
    assert names2["9900000106"] == "นายสมมติ, ทดสอบหก" and names2["9900000107"] == 'นางสาว "ฝน" ตัวอย่าง'
    # every variant of variants.json is in the golden files
    variants = json.loads((FIXTURES / "variants.json").read_text(encoding="utf-8"))
    for v in variants:
        assert any(x["name"] == v["name"] for x in golden(v["fixture"])["variants"]), v["name"]


def test_ac4_1_detail_values_from_grade_tui(tmp_path):
    c = tmp_path / F1
    shutil.copytree(FIXTURES / F1, c)
    r = tui_api.apply_edits(c, [{"student_id": "9900000001", "column": "hw2", "value": "9", "original": ""},
                                {"student_id": "9900000001", "column": "20 Jan 2027", "value": "P", "original": ""}])
    assert r["status"] == "success" and r["saved"] == 2, r
    d = tui_api.get_course_data(c)
    s = next(x for x in d["student_grades"] if x["Student ID"] == "9900000001")
    got = (s["attendance_pct"], s["homework_pct"], s["Coursework Total"], s["midterm_pct"], s["final_pct"],
           s["Final Score"], s["Grade"])
    assert got == (9.33, 17, 27, 21, 0, 48, "F")
    # the golden variant the node test runs says the same
    v = student(golden(F1), "9900000001", "s4_1_detail")
    assert (v["pct"]["attendance"], v["pct"]["homework"], v["coursework_total"], v["pct"]["midterm"],
            v["pct"]["final"], v["final_score"], v["grade"]) == got
    v2 = student(golden(F1), "9900000001", "s4_2_typed_final")
    assert (v2["pct"]["final"], v2["final_score"], v2["grade"]) == (28, 76, "B+")


def test_ac2_5_big_course_payload_within_budget(tmp_path):
    out = tmp_path / "big"
    r = subprocess.run([sys.executable, str(ROOT / "web" / "tools" / "make_big_fixture.py"), "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    course = out if (out / "course_info").is_dir() else next(p.parent for p in out.glob("*/course_info"))
    from src.webpush import build_course_json
    cj = build_course_json(course)
    if isinstance(cj, (str, bytes)):
        cj = json.loads(cj)
    assert len([c for c in cj["columns"]]) >= 80
    roster = next((course / "course_info").glob("*_student_info.csv"))
    n_students = len([l for l in roster.read_text(encoding="utf-8").splitlines()[1:] if l.strip()])
    assert n_students >= 300
    assert all(l.split(",")[0].startswith("99") for l in roster.read_text(encoding="utf-8").splitlines()[1:] if l)
    size = len(json.dumps(cj, ensure_ascii=False).encode("utf-8")) + roster.stat().st_size
    size += sum((course / f).stat().st_size for f in cj["files"])
    assert size <= 500 * 1024, size
