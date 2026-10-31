"""A Drive copy that can't be read (SPEC_drive_unreadable.md): Drive for Desktop not running, so macOS lists the folder
but every read fails. Every Drive command says so before writing anything. The unreadable file is simulated with
chmod 000."""

import json
import os
from pathlib import Path

import pytest

import grader
from src import webdrive, webpull, webpush
from src.sections import course_sections
from test_sections import SEC51, here, one_section_course, roster, sec_list, two_sections  # noqa: F401
from test_split import old_model

OLD, NEW = "2026_S2_Astro51_SEC_51", "2026_S2_Astro"
pytestmark = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads chmod 000 files")


@pytest.fixture
def lock():
    """lock(path): makes a file unreadable until the test ends."""
    locked = []

    def do(path: Path) -> Path:
        os.chmod(path, 0)
        locked.append(path)
        return path
    yield do
    for p in locked:
        if p.exists():
            os.chmod(p, 0o644)


def files(root: Path) -> dict:
    """{relative path: bytes, or None when it can't be read} of every file under root."""
    out = {}
    for p in sorted(root.rglob("*")) if root.is_dir() else []:
        if p.is_file():
            try:
                out[p.relative_to(root).as_posix()] = p.read_bytes()
            except OSError:
                out[p.relative_to(root).as_posix()] = None
    return out


def mirror_of(drive_root: Path, name: str = OLD) -> Path:
    return drive_root / "grade_courses" / "term" / name


def pushed(here, drive_root, course=None) -> Path:
    """A course (the flat one-section course by default), pushed, with an archive file on its Drive copy."""
    c = course or one_section_course(here)
    webpush.push(c, drive_root)
    arch = mirror_of(drive_root, c.name) / "archive" / "web_edits_20261030-153000.jsonl"
    arch.parent.mkdir(exist_ok=True)
    arch.write_text(json.dumps({"kind": "pull", "lines": 0}) + "\n", encoding="utf-8")
    return c


def assert_message(out: str, file: str):
    assert "Can't read the web copy" in out and file in out and "Google Drive for Desktop" in out, out
    assert "Traceback" not in out


# ---- grader commands ---------------------------------------------------------------------------------------------
def test_adding_a_section_to_a_flat_course_waits_for_drive(here, drive_root, lock, capsys):
    """Moving the course into section folders needs its web copy read first; nothing changes until it can be."""
    c = pushed(here, drive_root)
    lock(next((mirror_of(drive_root) / "archive").glob("*.jsonl")))
    before = files(mirror_of(drive_root)), files(c)
    capsys.readouterr()
    with pytest.raises(SystemExit):
        grader.update_course(input_file=str(sec_list(here, "52")), yes=True)
    out = capsys.readouterr().out
    assert_message(out, "archive/web_edits_20261030-153000.jsonl")
    assert "Nothing was split." in out
    assert c.is_dir() and not (here / NEW).exists() and (files(mirror_of(drive_root)), files(c)) == before


def test_grader_split_waits_for_drive(here, drive_root, lock, capsys):
    c = pushed(here, drive_root, old_model(here))
    lock(mirror_of(drive_root) / "push.json")
    capsys.readouterr()
    with pytest.raises(SystemExit):
        grader.split_cmd(str(c), yes=True)
    assert_message(capsys.readouterr().out, "push.json")
    assert c.is_dir() and not (here / NEW).exists()


def test_plain_update_skips_the_push_question(here, drive_root, lock, monkeypatch, capsys):
    from test_sections import answer, class_list
    c = pushed(here, drive_root)
    grader.update_course(input_file=str(class_list(here / "repclasslist_Astro51.xlsx", "51",
                                                   students=SEC51 + [("69000009", "นาย ฌ  เก้า")])))
    lock(mirror_of(drive_root) / "course.json")
    monkeypatch.chdir(c)
    answer(monkeypatch, "y")  # a terminal; every question is recorded
    asked = []
    monkeypatch.setattr("builtins.input", lambda q="": asked.append(q) or "y")
    capsys.readouterr()
    grader.update_course()
    out = capsys.readouterr().out
    assert_message(out, "course.json")
    assert "Not pushed." in out and not any("Push now" in q for q in asked)


# ---- web-push, web-pull ------------------------------------------------------------------------------------------
def test_web_push_refuses_and_writes_nothing(here, drive_root, lock):
    c = pushed(here, drive_root)
    lock(mirror_of(drive_root) / "course.json")
    before = files(mirror_of(drive_root))
    with pytest.raises(webdrive.Refused) as e:
        webpush.push(c, drive_root)
    assert_message(str(e.value), "course.json")
    assert "Nothing on Drive was changed." in str(e.value)
    assert files(mirror_of(drive_root)) == before


def test_web_push_of_a_course_with_sections_refuses_too(here, drive_root, lock):
    c = pushed(here, drive_root, two_sections(here))
    lock(mirror_of(drive_root, NEW) / "push.json")
    with pytest.raises(webdrive.Refused) as e:
        webpush.push(c / "sec51", drive_root)
    assert_message(str(e.value), "push.json")


def test_web_pull_refuses_and_applies_nothing(here, drive_root, lock):
    c = pushed(here, drive_root)
    lock(mirror_of(drive_root) / "push.json")
    before = files(c)
    with pytest.raises(webdrive.Refused) as e:
        webpull.pull(c, drive_root, yes=True)
    assert_message(str(e.value), "push.json")
    assert "Nothing was pulled." in str(e.value)
    assert files(c) == before


# ---- the check itself --------------------------------------------------------------------------------------------
def test_check_readable_passes_a_missing_or_readable_copy(here, drive_root):
    webdrive.check_readable(drive_root / "nowhere")
    pushed(here, drive_root)
    webdrive.check_readable(mirror_of(drive_root))


def test_archived_keys_reports_an_unreadable_archive(here, drive_root, lock):
    pushed(here, drive_root)
    lock(next((mirror_of(drive_root) / "archive").glob("*.jsonl")))
    with pytest.raises(webdrive.Unreadable):
        webdrive.unpulled(mirror_of(drive_root))


def test_an_unreadable_journal_keeps_its_own_message(here, drive_root, lock):
    """web_edits.jsonl is read by journal(), whose message (web/SPEC.md edge 19) stays."""
    pushed(here, drive_root)
    lock(mirror_of(drive_root) / "web_edits.jsonl")
    with pytest.raises(webdrive.Unreadable, match="Couldn't read grade_courses/term/"):
        webdrive.journal(mirror_of(drive_root))
