"""Renaming a course to match its sections (SPEC_sections.md Revision 2, R2-R4): `grader update -i` offers it, the
rename covers history/ and the Drive copy, `grader undo` puts it back, and a push is offered after."""

import builtins
import json
import sys
from pathlib import Path

import pytest

import grader
from src import rename, webpush
from src.history import list_entries, snapshot
from src.sections import course_sections
from test_sections import SEC51, Stdin, class_list, config, here, one_section_course, roster  # noqa: F401

OLD, NEW = "2026_S2_Astro51_SEC_51", "2026_S2_Astro_SEC_51-52"


def add52(here, **kw):
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro52.xlsx", "52")), **kw)


def scored_course(here) -> Path:
    """The one-section course with score files and one score change in history/."""
    c = one_section_course(here)
    grader.update_course(config_file=str(c / "course_info" / f"{OLD}_config.yaml"), yes=True)
    hw = c / "data" / f"{OLD}_homework.csv"
    snapshot(c, [hw], "test", "edit")
    lines = hw.read_text(encoding="utf-8").splitlines()
    cells = lines[1].split(",")
    cells[2] = "7"
    hw.write_text("\n".join([lines[0], ",".join(cells), *lines[2:]]) + "\n", encoding="utf-8")
    return c


def answers(monkeypatch, *texts):
    """A terminal that answers each question in turn; returns the questions asked."""
    asked, queue = [], list(texts)
    monkeypatch.setattr(sys, "stdin", Stdin(True))
    monkeypatch.setattr(builtins, "input", lambda q="": (asked.append(q), queue.pop(0))[1])
    return asked


def names_under(course: Path, prefix: str) -> list[str]:
    return sorted(p.relative_to(course).as_posix() for p in course.rglob(f"{prefix}_*"))


# ---- the target name ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,secs,want", [
    (OLD, ["51", "52"], NEW),
    (OLD, ["51"], None),
    (NEW, ["51", "52"], None),
    (NEW, ["51", "52", "53"], "2026_S2_Astro_SEC_51-52-53"),
    ("2026_S2_PHYS1120_SEC_20", ["20", "21"], "2026_S2_PHYS1120_SEC_20-21"),
    ("2026_S2_Astro-51_SEC_51", ["51", "52"], "2026_S2_Astro_SEC_51-52"),
    ("9_ฟิสิกส์จำลอง_grading", ["51", "52"], None),
    ("2026_S1_Test_SEC_51_grading", ["51", "52"], None),
])
def test_target_name(name, secs, want):
    assert rename.target_name(name, secs) == want


# ---- what moves ---------------------------------------------------------------------------------------------------
def test_adding_a_section_renames_every_file_and_history(here):
    c = scored_course(here)
    add52(here, yes=True)
    new = here / NEW
    assert not c.exists() and new.is_dir()
    assert names_under(new, OLD) == []
    moved = names_under(new, NEW)
    for rel in (f"course_info/{NEW}_config.yaml", f"course_info/{NEW}_student_info.csv",
                f"course_info/{NEW}_config.yaml.bak", f"data/{NEW}_homework.csv", f"data/{NEW}_attendance.xlsx"):
        assert rel in moved
    assert any(r.startswith("history/") for r in moved)
    log = (new / "history" / "log.jsonl").read_text(encoding="utf-8")
    assert OLD + "_" not in log
    for e in list_entries(new):
        for f in e["files"]:
            assert (new / "history" / e["id"] / f).exists(), f
    for name in rename.SYNC_FILES:
        f = new / "history" / name
        if f.exists():
            assert OLD + "_" not in f.read_text(encoding="utf-8")
    assert course_sections(new) == ["51", "52"]
    last = list_entries(new)[-1]
    assert (last["action"], last["from"], last["to"]) == ("rename", OLD, NEW)


def test_undo_of_an_earlier_change_restores_the_renamed_file(here, monkeypatch):
    c = scored_course(here)
    before_edit = next(e for e in list_entries(c) if e["action"] == "edit")
    add52(here, yes=True)
    new = here / NEW
    monkeypatch.chdir(new)
    grader.undo_course(before_edit["id"], None, yes=True)
    row = (new / "data" / f"{NEW}_homework.csv").read_text(encoding="utf-8").splitlines()[1].split(",")
    assert row[2] == ""


def test_undo_renames_back_and_its_undo_renames_again(here, monkeypatch, capsys):
    scored_course(here)
    add52(here, yes=True)
    monkeypatch.chdir(here / NEW)
    grader.undo_course(None, None, yes=True)
    old = here / OLD
    assert old.is_dir() and not (here / NEW).exists()
    assert names_under(old, NEW) == [] and f"data/{OLD}_homework.csv" in names_under(old, OLD)
    assert course_sections(old) == ["51", "52"]  # only the name went back
    undo = list_entries(old)[-1]
    assert undo["action"] == "undo" and undo["to"] == OLD
    monkeypatch.chdir(old)
    grader.undo_course(undo["id"], None, yes=True)
    assert (here / NEW).is_dir() and not old.exists()
    assert names_under(here / NEW, OLD) == []


