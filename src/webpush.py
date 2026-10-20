"""
`grader web-push`: copy a course to Drive for the grade_web app (web/SPEC.md "Mac commands", REQUIREMENTS S1).

It never writes into the Mac course folder (S1.2). Every check runs before the first write, and a refusal writes
nothing anywhere. grade-tui's loaders sync attendance and totals as a side effect, so course.json is built from a
staging copy of the pushed files in a temporary folder, never from the course itself.

Pushed: course.json (the resolved config, docs/adr/003), push.json, the roster and every data/*.csv, byte for
byte. The journal web_edits.jsonl is only created when missing (docs/adr/002); archive/ is never touched except to
add the `_discarded` file of `--force`.
"""

import csv
import io
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from src import attendance, webdrive
from src.csvio import atomic_write_bytes, fmt_value, read_csv_text
from src.data_loader import load_config, load_course_data, parse_pts
from src.sync import SENTINELS, config_file, is_total, prefix_of
from src.webdrive import Refused, fmt_time, pad, width

TOP = ("course.json", "push.json", webdrive.JOURNAL)  # the only top-level files a pushed course keeps


# ---- read-only checks of the Mac course ---------------------------------------------------------------------------
def _decode(path: Path, rel: str) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8").removeprefix("﻿")
    except UnicodeDecodeError as e:
        raise Refused(f"❌ {rel} is not UTF-8 text (byte 0x{raw[e.start]:02x} at position {e.start}; saved by Excel "
                      "as Thai?). Save it as \"CSV UTF-8\", then push again.")


def _students(path: Path, rel: str) -> list[str]:
    """The Student IDs of a CSV, one per row, after checking it is UTF-8 with a `Student ID` column."""
    rows = list(csv.reader(io.StringIO(_decode(path, rel), newline="")))
    header = [h.strip() for h in rows[0]] if rows else []
    if "Student ID" not in header:
        more = "…" if len(header) > 3 else ""
        raise Refused(f"❌ {rel} has no 'Student ID' column (header: {', '.join(header[:3])}{more}). Fix the header, "
                      "then push again.")
    i = header.index("Student ID")
    ids = [r[i].strip() for r in rows[1:] if i < len(r)]
    return [s for s in ids if s and s.lower() not in SENTINELS]


def roster_of(course: Path) -> Path | None:
    files = sorted(p for p in (course / "course_info").glob("*_student_info.csv") if not p.name.startswith("."))
    return files[0] if files else None


def data_csvs(course: Path) -> list[Path]:
    data = course / "data"
    return sorted(p for p in data.glob("*.csv") if not p.name.startswith(".")) if data.is_dir() else []


