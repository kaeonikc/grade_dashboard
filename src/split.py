"""
`grader split` (SPEC_section_folders.md F9): a one-folder course whose roster has a `Section` column becomes a course
with one sub-folder per section.

    2026_S2_Astro51_SEC_51/                       2026_S2_Astro/
      course_info/<old>_config.yaml        →        course_info/2026_S2_Astro_config.yaml   (sections[N].folder)
      course_info/<old>_student_info.csv            history/  reports/
      data/<old>_homework.csv …                     sec51/course_info/2026_S2_Astro_SEC_51_student_info.csv
                                                    sec51/data/2026_S2_Astro_SEC_51_homework.csv …  (sec 51's rows)
                                                    sec52/ …

Every score row and attendance mark goes to its student's section; headers, `(Npts)` and cell text are kept as they
are. The old folder is renamed `<old>_before_split` and keeps its history; the new course's history starts with the
split, and `grader undo` of it puts the old folder back. The same move turns a flat one-section course into the
layout when `grader update -i` adds a second section ("promote": every student in the config's sec_num).
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src import course as course_mod
from src import webdrive
from src.course import SECTION_KEYS
from src.csvio import CsvText, read_csv_text, write_csv_text
from src.webdrive import Refused

BEFORE = "_before_split"
_FOLDER = re.compile(r"^(?P<term>\d{4}_S\d+)_(?P<abbr>.+?)(?:_SEC_[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*)?$")
SENTINELS = {"max", "max score", "full score", "full"}


def layout_name(folder_name: str, sections) -> str | None:
    """
    The course folder's name in the layout, `<term>_<abbr>`: `2026_S2_Astro51_SEC_51` → `2026_S2_Astro` (a trailing
    section number is taken off the abbreviation, never digits of a course code: `PHYS1120` stays). None when the
    name doesn't start with a term.
    """
    m = _FOLDER.match(folder_name.removesuffix("_grading"))
    if not m:
        return None
    abbr = m["abbr"]
    for s in sorted({str(x) for x in sections}, key=len, reverse=True):
        rest = abbr[:-len(s)].rstrip("-_") if abbr.endswith(s) else ""
        if rest and not rest[-1].isdigit():
            abbr = rest
            break
    return f"{m['term']}_{abbr}"


def layout_config(raw: dict, sections, folders: dict | None = None) -> dict:
    """
    A config for the layout from a flat one: the same keys in the same order, without the top-level sec_num and
    schedules, and `sections:` (where sec_num was) with each section's folder and schedules. A section's schedules
    come from the old `sections[N]`, else, for the old sec_num, from the top-level keys.
    """
    by_sec = {str(k).strip(): v for k, v in (raw.get("sections") or {}).items() if isinstance(v, dict)}
    top = str(raw.get("sec_num") or "").strip()
    secs = {}
    for num in sections:
        num = str(num)
        entry = by_sec.get(num) or ({k: raw.get(k) for k in SECTION_KEYS} if num == top else {})
        secs[num] = {"folder": (folders or {}).get(num) or str(entry.get("folder") or f"sec{num}")}
        for key in SECTION_KEYS:
            if entry.get(key) is not None:
                secs[num][key] = copy.deepcopy(entry[key])
    out, placed = {}, False
    for key, val in raw.items():
        if key in ("sec_num", "sections") + SECTION_KEYS:
            if not placed:
                out["sections"], placed = secs, True
            continue
        out[key] = val
    if not placed:
        out["sections"] = secs
    return out


def dump_yaml(path: Path, data: dict) -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---- rows by student ---------------------------------------------------------------------------------------------
def _sid_col(doc: CsvText) -> int | None:
    return doc.col("Student ID")


def keep_rows(doc: CsvText, ids: set, drop: tuple = ()) -> CsvText:
    """A copy with only the rows of `ids` (and any Max/Full Score row), and without the columns named in `drop`."""
    i = _sid_col(doc)
    gone = [j for j, h in enumerate(doc.header) if h.strip() in drop]
    pick = lambda row: [v for j, v in enumerate(row) if j not in gone]
    rows = [r for r in doc.rows if i is None or r[i].strip() in ids or r[i].strip().lower() in SENTINELS]
    return CsvText(pick(doc.header), [pick(r) for r in rows], doc.bom, doc.eol)


def data_files(folder: Path) -> list[Path]:
    """The score and attendance csv files of a folder's data/ (no .bak, no hidden files)."""
    data = folder / "data"
    return sorted(p for p in data.glob("*.csv") if not p.name.startswith(".")) if data.is_dir() else []


