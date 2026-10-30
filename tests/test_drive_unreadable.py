"""A Drive copy that can't be read (SPEC_drive_unreadable.md): Drive for Desktop not running, so macOS lists the folder
but every read fails. Every Drive command says so before writing anything; `update -i` keeps its roster update and
skips the rename and push. The unreadable file is simulated with chmod 000."""

import json
import os
from pathlib import Path

import pytest

import grader
from src import webdrive, webpull, webpush
from src.history import list_entries
from src.sections import course_sections
from test_rename import NEW, OLD, add52, answers, scored_course
from test_sections import here, one_section_course  # noqa: F401

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


def pushed(here, drive_root) -> Path:
    """The one-section course, pushed, with an archive file on its Drive copy (as after a pull)."""
    c = one_section_course(here)
    webpush.push(c, drive_root)
    arch = mirror_of(drive_root) / "archive" / "web_edits_20261030-153000.jsonl"
    arch.parent.mkdir(exist_ok=True)
    arch.write_text(json.dumps({"kind": "pull", "lines": 0}) + "\n", encoding="utf-8")
    return c


def assert_message(out: str, file: str):
    assert "Can't read the web copy" in out and file in out and "Google Drive for Desktop" in out, out
    assert "Traceback" not in out


# ---- update -i ---------------------------------------------------------------------------------------------------
def test_update_adds_the_section_and_skips_the_rename(here, drive_root, lock, capsys):
    c = pushed(here, drive_root)
    lock(next((mirror_of(drive_root) / "archive").glob("*.jsonl")))
    before = files(mirror_of(drive_root))
    capsys.readouterr()
    add52(here, yes=True)
    out = capsys.readouterr().out
    assert_message(out, "archive/web_edits_20261030-153000.jsonl")
    assert "⚠️" in out and "Nothing was renamed." in out and "The roster was updated; only the rename waits." in out
    assert course_sections(c) == ["51", "52"]
    assert c.is_dir() and not (here / NEW).exists() and not mirror_of(drive_root, NEW).exists()
    assert files(mirror_of(drive_root)) == before
    assert not [e for e in list_entries(c) if e["action"] == "rename"]


def test_a_known_section_with_an_unreadable_push_json(here, drive_root, lock, monkeypatch, capsys):
    """The Astro course on 31 Oct: both sections in, the old name, Drive for Desktop not running."""
    c = pushed(here, drive_root)
    answers(monkeypatch, "y", "n", "n")
    add52(here)
    lock(mirror_of(drive_root) / "push.json")
    before = files(mirror_of(drive_root))
    capsys.readouterr()
    add52(here, yes=True)
    out = capsys.readouterr().out
    assert_message(out, "push.json")
    assert c.is_dir() and not (here / NEW).exists() and files(mirror_of(drive_root)) == before


def test_plain_update_skips_the_push_question(here, drive_root, lock, monkeypatch, capsys):
    c = scored_course(here)
    webpush.push(c, drive_root)
    lock(mirror_of(drive_root) / "course.json")
    add52(here, yes=True)   # rename skipped (the copy can't be read); the score files miss sec 52
    assert c.is_dir()
    monkeypatch.chdir(c)
    answers(monkeypatch)    # no answers: any question would fail the test
    capsys.readouterr()
    grader.update_course()
    out = capsys.readouterr().out
    assert_message(out, "course.json")
    assert "Not pushed." in out and "Push now" not in out


def test_an_unreadable_journal_keeps_its_own_message(here, drive_root, lock, capsys):
    """web_edits.jsonl is read by journal(), whose message (web/SPEC.md edge 19) stays; update -i still carries on."""
    c = pushed(here, drive_root)
    lock(mirror_of(drive_root) / "web_edits.jsonl")
    capsys.readouterr()
    add52(here, yes=True)
    out = capsys.readouterr().out
    assert "⚠️ Couldn't read grade_courses/term/" in out and "The roster was updated" in out and "Traceback" not in out
    assert course_sections(c) == ["51", "52"] and c.is_dir() and not (here / NEW).exists()


# ---- web-push, web-pull, undo ------------------------------------------------------------------------------------
def test_web_push_refuses_and_writes_nothing(here, drive_root, lock):
    c = pushed(here, drive_root)
    lock(mirror_of(drive_root) / "course.json")
    before = files(mirror_of(drive_root))
    with pytest.raises(webdrive.Refused) as e:
        webpush.push(c, drive_root)
    assert_message(str(e.value), "course.json")
    assert "Nothing on Drive was changed." in str(e.value)
    assert files(mirror_of(drive_root)) == before


def test_web_pull_refuses_and_applies_nothing(here, drive_root, lock):
    c = pushed(here, drive_root)
    lock(mirror_of(drive_root) / "push.json")
    before = files(c)
    with pytest.raises(webdrive.Refused) as e:
        webpull.pull(c, drive_root, yes=True)
    assert_message(str(e.value), "push.json")
    assert "Nothing was pulled." in str(e.value)
    assert files(c) == before


def test_undo_of_a_rename_refuses(here, drive_root, lock, monkeypatch, capsys):
    pushed(here, drive_root)
    add52(here, yes=True)   # readable: renamed and pushed
    new = here / NEW
    rid = next(e["id"] for e in list_entries(new) if e["action"] == "rename")
    lock(mirror_of(drive_root, NEW) / "push.json")
    monkeypatch.chdir(new)
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        grader.undo_course(rid, None, yes=True)
    assert e.value.code == 1
    assert_message(capsys.readouterr().out, "push.json")
    assert new.is_dir() and not (here / OLD).exists() and mirror_of(drive_root, NEW).is_dir()


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
