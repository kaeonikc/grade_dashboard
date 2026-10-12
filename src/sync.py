"""
Keep every score file's `total` column in step with its cells (INTEGRATION.md, contract 2).

A CSV can't hold a formula, so the stored total goes stale when a score is edited by
hand. Every writer therefore recomputes it:

    total = plain sum of the row's cells in the columns that config.yaml's
            data_mapping lists for that category (empty / ขส / invalid = 0),
            header  `total (Σ points of those columns)`

Columns in the file but not in data_mapping (added by hand, or by `exam submit
scores`) don't count until `grader sync` adds them to the config. Category rules
such as drop_lowest_homework affect only the dashboard's grade, never this total.
Attendance files are never touched here.

exam_projects/cli/exam_cli/gradebook.py has a copy of `total_for`; both are
tested against the table in INTEGRATION.md.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.cells import classify
from src.csvio import CsvText, fmt_value, read_csv_text, write_csv_text

SENTINELS = {"max", "max score", "full score", "full"}


# ---- config ---------------------------------------------------------------------------------------------------
def config_file(course) -> Path:
    info = Path(course) / "course_info"
    files = sorted(f for f in info.glob("*_config.yaml") if not f.name.startswith("."))
    if not files:
        raise FileNotFoundError(f"No *_config.yaml in {info}")
    return files[0]


def raw_config(course) -> dict:
    return yaml.safe_load(config_file(course).read_text(encoding="utf-8")) or {}


def prefix_of(course) -> str:
    return config_file(course).name[: -len("_config.yaml")]


def parse_pts(col: str):
    from src.data_loader import parse_pts as _p
    return _p(str(col))


def parse_item(item):
    """A data_mapping entry → (name, points or None)."""
    from src.data_loader import parse_config_col
    return parse_config_col(item)


def category_items(value) -> list:
    """The list of entries of one data_mapping category (plain list, or {total_pts:, columns: [...]})."""
    if isinstance(value, dict) and "columns" in value:
        value = value.get("columns") or []
    return list(value) if isinstance(value, list) else []


def mapping(config: dict) -> dict:
    """{category: [(column, points or None)]} for every score category (attendance left out)."""
    out = {}
    for cat, value in (config.get("data_mapping") or {}).items():
        if str(cat) == "attendance":
            continue
        out[str(cat)] = [parse_item(i) for i in category_items(value)]
    return out


def is_attendance(path: Path) -> bool:
    return "attendance" in Path(path).name


# ---- the total rule -------------------------------------------------------------------------------------------
def is_total(header: str) -> bool:
    return header.strip().lower().startswith("total")


def score_columns(doc: CsvText) -> list:
    """[(index, clean name, header points or None)] of the score columns (not ID, Name, total, formulas)."""
    out = []
    for i, h in enumerate(doc.header):
        hs = h.strip()
        if hs in ("Student ID", "Name") or not hs or is_total(hs) or hs.startswith("=") or "unnamed" in hs.lower():
            continue
        name, pts = parse_pts(hs)
        out.append((i, name, pts))
    return out


def _fmt_pts(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def total_for(columns: list, doc: CsvText) -> tuple:
    """
    (total header, {row index: total text}) for `columns` = [(name, config points or None)] of the category.
    A mapped column's points come from the config, else from its header.
    """
    present = {name: (i, hp) for i, name, hp in score_columns(doc)}
    idx, total_pts = [], 0.0
    for name, cfg_pts in columns:
        if name not in present:
            continue
        i, hp = present[name]
        idx.append(i)
        pts = cfg_pts if cfg_pts is not None else hp
        total_pts += float(pts or 0)
    header = f"total ({_fmt_pts(total_pts)}pts)"
    sid_i = doc.col("Student ID")
    values = {}
    for r, row in enumerate(doc.rows):
        sid = row[sid_i].strip() if sid_i is not None and sid_i < len(row) else ""
        if not sid:
            continue
        if sid.lower() in SENTINELS:
            values[r] = fmt_value(total_pts)
            continue
        s = 0.0
        for i in idx:
            kind, x = classify(row[i] if i < len(row) else "")
            if kind == "num":
                s += x
        values[r] = fmt_value(round(s, 2))
    return header, values


def _same(old: str, new: str) -> bool:
    old, new = (old or "").strip(), (new or "").strip()
    if old == new:
        return True
    try:
        return abs(float(old) - float(new)) < 1e-6
    except ValueError:
        return False


def apply_total(doc: CsvText, columns: list) -> int:
    """Put the totals into `doc` (adding the total column if missing). Returns how many cells changed."""
    header, values = total_for(columns, doc)
    ti = next((i for i, h in enumerate(doc.header) if is_total(h)), None)
    changed = 0
    if ti is None:
        doc.header.append(header)
        for row in doc.rows:
            row.append("")
        ti = len(doc.header) - 1
        changed += 1
    elif doc.header[ti] != header:
        doc.header[ti] = header
        changed += 1
    for r, v in values.items():
        row = doc.rows[r]
        while len(row) <= ti:
            row.append("")
        if not _same(row[ti], v):
            row[ti] = v
            changed += 1
    return changed


# ---- files ----------------------------------------------------------------------------------------------------
def data_files(course) -> dict:
    """{category: path} for the score categories whose data/<prefix>_<category>.csv exists."""
    course = Path(course)
    prefix = prefix_of(course)
    out = {}
    for cat in mapping(raw_config(course)):
        p = course / "data" / f"{prefix}_{cat}.csv"
        if p.exists() and not is_attendance(p):
            out[cat] = p
    return out


def category_of(course, path) -> str | None:
    path = Path(path)
    for cat, p in data_files(course).items():
        if p.resolve() == path.resolve():
            return cat
    return None


def sync_file(course, category: str, entry=None, tool: str = "grade-tui", action: str = "totals") -> int:
    """Refresh one category file's total column; writes (after a snapshot) only if something changed."""
    course = Path(course)
    path = data_files(course).get(category)
    if path is None:
        return 0
    doc = read_csv_text(path)
    if doc.col("Student ID") is None:
        return 0
    changed = apply_total(doc, mapping(raw_config(course))[category])
    if not changed:
        return 0
    from src.history import Entry
    own = entry is None
    e = entry or Entry(course, tool, action)
    e.capture(path)
    write_csv_text(path, doc)
    if own:
        e.close(changed)
    return changed