def check_course(course: Path) -> tuple[list[str], list[str]]:
    """(roster IDs, warnings), or Refused. Reads only."""
    stem = course.name.removesuffix("_grading")
    try:
        cfg_path = config_file(course)
    except FileNotFoundError:
        raise Refused(f"❌ No config in course_info/ (expected {stem}_config.yaml). Nothing was pushed.")
    try:
        yaml.safe_load(cfg_path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError as e:
        raise Refused(f"❌ course_info/{cfg_path.name} can't be read: not UTF-8 text (position {e.start}). Fix it, "
                      "then push again.")
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        why = f"{e.problem} (line {mark.line + 1})" if mark is not None else str(e)
        raise Refused(f"❌ course_info/{cfg_path.name} can't be read: {why}. Fix it, then push again.")

    roster = roster_of(course)
    if roster is None:
        raise Refused(f"❌ No student list in course_info/ (expected {stem}_student_info.csv). Nothing was pushed.")
    ids = _students(roster, f"course_info/{roster.name}")
    if not ids:
        raise Refused(f"❌ course_info/{roster.name} has no students.")

    warnings = []
    for path in data_csvs(course):
        rel = f"data/{path.name}"
        found = _students(path, rel)
        if not found:
            raise Refused(f"❌ {rel} has no students (header only). Add them with grader update, or remove the file, "
                          "then push again.")
        for sid, n in Counter(found).items():
            if n > 1:
                rows = "both rows" if n == 2 else f"all {n} rows"
                warnings.append(f"⚠️  {rel}: Student ID {sid} is on {n} rows. The web shows it once and a save sets "
                                f"{rows}.")

    xlsx = sorted(f"data/{p.name}" for p in (course / "data").glob("*.xlsx")
                  if not p.name.endswith("attendance.xlsx") and not p.name.startswith(("~$", ".")))
    if xlsx:
        files = f" {xlsx[0]}. " if len(xlsx) == 1 else "".join(f"\n     {f}" for f in xlsx) + "\n   "
        raise Refused(f"❌ grade_web reads score files as CSV only:{files}Keep those scores in a .csv file, then "
                      "push again. Nothing on Drive was changed.")

    plan = attendance.plan(course)
    if plan is not None and plan.has_changes():
        raise Refused("\n".join(["❌ The attendance xlsx and csv differ: run `grader sync` first, then grader "
                                 "web-push again. Nothing on Drive was changed."] + attendance.describe(plan)))
    return list(dict.fromkeys(ids)), warnings


# ---- course.json ---------------------------------------------------------------------------------------------------
def build_course_json(course) -> dict:
    """
    course.json for a course folder (web/SPEC.md "course.json"), from grade-tui's own loaders. They may write into
    the folder (attendance auto-sync), so callers pass a staging copy.
    """
    course = Path(course)
    config = load_config(course)
    _, max_scores = load_course_data(course)
    roster = roster_of(course)
    files = [f"data/{p.name}" for p in data_csvs(course)]

    where = {}  # clean name → (file, header): the first file holding it, as tui_api._find_column_file finds it
    for rel in files:
        for h in (h.strip() for h in read_csv_text(course / rel).header):
            if h and h not in ("Student ID", "Name") and not is_total(h):
                where.setdefault(h, (rel, h))
                where.setdefault(parse_pts(h)[0], (rel, h))

    weights = config.get("weights") or {}
    mapping = config.get("data_mapping") or {}
    order = list(weights) + [c for c in mapping if c not in weights]
    columns = [{"name": name, "header": where[name][1], "file": where[name][0], "category": cat}
               for cat in order for name in (mapping.get(cat) or []) if name in where]
    return {
        "format": 1,
        "course_id": str(config.get("course_id", "")),
        "course_name": str(config.get("course_name", "")),
        "term": str(config.get("term", "")),
        "folder": course.name,
        "prefix": prefix_of(course),
        "category_order": list(weights),
        "weights": weights,
        "grade_boundaries": config.get("grade_boundaries") or {},
        "rules": config.get("rules") or {},
        "data_mapping": mapping,
        "total_pts": config.get("total_pts") or {},
        "max_scores": max_scores,
        "roster": f"course_info/{roster.name}" if roster else None,
        "files": files,
        "columns": columns,
    }


def _staged_course_json(course: Path, roster: Path, data: list[Path]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / course.name
        (stage / "course_info").mkdir(parents=True)
        (stage / "data").mkdir()
        cfg = config_file(course)
        for src in [cfg, roster] + data:
            shutil.copy2(src, stage / src.relative_to(course))
        return build_course_json(stage)


# ---- the push ----------------------------------------------------------------------------------------------------
def _jtext(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _change(line: dict) -> str:
    if line.get("kind") == "config":
        new, old = line.get("value") or {}, line.get("original") or {}
        return ", ".join(f"{k} {fmt_value(old.get(k))} → {fmt_value(v)}" for k, v in new.items() if old.get(k) != v)
    return f"{line.get('original') or '(blank)'} → {line.get('value') or '(blank)'}"


def _unpulled_lines(lines: list[dict]) -> list[str]:
    """`ID  column  original → value  time` per edit (a config line: `part  changes  time`), padded by display width."""
    cells = [l for l in lines if l.get("kind") != "config"]
    w_id = max((width(str(l.get("student_id", ""))) for l in cells), default=0) + 2
    w_col = max((width(str(l.get("column", ""))) for l in cells), default=0) + 3
    w_chg = max((width(_change(l)) for l in cells), default=0) + 3
    out = []
    for l in lines:
        when = fmt_time(l["ts"]) if l.get("ts") else ""
        if l.get("kind") == "config":
            head = pad(str(l.get("part", "")).replace("_", " "), w_id + w_col) + _change(l) + "   "
        else:
            head = pad(str(l.get("student_id", "")), w_id) + pad(str(l.get("column", "")), w_col) + pad(_change(l), w_chg)
        out.append(f"     {head}{when}".rstrip())
    return out


def push(course: Path, root: Path, force: bool = False, semester: str | None = None) -> None:
    """Prints as it goes. Raises Refused (nothing written) when the course or the Drive copy isn't ready."""
    course = Path(course).resolve()
    mirror, old = webdrive.place_of(root, course, semester)
    old = webdrive.old_copy(mirror, old)
    print(f"🔄 Web push: {course.name} → {webdrive.shown(root, mirror)}")
    ids, warnings = check_course(course)
    for w in warnings:
        print(w)

    copies = webdrive.conflict_copies(mirror)
    if copies:
        raise Refused(f"❌ Drive has duplicate files in {webdrive.label(mirror)}/: {', '.join(copies)}. Fix "
                      "them as the README's \"Duplicate files\" says, then run again.")
    old_waiting = webdrive.unpulled(old) if old else []
    if old_waiting:  # even with --force: those edits are on a copy this push doesn't replace (SPEC_semester_groups D7)
        n = len(old_waiting)
        raise Refused("\n".join(
            [f"❌ The old copy {webdrive.shown(root, old)} has {n} web edit{'s' if n != 1 else ''} not pulled yet "
             f"(last saved {fmt_time(webdrive.last_saved(old_waiting))}):"]
            + _unpulled_lines(old_waiting)
            + ["   Bring them in first:  grader web-pull         (preview, then --yes)",
               "   Nothing on Drive was changed."]))
    waiting = webdrive.unpulled(mirror)
    if waiting and not force:
        n = len(waiting)
        raise Refused("\n".join(
            [f"❌ {n} web edit{'s' if n != 1 else ''} {'have' if n != 1 else 'has'}n't been pulled yet "
             f"(last saved {fmt_time(webdrive.last_saved(waiting))}):"]
            + _unpulled_lines(waiting)
            + ["   Bring them in first:  grader web-pull         (preview, then --yes)",
               "   Or drop them:         grader web-push --force (kept in archive/, marked discarded)",
               "   Nothing on Drive was changed."]))
    earlier = None
    if (mirror / "push.json").is_file():
        try:
            earlier = json.loads((mirror / "push.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            earlier = None

    roster = roster_of(course)
    data = data_csvs(course)
    course_json = _staged_course_json(course, roster, data)

    now = datetime.now().astimezone()
    push_id = f"p-{now:%Y%m%d-%H%M%S}"
    if waiting:
        header = {"kind": "discarded", "ts": now.isoformat(timespec="seconds"), "tool": "grader web-push",
                  "mac_folder": course.name, "push": (earlier or {}).get("push_id"), "lines": len(waiting)}
        arch = webdrive.write_archive(mirror, header, [{**l, "result": "discarded"} for l in waiting], "_discarded")
        print(f"⚠️  {len(waiting)} web edits not pulled are dropped from this push. They are kept in")
        print(f"    {webdrive.ARCHIVE}/{arch.name}")
    print(f"   {course_json['course_name']} ({course_json['course_id']}, {course_json['term']}) · {len(ids)} students · "
          f"{len(course_json['columns'])} counted columns")
    if earlier and earlier.get("pushed_at"):
        print(f"   Replacing the copy pushed {fmt_time(earlier['pushed_at'])}.")

    pushed = [roster.relative_to(course).as_posix()] + [f"data/{p.name}" for p in data]
    for rel in pushed:
        target = mirror / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, (course / rel).read_bytes())
    atomic_write_bytes(mirror / "course.json", _jtext(course_json))
    journal = mirror / webdrive.JOURNAL
    new_journal = not journal.exists()
    if new_journal:
        atomic_write_bytes(journal, b"")
    atomic_write_bytes(mirror / "push.json", _jtext({
        "format": 1, "push_id": push_id, "pushed_at": now.isoformat(timespec="seconds"),
        "course_id": course_json["course_id"], "course_name": course_json["course_name"],
        "term": course_json["term"], "mac_folder": course.name, "tool": "grader web-push",
        "files": ["course.json"] + pushed}))

    keep = set(pushed)
    stale = [p for sub in ("data", "course_info") if (mirror / sub).is_dir() for p in sorted((mirror / sub).rglob("*"))
             if p.is_file() and p.relative_to(mirror).as_posix() not in keep]
    stale += [p for p in sorted(mirror.iterdir()) if p.is_file() and p.name not in TOP]
    for p in stale:
        p.unlink()

    for rel in ["course.json"] + pushed:
        print(f"  ✍️  {rel}")
    print(f"  ✍️  {webdrive.JOURNAL} (new, empty)" if new_journal else f"  ⏭  {webdrive.JOURNAL} kept (0 edits not pulled)")
    print(f"  ✍️  push.json ({push_id})")
    for p in stale:
        print(f"  🗑️  Removed from Drive: {p.relative_to(mirror).as_posix()} (no longer in the course)")
    skipped = [f"data/{p.name} (the web edits the csv)" for p in sorted((course / "data").glob("*attendance.xlsx"))
               if not p.name.startswith(("~$", "."))]
    skipped += [f"{p.name}/" for p in sorted(course.iterdir()) if p.is_dir() and p.name in ("history", "reports")]
    if skipped:
        print(f"  ⏭  Not copied: {', '.join(skipped)}")
    print(f"✅ Pushed {fmt_time(now.isoformat())}. 0 edits waiting to be pulled.")
    print("   Wait until Drive for Desktop shows \"up to date\", then open grade_web on your phone.")
    print("   Bring web edits back with: grader web-pull")
    if old:
        print(f"   The old copy {webdrive.shown(root, old)} is no longer updated: delete it in Drive (it has no edits "
              "waiting).")
    linked = Path(root) / webdrive.FOLDER
    if old or not ((linked / mirror.parent.name).exists() or (linked / course.name).exists()):
        print(f"   The phone lists it once grade_web has a shortcut to {webdrive.label(mirror.parent)}: in Drive, "
              f"right-click {mirror.parent.name} › Organise › Add shortcut › grade_web (once per term).")