def test_history_lists_the_rename(here, monkeypatch, capsys):
    one_section_course(here)
    add52(here, yes=True)
    monkeypatch.chdir(here / NEW)
    capsys.readouterr()
    grader.history_course()
    assert f"[grader rename]" in capsys.readouterr().out


# ---- refusals ----------------------------------------------------------------------------------------------------
def test_an_existing_target_is_never_overwritten(here, capsys):
    c = one_section_course(here)
    (here / NEW).mkdir()
    add52(here, yes=True)
    assert c.is_dir() and course_sections(c) == ["51", "52"]  # the section is added, the name stays
    assert "already exists" in capsys.readouterr().out
    assert list((here / NEW).iterdir()) == []


def test_unpulled_web_edits_stop_the_rename(here, drive_root, capsys):
    c = one_section_course(here)
    webpush.push(c, drive_root)
    mirror = drive_root / "grade_courses" / "term" / OLD
    line = {"batch": "b-1", "seq": 0, "ts": "2026-10-30T09:00:00+07:00", "kind": "cell", "push": "p",
            "file": f"data/{OLD}_attendance.csv", "student_id": SEC51[0][0], "column": "a1", "value": "P",
            "original": ""}
    (mirror / "web_edits.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    add52(here, yes=True)
    out = capsys.readouterr().out
    assert "not pulled yet" in out and c.is_dir() and mirror.is_dir()
    assert not (here / NEW).exists() and not mirror.with_name(NEW).exists()


# ---- questions ---------------------------------------------------------------------------------------------------
def test_questions_come_in_order_and_no_keeps_the_name(here, drive_root, monkeypatch):
    c = one_section_course(here)
    webpush.push(c, drive_root)
    asked = answers(monkeypatch, "y", "n", "n")
    add52(here)
    assert [q.split()[1] for q in asked] == ["Add", "Rename", "The"]
    assert "Push now?" in asked[2] and "2 students, the course has 5" in asked[2]
    assert c.is_dir() and course_sections(c) == ["51", "52"]


def test_a_known_section_still_offers_the_rename(here, monkeypatch, capsys):
    """The Astro course as it is now: sec 52 is in, the name still says 51."""
    c = one_section_course(here)
    answers(monkeypatch, "y", "n")
    add52(here)
    monkeypatch.setattr(sys, "stdin", Stdin(False))   # no terminal, no -y: a hint, nothing renamed
    capsys.readouterr()
    add52(here)
    assert c.is_dir() and "-y renames it" in capsys.readouterr().out
    asked = answers(monkeypatch, "y")
    add52(here)
    assert [q.split()[1] for q in asked] == ["Rename"]
    assert (here / NEW).is_dir() and not c.exists()


# ---- the Drive copy ----------------------------------------------------------------------------------------------
def test_the_drive_copy_is_renamed_and_pushed(here, drive_root, capsys):
    c = one_section_course(here)
    webpush.push(c, drive_root)
    sem = drive_root / "grade_courses" / "term"
    add52(here, yes=True)
    assert not (sem / OLD).exists() and (sem / NEW).is_dir()
    files = [p.relative_to(sem / NEW).as_posix() for p in (sem / NEW).rglob("*") if p.is_file()]
    assert not [f for f in files if OLD in f] and f"course_info/{NEW}_student_info.csv" in files
    cj = json.loads((sem / NEW / "course.json").read_text(encoding="utf-8"))
    assert cj["folder"] == NEW and cj["renamed_from"] == [OLD]
    assert cj["sections"] == {"51": {"day": "ศ.", "time": "08:30-12:30"}, "52": {"day": "ศ.", "time": "08:30-12:30"}}
    assert len(roster(here / NEW)) == 5


def test_no_push_question_without_a_drive_copy(here, monkeypatch):
    one_section_course(here)
    asked = answers(monkeypatch, "y", "y")
    add52(here)
    assert [q.split()[1] for q in asked] == ["Add", "Rename"]


def test_score_files_missing_students_point_to_grader_update(here, drive_root, monkeypatch, capsys):
    c = scored_course(here)
    webpush.push(c, drive_root)
    capsys.readouterr()
    add52(here, yes=True)
    out = capsys.readouterr().out
    assert "Run grader update (no -i)" in out and "Push now" not in out
    monkeypatch.chdir(here / NEW)
    asked = answers(monkeypatch, "y")
    grader.update_course()
    assert len(asked) == 1 and "2 students, the course has 5" in asked[0]
    cj = json.loads((drive_root / "grade_courses" / "term" / NEW / "course.json").read_text(encoding="utf-8"))
    assert cj["folder"] == NEW