def suffix_of(name: str, prefix: str) -> str:
    """`homework.csv` of `<prefix>_homework.csv` (a file not named after the course keeps its name)."""
    return name[len(prefix) + 1:] if name.startswith(f"{prefix}_") else name


# ---- the plan ------------------------------------------------------------------------------------------------------
@dataclass
class Plan:
    course: Path            # the one-folder course
    target: Path            # the new course folder
    secmap: dict            # {student id: section}
    sections: list          # in numeric order
    old_prefix: str
    new_prefix: str
    raw: dict               # the old config as written
    drive: tuple | None     # (Drive root, the old course's Drive copy)
    promote: bool


def plan(course, secmap: dict | None = None, root=None, name: str | None = None) -> Plan:
    """Every check before anything is written; Refused names the problem. `name`: the new folder's name instead of
    the one made from the old folder's (grader mock)."""
    from src.attendance import plan as att_plan
    from src.rename import drive_copy
    from src.sections import section_column, sort_sections
    from src.sync import prefix_of, raw_config
    course = Path(course).resolve()
    c = course_mod.at(course)
    if c is None or c.root != course:
        raise Refused(f"❌ {course.name} is not a course folder (no course_info/*_config.yaml). Nothing was split.")
    if c.layout:
        raise Refused(f"❌ {course.name} already has section folders. Nothing to split.")
    promote = secmap is not None
    secmap = secmap if promote else section_column(course)
    sections = sort_sections(secmap.values())
    if not promote and len(sections) < 2:
        raise Refused(f"❌ {course.name}'s roster doesn't name two sections (its Section column). Nothing to split.")
    blank = sorted(sid for sid, s in secmap.items() if not s)
    if blank:
        more = f" (+{len(blank) - 5} more)" if len(blank) > 5 else ""
        raise Refused(f"❌ {len(blank)} student(s) have no Section in the roster: {', '.join(blank[:5])}{more}. Fill "
                      "their Section, then run grader split again. Nothing was split.")
    name = name or layout_name(course.name, sections)
    if name is None:
        raise Refused(f"❌ Can't tell the new name from {course.name} (it doesn't start with a term like 2026_S2_). "
                      "Nothing was split.")
    target = course.with_name(name)
    if target.exists():
        raise Refused(f"❌ {target.name} already exists next to {course.name}. Nothing was split.")
    if course.with_name(course.name + BEFORE).exists():
        raise Refused(f"❌ {course.name}{BEFORE} already exists. Nothing was split.")
    p = att_plan(course)
    if p is not None and p.has_changes():
        raise Refused("❌ The attendance xlsx and csv differ: run grader sync first. Nothing was split.")
    drive = drive_copy(course, root)
    if drive:
        _, mirror = drive
        webdrive.check_readable(mirror, "Nothing was split.")
        waiting = webdrive.unpulled(mirror)
        if waiting:
            raise Refused(f"❌ The web copy {webdrive.label(mirror)} has {len(waiting)} edit(s) not pulled yet. Bring "
                          "them in first (grader web-pull), then run this again. Nothing was split.")
    return Plan(course, target, secmap, sections, prefix_of(course), name, raw_config(course), drive, promote)


