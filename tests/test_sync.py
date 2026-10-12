import csv
import io

import pytest
import yaml

import grader
from src import sync, tui_api
from src.csvio import read_csv_text

# The same cases are in INTEGRATION.md and in exam_projects' contract test (total rule).
TOTAL_CASES = [
    # (cells of the mapped columns, total)
    (["30", "5"], "35"),
    (["12.5", ""], "12.5"),
    (["ขส", "ขส"], "0"),
    (["abs", "3"], "3"),
    (["", ""], "0"),
]


def rows(path):
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


def mid(course):
    return next((course / "data").glob("*_midterm.csv"))


@pytest.mark.parametrize("cells,total", TOTAL_CASES)
def test_total_rule(cells, total):
    doc = read_csv_text_from("Student ID,Name,a (35pts),b (5pts),extra (9pts),total (1pts)\n1,x,"
                             + ",".join(cells) + ",9,\n")
    header, values = sync.total_for([("a", 35.0), ("b", 5.0)], doc)
    assert header == "total (40pts)"
    assert values == {0: total}  # 'extra' isn't mapped, so it doesn't count


def read_csv_text_from(text, tmp=[]):
    import tempfile
    from pathlib import Path
    p = Path(tempfile.mkdtemp()) / "f.csv"
    p.write_text(text, encoding="utf-8")
    return read_csv_text(p)


def test_open_course_refreshes_stale_total_and_keeps_attendance(course):
    att = course / "data" / "2026_S1_Test_SEC_51_attendance.csv"
    att.write_text("Student ID,Name,a1,total (1500pts)\n69000001,x,P,5.0\n", encoding="utf-8")
    before_att = att.read_bytes()
    tui_api.get_course_data(course)
    r = rows(mid(course))
    assert r[0][-1] == "total (40pts)"
    assert [float(x[-1]) for x in r[1:]] == [40, 0, 2]  # 35+5 · ขส · abs+2 (a matching "40.0" isn't rewritten)
    assert att.read_bytes() == before_att  # attendance never touched


def test_edit_updates_total_at_once(course):
    tui_api.get_course_data(course)
    assert tui_api.update_student_score(course, "69000002", "midterm_showsol", "4")["status"] == "success"
    assert rows(mid(course))[2][-1] == "4"


def test_hand_added_column_is_proposed_then_counted(course, monkeypatch, capsys):
    tui_api.get_course_data(course)
    f = mid(course)
    r = rows(f)
    r[0].insert(4, "bonus (2pts)")
    for x in r[1:]:
        x.insert(4, "1")
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(r)
    f.write_bytes(b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))

    data = tui_api.get_course_data(course)
    assert any("bonus (2pts)" in w and "grader sync" in w for w in data["warnings"])
    assert float(rows(f)[1][-1]) == 40  # not counted yet

    grader.sync_cmd(str(course), yes=True)
    cfg = yaml.safe_load(next((course / "course_info").glob("*_config.yaml")).read_text(encoding="utf-8"))
    assert {"bonus": 2} in cfg["data_mapping"]["midterm"]
    r = rows(f)
    assert r[0][-1] == "total (42pts)" and r[1][-1] == "41"
    assert f.read_bytes().startswith(b"\xef\xbb\xbf") and b"\r\n" in f.read_bytes()
    out = capsys.readouterr().out
    assert "bonus: 2 (now counts)" in out
    # one history entry, undoable
    entries = [e for e in __import__("src.history", fromlist=["x"]).list_entries(course) if e["tool"] == "grader"]
    assert entries[-1]["action"] == "sync" and len(entries[-1]["files"]) == 2


def test_points_conflict_choice(course, monkeypatch):
    cfg = next((course / "course_info").glob("*_config.yaml"))
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("midterm_mcq: 35", "midterm_mcq: 30"), encoding="utf-8")
    ch = sync.find_changes(course)
    assert ("midterm", mid(course).name, "midterm_mcq", 35.0, 30.0) in ch.conflicts
    grader.sync_cmd(str(course), yes=True)  # --yes never decides a conflict
    assert "midterm_mcq: 30" in cfg.read_text(encoding="utf-8")
    monkeypatch.setattr(grader, "_ask", lambda q, default="": "c")  # keep the config's points
    grader.sync_cmd(str(course))
    assert rows(mid(course))[0][2] == "midterm_mcq (30pts)"
    assert rows(mid(course))[0][-1] == "total (35pts)"


def test_set_category_keeps_other_lines(tmp_path):
    p = tmp_path / "c_config.yaml"
    text = ("# my course\nweights:\n  final: 0.4  # 40 %\ndata_mapping:\n  homework: [\"hw1 (10pts)\"]  # keep\n"
            "  final:\n  - final_exam (40pts)\n# boundaries below\ngrade_boundaries:\n  A: 80\n")
    p.write_text(text, encoding="utf-8")
    out = sync.set_category(p, "final", ["final_exam (40pts)", {"bonus": 5}])
    assert "# my course" in out and "0.4  # 40 %" in out and '["hw1 (10pts)"]  # keep' in out
    assert "# boundaries below" in out
    assert yaml.safe_load(out)["data_mapping"]["final"] == ["final_exam (40pts)", {"bonus": 5}]
