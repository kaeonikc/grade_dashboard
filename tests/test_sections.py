"""Courses with section folders (SPEC_section_folders.md): `grader init -i a_sec51 -i a_sec52`, `grader update -i`
adding a section or moving a flat course into folders, the commands that run on every section, grade-tui's bridge
(All merged, edits routed to each student's section), exports, grade_web's merged copy, and `grader mock`.
The class lists are fake xlsx files built here; the repo's repclasslist.xls is never read."""

import builtins
import csv
import io
import json
import sys
from pathlib import Path

import openpyxl
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import grader  # noqa: E402
from src import course as course_mod  # noqa: E402
from src.sections import counts, course_sections, roster_sections, sort_sections, tagger  # noqa: E402

SEC51 = [("69000001", "นาย ก  หนึ่ง"), ("69000003", "นาง ค  สาม")]
SEC52 = [("69000002", "นาย ข  สอง"), ("69000004", "นาง ง  สี่"), ("69000006", "นาย ฉ  หก")]
COURSE = "2026_S2_Astro"


def class_list(path: Path, sec="51", students=None, course="SC 2202  ดาราศาสตร์และอวกาศ", term="2/2569",
               time="08:30-12:30") -> Path:
    """A class list in the layout course_info_prep/convert_student_info.py reads (made-up people)."""
    students = students if students is not None else (SEC51 if sec == "51" else SEC52)
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in (["มหาวิทยาลัยราชภัฏจำลอง"],
                [f"วิทยาเขตจำลอง ภาคการศึกษา {term}"],
                ["ปริญญาตรี ภาคปกติ"],
                [f"รหัสวิชา  {course}  หน่วยกิต  3(2-2-5)  Sec  {sec}"],
                ["ผู้สอน อาจารย์จำลอง"],
                [f"วันเวลาเรียน ศ. {time} SCI7-206"],
                ["วันเวลาสอบ F 16/02/27 15:10-17:10, M 15/12/26 15:10-17:10"],
                ["ลำดับ", "รหัสประจำตัว", "ชื่อ - สกุล", "หมู่เรียน"],
                ["", "", "", ""]):
        ws.append(row)
    for i, (sid, name) in enumerate(students, 1):
        ws.append([i, sid, name, f"ว 68.ค.บ.4.{sec[-1]}"])
    wb.save(path)
    return path


class Stdin(io.StringIO):
    def __init__(self, tty: bool):
        super().__init__("")
        self.tty = tty

    def isatty(self):
        return self.tty


@pytest.fixture
def here(tmp_path, monkeypatch):
    term = tmp_path / "term"
    term.mkdir()
    monkeypatch.chdir(term)
    monkeypatch.setattr(sys, "stdin", Stdin(False))
    return term


def answer(monkeypatch, text: str):
    monkeypatch.setattr(sys, "stdin", Stdin(True))
    monkeypatch.setattr(builtins, "input", lambda *_: text)


def sec_list(here, sec="51", **kw) -> Path:
    return class_list(here / f"repclasslist_Astro_sec{sec}.xlsx", sec, **kw)


def roster(folder: Path) -> list[dict]:
    f = next((folder / "course_info").glob("*_student_info.csv"))
    return list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))))


