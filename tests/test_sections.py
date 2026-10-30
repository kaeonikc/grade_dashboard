"""Courses with several sections in one folder (SPEC_sections.md): `grader init -i a -i b`, `grader update -i` adding a
section, the roster's Section column, config `sections:`, the attendance xlsx's Sec column, and the course ID parse.
The class lists are fake xlsx files built here; the repo's repclasslist.xls is never read."""

import builtins
import csv
import io
import sys
from pathlib import Path

import openpyxl
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import grader  # noqa: E402
from src import attendance  # noqa: E402
from src.sections import counts, course_sections, roster_sections, sort_sections, tagger  # noqa: E402

SEC51 = [("69000001", "นาย ก  หนึ่ง"), ("69000003", "นาง ค  สาม")]
SEC52 = [("69000002", "นาย ข  สอง"), ("69000004", "นาง ง  สี่"), ("69000006", "นาย ฉ  หก")]


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


def roster(course: Path) -> list[dict]:
    f = next((course / "course_info").glob("*_student_info.csv"))
    return list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))))


def config(course: Path) -> dict:
    return yaml.safe_load(next((course / "course_info").glob("*_config.yaml")).read_text(encoding="utf-8"))


def xlsx_rows(course: Path) -> list[list]:
    ws = openpyxl.load_workbook(next((course / "data").glob("*_attendance.xlsx"))).active
    return [[c.value for c in row] for row in ws.iter_rows()]


def one_section_course(here) -> Path:
    grader.init_course(None, None, None, str(class_list(here / "repclasslist_Astro51.xlsx")))
    return here / "2026_S2_Astro51_SEC_51"


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


# ---- init -------------------------------------------------------------------------------------------------------
def test_init_one_class_list_writes_section_and_sections(here):
    c = one_section_course(here)
    assert {r["Section"] for r in roster(c)} == {"51"}
    cfg = config(c)
    assert str(cfg["course_id"]) == "SC 2202" and cfg["sec_num"] == "51"
    assert list(cfg["sections"]) == ["51"]
    assert xlsx_rows(c)[0][:3] == ["Student ID", "Name", "a1"]  # one section: no Sec column


def test_init_two_class_lists_makes_one_course(here, capsys):
    grader.init_course(None, None, None, [str(class_list(here / "repclasslist_Astro52.xlsx", "52", time="13:30-17:30")),
                                          str(class_list(here / "repclasslist_Astro51.xlsx", "51"))])
    c = here / "2026_S2_Astro_SEC_51-52"
    assert c.is_dir()
    assert (c / "course_info" / "2026_S2_Astro_SEC_51-52_config.yaml").exists()
    rows = roster(c)
    assert [r["Student ID"] for r in rows] == sorted(r["Student ID"] for r in rows)
    assert {r["Student ID"]: r["Section"] for r in rows} == {**{s: "51" for s, _ in SEC51}, **{s: "52" for s, _ in SEC52}}
    cfg = config(c)
    assert cfg["sec_num"] == "51" and cfg["class_schedule"]["time"] == "08:30-12:30"
    assert cfg["sections"]["52"]["class_schedule"]["time"] == "13:30-17:30"
    assert "&id" not in (c / "course_info" / "2026_S2_Astro_SEC_51-52_config.yaml").read_text(encoding="utf-8")
    sheet = xlsx_rows(c)
    assert sheet[0][:4] == ["Student ID", "Name", "Sec", "a1"]
    assert {r[0]: r[2] for r in sheet[1:]}["69000002"] == "52"
    assert sheet[1][-1].startswith("=COUNTIF(D2:R2")
    att_csv = next((c / "data").glob("*_attendance.csv")).read_text(encoding="utf-8")
    assert "Sec" not in att_csv.splitlines()[0]
    out = capsys.readouterr().out
    assert "abbreviation Astro from the file names" in out and "sec 51: 2 · sec 52: 3" in out


def test_init_refuses_class_lists_of_different_courses(here, capsys):
    a = class_list(here / "repclasslist_A51.xlsx", "51")
    b = class_list(here / "repclasslist_A52.xlsx", "52", course="PHYS1120  ฟิสิกส์")
    with pytest.raises(SystemExit):
        grader.init_course(None, None, None, [str(a), str(b)])
    assert "one course's sections only" in capsys.readouterr().out
    assert not any(p.is_dir() for p in here.iterdir())


def test_init_refuses_two_lists_of_the_same_section(here, capsys):
    a = class_list(here / "repclasslist_A51.xlsx", "51")
    b = class_list(here / "repclasslist_B51.xlsx", "51")
    with pytest.raises(SystemExit):
        grader.init_course(None, None, None, [str(a), str(b)])
    assert "Two class lists are section 51" in capsys.readouterr().out


