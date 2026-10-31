"""`grader split` (SPEC_section_folders.md F9): a one-folder course with a `Section` column in its roster becomes a
course with one folder per section, keeping every score and attendance mark; the refusals; `grader undo` of it."""

import csv
import io
import json
import sys

import openpyxl
import pytest
import yaml

import grader
from src import attendance, split, webpush
from src.history import list_entries
from src.sections import course_sections
from test_sections import SEC51, SEC52, Stdin, answer, here, rows  # noqa: F401
from test_sections import class_list, config, one_section_course, roster, set_score

OLD, NEW = "2026_S2_Astro51_SEC_51", "2026_S2_Astro"


def old_model(here):
    """The Astro course as it was on 30 Oct: one folder, 5 students in sec 51 and 52, scores and a1 marks."""
    c = one_section_course(here)
    f = next((c / "course_info").glob("*_student_info.csv"))
    lines = f.read_text(encoding="utf-8").splitlines()
    lines += [f"{sid},{name},ว 68.ค.บ.4.2,52" for sid, name in SEC52]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cfg_path = next((c / "course_info").glob("*_config.yaml"))
    cfg = config(c)
    cfg["sections"] = {"51": {"class_schedule": cfg["class_schedule"], "exam_schedule": cfg["exam_schedule"]},
                       "52": {"class_schedule": {**cfg["class_schedule"], "time": "13:30-17:30"},
                              "exam_schedule": cfg["exam_schedule"]}}
    cfg_path.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    grader.update_course(config_file=str(cfg_path), yes=True)
    hw = next((c / "data").glob("*_homework.csv"))
    for i, (sid, _) in enumerate(SEC51 + SEC52):
        set_score(hw, sid, "hw1", str(3 + i))
    set_score(next((c / "data").glob("*_midterm.csv")), SEC52[0][0], "midterm_score", "ขส")
    xlsx = next((c / "data").glob("*_attendance.xlsx"))
    wb = openpyxl.load_workbook(xlsx)
    ws = wb.active
    a1 = [cell.value for cell in ws[1]].index("a1") + 1
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value) in {sid for sid, _ in SEC51}:
            ws.cell(row=r, column=a1).value = "P"
    wb.save(xlsx)
    attendance.auto_sync(c)
    return c


def by_sid(path) -> dict:
    return {r["Student ID"]: r for r in rows(path)}


def test_split_keeps_every_value(here, capsys):
    c = old_model(here)
    before = {p.name.removeprefix(f"{OLD}_"): by_sid(p) for p in sorted((c / "data").glob("*.csv"))}
    grader.split_cmd(str(c), yes=True)
    out = capsys.readouterr().out
    assert "sec51/: 2 students, 2 attendance marks" in out and "sec52/: 3 students, 0 attendance marks" in out
    new = here / NEW
    assert course_sections(new) == ["51", "52"] and (here / f"{OLD}_before_split").is_dir() and not c.exists()
    cfg = config(new)
    assert "sec_num" not in cfg and cfg["sections"]["52"]["folder"] == "sec52"
    assert cfg["sections"]["52"]["class_schedule"]["time"] == "13:30-17:30"
    for sec, people in (("51", SEC51), ("52", SEC52)):
        unit = new / f"sec{sec}"
        assert [r["Student ID"] for r in roster(unit)] == [sid for sid, _ in people]
        assert "Section" not in roster(unit)[0]
        for suffix, old_rows in before.items():
            mine = by_sid(unit / "data" / f"{NEW}_SEC_{sec}_{suffix}")
            assert set(mine) == {sid for sid, _ in people}, suffix
            for sid in mine:
                assert mine[sid] == old_rows[sid], (suffix, sid)
    X = attendance.read_xlsx_sheet(new / "sec51" / "data" / f"{NEW}_SEC_51_attendance.xlsx")
    assert {sid: r["a1"] for sid, r in X.rows.items()} == {sid: "P" for sid, _ in SEC51}
    assert attendance.plan(new / "sec51") is None or not attendance.plan(new / "sec51").has_changes()
    e = list_entries(new)[-1]
    assert (e["action"], e["from"], e["to"]) == ("split", OLD, NEW)