def sync_course(course, tool: str = "grade-tui", action: str = "totals", entry=None) -> dict:
    """Refresh every score file's total; one history entry for all of them. Returns {file name: cells}."""
    from src.history import Entry
    course = Path(course)
    e = entry or Entry(course, tool, action)
    done = {}
    for cat, path in data_files(course).items():
        n = sync_file(course, cat, entry=e)
        if n:
            done[path.name] = n
    if entry is None:
        e.close(sum(done.values()) or None)
    return done


# ---- what `grader sync` reports -------------------------------------------------------------------------------
@dataclass
class Changes:
    unmapped: list = field(default_factory=list)   # (category, file, column, header points)
    conflicts: list = field(default_factory=list)  # (category, file, column, header points, config points)
    missing: list = field(default_factory=list)    # (category, column): in data_mapping, not in the file
    no_points: list = field(default_factory=list)  # (category, column): no points in config or header
    stale: dict = field(default_factory=dict)      # file name → total cells that would change

    def empty(self) -> bool:
        return not (self.unmapped or self.conflicts or self.missing or self.no_points or self.stale)


def find_changes(course) -> Changes:
    course = Path(course)
    cfg_map = mapping(raw_config(course))
    ch = Changes()
    for cat, path in data_files(course).items():
        doc = read_csv_text(path)
        cols = cfg_map[cat]
        mapped = {name: pts for name, pts in cols}
        present = {name: hp for _, name, hp in score_columns(doc)}
        for name, hp in present.items():
            if name not in mapped:
                ch.unmapped.append((cat, path.name, name, hp))
            elif hp is not None and mapped[name] is not None and abs(hp - mapped[name]) > 1e-9:
                ch.conflicts.append((cat, path.name, name, hp, mapped[name]))
            elif hp is None and mapped[name] is None:
                ch.no_points.append((cat, name))
        for name in mapped:
            if name not in present:
                ch.missing.append((cat, name))
        if doc.col("Student ID") is not None:
            n = apply_total(doc, cols)
            if n:
                ch.stale[path.name] = n
    return ch


def warnings_for(ch: Changes) -> list:
    """One-line warnings for grade-tui's warning bar."""
    out = []
    for cat, f, col, hp in ch.unmapped:
        pts = f" ({_fmt_pts(hp)}pts)" if hp is not None else ""
        out.append(f"{f}: column '{col}{pts}' isn't in config.yaml, so it doesn't count: run `grader sync`")
    for cat, f, col, hp, cp in ch.conflicts:
        out.append(f"{f}: '{col}' is {_fmt_pts(hp)} pts in the file but {_fmt_pts(cp)} in config.yaml: "
                   f"run `grader sync`")
    for cat, col in ch.missing:
        out.append(f"[{cat}] column '{col}' is in config.yaml but not in the file: run `grader update`")
    for cat, col in ch.no_points:
        out.append(f"[{cat}] column '{col}' has no points (write `- {col}: N` in config.yaml)")
    return out


# ---- editing data_mapping (comments outside the edited category are kept) -----------------------------------------
def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def set_category(config_path: Path, category: str, value) -> str:
    """
    The config text with data_mapping[category] replaced by `value` (block style). Lines outside that
    category stay byte-identical. Checked by re-parsing: everything else must load exactly as before.
    """
    text = config_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    dm = next((i for i, ln in enumerate(lines) if ln.startswith("data_mapping:")), None)
    if dm is None:
        raise ValueError("config.yaml has no data_mapping:")
    end_dm = next((j for j in range(dm + 1, len(lines)) if lines[j].strip() and _indent(lines[j]) == 0
                   and not lines[j].lstrip().startswith("#")), len(lines))
    child = next((_indent(lines[j]) for j in range(dm + 1, end_dm) if lines[j].strip()
                  and not lines[j].lstrip().startswith("#")), 2)
    start = next((j for j in range(dm + 1, end_dm) if _indent(lines[j]) == child
                  and lines[j].strip().split(":", 1)[0].strip().strip("'\"") == category), None)
    body = yaml.safe_dump({category: value}, allow_unicode=True, default_flow_style=False, sort_keys=False)
    new = [" " * child + ln for ln in body.splitlines()]
    if start is None:
        insert = end_dm
        while insert > dm + 1 and not lines[insert - 1].strip():
            insert -= 1
        lines[insert:insert] = new
    else:
        stop = start + 1
        while stop < end_dm and (not lines[stop].strip() or _indent(lines[stop]) > child
                                 or lines[stop].lstrip().startswith("- ")):
            stop += 1
        while stop > start + 1 and not lines[stop - 1].strip():
            stop -= 1
        lines[start:stop] = new
    out = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    before = yaml.safe_load(text) or {}
    after = yaml.safe_load(out) or {}
    expect = dict(before)
    expect["data_mapping"] = dict(before.get("data_mapping") or {})
    expect["data_mapping"][category] = value
    if after != expect:
        raise ValueError(f"couldn't edit data_mapping.{category} safely in {config_path.name}")
    return out
