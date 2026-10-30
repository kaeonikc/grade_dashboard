"""
Courses with several sections in one folder (SPEC_sections.md).

The roster course_info/<prefix>_student_info.csv is the source of truth: its `Section` column says which section each
student is in. A roster without that column is a course without sections, and everything behaves as before. A course
"has sections" (selector, per-section exports, [51] tags) only when its roster names two or more.
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


def roster_file(course) -> Path | None:
    files = sorted(p for p in (Path(course) / "course_info").glob("*_student_info.csv")
                   if not p.name.startswith("."))
    return files[0] if files else None


def roster_sections(course) -> dict[str, str]:
    """{student id: section} from the roster ("" for a blank cell); {} when there's no roster or no Section column."""
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
