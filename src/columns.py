"""
Which side changed: config.yaml or the score CSV? (SPEC_config_columns.md)

A score-file column that isn't in config.yaml's data_mapping can mean two opposite things:

    removed  — it WAS in the config and you took it out → the CSV should follow the config:
               `grader update` / `grader sync` ask: delete it / rename it to a new config column / keep it
    hand     — you added it to the CSV (or `exam submit scores` did) → `grader sync` offers to add it to the config

To tell them apart, every `grader mkdb/update/sync` remembers the config's columns as they were when the files
were last aligned: history/config_sync.json  {"mapping": {category: {column: points}}, "kept": {category: [column]}}.
Without that file yet (a course from before this existed), the earlier configs kept in history/ and
course_info/*_config.yaml.bak are used instead.

The same memory decides points that differ between a header and the config: the side that still has the
remembered value is the one you didn't touch, so the other side wins. A bare header (`4`) holds the category
default (src/points.py), so when you change pts_each, `grader update` / `grader sync` ask before the scores
already in those columns count out of the new value (`settle_default_changes`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from src.cells import classify
from src.csvio import atomic_write_bytes, read_csv_text, write_csv_text
from src.points import at_default, defaults, fmt_pts, header_for
from src.sync import config_file, data_files, mapping, raw_config, score_columns, set_category

BASE = "config_sync.json"


def base_path(course) -> Path:
    return Path(course) / "history" / BASE


def load_base(course) -> dict | None:
    p = base_path(course)
    if not p.exists():
        return None
    try:
        b = json.loads(p.read_text(encoding="utf-8"))
        return b if isinstance(b, dict) and isinstance(b.get("mapping"), dict) else None
    except ValueError:
        return None


def _mapping_of(text: str) -> dict:
    try:
        cfg = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}
    return {cat: {name: pts for name, pts in cols} for cat, cols in mapping(cfg).items()}


def remembered(course) -> tuple[dict, dict, bool]:
    """({category: {column: points}} the config had when the files were last aligned, {category: set(kept)},
    exact). Without config_sync.json: every column any earlier config in history/ or *.bak listed (exact=False)."""
    course = Path(course)
    b = load_base(course)
    if b is not None:
        return b["mapping"], {c: set(v) for c, v in (b.get("kept") or {}).items()}, True
    seen: dict = {}
    olds = sorted((course / "history").glob("*/course_info/*_config.yaml")) if (course / "history").is_dir() else []
    olds += sorted((course / "course_info").glob("*_config.yaml.bak"))
    for f in olds:
        for cat, cols in _mapping_of(f.read_text(encoding="utf-8")).items():
            for name in cols:
                seen.setdefault(cat, {})[name] = None  # points of old snapshots aren't trusted
    return seen, {}, False


def save_base(course, kept: dict | None = None) -> None:
    """Remember the config's columns now (call after the files were aligned with it)."""
    course = Path(course)
    old = load_base(course) or {}
    cur = {cat: {name: pts for name, pts in cols} for cat, cols in mapping(raw_config(course)).items()}
    keep = {c: set(v) for c, v in (old.get("kept") or {}).items()}
    for c, v in (kept or {}).items():
        keep.setdefault(c, set()).update(v)
    files = data_files(course)
    present = {}
    for cat, p in files.items():
        present[cat] = {name for _, name, _ in score_columns(read_csv_text(p))}
    keep = {c: sorted(n for n in v if n in present.get(c, set()) and n not in cur.get(c, {}))
            for c, v in keep.items()}
    keep = {c: v for c, v in keep.items() if v}
    p = base_path(course)
    p.parent.mkdir(exist_ok=True)
    data = {"ts": datetime.now().isoformat(timespec="seconds"), "mapping": cur, "kept": keep}
    atomic_write_bytes(p, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


# ---- columns not in the config ----------------------------------------------------------------------------------
@dataclass
class Unmapped:
    category: str
    path: Path
    name: str
    header: str
    points: float | None
    filled: int          # cells with something in them (a number, ขส, text)
    kind: str            # "removed" / "kept" / "hand"


def filled_cells(doc, i: int) -> int:
    return sum(1 for r in doc.rows if i < len(r) and classify(r[i])[0] != "empty")


def unmapped(course) -> list[Unmapped]:
    course = Path(course)
    cfg = {cat: {name for name, _ in cols} for cat, cols in mapping(raw_config(course)).items()}
    before, kept, _ = remembered(course)
    out = []
    for cat, p in data_files(course).items():
        doc = read_csv_text(p)
        for i, name, pts in score_columns(doc):
            if name in cfg.get(cat, set()):
                continue
            kind = "kept" if name in kept.get(cat, set()) else "removed" if name in before.get(cat, {}) else "hand"
            out.append(Unmapped(cat, p, name, doc.header[i], pts, filled_cells(doc, i), kind))
    return out


def rename_targets(course, category: str, taken: set = frozenset()) -> list[str]:
    """Config columns of `category` that a removed column's scores could move into: missing from the CSV, or
    there but still empty."""
    course = Path(course)
    cols = dict(mapping(raw_config(course)).get(category, []))
    p = data_files(course).get(category)
    if p is None:
        return []
    doc = read_csv_text(p)
    present = {name: i for i, name, _ in score_columns(doc)}
    return [n for n in cols if n not in taken and (n not in present or filled_cells(doc, present[n]) == 0)]


def points_side(course, category: str, column: str, header_pts, config_pts) -> str | None:
    """'config' when you changed the config's points (the header still has the remembered ones), 'file' when you
    changed the header, None when that can't be told."""
    before, _, exact = remembered(course)
    if not exact:
        return None
    old = before.get(category, {}).get(column)
    if old is None:
        return None
    if header_pts is not None and abs(old - header_pts) < 1e-9 and config_pts is not None:
        return "config"
    if config_pts is not None and abs(old - config_pts) < 1e-9 and header_pts is not None:
        return "file"
    return None


# ---- the edits ----------------------------------------------------------------------------------------------
def delete_column(path: Path, name: str, entry) -> None:
    doc = read_csv_text(path)
    idx = [i for i, n, _ in score_columns(doc) if n == name]
    if not idx:
        return
    i = idx[0]
    entry.capture(path)
    doc.header.pop(i)
    for r in doc.rows:
        if i < len(r):
            r.pop(i)
    write_csv_text(path, doc)


def rename_column(course, path: Path, name: str, target: str, entry) -> None:
    """Moves the scores of `name` into config column `target` (which is missing or empty) and drops `name`."""
    doc = read_csv_text(path)
    cols = {n: (i, pts) for i, n, pts in score_columns(doc)}
    if name not in cols:
        return
    i, pts = cols[name]
    cfg = raw_config(course)
    cat_pts, default = None, None
    for cat, items in mapping(cfg).items():
        if data_files(course).get(cat) == path:
            cat_pts, default = dict(items).get(target), defaults(cfg).get(cat)
    pts = cat_pts if cat_pts is not None else pts
    entry.capture(path)
    if target in cols:
        j = cols[target][0]
        for r in doc.rows:
            while len(r) <= max(i, j):
                r.append("")
            r[j] = r[i]
        doc.header.pop(i)
        for r in doc.rows:
            r.pop(i)
    else:
        doc.header[i] = header_for(target, pts, default)
    write_csv_text(path, doc)


@dataclass
class Settled:
    deleted: list = field(default_factory=list)
    renamed: list = field(default_factory=list)   # (old, new)
    kept: dict = field(default_factory=dict)      # category → {column}


def settle_removed(course, ask, entry, yes: bool = False, say=print) -> Settled:
    """Columns you took out of config.yaml but that are still in a CSV: an empty one is deleted; one with scores
    is asked about — [d] delete / [r] rename to a new config column (keeps its scores) / [k] keep (not counted,
    never proposed for the config again). `--yes` or no terminal = keep."""
    out = Settled()
    taken: set = set()
    for u in unmapped(course):
        if u.kind != "removed":
            continue
        where = f"[{u.category}] '{u.header}'"
        if u.filled == 0:
            delete_column(u.path, u.name, entry)
            out.deleted.append(u.name)
            say(f"  🗑️  {where}: removed from config.yaml and empty → deleted from {u.path.name}")
            continue
        targets = rename_targets(course, u.category, taken)
        opts = "[d] delete it / " + ("[r] rename it to a new config column (keeps its scores) / " if targets else "") \
            + "[k] keep it (not counted)"
        ans = "k" if yes else (ask(f"  {where} was removed from config.yaml but still has {u.filled} filled cell(s) in "
                                   f"{u.path.name}. {opts}? [k]", "k") or "k").strip().lower()[:1]
        if ans == "d":
            delete_column(u.path, u.name, entry)
            out.deleted.append(u.name)
            say(f"  🗑️  {u.name}: deleted from {u.path.name} (grader undo brings it back)")
        elif ans == "r" and targets:
            target = targets[0]
            if len(targets) > 1:
                menu = "  ".join(f"{n}) {t}" for n, t in enumerate(targets, 1))
                pick = ask(f"    Rename '{u.name}' to: {menu} ? [1]", "1").strip() or "1"
                try:
                    target = targets[int(pick) - 1]
                except (ValueError, IndexError):
                    say(f"    ⏭  no such choice: '{u.name}' kept")
                    out.kept.setdefault(u.category, set()).add(u.name)
                    continue
            rename_column(course, u.path, u.name, target, entry)
            taken.add(target)
            out.renamed.append((u.name, target))
            say(f"  ✏️  {u.name} → {target}: its {u.filled} cell(s) moved into {u.path.name}'s '{target}'")
        else:
            out.kept.setdefault(u.category, set()).add(u.name)
            say(f"  📌 {u.name}: kept in {u.path.name} (not counted; won't be proposed for config.yaml)")
    return out


# ---- pts_each changed under bare headers ---------------------------------------------------------------------------
@dataclass
class DefaultChange:
    category: str
    path: Path
    old: float           # the points those columns had when the files were last aligned
    new: float | None    # the category default now
    columns: list        # bare-header columns that have scores
    students: int        # rows with a score in any of them


def default_changes(course) -> list[DefaultChange]:
    """Categories whose default changed while bare-header columns at it already hold scores. A bare header can't
    show the old value, so the scores would silently count out of the new one."""
    course = Path(course)
    before, _, exact = remembered(course)
    if not exact:
        return []
    cfg = raw_config(course)
    cfg_map, dflt = mapping(cfg), defaults(cfg)
    out = []
    for cat, path in data_files(course).items():
        new = dflt.get(cat)
        cols = dict(cfg_map.get(cat, []))
        doc = read_csv_text(path)
        olds, names, rows = set(), [], set()
        for i, name, hp in score_columns(doc):
            if hp is not None or name not in cols:
                continue
            old, now = before.get(cat, {}).get(name), cols[name]
            if old is None or (now is not None and abs(old - now) < 1e-9):
                continue
            if now is not None and not at_default(now, new):
                continue  # its own config value changed: the header follows (SPEC_config_columns.md #5)
            if filled_cells(doc, i) == 0:
                continue
            olds.add(old)
            names.append(name)
            rows |= {r for r, row in enumerate(doc.rows) if i < len(row) and classify(row[i])[0] != "empty"}
        if names and len(olds) == 1:
            out.append(DefaultChange(cat, path, olds.pop(), new, names, len(rows)))
    return out


def settle_default_changes(course, ask, entry, yes: bool = False, say=print) -> list[DefaultChange]:
    """Asks about each default_changes(): [y] keep the new value / [n] put the old pts_each back in config.yaml.
    `--yes` or no terminal = keep the new value. Returns the ones put back."""
    course = Path(course)
    restored = []
    for c in default_changes(course):
        new = f"{fmt_pts(c.new)}" if c.new is not None else "no default"
        cols = ", ".join(c.columns[:4]) + (", …" if len(c.columns) > 4 else "")
        out_of = f"count out of {fmt_pts(c.new)}" if c.new is not None else "have no points"
        q = (f"  [{c.category}] {fmt_pts(c.old)} → {new} pts each; {c.students} students' scores in {cols} now "
             f"{out_of}. [y] keep {new} / [n] put {fmt_pts(c.old)} back in config.yaml? [y]")
        ans = "y" if yes else (ask(q, "y") or "y").strip().lower()[:1]
        if ans != "n":
            say(f"  ✔️  [{c.category}] {new} pts each, as in config.yaml")
            continue
        path = config_file(course)
        value = raw_config(course)["data_mapping"][c.category]
        if isinstance(value, dict) and "columns" in value:
            value = dict(value)
        else:
            value = {"columns": list(value or [])}
        value["pts_each"] = int(c.old) if float(c.old).is_integer() else c.old
        value = {"pts_each": value.pop("pts_each"), **value}
        entry.capture(path)
        atomic_write_bytes(path, set_category(path, c.category, value).encode("utf-8"))
        restored.append(c)
        say(f"  ↩️  [{c.category}] pts_each: {fmt_pts(c.old)} put back in {path.name}")
    return restored
