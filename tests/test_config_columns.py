import csv
import io

import grader
from src import columns
from src.history import list_entries
from src.sync import find_changes


def cfg(course):
    return next((course / "course_info").glob("*_config.yaml"))


def data(course, cat):
    return next((course / "data").glob(f"*_{cat}.csv"))


def rows(path):
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


def edit_cfg(course, old, new):
    p = cfg(course)
    text = p.read_text(encoding="utf-8")
    assert old in text
    p.write_text(text.replace(old, new), encoding="utf-8")


def answers(monkeypatch, *seq):
    it = iter(seq)
    monkeypatch.setattr(grader, "_ask", lambda q, default="": next(it, default))


def update(course):
    grader.update_course(config_file=str(cfg(course)))


def test_column_removed_from_config_is_not_proposed_back(course, monkeypatch):
    grader.sync_cmd(str(course), yes=True)          # remembers the config's columns
    edit_cfg(course, "  - midterm_showsol: 5\n", "")
    ch = find_changes(course)
    assert [u.name for u in ch.removed] == ["midterm_showsol"] and ch.unmapped == []
    answers(monkeypatch, "k")
    update(course)
    assert "midterm_showsol (5pts)" in rows(data(course, "midterm"))[0]   # kept, as asked
    assert find_changes(course).removed == [] and find_changes(course).unmapped == []
    answers(monkeypatch)                            # nothing to ask any more
    grader.sync_cmd(str(course))
    assert "midterm_showsol" not in cfg(course).read_text(encoding="utf-8")


def test_removed_column_deleted_and_undone(course, monkeypatch):
    grader.sync_cmd(str(course), yes=True)
    before = data(course, "midterm").read_bytes()
    edit_cfg(course, "  - midterm_showsol: 5\n", "")
    answers(monkeypatch, "d")
    update(course)
    assert rows(data(course, "midterm"))[0] == ["Student ID", "Name", "midterm_mcq (35pts)", "total (35pts)"]
    entry = next(e for e in reversed(list_entries(course)) if e["action"] == "update-columns")
    grader.undo_course(entry["id"], course=str(course), yes=True)
    assert "midterm_showsol (5pts)" in rows(data(course, "midterm"))[0]
    del before


def test_rename_in_config_moves_the_scores(course, monkeypatch):
    grader.sync_cmd(str(course), yes=True)
    edit_cfg(course, "  - final_exam\n", "  - final_mcq: 40\n")
    answers(monkeypatch, "r")                       # one target only: no menu
    update(course)
    r = rows(data(course, "final"))
    assert r[0] == ["Student ID", "Name", "final_mcq (40pts)", "total (40pts)"]
    assert [x[2] for x in r[1:]] == ["40", "20", "ขส"]


def test_empty_removed_column_is_deleted_without_asking(course, monkeypatch):
    grader.sync_cmd(str(course), yes=True)
    p = data(course, "midterm")
    r = rows(p)
    for x in r[1:]:
        x[3] = ""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(r)
    p.write_text(buf.getvalue(), encoding="utf-8")
    edit_cfg(course, "  - midterm_showsol: 5\n", "")
    answers(monkeypatch)                            # any question would get the default (keep)
    update(course)
    assert "midterm_showsol (5pts)" not in rows(p)[0]


def test_old_course_without_memory_uses_earlier_configs(course):
    hist = course / "history" / "20260101-000000_grader_sync" / "course_info"
    hist.mkdir(parents=True)
    hist.joinpath(cfg(course).name).write_text(cfg(course).read_text(encoding="utf-8"), encoding="utf-8")
    edit_cfg(course, "  - midterm_showsol: 5\n", "")
    assert not columns.base_path(course).exists()
    assert [u.name for u in find_changes(course).removed] == ["midterm_showsol"]


def test_points_follow_the_side_you_edited(course, monkeypatch):
    grader.sync_cmd(str(course), yes=True)
    edit_cfg(course, "midterm_mcq: 35", "midterm_mcq: 30")   # config edited
    ch = find_changes(course)
    assert [c[2] for c in ch.follow_config] == ["midterm_mcq"] and ch.conflicts == []
    answers(monkeypatch)
    grader.sync_cmd(str(course))                    # no question: the header follows
    assert rows(data(course, "midterm"))[0][2] == "midterm_mcq (30pts)"

    p = data(course, "midterm")                     # now the header is edited by hand
    p.write_bytes(p.read_bytes().replace("midterm_mcq (30pts)".encode(), "midterm_mcq (32pts)".encode()))
    ch = find_changes(course)
    assert [c[2] for c in ch.conflicts] == ["midterm_mcq"] and ch.follow_config == []
    update(course)                                  # update keeps your header too
    assert rows(p)[0][2] == "midterm_mcq (32pts)"


def test_hand_added_column_is_still_proposed(course):
    grader.sync_cmd(str(course), yes=True)
    p = data(course, "final")
    r = rows(p)
    r[0].insert(3, "bonus (2pts)")
    for x in r[1:]:
        x.insert(3, "1")
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(r)
    p.write_text(buf.getvalue(), encoding="utf-8")
    ch = find_changes(course)
    assert [c[2] for c in ch.unmapped] == ["bonus"] and ch.removed == []
