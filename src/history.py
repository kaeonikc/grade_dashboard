"""
Shared, timestamped history of every write into a course folder (INTEGRATION.md).

Before a tool changes a file under <course>/ it copies the current version into

    <course>/history/<YYYYMMDD-HHMMSS>_<tool>_<action>/<path relative to course>

and appends one JSON line to <course>/history/log.jsonl:

    {"id", "ts", "tool", "action", "files", "cells", "note"}

`grader history` lists the entries and `grader undo [ID]` restores one.
exam_projects (`exam submit scores`) writes entries in the same format with tool "exam".
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

HISTORY = "history"
LOG = "log.jsonl"


def course_dir_of(path) -> Path | None:
    """The course folder (the one holding course_info/) that `path` lives in."""
    p = Path(path).resolve()
    for d in [p] + list(p.parents)[:3]:
        if (d / "course_info").is_dir():
            return d
    return None


def _safe(word: str) -> str:
    return "".join(c if c.isalnum() or c in "-." else "-" for c in str(word)) or "x"


class Entry:
    """One history entry. Files are copied the first time they are captured."""

    def __init__(self, course_dir, tool: str, action: str, note: str = ""):
        self.course = Path(course_dir).resolve()
        self.tool, self.action, self.note = tool, action, note
        self.files: list[str] = []
        self.dir: Path | None = None
        self.id: str | None = None

    def _open(self) -> Path:
        if self.dir is None:
            root = self.course / HISTORY
            root.mkdir(exist_ok=True)
            base = f"{datetime.now():%Y%m%d-%H%M%S}_{_safe(self.tool)}_{_safe(self.action)}"
            name, n = base, 2
            while (root / name).exists():
                name, n = f"{base}-{n}", n + 1
            (root / name).mkdir()
            self.dir, self.id = root / name, name
        return self.dir

    def capture(self, path) -> None:
        path = Path(path).resolve()
        rel = path.relative_to(self.course).as_posix()
        if rel in self.files or not path.exists():
            return
        dest = self._open() / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        self.files.append(rel)

    def close(self, cells: int | None = None, **extra) -> str | None:
        if not self.files:
            return None
        line = {"id": self.id, "ts": datetime.now().isoformat(timespec="seconds"), "tool": self.tool,
                "action": self.action, "files": self.files, "cells": cells, "note": self.note, **extra}
        with open(self.course / HISTORY / LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return self.id


def snapshot(course_dir, files, tool: str, action: str, note: str = "", cells: int | None = None,
             **extra) -> str | None:
    e = Entry(course_dir, tool, action, note)
    for f in files:
        e.capture(f)
    return e.close(cells, **extra)


def list_entries(course_dir) -> list[dict]:
    """Entries oldest first; only those whose snapshot folder still exists."""
    log = Path(course_dir) / HISTORY / LOG
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("id") and (Path(course_dir) / HISTORY / e["id"]).is_dir():
            out.append(e)
    return out


# Recomputed automatically (grade-tui's total column sync), so never the change you want back.
AUTOMATIC = {("grade-tui", "totals")}


def latest_undoable(course_dir) -> dict | None:
    """The newest real change: not an undo, not an automatic totals sync, not undone yet."""
    entries = list_entries(course_dir)
    undone = {e.get("undoes") for e in entries if e.get("action") == "undo"}
    for e in reversed(entries):
        if e.get("action") == "undo" or (e.get("tool"), e.get("action")) in AUTOMATIC or e["id"] in undone:
            continue
        return e
    return None


def later_changes(course_dir, entry_id: str) -> list[dict]:
    """Entries after `entry_id` that touched the same files (restoring it discards them)."""
    entries = list_entries(course_dir)
    ids = [e["id"] for e in entries]
    if entry_id not in ids:
        return []
    files = set(entries[ids.index(entry_id)]["files"])
    undone = {e.get("undoes") for e in entries if e.get("action") == "undo"}
    return [e for e in entries[ids.index(entry_id) + 1:]
            if files & set(e["files"]) and (e.get("tool"), e.get("action")) not in AUTOMATIC
            and e.get("action") != "undo" and e["id"] not in undone]


def restore(course_dir, entry_id: str) -> list[str]:
    """
    Puts back the files saved in `entry_id`. The current versions are saved
    first as a "grader undo" entry, so an undo can itself be undone.
    """
    course = Path(course_dir).resolve()
    entry = next((e for e in list_entries(course) if e["id"] == entry_id), None)
    if entry is None:
        raise KeyError(f"no history entry {entry_id!r}")
    snapshot(course, [course / f for f in entry["files"]], "grader", "undo", note=f"before restoring {entry_id}",
             undoes=entry_id)
    from src.csvio import atomic_write_bytes
    for rel in entry["files"]:
        atomic_write_bytes(course / rel, (course / HISTORY / entry_id / rel).read_bytes())
    return list(entry["files"])