def apply(p: Plan, say=print) -> Path:
    """Builds the new course, renames the old folder `<old>_before_split`, and logs the split. Returns the new root."""
    from src.sections import roster_file
    target = p.target
    try:
        for d in ("course_info", "history", "reports"):
            (target / d).mkdir(parents=True)
        dump_yaml(target / "course_info" / f"{p.new_prefix}_config.yaml", layout_config(p.raw, p.sections))
        roster = read_csv_text(roster_file(p.course))
        for num in p.sections:
            ids = {sid for sid, s in p.secmap.items() if s == num}
            unit, sp = target / f"sec{num}", f"{p.new_prefix}_SEC_{num}"
            for d in ("course_info", "data", "reports"):
                (unit / d).mkdir(parents=True)
            write_csv_text(unit / "course_info" / f"{sp}_student_info.csv", keep_rows(roster, ids, drop=("Section",)))
            marks = _split_data(p, unit, sp, ids)
            say(f"   sec{num}/: {len(ids)} students" + (f", {marks} attendance marks" if marks is not None else ""))
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    before = p.course.with_name(p.course.name + BEFORE)
    p.course.rename(before)
    log_entry(target, "split", note=f"{p.course.name} → {target.name}", **{"from": p.course.name, "to": target.name,
              "before": before.name})
    return target


def _split_data(p: Plan, unit: Path, sp: str, ids: set) -> int | None:
    """Writes one section's score csvs and attendance sheet; returns its attendance marks (None without a sheet)."""
    from src.attendance import files_of, make_csv, read_csv_sheet, read_xlsx_sheet
    xlsx, att_csv = files_of(p.course)
    for path in data_files(p.course):
        if att_csv is not None and path == att_csv and xlsx is not None:
            continue  # made from the section's xlsx below
        write_csv_text(unit / "data" / f"{sp}_{suffix_of(path.name, p.old_prefix)}", keep_rows(read_csv_text(path), ids))
    if xlsx is None:
        return None
    import pandas as pd
    import grader
    new_xlsx = unit / "data" / f"{sp}_attendance.xlsx"
    shutil.copy2(xlsx, new_xlsx)
    roster = pd.read_csv(next((unit / "course_info").glob("*_student_info.csv")), dtype=str, keep_default_na=False)
    sessions = (read_csv_sheet(att_csv) if att_csv is not None and att_csv.exists() else read_xlsx_sheet(xlsx)).sessions
    grader.save_attendance_excel(new_xlsx, roster, sessions)
    make_csv(unit)
    sheet = read_csv_sheet(unit / "data" / f"{sp}_attendance.csv")
    return sum(1 for row in sheet.rows.values() for s in sheet.sessions if str(row.get(s, "")).strip())