# ---- update -i adds a section ------------------------------------------------------------------------------------
def test_update_adds_a_section_with_yes(here, capsys):
    c = one_section_course(here)
    capsys.readouterr()
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52", time="13:30-17:30")),
                         yes=True)
    assert course_sections(c) == ["51", "52"]
    cfg = config(c)
    assert cfg["sec_num"] == "51" and cfg["class_schedule"]["time"] == "08:30-12:30"
    assert list(cfg["sections"]) == ["51", "52"]
    assert cfg["sections"]["52"]["class_schedule"]["time"] == "13:30-17:30"
    out = capsys.readouterr().out
    assert "Total students now: 5 (sec 51: 2 · sec 52: 3)" in out
    assert "is unchanged; rename it by hand" in out
    assert (c / "course_info" / "2026_S2_Astro51_SEC_51_student_info.csv").exists()  # nothing renamed


def test_update_asks_before_adding_a_section(here, monkeypatch, capsys):
    c = one_section_course(here)
    answer(monkeypatch, "n")
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")))
    assert course_sections(c) == ["51"] and "Nothing changed." in capsys.readouterr().out
    answer(monkeypatch, "y")
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")))
    assert course_sections(c) == ["51", "52"]


def test_update_without_a_terminal_refuses_a_new_section(here, capsys):
    c = one_section_course(here)
    before = roster(c)
    with pytest.raises(SystemExit):
        grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")))
    assert "-y" in capsys.readouterr().out and roster(c) == before


def test_update_fills_an_old_roster_from_sec_num(here):
    c = one_section_course(here)
    f = next((c / "course_info").glob("*_student_info.csv"))
    lines = f.read_text(encoding="utf-8").splitlines()
    f.write_text("\n".join(",".join(l.split(",")[:3]) for l in lines) + "\n", encoding="utf-8")  # drop Section
    cfg_path = next((c / "course_info").glob("*_config.yaml"))
    cfg = config(c)
    cfg.pop("sections")
    cfg_path.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")), yes=True)
    assert roster_sections(c) == {**{s: "51" for s, _ in SEC51}, **{s: "52" for s, _ in SEC52}}
    assert list(config(c)["sections"]) == ["51", "52"]


def test_reupdating_one_section_keeps_the_others(here):
    c = one_section_course(here)
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52", time="13:30-17:30")),
                         yes=True)
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro51.xlsx", "51", time="09:00-12:00",
                                                   students=SEC51 + [("69000009", "นาย ฌ  เก้า")])))
    cfg = config(c)
    assert cfg["sections"]["52"]["class_schedule"]["time"] == "13:30-17:30"
    assert cfg["sections"]["51"]["class_schedule"]["time"] == "09:00-12:00" == cfg["class_schedule"]["time"]
    assert roster_sections(c)["69000009"] == "51"


def test_a_student_in_another_sections_list_moves(here, capsys):
    c = one_section_course(here)
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52",
                                                   students=SEC52 + [SEC51[0]])), yes=True)
    assert roster_sections(c)[SEC51[0][0]] == "52"
    assert f"{SEC51[0][0]} moves sec 51 → 52" in capsys.readouterr().out


def test_update_inside_a_folder_refuses_another_course(here, monkeypatch, capsys):
    c = one_section_course(here)
    other = class_list(here / "repclasslist_X.xlsx", "52", course="PHYS1120  ฟิสิกส์")
    monkeypatch.chdir(c)
    before = roster(c)
    with pytest.raises(SystemExit):
        grader.update_course(input_file=str(other), yes=True)
    assert "Nothing changed" in capsys.readouterr().out and roster(c) == before


def test_update_finds_a_course_made_before_the_id_fix(here):
    c = one_section_course(here)
    cfg_path = next((c / "course_info").glob("*_config.yaml"))
    cfg = config(c)
    cfg["course_id"], cfg["course_name"] = "SC", "2202  ดาราศาสตร์และอวกาศ"  # the old parse
    cfg_path.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")), yes=True)
    cfg = config(c)
    assert (str(cfg["course_id"]), cfg["course_name"]) == ("SC 2202", "ดาราศาสตร์และอวกาศ")
    assert course_sections(c) == ["51", "52"]


