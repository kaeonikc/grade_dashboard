"""`grader init` names a course after its abbreviation: <term>_<abbr>_SEC_<n>/ and <term>_<abbr>_SEC_<n>_* files
(SPEC.md Part B). The class lists are fake xlsx files built here; the repo's repclasslist.xls is never read."""

import builtins
import io
import sys
from pathlib import Path

import openpyxl
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import grader  # noqa: E402

STUDENTS = [("69000001", "นาย ก  หนึ่ง"), ("69000002", "นาง ข  สอง")]


def class_list(path: Path, students=STUDENTS) -> Path:
    """A class list in the layout course_info_prep/convert_student_info.py reads (made-up university and people)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in (["มหาวิทยาลัยราชภัฏจำลอง"],
                ["วิทยาเขตจำลอง ภาคการศึกษา 1/2569"],
                ["ปริญญาตรี ภาคปกติ"],
                ["รหัสวิชา 9999901 ฟิสิกส์ยุคใหม่ หน่วยกิต 3(3-0-6) Sec 51"],
                ["ผู้สอน อาจารย์จำลอง"],
                ["วันเวลาเรียน จันทร์ 09:00-12:00 SC101"],
                ["ลำดับ", "รหัสประจำตัว", "ชื่อ - สกุล", "หมู่เรียน"],
                ["", "", "", ""]):
        ws.append(row)
    for i, (sid, name) in enumerate(students, 1):
        ws.append([i, sid, name, "G1"])
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
    term = tmp_path / "term"  # a folder of its own: conftest's autouse Drive root also lives in tmp_path
    term.mkdir()
    monkeypatch.chdir(term)
    monkeypatch.setattr(sys, "stdin", Stdin(False))
    return term


def files(d: Path) -> set[str]:
    return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file() and "history" not in p.parts}


def test_abbreviation_from_the_file_name(here, capsys):
    grader.init_course(None, None, None, str(class_list(here / "repclasslist_ModPhys.xlsx")))
    c = here / "2026_S1_ModPhys_SEC_51"
    p = "2026_S1_ModPhys_SEC_51"
    assert {f"course_info/{p}_config.yaml", f"course_info/{p}_student_info.csv",
            f"data/{p}_attendance.xlsx", f"data/{p}_attendance.csv"} <= files(c)
    assert not any("_grading" in f or "ฟิสิกส์" in f for f in files(here))
    cfg = yaml.safe_load((c / "course_info" / f"{p}_config.yaml").read_text(encoding="utf-8"))
    assert cfg["course_name"] == "ฟิสิกส์ยุคใหม่" and str(cfg["course_id"]) == "9999901"
    assert "(abbreviation ModPhys from the file name)" in capsys.readouterr().out


def test_abbr_option_wins_over_the_file_name(here, capsys):
    grader.init_course(None, None, None, str(class_list(here / "repclasslist_ModPhys.xlsx")), "MP")
    assert (here / "2026_S1_MP_SEC_51" / "course_info" / "2026_S1_MP_SEC_51_config.yaml").exists()
    assert not (here / "2026_S1_ModPhys_SEC_51").exists()
    assert "--abbr MP overrides ModPhys from the file name" in capsys.readouterr().out


def test_no_abbreviation_and_no_terminal_uses_the_course_id(here, capsys):
    grader.init_course(None, None, None, str(class_list(here / "repclasslist.xlsx")))
    assert (here / "2026_S1_9999901_SEC_51").is_dir()
    assert "using the course ID 9999901" in capsys.readouterr().out


def test_prompt_asks_until_valid(here, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", Stdin(True))
    answers = iter(["bad name", "ModPhys"])
    asked = []
    monkeypatch.setattr(builtins, "input", lambda q: asked.append(q) or next(answers))
    grader.init_course(None, None, None, str(class_list(here / "repclasslist.xlsx")))
    assert asked == ["Abbreviation for folder/file names [9999901]: "] * 2
    assert (here / "2026_S1_ModPhys_SEC_51").is_dir()
    assert "Course 9999901 ฟิสิกส์ยุคใหม่, SEC 51" in capsys.readouterr().out


def test_prompt_empty_answer_takes_the_default(here, monkeypatch):
    monkeypatch.setattr(sys, "stdin", Stdin(True))
    monkeypatch.setattr(builtins, "input", lambda q: "")
    grader.init_course(None, None, None, str(class_list(here / "repclasslist.xlsx")))
    assert (here / "2026_S1_9999901_SEC_51").is_dir()


@pytest.mark.parametrize("bad", ["ฟิสิกส์", "a b", "-x", "x" * 31, ""])
def test_invalid_abbr_stops_before_anything_is_created(here, bad):
    src = class_list(here / "repclasslist.xlsx")
    with pytest.raises(SystemExit):
        grader.init_course(None, None, None, str(src), bad)
    assert [p.name for p in here.iterdir()] == ["repclasslist.xlsx"]


def test_unusable_file_name_part_warns_and_falls_through(here, capsys):
    grader.init_course(None, None, None, str(class_list(here / "repclasslist_ModPhys (1).xlsx")))
    out = capsys.readouterr().out
    assert "can't be an abbreviation" in out and "using the course ID" in out
    assert (here / "2026_S1_9999901_SEC_51").is_dir()


def test_without_a_class_list(here):
    grader.init_course("สัมพัทธภาพ", "2026_S2", "P1", None, "GR")
    assert files(here / "2026_S2_GR") == {"course_info/2026_S2_GR_config.yaml"}


def test_update_keeps_the_course_prefix_for_the_roster(here):
    src = class_list(here / "repclasslist_ModPhys.xlsx")
    grader.init_course(None, None, None, str(src))
    class_list(src, STUDENTS + [("69000003", "นาย ค  สาม")])
    grader.update_course(input_file=str(src))
    info = here / "2026_S1_ModPhys_SEC_51" / "course_info"
    rosters = sorted(p.name for p in info.glob("*_student_info.csv"))
    assert rosters == ["2026_S1_ModPhys_SEC_51_student_info.csv"]
    assert "69000003" in (info / rosters[0]).read_text(encoding="utf-8")


def test_update_on_an_old_style_course_keeps_its_thai_prefix(here):
    src = class_list(here / "repclasslist_ModPhys.xlsx")
    grader.init_course(None, None, None, str(src))
    new, old = "2026_S1_ModPhys_SEC_51", "2026_S1_ฟิสิกส์ยุคใหม่_SEC_51"
    course = here / f"{old}_grading"
    (here / new).rename(course)
    for f in list(course.rglob(f"{new}_*")):
        f.rename(f.with_name(f.name.replace(new, old)))
    class_list(src, STUDENTS + [("69000003", "นาย ค  สาม")])
    grader.update_course(input_file=str(src))
    rosters = sorted(p.name for p in (course / "course_info").glob("*_student_info.csv"))
    assert rosters == [f"{old}_student_info.csv"]


def test_mock_course_uses_the_short_name(here):
    grader.mock_course()
    c = here / "courses" / "0_GenPhysMock"
    assert (c / "course_info" / "0_GenPhysMock_config.yaml").exists()
    assert grader.get_course_file_prefix(c) == "0_GenPhysMock"
    assert not any("_grading" in f for f in files(here / "courses"))
