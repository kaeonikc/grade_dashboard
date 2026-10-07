import json

from src.calculators import calculate_final_grades, validate_scores
from src.data_loader import load_config, load_course_data
from src import tui_api


def load(course):
    config = load_config(course)
    df, max_scores = load_course_data(course)
    tui_api._fill_default_max_scores(config, max_scores)
    return config, df, max_scores


def test_absent_counts_as_zero_and_is_reported(course):
    config, df, max_scores = load(course)
    assert sorted(df.attrs["absences"]) == [("69000002", "midterm_mcq"), ("69000003", "final_exam")]
    assert df.attrs["invalid_cells"] == [("69000003", "midterm_mcq", "abs")]
    final = calculate_final_grades(df, config, max_scores)
    row = final.set_index("Student ID").loc["69000002"]
    assert row["Midterm Total"] == 0
    warnings = validate_scores(df, config, max_scores)
    assert any("'abs'" in w and "69000003" in w for w in warnings)
    assert not any("ขส" in w and "69000002" in w and "not a score" in w for w in warnings)


def test_tui_json_shows_absent_cells(course):
    data = tui_api.get_course_data(course)
    assert data["status"] == "success", data.get("traceback")
    rows = {r["Student ID"]: r for r in data["raw_scores"]}
    assert rows["69000002"]["midterm_mcq"] == "ขส"
    assert {(a["student_id"], a["column"]) for a in data["absences"]} == {
        ("69000002", "midterm_mcq"), ("69000003", "final_exam")}
    json.dumps(data)  # serialisable for the Rust side


def test_opening_twice_does_not_rewrite_files(course):
    tui_api.get_course_data(course)  # may sync totals once
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (course / "data").glob("*.csv")}
    tui_api.get_course_data(course)
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (course / "data").glob("*.csv")}
    assert before == after


def test_totals_sync_only_touches_total_cells(course):
    mid = next((course / "data").glob("*_midterm.csv"))
    original = mid.read_bytes()
    tui_api.get_course_data(course)
    new = mid.read_bytes()
    assert new.startswith(b"\xef\xbb\xbf") and b"\r\n" in new  # BOM and CRLF kept
    # every non-total cell is byte-identical
    strip = lambda b: [line.rsplit(",", 1)[0] for line in b.decode("utf-8-sig").split("\r\n")]
    assert strip(original) == strip(new)


def test_cell_edit_keeps_other_cells(course):
    mid = next((course / "data").glob("*_midterm.csv"))
    tui_api.get_course_data(course)
    before = mid.read_bytes().decode("utf-8-sig").split("\r\n")
    res = tui_api.update_student_score(course, "69000001", "midterm_showsol", "4")
    assert res["status"] == "success", res
    after = mid.read_bytes().decode("utf-8-sig").split("\r\n")
    assert after[1].split(",")[3] == "4"
    assert before[2:] == after[2:]
    res = tui_api.update_student_score(course, "69000003", "midterm_mcq", "ขส")
    assert res["status"] == "success"
    assert "69000003,นาย ค  สาม,ขส," in mid.read_bytes().decode("utf-8-sig")