def test_adding_a_section_keeps_attendance_marks(here):
    c = one_section_course(here)
    xlsx = next((c / "data").glob("*_attendance.xlsx"))
    wb = openpyxl.load_workbook(xlsx)
    ws = wb.active
    ws.cell(row=2, column=3).value = "P"   # 69000001, a1
    ws.cell(row=3, column=4).value = "L"   # 69000003, a2
    wb.save(xlsx)
    attendance.auto_sync(c)
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")), yes=True)
    sheet = xlsx_rows(c)
    head = sheet[0]
    assert head[:4] == ["Student ID", "Name", "Sec", "a1"]
    by_sid = {r[0]: dict(zip(head, r)) for r in sheet[1:]}
    assert by_sid["69000001"]["a1"] == "P" and by_sid["69000003"]["a2"] == "L"
    assert by_sid["69000004"]["Sec"] == "52"
    X, C = attendance.read_xlsx_sheet(xlsx), attendance.read_csv_sheet(next((c / "data").glob("*_attendance.csv")))
    assert X.sessions == C.sessions and X.rows == C.rows and "Sec" not in X.sessions
    assert attendance.plan(c) is None or not attendance.plan(c).has_changes()


def test_undo_restores_the_one_section_course(here, monkeypatch):
    c = one_section_course(here)
    before = roster(c)
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")), yes=True)
    monkeypatch.chdir(c)
    grader.undo_course(None, None, yes=True)
    assert roster(c) == before and course_sections(c) == ["51"]


# ---- helpers ----------------------------------------------------------------------------------------------------
def test_section_helpers():
    secmap = {"3": "52", "1": "51", "2": "8", "4": ""}
    assert sort_sections(secmap.values()) == ["8", "51", "52"]
    assert counts(secmap) == "sec 8: 1 · sec 51: 1 · sec 52: 1 · no sec: 1"
    tag = tagger(secmap)
    assert tag("3") == "[52] " and tag("4") == "[?] "
    assert tagger({"1": "51"})("1") == ""


# ---- grade-tui bridge -------------------------------------------------------------------------------------------
def two_section_course(here) -> Path:
    """A two-section course with its score files made by `grader update`, and a few scores."""
    grader.init_course(None, None, None, [str(class_list(here / "repclasslist_Astro51.xlsx", "51")),
                                          str(class_list(here / "repclasslist_Astro52.xlsx", "52"))])
    c = here / "2026_S2_Astro_SEC_51-52"
    grader.update_course(config_file=str(next((c / "course_info").glob("*_config.yaml"))), yes=True)
    hw = next((c / "data").glob("*_homework.csv"))
    lines = hw.read_text(encoding="utf-8").splitlines()
    head = lines[0].split(",")
    out = [lines[0]]
    for i, line in enumerate(lines[1:]):
        cells = line.split(",")
        cells[head.index("hw1 (100pts)") if "hw1 (100pts)" in head else 2] = str(40 + 10 * i)
        out.append(",".join(cells))
    hw.write_text("\n".join(out) + "\n", encoding="utf-8")
    return c


def test_course_data_carries_sections(here):
    from src import tui_api
    c = two_section_course(here)
    d = tui_api.get_course_data(str(c))
    assert d["status"] == "success", d.get("traceback")
    assert d["sections"] == ["51", "52"]
    secs = {r["Student ID"]: r["Section"] for r in d["student_grades"]}
    assert secs == {r["Student ID"]: r["Section"] for r in d["raw_scores"]} == roster_sections(c)
    assert set(d["by_section"]) == {"51", "52"}
    n = {s: sum(v["count"] for v in d["by_section"][s]["grade_distribution"].values()) for s in ("51", "52")}
    assert n == {"51": 2, "52": 3}
    assert d["by_section"]["52"]["analytics"]["overview"]["total_count"] == 3
    for s in ("51", "52"):  # raw_index stays a whole-course row
        for r in d["by_section"][s]["analytics"]["at_risk"]:
            assert d["student_grades"][r["raw_index"]]["Student ID"] == r["student_id"]


def test_one_section_course_data_has_no_sections(here):
    from src import tui_api
    c = one_section_course(here)
    grader.update_course(config_file=str(next((c / "course_info").glob("*_config.yaml"))), yes=True)
    d = tui_api.get_course_data(str(c))
    assert d["sections"] == [] and d["by_section"] == {} and "Section" not in d["student_grades"][0]