# ---- a student changing section (update -i) --------------------------------------------------------------------
def move_students(src: Path, dst: Path, sids: list, entry) -> dict:
    """
    Moves students' rows from one section folder's files to another's (their roster row there is already merged):
    each score file and the attendance csv by its name after the prefix, cells by header. A cell already filled in
    the destination is kept. The source roster loses them, and both attendance sheets follow. Returns {sid: cells}.
    """
    from src.attendance import align_rows, auto_sync, files_of
    from src.sections import roster_file
    src, dst = Path(src), Path(dst)
    ids = {str(s) for s in sids}
    sp, dp = course_mod.prefix_for(src), course_mod.prefix_for(dst)
    roster = roster_file(src)
    if roster is not None:
        entry.capture(roster)
        doc = read_csv_text(roster)
        i = _sid_col(doc)
        doc.rows = [r for r in doc.rows if i is None or r[i].strip() not in ids]
        write_csv_text(roster, doc)
    moved = {sid: 0 for sid in ids}
    for path in data_files(src):
        target = dst / "data" / f"{dp}_{suffix_of(path.name, sp)}"
        if not target.exists():
            continue
        entry.capture(path)
        entry.capture(target)
        a, b = read_csv_text(path), read_csv_text(target)
        ai, bi = _sid_col(a), _sid_col(b)
        if ai is None or bi is None:
            continue
        rows = {r[ai].strip(): r for r in a.rows if r[ai].strip() in ids}
        a.rows = [r for r in a.rows if r[ai].strip() not in ids]
        at_b = {r[bi].strip(): r for r in b.rows}
        where = {h.strip(): j for j, h in enumerate(b.header)}
        for sid, row in rows.items():
            out = at_b.get(sid)
            if out is None:
                out = [""] * len(b.header)
                out[bi] = sid
                b.rows.append(out)
            for j, h in enumerate(a.header):
                k = where.get(h.strip())
                if k is not None and row[j].strip() and not out[k].strip():
                    out[k] = row[j]
                    moved[sid] += h.strip() not in ("Student ID", "Name") and not h.strip().lower().startswith("total")
        write_csv_text(path, a)
        write_csv_text(target, b)
    xlsx, csv = files_of(src)
    if xlsx is not None:  # their rows leave the source sheet too: their marks went with them (align_rows keeps a
        from src.attendance import (Target, _open_xlsx, baseline_path, edit_xlsx, read_csv_sheet,  # row with marks)
                                    read_xlsx_sheet, save_baseline, save_xlsx)
        X = read_xlsx_sheet(xlsx)
        gone = ids & set(X.rows)
        if gone:
            entry.capture(xlsx)
            entry.capture(baseline_path(src))
            wb, ws = _open_xlsx(xlsx)
            edit_xlsx(wb, ws, Target(X.sessions, {}, {}, {}), drop_rows=gone, keep_columns=True)
            save_xlsx(wb, xlsx)
        align_rows(src, entry=entry)
        X2, C2 = read_xlsx_sheet(xlsx), (read_csv_sheet(csv) if csv is not None and csv.exists() else None)
        if C2 is not None and X2.sessions == C2.sessions and X2.rows == C2.rows:
            save_baseline(src, X2.sessions, X2.rows, xlsx, csv)
    if files_of(dst)[0] is not None:
        auto_sync(dst, tool="grader", entry=entry)
    return moved


# ---- history -------------------------------------------------------------------------------------------------------
def log_entry(root: Path, action: str, note: str = "", **extra) -> str:
    """An entry without file snapshots (a split, or a section added by moving the course into the layout)."""
    hist = root / "history"
    hist.mkdir(exist_ok=True)
    base = f"{datetime.now():%Y%m%d-%H%M%S}_grader_{action}"
    name, n = base, 2
    while (hist / name).exists():
        name, n = f"{base}-{n}", n + 1
    (hist / name).mkdir()
    line = {"id": name, "ts": datetime.now().isoformat(timespec="seconds"), "tool": "grader", "action": action,
            "files": [], "cells": None, "note": note, **extra}
    with open(hist / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return name


def undo(root: Path, entry: dict) -> Path:
    """
    Puts the one-folder course back: the new course is removed (refused when anything changed in it since the split)
    and `<old>_before_split` gets its name back. Returns the old folder.
    """
    from src.history import list_entries
    root = Path(root).resolve()
    entries = list_entries(root)
    ids = [e["id"] for e in entries]
    after = entries[ids.index(entry["id"]) + 1:] if entry["id"] in ids else []
    later = [e for e in after if e.get("action") != "undo"]  # in log order (ids of one second don't sort by time)
    if later:
        raise Refused(f"❌ {len(later)} change(s) were made in {root.name} after the split (newest: {later[-1]['id']}). "
                      "Undoing the split would lose them. Nothing was changed.")
    before = root.with_name(entry["before"])
    old = root.with_name(entry["from"])
    if not before.is_dir():
        raise Refused(f"❌ {before.name} isn't there any more, so the split can't be undone. Nothing was changed.")
    if old.exists():
        raise Refused(f"❌ {old.name} already exists. Nothing was changed.")
    shutil.rmtree(root)
    before.rename(old)
    return old


def split(course, secmap: dict | None = None, root=None, say=print, name: str | None = None) -> Path:
    return apply(plan(course, secmap, root, name), say)
