import subprocess
import sys

from src import history, tui_api

GRADER = [sys.executable, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "grader.py")]


def test_snapshot_and_restore_are_byte_identical(course):
    mid = next((course / "data").glob("*_midterm.csv"))
    original = mid.read_bytes()
    eid = history.snapshot(course, [mid], "exam", "scores", note="t", cells=3)
    mid.write_bytes(b"broken")
    assert history.restore(course, eid) == [f"data/{mid.name}"]
    assert mid.read_bytes() == original
    entries = history.list_entries(course)
    assert [e["action"] for e in entries] == ["scores", "undo"]
    assert entries[1]["undoes"] == eid


def test_latest_undoable_skips_totals_and_undone(course):
    mid = next((course / "data").glob("*_midterm.csv"))
    a = history.snapshot(course, [mid], "exam", "scores")
    history.snapshot(course, [mid], "grade-tui", "totals")
    assert history.latest_undoable(course)["id"] == a
    history.restore(course, a)
    assert history.latest_undoable(course) is None


def test_grader_undo_restores_last_tui_edit(course):
    tui_api.get_course_data(course)
    fin = next((course / "data").glob("*_final.csv"))
    before = fin.read_bytes()
    assert tui_api.update_student_score(course, "69000002", "final_exam", "33")["status"] == "success"
    assert fin.read_bytes() != before
    out = subprocess.run(GRADER + ["undo", "--course", str(course), "--yes"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert fin.read_bytes() == before
    out = subprocess.run(GRADER + ["history", "--course", str(course)], capture_output=True, text=True)
    assert "(undone)" in out.stdout


def test_undo_without_terminal_asks_and_does_nothing(course):
    fin = next((course / "data").glob("*_final.csv"))
    history.snapshot(course, [fin], "exam", "scores")
    fin.write_bytes(b"changed")
    out = subprocess.run(GRADER + ["undo", "--course", str(course)], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL)
    assert "Not restored" in out.stdout
    assert fin.read_bytes() == b"changed"