# ---- exports ----------------------------------------------------------------------------------------------------
def test_export_writes_the_course_and_each_section(here):
    from src import tui_api
    c = two_section_course(here)
    assert tui_api.run_export(str(c))["status"] == "success"
    p = "2026_S2_Astro_SEC_51-52"
    rep = c / "reports"
    both = list(csv.DictReader(io.StringIO((rep / f"{p}_final_grades.csv").read_text(encoding="utf-8"))))
    assert list(both[0])[:3] == ["Student ID", "Name", "Section"] and len(both) == 5
    for sec, n in (("51", 2), ("52", 3)):
        rows = list(csv.DictReader(io.StringIO((rep / f"{p}_final_grades_sec{sec}.csv").read_text(encoding="utf-8"))))
        assert len(rows) == n and {r["Section"] for r in rows} == {sec}
        copy = (rep / f"{p}_copy_friendly_scores_sec{sec}.csv").read_text(encoding="utf-8").splitlines()
        assert len(copy) == n + 1


def test_export_of_a_one_section_course_is_as_before(here):
    from src import tui_api
    c = one_section_course(here)
    grader.update_course(config_file=str(next((c / "course_info").glob("*_config.yaml"))), yes=True)
    assert tui_api.run_export(str(c))["status"] == "success"
    names = sorted(f.name for f in (c / "reports").iterdir())
    assert names == ["2026_S2_Astro51_SEC_51_copy_friendly_scores.csv", "2026_S2_Astro51_SEC_51_final_grades.csv"]
    head = (c / "reports" / names[1]).read_text(encoding="utf-8").splitlines()[0]
    assert "Section" not in head


# ---- CLI output names sections ----------------------------------------------------------------------------------
def test_web_push_counts_students_per_section(here, drive_root, capsys):
    from src import webpush
    c = two_section_course(here)
    capsys.readouterr()
    webpush.push(c, drive_root)
    assert "5 students (sec 51: 2 · sec 52: 3)" in capsys.readouterr().out


def test_web_pull_accepts_a_push_made_before_the_id_fix(here, drive_root, capsys):
    """Pushed as course_id "SC", then `update -i` repairs it to "SC 2202": the Drive copy is still this course."""
    from src import webpull, webpush
    c = one_section_course(here)
    cfg_path = next((c / "course_info").glob("*_config.yaml"))
    cfg = config(c)
    cfg["course_id"], cfg["course_name"] = "SC", "2202  ดาราศาสตร์และอวกาศ"  # the old parse
    cfg_path.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    grader.update_course(config_file=str(cfg_path), yes=True)
    webpush.push(c, drive_root)
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")), yes=True)
    assert str(config(c)["course_id"]) == "SC 2202"
    capsys.readouterr()
    assert webpull.pull(c, drive_root) == 0
    assert "Nothing to pull" in capsys.readouterr().out
    cfg = config(c)
    cfg["course_id"] = "PHYS1120"
    cfg_path.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(webpull.Refused, match="another course"):
        webpull.pull(c, drive_root)


def test_web_pull_preview_tags_students_and_orders_by_section():
    from src.webpull import Change, preview
    def cell(sid, col, mac, val):
        c = Change([{"kind": "cell", "student_id": sid, "column": col, "original": mac, "value": val}])
        c.result, c.mac = "apply", mac
        return c
    changes = [cell("3", "hw1", "1", "2"), cell("1", "hw1", "", "5"), cell("2", "hw1", "4", "6")]
    out = preview(changes, {"1": "52", "2": "51", "3": "51"})
    lines = [l for l in out if " hw1: " in l]
    assert lines == ["  [51] 2 hw1: 4 → 6", "  [51] 3 hw1: 1 → 2", "  [52] 1 hw1: (blank) → 5"]
    one = [l for l in preview(changes, {"1": "51", "2": "51", "3": "51"}) if " hw1: " in l]
    assert one[0] == "  3 hw1: 1 → 2", "one section: no tags, journal order"


def test_sync_preview_tags_attendance_lines(here):
    c = two_section_course(here)
    csv_path = next((c / "data").glob("*_attendance.csv"))
    text = csv_path.read_text(encoding="utf-8").splitlines()
    head = text[0].split(",")
    row = text[1].split(",")
    row[head.index("a1")] = "P"
    text[1] = ",".join(row)
    csv_path.write_text("\n".join(text) + "\n", encoding="utf-8")
    lines = attendance.describe(attendance.plan(c))
    assert any(l.strip().startswith(f"[51] {row[0]} a1") for l in lines), lines


def test_mock_course_has_two_sections(here):
    grader.mock_course()
    c = here / "courses" / "0_GenPhysMock"
    assert course_sections(c) == ["51", "52"]
    assert counts(roster_sections(c)) == "sec 51: 16 · sec 52: 14"
    assert list(config(c)["sections"]) == ["51", "52"]
    assert xlsx_rows(c)[0][:3] == ["Student ID", "Name", "Sec"]
