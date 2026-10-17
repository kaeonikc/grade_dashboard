"""Default points per category: bare headers at the default (SPEC_default_points.md, INTEGRATION.md "Points")."""
import csv
import io

import pytest
import yaml

import grader
from src.calculators import validate_scores
from src.data_loader import load_config, load_course_data
from src.history import list_entries
from src.points import header_for
from src.sync import find_changes, mapping, raw_config
from conftest import PREFIX, write

# The same table is in INTEGRATION.md and in exam_projects' contract test.
HEADER_CASES = [
    ("4", 10, 10, "4"),
    ("5", 20, 10, "5 (20pts)"),
    ("hw1", 15, None, "hw1 (15pts)"),
    ("final_mcq", 35, 35, "final_mcq"),
    ("final_mcq", 35, None, "final_mcq (35pts)"),
]

LAB_OLD = ("Student ID,Name," + ",".join(f"{i} (10pts)" for i in range(1, 11)) + ",total (100pts)\n"
           "69000001,นาย ก  หนึ่ง,10,9,8,10,7,10,9.5,10,10,10,93.5\n"
           "69000002,นาย ข  สอง,ขส,,5,,,,,,,,5\n"
           "69000003,นาย ค  สาม,,,,,,,,,,,0\n")


def cfg(course):
    return next((course / "course_info").glob("*_config.yaml"))


def data(course, cat):
    return course / "data" / f"{PREFIX}_{cat}.csv"


def rows(path):
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


def set_mapping(course, cat, value, weight=0.1):
    """Put data_mapping[cat] (and a weight) into the course config."""
    c = yaml.safe_load(cfg(course).read_text(encoding="utf-8"))
    c["data_mapping"][cat] = value
    c["weights"][cat] = weight
    cfg(course).write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding="utf-8")


def answers(monkeypatch, *seq):
    it = iter(seq)
    asked = []

    def ask(q, default=""):
        asked.append(q)
        return next(it, default)
    monkeypatch.setattr(grader, "_ask", ask)
    return asked


def update(course, yes=False):
    grader.update_course(config_file=str(cfg(course)), yes=yes)


@pytest.fixture
def lab_course(course):
    """The test course plus a lab of 10 × 10 pts, written the old way: `- 1: 10` and `1 (10pts)` headers."""
    set_mapping(course, "lab", [{i: 10} for i in range(1, 11)])
    write(data(course, "lab"), LAB_OLD)
    return course


@pytest.mark.parametrize("name,pts,default,header", HEADER_CASES)
def test_header_rule_matches_the_contract(name, pts, default, header):
    assert header_for(name, pts, default) == header


def test_new_lab_file_has_bare_headers(course):
    set_mapping(course, "lab", list(range(1, 11)))          # bare entries: the built-in 10 each
    update(course)
    assert rows(data(course, "lab"))[0] == ["Student ID", "Name", *map(str, range(1, 11)), "total (100pts)"]


def test_update_reshapes_old_lab_headers_and_keeps_every_score(lab_course, capsys):
    before = rows(data(lab_course, "lab"))
    update(lab_course)
    after = rows(data(lab_course, "lab"))
    assert after[0] == ["Student ID", "Name", *map(str, range(1, 11)), "total (100pts)"]
    assert after[1:] == before[1:]
    out = capsys.readouterr().out
    assert "[lab] 10 header(s) reshaped ('1 (10pts)' → '1', …): 10 pts each" in out
    assert "Updated max points header" not in out            # one line per file, not ten
    entry = next(e for e in reversed(list_entries(lab_course)) if e["action"] == "update")
    grader.undo_course(entry["id"], course=str(lab_course), yes=True)
    assert rows(data(lab_course, "lab"))[0] == before[0]


def test_bare_headers_count_out_of_the_default(lab_course):
    update(lab_course)
    _, max_scores = load_course_data(lab_course)
    assert all(max_scores[str(i)] == 10 for i in range(1, 11))
    assert dict(mapping(raw_config(lab_course)))["lab"][0] == ("1", 10.0)
    assert find_changes(lab_course).empty()


def test_pts_each_for_any_category(course):
    set_mapping(course, "quiz", {"pts_each": 5, "columns": ["q1", "q2", {"q3": 8}]})
    update(course)
    assert rows(data(course, "quiz"))[0] == ["Student ID", "Name", "q1", "q2", "q3 (8pts)", "total (18pts)"]
    config = load_config(course)
    raw_df, max_scores = load_course_data(course)
    assert (max_scores["q1"], max_scores["q2"], max_scores["q3"]) == (5, 5, 8)
    assert config["default_pts"]["quiz"] == 5 and "quiz" not in config["total_pts"]
    assert not any("Manual total" in w for w in validate_scores(raw_df, config, max_scores))


