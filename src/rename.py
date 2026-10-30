"""
Renaming a course folder to match its sections (SPEC_sections.md, Revision 2: R2-R4).

`2026_S2_Astro51_SEC_51` that now holds sec 51 and 52 becomes `2026_S2_Astro_SEC_51-52`. Everything named after the
course moves with it: the folder, every `<prefix>_*` file (history snapshots and .bak files included), the paths in
history/log.jsonl and the sync baselines, and the Drive copy (renamed in place, so Drive keeps its file IDs). The
rename is a history entry of its own, so `grader undo` can put the old name back.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from src import webdrive
from src.history import HISTORY, LOG
from src.webdrive import Refused, Unreadable

_NAME = re.compile(r"^(?P<term>\d{4}_S\d+)_(?P<abbr>.+?)_SEC_(?P<secs>[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*)$")
SYNC_FILES = ("attendance_sync.json", "config_sync.json")


def target_name(name: str, sections) -> str | None:
    """
    The name a course folder (or file prefix) `<term>_<abbr>_SEC_<secs>` should have for `sections`, or None when
    it already matches or isn't in that form (`…_grading` folders). A trailing section number is taken off the
    abbreviation (`Astro51` → `Astro`), never digits of a course code (`PHYS1120` stays).
    """
    m = _NAME.match(name)
    secs = [str(s) for s in sections]
    if not m or not secs:
        return None
    want = "-".join(secs)
    if m["secs"] == want:
        return None
    abbr = m["abbr"]
    for s in sorted(set(m["secs"].split("-")) | set(secs), key=len, reverse=True):
        rest = abbr[:-len(s)].rstrip("-_") if abbr.endswith(s) else ""
        if rest and not rest[-1].isdigit():
            abbr = rest
            break
    return f"{m['term']}_{abbr}_SEC_{want}"


def _swap_path(text: str, old: str, new: str) -> str:
    """`data/<old>_homework.csv` → `data/<new>_homework.csv`: only a last path part that starts with `<old>_`."""
    head, sep, last = text.rpartition("/")
    return f"{head}{sep}{new}{last[len(old):]}" if last.startswith(f"{old}_") else text


def _swap_json(obj, old: str, new: str):
    if isinstance(obj, str):
        return _swap_path(obj, old, new)
    if isinstance(obj, list):
        return [_swap_json(v, old, new) for v in obj]
    if isinstance(obj, dict):
        return {_swap_json(k, old, new): _swap_json(v, old, new) for k, v in obj.items()}
    return obj


def _files_to_move(course: Path, old: str, new: str) -> list[tuple[Path, Path]]:
    return [(p, p.with_name(new + p.name[len(old):])) for p in sorted(course.rglob(f"{old}_*")) if p.is_file()]


def drive_copy(course: Path, root=None) -> tuple[Path, Path] | None:
    """(Drive root, the course's Drive copy) when Drive is there and holds a copy of this course; else None."""
    try:
        root = webdrive.drive_root(root)
    except Refused:
        return None
    mirror = webdrive.place_of(root, course)[0]
    return (root, mirror) if mirror.is_dir() else None


def plan(course: Path, new_name: str, root=None, new_prefix: str | None = None) -> dict:
    """
    What a rename to `new_name` does, after every check (Refused names the problem; nothing is changed). The files'
    prefix follows the folder when it is the folder's name, else it gets the same new sections (or stays).
    """
    from src.data_loader import get_course_file_prefix
    course = Path(course).resolve()
    old_name = course.name
    prefix = get_course_file_prefix(course)
    if new_prefix is None:
        new_prefix = new_name if prefix == old_name else (
            target_name(prefix, _NAME.match(new_name)["secs"].split("-")) or prefix)
    dest = course.with_name(new_name)
    if dest.exists():
        raise Refused(f"❌ {dest.name} already exists next to {old_name}. Nothing was renamed.")
    moves = _files_to_move(course, prefix, new_prefix) if new_prefix != prefix else []
    taken = [b for _, b in moves if b.exists()]
    if taken:
        raise Refused(f"❌ {taken[0].relative_to(course)} already exists. Nothing was renamed.")
    drive = drive_copy(course, root)
    if drive:
        _, mirror = drive
        webdrive.check_readable(mirror, "Nothing was renamed.")  # before the folder and the copy move together (U3)
        waiting = webdrive.unpulled(mirror)
        if waiting:
            raise Refused(f"❌ The web copy {webdrive.label(mirror)} has {len(waiting)} edit(s) not pulled yet. "
                          "Bring them in first (grader web-pull), then run this again. Nothing was renamed.")
        if mirror.with_name(new_name).exists():
            raise Refused(f"❌ Drive already has {webdrive.label(mirror.with_name(new_name))}. Nothing was renamed.")
    return {"course": course, "from": old_name, "to": new_name, "from_prefix": prefix, "to_prefix": new_prefix,
            "moves": moves, "drive": drive}


def apply(p: dict) -> Path:
    """Carries out a plan(); returns the course folder's new path."""
    course, old, new = p["course"], p["from_prefix"], p["to_prefix"]
    for a, b in p["moves"]:
        a.rename(b)
    hist = course / HISTORY
    if new != old and (hist / LOG).exists():
        lines = []
        for text in (hist / LOG).read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(text)
            except ValueError:
                lines.append(text)
                continue
            if isinstance(e, dict) and isinstance(e.get("files"), list):
                e["files"] = [_swap_path(f, old, new) for f in e["files"]]
            lines.append(json.dumps(e, ensure_ascii=False))
        (hist / LOG).write_text("".join(f"{l}\n" for l in lines), encoding="utf-8")
    for name in SYNC_FILES if new != old else ():
        f = hist / name
        if f.is_file():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            f.write_text(json.dumps(_swap_json(data, old, new), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    dest = course.with_name(p["to"])
    course.rename(dest)
    if p["drive"]:
        _, mirror = p["drive"]
        mirror.rename(mirror.with_name(p["to"]))
    return dest


def _log(course: Path, p: dict, **extra) -> str:
    hist = course / HISTORY
    hist.mkdir(exist_ok=True)
    base = f"{datetime.now():%Y%m%d-%H%M%S}_grader_{extra.get('action', 'rename')}"
    name, n = base, 2
    while (hist / name).exists():
        name, n = f"{base}-{n}", n + 1
    (hist / name).mkdir()
    line = {"id": name, "ts": datetime.now().isoformat(timespec="seconds"), "tool": "grader", "action": "rename",
            "files": [], "cells": None, "note": f"{p['from']} → {p['to']}", "from": p["from"], "to": p["to"],
            "from_prefix": p["from_prefix"], "to_prefix": p["to_prefix"], **extra}
    with open(hist / LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return name


def rename(course: Path, new_name: str, root=None) -> Path:
    """Renames the course (plan + apply) and logs it. Refused when a check fails, before anything changes."""
    p = plan(course, new_name, root)
    dest = apply(p)
    _log(dest, p)
    return dest


def is_rename(entry: dict) -> bool:
    return bool(entry.get("from") and entry.get("to"))


def undo(course: Path, entry: dict, root=None) -> Path:
    """Puts the name `entry` (a rename, or the undo of one) replaced back; logged as an undo of `entry`."""
    course = Path(course).resolve()
    if course.name != entry["to"]:
        raise Refused(f"❌ This course is {course.name} now, not {entry['to']} (renamed again since?). "
                      "Nothing was renamed.")
    p = plan(course, entry["from"], root, new_prefix=entry.get("from_prefix"))
    dest = apply(p)
    _log(dest, p, action="undo", undoes=entry["id"])
    return dest


def renamed_from(course: Path) -> list[str]:
    """The names this course had before (from its history), for grade_web to carry drafts over."""
    from src.history import list_entries
    names = [e["from"] for e in list_entries(course) if is_rename(e)]
    return sorted({n for n in names if n != Path(course).resolve().name})


def done_lines(old: str, new: str) -> list[str]:
    return [f"📁 Renamed {old} → {new}",
            f"   Your shell is still in the old path: cd ../{new}",
            "   If an exam links this course (grading_dir:), run exam submit link again."]


# ---- the questions update -i asks ---------------------------------------------------------------------------------
def _ask(question: str, yes: bool, hint: str) -> bool:
    import sys
    if yes:
        return True
    if not sys.stdin.isatty():
        print(f"ℹ️  {hint}")
        return False
    return input(f"❓ {question} [y/N] ").strip().lower() in ("y", "yes")


def offer(course: Path, sections, yes: bool, again: str, root=None) -> Path:
    """
    `update -i`: when the folder name doesn't match its sections, asks to rename it. Returns the course's path
    (renamed or not). `again` is the command to suggest when there's no terminal to ask on.
    """
    course = Path(course).resolve()
    new = target_name(course.name, sections)
    if not new:
        return course
    if not _ask(f"Rename {course.name} → {new}?", yes, f"{course.name} could be named {new}: {again} -y renames it."):
        return course
    try:
        dest = rename(course, new, root)
    except Unreadable as e:  # the roster update before it needs no Drive, so it stands (SPEC_drive_unreadable U1)
        print(warning(e))
        print("   The roster was updated; only the rename waits.")
        return course
    except Refused as e:
        print(e)
        return course
    for line in done_lines(course.name, new):
        print(line)
    return dest


def offer_push(course: Path, yes: bool, reason: str, root=None, only_if_counts_differ: bool = False) -> None:
    """
    After a section was added or the course renamed: asks to push when Drive holds a copy of it. With
    `only_if_counts_differ` (plain `grader update`), only when the copy's student count isn't the course's.
    """
    drive = drive_copy(course, root)
    if not drive:
        return
    root, mirror = drive
    try:
        webdrive.check_readable(mirror, "Not pushed.")
        webdrive.journal(mirror)
    except Unreadable as e:
        print(warning(e))
        return
    from src.sections import roster_file
    here, there = roster_file(course), next((mirror / "course_info").glob("*_student_info.csv"), None)
    n_here = _count(here)
    n_there = _count(there)
    if only_if_counts_differ and n_there == n_here:
        return
    what = (f"The web copy has {n_there} students, the course has {n_here}." if n_there != n_here
            else f"The web copy is out of date ({reason}).")
    if not _ask(f"{what} Push now?", yes, f"{what} Run grader web-push so the phone sees it."):
        return
    from src import webpush
    try:
        webpush.push(course, root)
    except Refused as e:
        print(e)


def _count(roster) -> int:
    if roster is None or not Path(roster).is_file():
        return 0
    import csv
    import io
    try:
        text = Path(roster).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return 0
    rows = list(csv.reader(io.StringIO(text, newline="")))
    return sum(1 for r in rows[1:] if r and r[0].strip())


def warning(e: Exception) -> str:
    """A refusal shown as a warning (the command carries on): ❌ → ⚠️."""
    text = str(e)
    return "⚠️ " + text[1:].lstrip() if text.startswith("❌") else text
