"""
Courses with several sections (SPEC_section_folders.md): one sub-folder per section, each with its own roster.

A student's section is the section folder whose roster lists them (src/course.py says where the folders are). A course
"has sections" (selector, per-section exports, [51] tags) only when it has two or more. The roster `Section` column of
the older one-folder layout (SPEC_sections.md) is read only by `grader split`, which turns such a course into folders.
"""

import csv
import io
import re
from pathlib import Path


def sec_key(sec) -> tuple:
    """Numeric order for section numbers ("8" before "51"); anything else after them, by text."""
    s = str(sec).strip()
    return (0, int(s), s) if s.isdigit() else (1, 0, s)


def sort_sections(secs) -> list[str]:
    return sorted({str(s).strip() for s in secs if str(s).strip()}, key=sec_key)


def norm_id(course_id) -> str:
    """A course ID compared with spaces removed: "SC 2202" == "SC2202"."""
    return re.sub(r"\s+", "", str(course_id or "")).casefold()


def same_course_id(id_a, name_a, id_b, name_b) -> bool:
    """
    The same course: the same course ID with spaces ignored ("SC 2202" == "SC2202"). A course made before the ID
    parse fix (course_id "SC", course_name "2202 ดาราศาสตร์…") matches its repaired self too: ID + name, spaces
    removed, are equal (SPEC_sections.md). Either side may be the old form.
    """
    if norm_id(id_a) == norm_id(id_b):
        return True
    return bool(norm_id(id_a) and norm_id(id_b)) and \
        norm_id(f"{id_a or ''}{name_a or ''}") == norm_id(f"{id_b or ''}{name_b or ''}")


def roster_file(course) -> Path | None:
    files = sorted(p for p in (Path(course) / "course_info").glob("*_student_info.csv")
                   if not p.name.startswith("."))
    return files[0] if files else None


def _roster_ids(path: Path) -> list[str]:
    try:
        rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))
    except (OSError, UnicodeDecodeError):
        return []
    header = [h.strip() for h in rows[0]] if rows else []
    if "Student ID" not in header:
        return []
    i = header.index("Student ID")
    return [r[i].strip() for r in rows[1:] if i < len(r) and r[i].strip()]


def roster_sections(course) -> dict[str, str]:
    """
    {student id: section} of a course with section folders, from each section's roster, in section order; given one
    section folder, its own students. {} for a flat course.
    """
    from src.course import at
    c = at(course)
    if c is None or not c.layout:
        return {}
    here = Path(course).resolve()
    shown = [c.here] if c.here is not None and c.here.path == here else c.sections
    out = {}
    for s in shown:
        r = roster_file(s.path)
        for sid in _roster_ids(r) if r else []:
            out.setdefault(sid, s.num)
    return out


def section_column(course) -> dict[str, str]:
    """
    {student id: section} from a one-folder roster's `Section` column ("" for a blank cell); {} when there's no
    roster or no such column (the layout before SPEC_section_folders.md; `grader split` reads it).
    """
    path = roster_file(course)
    if path is None:
        return {}
    try:
        rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))
    except (OSError, UnicodeDecodeError):
        return {}
    header = [h.strip() for h in rows[0]] if rows else []
    if "Student ID" not in header or "Section" not in header:
        return {}
    i, j = header.index("Student ID"), header.index("Section")
    return {r[i].strip(): (r[j].strip() if j < len(r) else "") for r in rows[1:] if i < len(r) and r[i].strip()}


def sections_of(secmap: dict) -> list[str]:
    """The sections named in {student id: section}, in numeric order."""
    return sort_sections(secmap.values())


def course_sections(course) -> list[str]:
    return sections_of(roster_sections(course))


def counts(secmap: dict) -> str:
    """'sec 51: 28 · sec 52: 27' (blank sections counted as 'no sec')."""
    n = {}
    for s in secmap.values():
        n[s] = n.get(s, 0) + 1
    parts = [f"sec {s}: {n[s]}" for s in sort_sections(n)]
    if n.get(""):
        parts.append(f"no sec: {n['']}")
    return " · ".join(parts)


def tagger(secmap: dict):
    """f(student id) -> '[51] ' when the course has ≥2 sections, else '' (the CLI's per-student prefix)."""
    if len(sections_of(secmap)) < 2:
        return lambda sid: ""
    return lambda sid: f"[{secmap.get(str(sid).strip()) or '?'}] "


def order_key(secmap: dict):
    """Sort key for student ids: by section (numeric), then by id."""
    return lambda sid: (sec_key(secmap.get(str(sid).strip(), "")), str(sid))


def group_order(secmap: dict):
    """
    Sort key for the All view of a course with sections (SPEC_sections.md R5): section in numeric order, students
    with no section last, then ID.
    """
    def key(sid):
        sid = str(sid).strip()
        sec = secmap.get(sid, "")
        return ((0, sec_key(sec)) if sec else (1, (0, 0, "")), sid)
    return key


def blocks(ids, secmap: dict) -> list[tuple[str, list]]:
    """[(section, its ids in group order), …] for ids already in group order ("" = no section)."""
    out = []
    for sid in ids:
        sec = secmap.get(str(sid).strip(), "")
        if not out or out[-1][0] != sec:
            out.append((sec, []))
        out[-1][1].append(sid)
    return out


def block_title(sec: str, n: int) -> str:
    """'Sec 51 · 28 students' (the header line above a section's rows)."""
    who = f"{n} student{'s' if n != 1 else ''}"
    return f"Sec {sec} · {who}" if sec else f"No section · {who}"
