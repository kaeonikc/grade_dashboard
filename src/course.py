"""
Where a course's pieces are (SPEC_section_folders.md).

A **flat course** is one folder: `course_info/<prefix>_config.yaml`, its roster, `data/`, `history/`, `reports/`.

A **course with sections** is a folder holding the one shared config (`course_info/<prefix>_config.yaml`, whose
`sections[N].folder` names each section's sub-folder), `history/` for every change and `reports/` for the combined
exports, plus one sub-folder per section (`sec51/`) with that section's roster (`course_info/`), `data/` and
`reports/`, but no config. A section folder works like a flat course everywhere a single folder is meant (its config
is the shared one with its own `sec_num` and schedules on top), and its changes are logged in the course's history.

Standard library, plus yaml where a config is read (history_root, which Tab completion uses, needs no yaml).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

SECTION_KEYS = ("class_schedule", "exam_schedule")  # what a section's `sections[N]` entry sets for that section


def own_config(folder) -> Path | None:
    """The folder's own course_info/*_config.yaml (never a .bak), or None."""
    info = Path(folder) / "course_info"
    if not info.is_dir():
        return None
    files = sorted(f for f in info.glob("*_config.yaml") if f.is_file() and not f.name.startswith("."))
    return files[0] if files else None


def read_yaml(path) -> dict:
    import yaml
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _sec_key(s: str) -> tuple:
    return (0, int(s), s) if s.isdigit() else (1, 0, s)


def section_entries(config: dict) -> dict[str, dict]:
    """{"51": {"folder": "sec51", …}, …} in numeric order: the config's sections that have a folder."""
    secs = config.get("sections") if isinstance(config, dict) else None
    if not isinstance(secs, dict):
        return {}
    out = {str(k).strip(): v for k, v in secs.items() if isinstance(v, dict) and str(v.get("folder") or "").strip()}
    return {k: out[k] for k in sorted(out, key=_sec_key)}


def has_section_folders(config: dict) -> bool:
    return bool(section_entries(config))


@dataclass(frozen=True)
class Section:
    num: str
    path: Path      # the folder holding its roster and data/ (the course folder itself for a flat course)
    prefix: str     # its files' prefix: 2026_S2_Astro_SEC_51


@dataclass
class Course:
    root: Path                  # the course folder
    config_path: Path | None
    prefix: str                 # the config's stem: 2026_S2_Astro
    sections: list[Section] = field(default_factory=list)
    here: Section | None = None  # the section the path given to at() is in (None at a course with sections' top)

    @property
    def layout(self) -> bool:
        """True for a course with section folders."""
        return any(s.path != self.root for s in self.sections)

    @property
    def history(self) -> Path:
        return self.root / "history"

    def section(self, num) -> Section | None:
        return next((s for s in self.sections if s.num == str(num)), None)

    def config(self) -> dict:
        return read_yaml(self.config_path) if self.config_path else {}


def section_prefix(root_prefix: str, num: str, folder: Path) -> str:
    """A section's file prefix: its roster's stem when it has one, else `<course prefix>_SEC_<num>`."""
    info = Path(folder) / "course_info"
    rosters = sorted(f for f in info.glob("*_student_info.csv") if not f.name.startswith(".")) if info.is_dir() else []
    return rosters[0].name[:-len("_student_info.csv")] if rosters else f"{root_prefix}_SEC_{num}"


def _sections_of(root: Path, config: dict, prefix: str) -> list[Section]:
    out = []
    for num, entry in section_entries(config).items():
        folder = root / str(entry["folder"]).strip()
        out.append(Section(num, folder, section_prefix(prefix, num, folder)))
    return out


def at(path) -> Course | None:
    """
    The course that `path` (the course folder, a section folder, or anything inside either) belongs to, or None.
    The course folder is the nearest folder up (at most four levels) with a config of its own.
    """
    p = Path(path).resolve()
    if p.is_file() or not p.exists():
        p = p.parent
    for d in [p] + list(p.parents)[:4]:
        cfg_path = own_config(d)
        if cfg_path is None:
            continue
        config = read_yaml(cfg_path)
        prefix = cfg_path.name[:-len("_config.yaml")]
        sections = _sections_of(d, config, prefix)
        if not sections:
            sec = str(config.get("sec_num") or "").strip()
            flat = Section(sec, d, prefix)
            return Course(d, cfg_path, prefix, [flat], flat)
        here = next((s for s in sections if p == s.path or s.path in p.parents), None)
        return Course(d, cfg_path, prefix, sections, here)
    return None


def section_at(path) -> tuple[Course, Section] | None:
    """(course, section) when `path` is a section folder of a course with sections (exactly that folder)."""
    c = at(path)
    if c is None or not c.layout or c.here is None or c.here.path != Path(path).resolve():
        return None
    return c, c.here


def is_section_folder(path) -> bool:
    return section_at(path) is not None


def config_path(folder) -> Path | None:
    """The config a folder reads: its own, or for a section folder its course's."""
    own = own_config(folder)
    if own is not None:
        return own
    s = section_at(folder)
    return s[0].config_path if s else None


def overlay(config: dict, num: str) -> dict:
    """The shared config as section `num` sees it: its sec_num and schedules on top (a copy)."""
    entry = section_entries(config).get(str(num)) or {}
    out = copy.deepcopy(config)
    out["sec_num"] = str(num)
    for key in SECTION_KEYS:
        if key in entry:
            out[key] = copy.deepcopy(entry[key])
    return out


def config_for(folder) -> dict:
    """The raw config a folder reads ({} without one), overlaid for a section folder."""
    path = config_path(folder)
    if path is None:
        return {}
    config = read_yaml(path)
    s = section_at(folder)
    return overlay(config, s[1].num) if s else config


def prefix_for(folder) -> str | None:
    """The file prefix inside a folder: a section's `<course>_SEC_<N>`, else its config's stem."""
    s = section_at(folder)
    if s:
        return s[1].prefix
    own = own_config(folder)
    return own.name[:-len("_config.yaml")] if own else None


def history_root(path) -> Path | None:
    """
    The folder whose history/ records changes to `path`: the course folder, the nearest one up with a config of its
    own (a section folder has none). Reads no yaml.
    """
    p = Path(path).resolve()
    if p.is_file() or not p.exists():
        p = p.parent
    return next((d for d in [p] + list(p.parents)[:4] if own_config(d) is not None), None)


def state_file(folder, name: str) -> Path:
    """
    A sync baseline (attendance_sync.json, config_sync.json) for one folder's files: in its course's history/, named
    `<stem>.sec<N>.json` for a section folder so each section keeps its own.
    """
    s = section_at(folder)
    if s is None:
        return Path(folder) / "history" / name
    stem, dot, ext = name.rpartition(".")
    return s[0].history / f"{stem}.sec{s[1].num}{dot}{ext}"


def units(path) -> list[Path]:
    """The folders that hold rosters and data/ for the course at `path`: each section's, or the flat course's."""
    c = at(path)
    return [s.path for s in c.sections] if c else []


def courses_in(folder) -> list[Path]:
    """Course folders at `folder` itself or one level down, never a section folder on its own."""
    folder = Path(folder)
    found = []
    for d in [folder] + (sorted(x for x in folder.iterdir() if x.is_dir()) if folder.is_dir() else []):
        if own_config(d) is not None and d.resolve() not in found:
            found.append(d.resolve())
    return found