def config(course: Path) -> dict:
    return yaml.safe_load(next((course / "course_info").glob("*_config.yaml")).read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


def cell(row: dict, col: str) -> str:
    """A row's value under the header `col` or `col (Npts)`."""
    return next(v for k, v in row.items() if k == col or k.startswith(col + " ("))


def two_sections(here) -> Path:
    grader.init_course(None, None, None, [str(sec_list(here, "51")), str(sec_list(here, "52", time="13:30-17:30"))])
    return here / COURSE


def one_section_course(here) -> Path:
    """A flat course from a class list without _sec in its name: 2026_S2_Astro51_SEC_51 (as before folders)."""
    grader.init_course(None, None, None, str(class_list(here / "repclasslist_Astro51.xlsx")))
    return here / "2026_S2_Astro51_SEC_51"


def set_score(path: Path, sid: str, col: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[0].split(",")
    i = next(k for k, h in enumerate(head) if h.split(" (")[0] == col)
    out = [lines[0]]
    for line in lines[1:]:
        cells = line.split(",")
        if cells[0] == sid:
            cells[i] = value
        out.append(",".join(cells))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---- parsing ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("course,cid,name", [
    ("SC 2202  ดาราศาสตร์และอวกาศ", "SC 2202", "ดาราศาสตร์และอวกาศ"),
    ("PHYS1120  ฟิสิกส์สำหรับอุตสาหกรรม", "PHYS1120", "ฟิสิกส์สำหรับอุตสาหกรรม"),
    ("9999901 ฟิสิกส์ยุคใหม่", "9999901", "ฟิสิกส์ยุคใหม่"),
])
def test_course_id_parse(here, course, cid, name):
    import pandas as pd
    from course_info_prep.convert_student_info import extract_metadata
    meta = extract_metadata(pd.read_excel(class_list(here / "c.xlsx", course=course), header=None))
    assert (meta["course_id"], meta["course_name"], meta["sec_num"]) == (cid, name, "51")


# ---- init --------------------------------------------------------------------------------------------------------
def test_init_two_sec_files_make_section_folders(here, capsys):
    c = two_sections(here)
    assert "sec51 (2 students), sec52 (3 students)" in capsys.readouterr().out
    cfg = config(c)
    assert "sec_num" not in cfg and "class_schedule" not in cfg
    assert {n: e["folder"] for n, e in cfg["sections"].items()} == {"51": "sec51", "52": "sec52"}
    assert cfg["sections"]["52"]["class_schedule"]["time"] == "13:30-17:30"
    assert "&id" not in next((c / "course_info").glob("*_config.yaml")).read_text(encoding="utf-8")
    for sec, people in (("51", SEC51), ("52", SEC52)):
        unit = c / f"sec{sec}"
        assert [r["Student ID"] for r in roster(unit)] == [sid for sid, _ in people]
        assert list(roster(unit)[0]) == ["Student ID", "Name", "Class Group"]
        names = sorted(p.name for p in (unit / "data").iterdir())
        assert names == [f"{COURSE}_SEC_{sec}_{k}" for k in ("attendance.csv", "attendance.xlsx", "final.csv",
                                                             "homework.csv", "midterm.csv")]
        assert not (unit / "history").exists()
        assert not list((unit / "course_info").glob("*_config.yaml"))
    assert (c / "history").is_dir() and (c / "reports").is_dir()


def test_init_one_sec_file_makes_its_folder(here):
    grader.init_course(None, None, None, str(sec_list(here, "51")))
    c = here / COURSE
    assert list(config(c)["sections"]) == ["51"] and (c / "sec51" / "data").is_dir() and not (c / "sec52").exists()


def test_init_refuses_a_name_that_disagrees_with_the_sheet(here, capsys):
    bad = class_list(here / "repclasslist_Astro_sec52.xlsx", "51")
    with pytest.raises(SystemExit):
        grader.init_course(None, None, None, str(bad))
    assert "says sec52 in its name" in capsys.readouterr().out and not (here / COURSE).exists()


def test_init_without_sec_in_the_name_is_flat(here):
    c = one_section_course(here)
    cfg = config(c)
    assert cfg["sec_num"] == "51" and "sections" not in cfg and (c / "data").is_dir()


def test_init_two_lists_without_sec_names_still_makes_folders(here):
    grader.init_course(None, None, None, [str(class_list(here / "repclasslist_Astro51.xlsx", "51")),
                                          str(class_list(here / "repclasslist_Astro52.xlsx", "52"))])
    assert course_sections(here / COURSE) == ["51", "52"]


def test_init_refuses_other_courses_and_twice_one_section(here, capsys):
    other = class_list(here / "repclasslist_Astro_sec52.xlsx", "52", course="PHYS1120  ฟิสิกส์")
    with pytest.raises(SystemExit):
        grader.init_course(None, None, None, [str(sec_list(here, "51")), str(other)])
    assert "one course's sections only" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        grader.init_course(None, None, None, [str(sec_list(here, "51")),
                                              str(class_list(here / "repclasslist_Astro_x.xlsx", "51"))])
    assert "Two class lists are section 51" in capsys.readouterr().out and not (here / COURSE).exists()


# ---- update -i ---------------------------------------------------------------------------------------------------
def test_update_merges_into_a_known_section(here, monkeypatch):
    c = two_sections(here)
    grader.update_course(input_file=str(sec_list(here, "51", students=SEC51 + [("69000009", "นาย ฌ  เก้า")])))
    assert [r["Student ID"] for r in roster(c / "sec51")][-1] == "69000009"
    monkeypatch.chdir(c / "sec52")  # from inside a section folder too
    grader.update_course(input_file=str(sec_list(here, "52", students=SEC52 + [("69000010", "นาง ญ  สิบ")])))
    assert "69000010" in {r["Student ID"] for r in roster(c / "sec52")}
    assert "69000010" not in {r["Student ID"] for r in roster(c / "sec51")}
    assert not (c / "sec52" / "history").exists()


def test_update_adds_a_section_folder_after_asking(here, monkeypatch, capsys):
    grader.init_course(None, None, None, str(sec_list(here, "51")))
    c = here / COURSE
    with pytest.raises(SystemExit):  # no terminal, no -y
        grader.update_course(input_file=str(sec_list(here, "52")))
    assert "-y" in capsys.readouterr().out and not (c / "sec52").exists()
    answer(monkeypatch, "n")
    grader.update_course(input_file=str(sec_list(here, "52")))
    assert not (c / "sec52").exists()
    answer(monkeypatch, "y")
    grader.update_course(input_file=str(sec_list(here, "52", time="13:30-17:30")))
    assert course_sections(c) == ["51", "52"] and len(roster(c / "sec52")) == 3
    sec52 = config(c)["sections"]["52"]
    assert sec52["folder"] == "sec52" and sec52["class_schedule"]["time"] == "13:30-17:30"
    assert (c / "sec52" / "data" / f"{COURSE}_SEC_52_homework.csv").exists()


def test_update_moves_a_flat_course_into_folders(here):
    flat = one_section_course(here)
    grader.update_course(config_file=str(next((flat / "course_info").glob("*_config.yaml"))), yes=True)
    set_score(next((flat / "data").glob("*_homework.csv")), "69000003", "hw1", "7")
    grader.update_course(input_file=str(sec_list(here, "52")), yes=True)
    c = here / COURSE
    assert course_sections(c) == ["51", "52"]
    hw = {r["Student ID"]: r for r in rows(c / "sec51" / "data" / f"{COURSE}_SEC_51_homework.csv")}
    assert cell(hw["69000003"], "hw1") == "7"
    assert (here / "2026_S2_Astro51_SEC_51_before_split").is_dir() and not flat.exists()
    assert len(roster(c / "sec52")) == 3


def test_update_refuses_a_course_with_a_section_column(here, capsys):
    flat = one_section_course(here)
    f = next((flat / "course_info").glob("*_student_info.csv"))
    lines = f.read_text(encoding="utf-8").splitlines()
    assert lines[0].endswith(",Section")
    f.write_text("\n".join([lines[0], lines[1], lines[2].rsplit(",", 1)[0] + ",52"]) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        grader.update_course(input_file=str(sec_list(here, "52")), yes=True)
    assert "Run grader split first" in capsys.readouterr().out


def test_a_student_moving_section_takes_scores_and_marks(here, capsys):
    from src import attendance
    c = two_sections(here)
    mover = SEC51[0][0]
    set_score(c / "sec51" / "data" / f"{COURSE}_SEC_51_homework.csv", mover, "hw1", "8")
    xlsx = c / "sec51" / "data" / f"{COURSE}_SEC_51_attendance.xlsx"
    wb = openpyxl.load_workbook(xlsx)
    ws = wb.active
    row = next(r for r in range(2, ws.max_row + 1) if str(ws.cell(row=r, column=1).value) == mover)
    ws.cell(row=row, column=3).value = "P"
    wb.save(xlsx)
    attendance.auto_sync(c / "sec51")
    grader.update_course(input_file=str(sec_list(here, "52", students=SEC52 + [SEC51[0]])), yes=True)
    assert f"{mover} moves sec 51 → 52" in capsys.readouterr().out
    assert mover not in {r["Student ID"] for r in roster(c / "sec51")}
    hw52 = {r["Student ID"]: r for r in rows(c / "sec52" / "data" / f"{COURSE}_SEC_52_homework.csv")}
    assert cell(hw52[mover], "hw1") == "8"
    assert mover not in {r["Student ID"] for r in rows(c / "sec51" / "data" / f"{COURSE}_SEC_51_homework.csv")}
    att52 = {r["Student ID"]: r for r in rows(c / "sec52" / "data" / f"{COURSE}_SEC_52_attendance.csv")}
    assert att52[mover]["a1"] == "P"
    assert attendance.read_xlsx_sheet(c / "sec52" / "data" / f"{COURSE}_SEC_52_attendance.xlsx").rows[mover]["a1"] == "P"
    assert mover not in attendance.read_xlsx_sheet(xlsx).rows


def test_update_refuses_a_name_that_disagrees_with_the_sheet(here, capsys):
    two_sections(here)
    with pytest.raises(SystemExit):
        grader.update_course(input_file=str(class_list(here / "repclasslist_Astro_sec51.xlsx", "52")), yes=True)
    assert "says sec51 in its name" in capsys.readouterr().out


# ---- every section at once -----------------------------------------------------------------------------------------
def test_update_from_a_section_folder_covers_every_section(here, monkeypatch, capsys):
    c = two_sections(here)
    cfg_path = next((c / "course_info").glob("*_config.yaml"))
    cfg = config(c)
    cfg["data_mapping"]["homework"].append("hw3")
    cfg_path.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    monkeypatch.chdir(c / "sec51")
    capsys.readouterr()
    grader.update_course(yes=True)
    out = capsys.readouterr().out
    assert "── sec 51 (sec51/) ──" in out and "── sec 52 (sec52/) ──" in out
    for sec in ("51", "52"):
        head = (c / f"sec{sec}" / "data" / f"{COURSE}_SEC_{sec}_homework.csv").read_text(encoding="utf-8")
        assert "hw3" in head.splitlines()[0]
    assert not (c / "sec51" / "history").exists()


def test_one_save_across_sections_is_one_undo(here, monkeypatch):
    from src import tui_api
    from src.history import list_entries
    c = two_sections(here)
    edits = [{"student_id": SEC51[0][0], "column": "hw1", "value": "5", "original": ""},
             {"student_id": SEC52[1][0], "column": "hw1", "value": "6", "original": ""}]
    r = tui_api.apply_edits(str(c), edits)
    assert r["saved"] == 2 and len(r["files"]) == 2
    e = list_entries(c)[-1]
    assert e["action"] == "edit" and {f.split("/")[0] for f in e["files"]} == {"sec51", "sec52"}
    monkeypatch.chdir(c / "sec52")
    grader.undo_course(e["id"], None, yes=True)
    for sec, sid in (("51", SEC51[0][0]), ("52", SEC52[1][0])):
        hw = {r["Student ID"]: r for r in rows(c / f"sec{sec}" / "data" / f"{COURSE}_SEC_{sec}_homework.csv")}
        assert cell(hw[sid], "hw1") == ""


def test_sync_runs_for_each_section(here, capsys):
    c = two_sections(here)
    capsys.readouterr()
    grader.sync_cmd(str(c), yes=True)
    out = capsys.readouterr().out
    assert f"Sync: {COURSE} · sec 51" in out and f"Sync: {COURSE} · sec 52" in out


def test_history_from_a_section_folder_is_the_course_s(here, monkeypatch, capsys):
    c = two_sections(here)
    monkeypatch.chdir(c / "sec52")
    capsys.readouterr()
    grader.history_course()
    assert f"History of {COURSE}" in capsys.readouterr().out


# ---- the course model --------------------------------------------------------------------------------------------
def test_course_at_any_path(here):
    c = two_sections(here)
    for p in (c, c / "sec52", c / "sec52" / "data", c / "sec52" / "data" / f"{COURSE}_SEC_52_homework.csv"):
        got = course_mod.at(p)
        assert got.root == c.resolve() and got.layout and [s.num for s in got.sections] == ["51", "52"]
    assert course_mod.at(c).here is None and course_mod.at(c / "sec52").here.num == "52"
    assert course_mod.prefix_for(c / "sec52") == f"{COURSE}_SEC_52" and course_mod.prefix_for(c) == COURSE
    assert course_mod.config_for(c / "sec52")["sec_num"] == "52"
    assert course_mod.history_root(c / "sec52" / "data") == c.resolve()
    flat = one_section_course(here)
    f = course_mod.at(flat)
    assert not f.layout and f.sections[0].path == flat.resolve() and f.here.num == "51"


def test_section_helpers():
    secmap = {"3": "52", "1": "51", "2": "8", "4": ""}
    assert sort_sections(secmap.values()) == ["8", "51", "52"]
    assert counts(secmap) == "sec 8: 1 · sec 51: 1 · sec 52: 1 · no sec: 1"
    tag = tagger(secmap)
    assert tag("3") == "[52] " and tag("4") == "[?] "
    assert tagger({"1": "51"})("1") == ""


def test_group_order_and_blocks():
    from src.sections import block_title, blocks, group_order
    secmap = {"5": "52", "1": "51", "4": "", "2": "8", "3": "51"}
    ids = sorted(secmap, key=group_order(secmap))
    assert ids == ["2", "1", "3", "5", "4"]
    assert blocks(ids, secmap) == [("8", ["2"]), ("51", ["1", "3"]), ("52", ["5"]), ("", ["4"])]
    assert block_title("51", 28) == "Sec 51 · 28 students" and block_title("", 1) == "No section · 1 student"


# ---- grade-tui's bridge ------------------------------------------------------------------------------------------
def scored(here) -> Path:
    c = two_sections(here)
    for i, (sid, _) in enumerate(SEC51 + SEC52):
        sec = "51" if i < len(SEC51) else "52"
        set_score(c / f"sec{sec}" / "data" / f"{COURSE}_SEC_{sec}_homework.csv", sid, "hw1", str(4 + i))
    return c


def test_the_course_is_listed_once(here):
    from src import tui_api
    scored(here)
    assert [x["name"] for x in tui_api.get_courses()["courses"]] == [f"{COURSE} · sec 51, 52"]


def test_course_data_merges_the_sections(here):
    from src import tui_api
    c = scored(here)
    d = tui_api.get_course_data(str(c))
    assert d["status"] == "success", d.get("traceback")
    assert d["sections"] == ["51", "52"] and len(d["student_grades"]) == 5
    secs = {r["Student ID"]: r["Section"] for r in d["student_grades"]}
    assert secs == {r["Student ID"]: r["Section"] for r in d["raw_scores"]} == roster_sections(c)
    n = {s: sum(v["count"] for v in d["by_section"][s]["grade_distribution"].values()) for s in ("51", "52")}
    assert n == {"51": 2, "52": 3}
    assert float({r["Student ID"]: r["hw1"] for r in d["raw_scores"]}[SEC52[2][0]]) == 8
    for s in ("51", "52"):  # raw_index stays a whole-course row
        for r in d["by_section"][s]["analytics"]["at_risk"]:
            assert d["student_grades"][r["raw_index"]]["Student ID"] == r["student_id"]


def test_one_section_course_data_has_no_sections(here):
    from src import tui_api
    c = one_section_course(here)
    grader.update_course(config_file=str(next((c / "course_info").glob("*_config.yaml"))), yes=True)
    d = tui_api.get_course_data(str(c))
    assert d["sections"] == [] and d["by_section"] == {} and "Section" not in d["student_grades"][0]


def test_an_edit_for_a_student_in_no_section_is_not_found(here):
    from src import tui_api
    c = two_sections(here)
    r = tui_api.apply_edits(str(c), [{"student_id": "69999999", "column": "hw1", "value": "5", "original": ""}])
    assert r["saved"] == 0 and r["conflicts"][0]["reason"] == "not found"


# ---- exports -----------------------------------------------------------------------------------------------------
def test_export_writes_the_course_and_each_section_folder(here):
    from src import tui_api
    c = scored(here)
    assert tui_api.run_export(str(c))["status"] == "success"
    both = rows(c / "reports" / f"{COURSE}_final_grades.csv")
    assert list(both[0])[:3] == ["Student ID", "Name", "Section"]
    assert [r["Student ID"] for r in both] == ["69000001", "69000003", "69000002", "69000004", "69000006"]
    assert (c / "reports" / f"{COURSE}_copy_friendly_scores.csv").exists()
    for sec, n in (("51", 2), ("52", 3)):
        mine = rows(c / f"sec{sec}" / "reports" / f"{COURSE}_SEC_{sec}_final_grades.csv")
        assert len(mine) == n and {r["Section"] for r in mine} == {sec}
        copy = c / f"sec{sec}" / "reports" / f"{COURSE}_SEC_{sec}_copy_friendly_scores.csv"
        assert len(copy.read_text(encoding="utf-8").splitlines()) == n + 1


def test_export_of_a_one_section_course_is_as_before(here):
    from src import tui_api
    c = one_section_course(here)
    grader.update_course(config_file=str(next((c / "course_info").glob("*_config.yaml"))), yes=True)
    assert tui_api.run_export(str(c))["status"] == "success"
    names = sorted(f.name for f in (c / "reports").iterdir())
    assert names == ["2026_S2_Astro51_SEC_51_copy_friendly_scores.csv", "2026_S2_Astro51_SEC_51_final_grades.csv"]
    assert "Section" not in (c / "reports" / names[1]).read_text(encoding="utf-8").splitlines()[0]


def test_dashboard_all_view_prints_section_blocks(here, monkeypatch):
    from rich.console import Console
    from rich.prompt import Confirm
    from src import dashboard
    from src.calculators import calculate_final_grades
    from src.data_loader import load_course
    monkeypatch.setattr(Confirm, "ask", lambda *a, **k: False)
    c = scored(here)
    config_, df, max_scores = load_course(c)
    final_df = calculate_final_grades(df, config_, max_scores)
    rec = Console(record=True, width=250)
    dashboard.console, old = rec, dashboard.console
    try:
        dashboard.show_student_table(final_df, max_scores, config_, True, secmap=roster_sections(c))
    finally:
        dashboard.console = old
    out = rec.export_text()
    a, b = out.index("Sec 51 · 2 students"), out.index("Sec 52 · 3 students")
    assert a < out.index("69000003") < b < out.index("69000002")


# ---- grade_web ---------------------------------------------------------------------------------------------------
def test_web_push_sends_one_merged_course(here, drive_root, capsys):
    from src import webpush
    c = scored(here)
    capsys.readouterr()
    webpush.push(c / "sec52", drive_root)  # from a section folder: the whole course
    assert "5 students (sec 51: 2 · sec 52: 3)" in capsys.readouterr().out
    m = drive_root / "grade_courses" / "term" / COURSE
    cj = json.loads((m / "course.json").read_text(encoding="utf-8"))
    assert cj["folder"] == COURSE and cj["roster"] == f"course_info/{COURSE}_student_info.csv"
    assert set(cj["sections"]) == {"51", "52"}
    assert {r["Student ID"]: r["Section"] for r in rows(m / cj["roster"])} == roster_sections(c)
    hw = rows(m / "data" / f"{COURSE}_homework.csv")
    assert sorted(cell(r, "hw1") for r in hw) == ["4", "5", "6", "7", "8"]


def test_web_pull_puts_each_edit_in_its_section(here, drive_root, capsys):
    from src import webpull, webpush
    from src.history import list_entries
    c = scored(here)
    webpush.push(c, drive_root)
    m = drive_root / "grade_courses" / "term" / COURSE
    push_id = json.loads((m / "push.json").read_text(encoding="utf-8"))["push_id"]
    s52 = SEC52[0][0]
    line = {"batch": "b-1", "seq": 0, "ts": "2026-10-30T13:40:00+07:00", "kind": "cell", "push": push_id,
            "file": f"data/{COURSE}_attendance.csv", "student_id": s52, "column": "a1", "value": "P", "original": ""}
    (m / "web_edits.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    capsys.readouterr()
    assert webpull.pull(c, drive_root, yes=True) == 0
    out = capsys.readouterr().out
    assert f"[52] {s52} a1" in out and f"sec52/data/{COURSE}_SEC_52_attendance.csv" in out
    assert {r["Student ID"]: r["a1"] for r in rows(c / "sec52" / "data" / f"{COURSE}_SEC_52_attendance.csv")}[s52] == "P"
    assert all(r["a1"] == "" for r in rows(c / "sec51" / "data" / f"{COURSE}_SEC_51_attendance.csv"))
    assert list_entries(c)[-1]["action"] == "web-pull"


def test_web_pull_preview_tags_students_and_orders_by_section():
    from src.webpull import Change, preview
    changes = [Change([{"kind": "cell", "student_id": sid, "column": "hw1", "original": "", "value": "5"}],
                      result="apply", mac="") for sid in ("3", "2", "1")]
    out = "\n".join(preview(changes, {"1": "52", "2": "51", "3": "52"}))
    assert out.index("[51] 2 hw1") < out.index("[52] 1 hw1") < out.index("[52] 3 hw1")


# ---- grader mock -------------------------------------------------------------------------------------------------
def test_mock_course_has_two_section_folders(here):
    grader.mock_course()
    c = here / "courses" / "0_GenPhysMock"
    assert course_sections(c) == ["51", "52"]
    assert len(roster(c / "sec51")) == 16 and len(roster(c / "sec52")) == 14
    assert not (c / "history" / "log.jsonl").exists()
    assert not (here / "courses" / "0_GenPhysMock_flat").exists()
    assert not (here / "courses" / "0_GenPhysMock_flat_before_split").exists()