def test_split_asks_first(here, monkeypatch, capsys):
    c = old_model(here)
    with pytest.raises(SystemExit):  # no terminal, no -y
        grader.split_cmd(str(c))
    assert "grader split -y" in capsys.readouterr().out and c.is_dir()
    answer(monkeypatch, "n")
    grader.split_cmd(str(c))
    assert c.is_dir() and not (here / NEW).exists()
    answer(monkeypatch, "y")
    monkeypatch.chdir(c)
    grader.split_cmd()
    assert (here / NEW).is_dir()


@pytest.mark.parametrize("problem,message", [
    ("blank", "have no Section"),
    ("target", "already exists"),
    ("one", "doesn't name two sections"),
    ("attendance", "run grader sync first"),
])
def test_split_refuses(here, capsys, problem, message):
    c = old_model(here) if problem != "one" else one_section_course(here)
    if problem == "blank":
        f = next((c / "course_info").glob("*_student_info.csv"))
        lines = f.read_text(encoding="utf-8").splitlines()
        lines[-1] = lines[-1].rsplit(",", 1)[0] + ","
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif problem == "target":
        (here / NEW).mkdir()
    elif problem == "attendance":
        xlsx = next((c / "data").glob("*_attendance.xlsx"))
        wb = openpyxl.load_workbook(xlsx)
        wb.active.cell(row=2, column=4).value = "L"
        wb.save(xlsx)
    with pytest.raises(SystemExit):
        grader.split_cmd(str(c), yes=True)
    assert message in capsys.readouterr().out
    assert c.is_dir() and not (here / f"{OLD}_before_split").exists()
    assert problem == "target" or not (here / NEW).exists()


def test_split_refuses_unpulled_web_edits(here, drive_root, capsys):
    c = old_model(here)
    webpush.push(c, drive_root)
    mirror = drive_root / "grade_courses" / "term" / OLD
    line = {"batch": "b-1", "seq": 0, "ts": "2026-10-30T09:00:00+07:00", "kind": "cell", "push": "p",
            "file": f"data/{OLD}_attendance.csv", "student_id": SEC51[0][0], "column": "a2", "value": "P",
            "original": ""}
    (mirror / "web_edits.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        grader.split_cmd(str(c), yes=True)
    assert "not pulled yet" in capsys.readouterr().out and c.is_dir() and not (here / NEW).exists()


def test_split_offers_the_push_and_the_new_copy_is_one_course(here, drive_root, capsys):
    c = old_model(here)
    webpush.push(c, drive_root)
    grader.split_cmd(str(c), yes=True)
    out = capsys.readouterr().out
    assert f"The old web copy {OLD} is no longer updated" in out
    cj = json.loads((drive_root / "grade_courses" / "term" / NEW / "course.json").read_text(encoding="utf-8"))
    assert set(cj["sections"]) == {"51", "52"}


def test_undo_of_the_split_puts_the_old_folder_back(here, monkeypatch):
    c = old_model(here)
    grader.split_cmd(str(c), yes=True)
    new = here / NEW
    e = list_entries(new)[-1]
    monkeypatch.chdir(new / "sec51")
    grader.undo_course(e["id"], None, yes=True)
    monkeypatch.chdir(here)
    assert c.is_dir() and not new.exists() and not (here / f"{OLD}_before_split").exists()
    assert len(roster(c)) == 5


def test_undo_of_the_split_refuses_after_later_changes(here, monkeypatch, capsys):
    from src import tui_api
    c = old_model(here)
    grader.split_cmd(str(c), yes=True)
    new = here / NEW
    split_id = list_entries(new)[-1]["id"]
    tui_api.apply_edits(str(new), [{"student_id": SEC52[0][0], "column": "hw1", "value": "9", "original": "5"}])
    monkeypatch.chdir(new)
    with pytest.raises(SystemExit):
        grader.undo_course(split_id, None, yes=True)
    assert "after the split" in capsys.readouterr().out and new.is_dir()


def test_layout_name():
    assert split.layout_name(OLD, ["51", "52"]) == NEW
    assert split.layout_name("2026_S2_PHYS1120_SEC_20", ["20", "21"]) == "2026_S2_PHYS1120"
    assert split.layout_name("2026_S1_Optics_grading", ["51", "52"]) == "2026_S1_Optics"
    assert split.layout_name("9_ฟิสิกส์จำลอง_grading", ["51"]) is None
