"""Unit tests for src/webdrive.py: journal reading, archived keys, conflict copies, archive names, display width."""
import json

import pytest

from src import webdrive
from webtools import JOURNALS, put_archive, put_journal


def test_journal_skips_blank_lines_and_names_bad_ones(tmp_path):
    good = '{"batch":"b-1","seq":0,"ts":"2027-01-20T09:15:00+07:00"}'
    (tmp_path / "web_edits.jsonl").write_text(f"{good}\n\n[1]\n{{\"seq\":1}}\n{good[:20]}\n", encoding="utf-8")
    with pytest.raises(webdrive.Refused, match=r"aren't valid JSON: 3, 4, 5\."):
        webdrive.journal(tmp_path)
    (tmp_path / "web_edits.jsonl").write_text(f"{good}\n\n", encoding="utf-8")
    assert [webdrive.key(l) for l in webdrive.journal(tmp_path)] == ["b-1#0"]


def test_missing_journal_is_empty(tmp_path):
    assert webdrive.journal(tmp_path) == [] and webdrive.unpulled(tmp_path) == []


def test_unpulled_is_journal_minus_archived_keys(tmp_path):
    put_journal(tmp_path, "seven_lines.jsonl")
    put_archive(tmp_path)
    exp = json.loads((JOURNALS / "expected.json").read_text(encoding="utf-8"))["journals"]["seven_lines.jsonl"]
    left = webdrive.unpulled(tmp_path)
    assert len(left) == exp["unpulled"]
    assert webdrive.last_saved(left) == exp["last_saved"]
    assert webdrive.fmt_time(exp["last_saved"]) == "20 Jan 2027 09:45"


def test_conflict_copies_outside_archive(tmp_path):
    for rel in ["web_edits (1).jsonl", "data/x_homework (2).csv", "course.json", "data/x (draft).csv",
                "archive/web_edits_20270101-000000 (1).jsonl"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    assert webdrive.conflict_copies(tmp_path) == ["data/x_homework (2).csv", "web_edits (1).jsonl"]


def test_archive_names_never_overwrite(tmp_path):
    a = webdrive.write_archive(tmp_path, {"kind": "discarded"}, [{"batch": "b", "seq": 0}], "_discarded")
    b = webdrive.write_archive(tmp_path, {"kind": "discarded"}, [], "_discarded")
    assert a != b and a.exists() and b.exists()
    assert webdrive.archived_keys(tmp_path) == {"b#0"}


def test_display_width_ignores_thai_marks():
    assert webdrive.width("นายสมมติ") == 7
    assert webdrive.pad("ฟิสิกส์", 6) == "ฟิสิกส์  "
