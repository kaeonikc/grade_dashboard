import json
import subprocess
import sys

from src import history, tui_api
from test_attendance import att, csv_rows, ws_of  # noqa: F401  (att is a fixture)

API = [sys.executable, str(tui_api.Path(tui_api.__file__))]


def rows(course, name):
    p = next((course / "data").glob(f"*_{name}.csv"))
    return [line.split(",") for line in p.read_bytes().decode("utf-8-sig").splitlines()]


def edit(sid, col, value, original):
    return {"student_id": sid, "column": col, "value": value, "original": original}


def test_batch_across_two_files_is_one_history_entry_and_one_undo(course):
    tui_api.get_course_data(course)
    before = {p.name: p.read_bytes() for p in (course / "data").glob("*.csv")}
    n_before = len(history.list_entries(course))

    r = tui_api.apply_edits(course, [
        edit("69000002", "hw1", "20", "15"),
        edit("69000003", "hw1", "7.5", ""),
        edit("69000001", "final_exam", "38", "40"),
    ])

    assert r["status"] == "success", r
    assert r["saved"] == 3 and r["conflicts"] == []
    assert sorted(r["files"]) == ["2026_S1_Test_SEC_51_final.csv", "2026_S1_Test_SEC_51_homework.csv"]
    hw = rows(course, "homework")
    assert hw[2][2] == "20" and hw[3][2] == "7.5"
    assert hw[2][3] == "20" and hw[3][3] == "7.5"  # totals re-synced
    assert rows(course, "final")[1][2] == "38"

    edits = [e for e in history.list_entries(course)[n_before:] if e["action"] == "edit"]
    assert len(edits) == 1 and len(edits[0]["files"]) == 2 and edits[0]["cells"] == 3
    assert history.latest_undoable(course)["id"] == edits[0]["id"]
    history.restore(course, edits[0]["id"])
    assert {p.name: p.read_bytes() for p in (course / "data").glob("*.csv")} == before


def test_changed_on_disk_cell_is_skipped_and_reported(course):
    tui_api.get_course_data(course)
    r = tui_api.apply_edits(course, [
        edit("69000002", "hw1", "20", "14"),   # disk has 15
        edit("69000001", "hw1", "29", "30"),
    ])
    assert r["status"] == "success", r
    assert r["saved"] == 1
    assert r["conflicts"] == [{"student_id": "69000002", "column": "hw1", "reason": "changed", "disk_value": "15"}]
    hw = rows(course, "homework")
    assert hw[1][2] == "29" and hw[2][2] == "15"


def test_numbers_compare_by_value_and_absent_round_trips(course):
    tui_api.get_course_data(course)
    r = tui_api.apply_edits(course, [
        edit("69000001", "hw1", "ขส", "30.0"),            # disk "30"
        edit("69000002", "midterm_mcq", "31", "ขส"),
        edit("69000001", "midterm_showsol", "", "5"),
    ])
    assert r["saved"] == 3 and r["conflicts"] == [], r
    assert rows(course, "homework")[1][2] == "ขส"
    mid = rows(course, "midterm")
    assert mid[2][2] == "31" and mid[1][3] == ""


def test_unknown_column_or_student_is_reported_not_written(course):
    tui_api.get_course_data(course)
    r = tui_api.apply_edits(course, [
        edit("69000001", "no_such_col", "1", ""),
        edit("69999999", "hw1", "1", ""),
    ])
    assert r["saved"] == 0
    assert {c["reason"] for c in r["conflicts"]} == {"not found"}


def test_nothing_to_save_writes_no_history(course):
    tui_api.get_course_data(course)
    n = len(history.list_entries(course))
    r = tui_api.apply_edits(course, [])
    assert r["status"] == "success" and r["saved"] == 0
    assert len(history.list_entries(course)) == n


def test_attendance_edits_reach_csv_and_xlsx_with_totals(att):  # noqa: F811
    tui_api.get_course_data(att)
    r = tui_api.apply_edits(att, [
        edit("69000002", "29 Sep 2026", "P", ""),
        edit("69000003", "29 Sep 2026", "L", ""),
    ])
    assert r["saved"] == 2 and r["conflicts"] == [], r
    c = csv_rows(att)
    assert c[2][6] == "P" and c[3][6] == "L" and c[2][-1] == "2.8"
    ws = ws_of(att)
    assert ws.cell(row=3, column=7).value == "P" and ws.cell(row=4, column=7).value == "L"


def test_cli_reads_edits_from_stdin(course):
    tui_api.get_course_data(course)
    payload = json.dumps({"edits": [edit("69000003", "final_exam", "11", "ขส")]})
    out = subprocess.run(API + ["apply-edits", str(course)], input=payload, capture_output=True, text=True)
    r = json.loads(out.stdout)
    assert r["status"] == "success" and r["saved"] == 1, out.stdout + out.stderr
    assert rows(course, "final")[3][2] == "11"


def test_course_data_rows_carry_class_group(course):
    data = tui_api.get_course_data(course)
    assert [r["Class Group"] for r in data["raw_scores"]] == ["G1", "G1", "G1"]


def test_raw_scores_show_cells_as_written(course):
    """Blank stays blank (not the 0 it counts as), unreadable text stays text, so the TUI's
    'original' matches the file and 'only empty cells' can find blanks."""
    data = tui_api.get_course_data(course)
    by_id = {r["Student ID"]: r for r in data["raw_scores"]}
    assert by_id["69000003"]["hw1"] == ""
    assert by_id["69000003"]["midterm_mcq"] == "abs"
    assert by_id["69000002"]["midterm_mcq"] == "ขส"
    assert by_id["69000001"]["hw1"] == 30
    assert [r["Student ID"] for r in data["raw_scores"]] == [r["Student ID"] for r in data["student_grades"]]