def test_other_categories_keep_their_points(lab_course):
    update(lab_course)
    assert rows(data(lab_course, "midterm"))[0][2:] == ["midterm_mcq (35pts)", "midterm_showsol (5pts)",
                                                        "total (40pts)"]


def test_off_default_lab_column_keeps_its_points(lab_course):
    set_mapping(lab_course, "lab", [{i: 20 if i == 5 else 10} for i in range(1, 11)])
    update(lab_course)
    head = rows(data(lab_course, "lab"))[0]
    assert head[2 + 4] == "5 (20pts)" and head[2] == "1" and head[-1] == "total (110pts)"


def test_changing_pts_each_asks_and_can_put_it_back(lab_course, monkeypatch):
    update(lab_course)                                        # bare headers, remembered at 10
    grader.sync_cmd(str(lab_course), yes=True)
    set_mapping(lab_course, "lab", {"pts_each": 20, "columns": list(range(1, 11))})
    asked = answers(monkeypatch, "n")
    update(lab_course)
    assert len(asked) == 1 and "[lab] 10 → 20 pts each; 2 students' scores" in asked[0]
    lab = yaml.safe_load(cfg(lab_course).read_text(encoding="utf-8"))["data_mapping"]["lab"]
    assert lab["pts_each"] == 10 and lab["columns"] == list(range(1, 11))
    _, max_scores = load_course_data(lab_course)
    assert max_scores["1"] == 10
    answers(monkeypatch)                                      # settled: no question the next time
    update(lab_course)


def test_changing_pts_each_kept_with_yes(lab_course, monkeypatch):
    update(lab_course)
    grader.sync_cmd(str(lab_course), yes=True)
    set_mapping(lab_course, "lab", {"pts_each": 20, "columns": list(range(1, 11))})
    asked = answers(monkeypatch)
    update(lab_course, yes=True)
    assert asked == []
    assert rows(data(lab_course, "lab"))[0][-1] == "total (200pts)"
    _, max_scores = load_course_data(lab_course)
    assert max_scores["1"] == 20


def test_sync_asks_about_pts_each_too(lab_course, monkeypatch):
    update(lab_course)
    grader.sync_cmd(str(lab_course), yes=True)
    set_mapping(lab_course, "lab", {"pts_each": 20, "columns": list(range(1, 11))})
    asked = answers(monkeypatch, "n")
    grader.sync_cmd(str(lab_course))
    assert any("10 → 20 pts each" in q for q in asked)
    assert yaml.safe_load(cfg(lab_course).read_text(encoding="utf-8"))["data_mapping"]["lab"]["pts_each"] == 10


def test_sync_reshapes_old_headers(lab_course, capsys):
    ch = find_changes(lab_course)
    assert len(ch.reshape) == 10 and not ch.conflicts and not ch.unmapped
    grader.sync_cmd(str(lab_course), yes=True)
    assert rows(data(lab_course, "lab"))[0][2] == "1"
    assert "10 header(s) reshaped" in capsys.readouterr().out
    assert find_changes(lab_course).empty()


def test_hand_added_bare_column_counts_as_the_default(lab_course, monkeypatch):
    update(lab_course)
    p = data(lab_course, "lab")
    r = rows(p)
    r[0].insert(-1, "11")
    for x in r[1:]:
        x.insert(-1, "")
    r[1][-2] = "7"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(r)
    p.write_text(buf.getvalue(), encoding="utf-8")
    ch = find_changes(lab_course)
    assert [(c, n, hp) for c, _, n, hp in ch.unmapped] == [("lab", "11", 10.0)]
    grader.sync_cmd(str(lab_course), yes=True)
    lab = yaml.safe_load(cfg(lab_course).read_text(encoding="utf-8"))["data_mapping"]["lab"]
    assert lab[-1] == 11                                      # bare: at the default
    assert rows(p)[0][-2:] == ["11", "total (110pts)"]


def test_hand_written_points_on_a_bare_column_are_asked(lab_course, monkeypatch):
    update(lab_course)
    grader.sync_cmd(str(lab_course), yes=True)
    p = data(lab_course, "lab")
    p.write_text(p.read_text(encoding="utf-8").replace(",5,", ",5 (20pts),", 1), encoding="utf-8")
    ch = find_changes(lab_course)
    assert [(n, hp, cp) for _, _, n, hp, cp in ch.conflicts] == [("5", 20.0, 10.0)]
    answers(monkeypatch, "f")
    grader.sync_cmd(str(lab_course))
    lab = yaml.safe_load(cfg(lab_course).read_text(encoding="utf-8"))["data_mapping"]["lab"]
    assert {5: 20} in lab
    assert rows(p)[0][-1] == "total (110pts)"


def test_tui_gets_the_defaults(lab_course):
    from src.tui_api import get_course_data
    update(lab_course)
    d = get_course_data(str(lab_course))
    assert d["status"] == "success", d.get("message")
    assert d["default_pts"] == {"lab": 10.0}
    assert d["max_scores"]["1"] == 10.0
