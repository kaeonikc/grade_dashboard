"""
`grader web-pull`: bring grade_web edits back into the course (web/SPEC.md "Mac commands", REQUIREMENTS S11).

The journal lines not pulled yet are folded into one net change per cell and per config part (base = the first
line's `original`, final = the last line's `value`), then each is checked against the Mac files:

    apply            the Mac still holds the base value
    already applied  the Mac already holds the final value
    conflict         the Mac changed since the push: the Mac value is kept (cells and config alike)
    skipped          a total column, or a column or student the Mac files don't have
    no change        the web edited the cell back to where it started

Without --yes nothing is written. With --yes, every Mac file the pull changes (CSVs, the attendance xlsx and
baseline, the config) goes into ONE history entry, so one `grader undo` takes the whole pull back. Then a NEW
archive file on Drive marks the lines pulled; the journal itself is never rewritten (docs/adr/002).
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src import attendance, history, tui_api, webdrive
from src.csvio import fmt_value, read_csv_text
from src.sync import config_file, is_total, raw_config
from src.webdrive import Refused, fmt_time, pad, width

PARTS = {"weights": "weights", "grade_boundaries": "grade boundaries"}
RESULTS = ("apply", "already applied", "conflict", "skipped", "no change")  # the order of the per-column summary


# ---- net change --------------------------------------------------------------------------------------------------
@dataclass
class Change:
    """The net change of one cell or config part, with every journal line that touched it (in journal order)."""
    lines: list
    result: str = ""
    reason: str = ""            # why it was skipped
    mac: object = None          # the Mac value: cell text, or the config part as a dict
    file: Path | None = None    # the Mac file holding the cell

    @property
    def is_config(self) -> bool:
        return self.lines[0].get("kind") == "config"

    @property
    def sid(self) -> str:
        return str(self.lines[0].get("student_id", "")).strip()

    @property
    def column(self) -> str:
        return str(self.lines[0].get("column", ""))

    @property
    def label(self) -> str:
        """The column it is summarised under: the column name, or `weights` / `grade boundaries`."""
        part = str(self.lines[0].get("part", ""))
        return PARTS.get(part, part) if self.is_config else self.column

    @property
    def base(self):
        return self.lines[0].get("original")

    @property
    def final(self):
        return self.lines[-1].get("value")


def net_changes(lines: list[dict]) -> list[Change]:
    """One Change per cell (student_id, column) or config part, in the order each first appears."""
    groups = {}
    for line in lines:
        if line.get("kind") == "config":
            k = ("config", line.get("part"))
        else:
            k = ("cell", str(line.get("student_id", "")).strip(), str(line.get("column", "")))
        groups.setdefault(k, Change([])).lines.append(line)
    return list(groups.values())


def _same_num(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return a == b


def same_part(a, b) -> bool:
    """Two config parts ({key: number}) are equal: the same keys, numerically equal values."""
    a = {str(k): v for k, v in (a or {}).items()}
    b = {str(k): v for k, v in (b or {}).items()}
    return a.keys() == b.keys() and all(_same_num(a[k], b[k]) for k in a)


# ---- classification against the Mac (reads only) -----------------------------------------------------------------
def _mac_cell(file: Path, header: str, sid: str, docs: dict) -> str | None:
    """The Mac text of `header` on the first row of `sid` (None when the student isn't in the file)."""
    if file.suffix == ".xlsx":
        import openpyxl
        ws = openpyxl.load_workbook(file).active
        col, rows = tui_api._xlsx_cells(ws, header)
        return fmt_value(ws.cell(row=rows[sid], column=col).value).strip() if col and sid in rows else None
    if file not in docs:
        docs[file] = read_csv_text(file)
    doc = docs[file]
    si, ci = doc.col("Student ID"), doc.col(header)
    row = next((r for r in doc.rows if si is not None and r[si].strip() == sid), None)
    return row[ci].strip() if row is not None and ci is not None else None


def classify(course: Path, changes: list[Change]) -> None:
    """Sets each change's result (and reason, Mac value, file)."""
    config = raw_config(course)
    docs = {}
    for c in changes:
        if c.is_config:
            c.mac = config.get(c.lines[0].get("part")) or {}
            if same_part(c.base, c.final):
                c.result = "no change"
            elif same_part(c.mac, c.final):
                c.result = "already applied"
            elif same_part(c.mac, c.base):
                c.result = "apply"
            else:
                c.result = "conflict"
            continue
        if tui_api._same_cell(c.base, c.final):
            c.result = "no change"
            continue
        if is_total(c.column):
            c.result, c.reason = "skipped", "total column"
            continue
        file, header, _ = tui_api._find_column_file(course / "data", c.column)
        if file is None:
            c.result, c.reason = "skipped", "column not in Mac files"
            continue
        c.file, c.mac = file, _mac_cell(file, header, c.sid, docs)
        if c.mac is None:
            c.result, c.reason = "skipped", "student not in Mac files"
        elif tui_api._same_cell(c.mac, c.final):
            c.result = "already applied"
        elif tui_api._same_cell(c.mac, c.base):
            c.result = "apply"
        else:
            c.result = "conflict"


# ---- preview -------------------------------------------------------------------------------------------------------
def _v(value) -> str:
    text = fmt_value(value)
    return text if text != "" else "(blank)"


def _kv(part) -> str:
    return ", ".join(f"{k} {fmt_value(v)}" for k, v in (part or {}).items())


def _counted(n: int, word: str) -> str:
    plural = word in ("conflict", "edit", "cell", "line") and n != 1
    return f"{n} {word}{'s' if plural else ''}"


def _summary_word(result: str) -> str:
    return "to apply" if result == "apply" else result


def apply_line(c: Change) -> str:
    if c.is_config:
        mac = {str(k): v for k, v in (c.mac or {}).items()}
        diff = [f"{k} {fmt_value(mac.get(str(k)))} → {fmt_value(v)}" for k, v in c.final.items()
                if not _same_num(mac.get(str(k)), v)]
        return f"  {c.label}: {', '.join(diff)}"
    return f"  {c.sid} {c.column}: {_v(c.mac)} → {_v(c.final)}"


def conflict_line(c: Change) -> str:
    if c.is_config:
        return f"  conflict: {c.label} — Mac {_kv(c.mac)}, web {_kv(c.final)}; apply by hand if wanted"
    return f"  conflict: {c.sid} {c.column} — Mac {_v(c.mac)}, web {_v(c.final)} (not applied)"


def preview(changes: list[Change]) -> list[str]:
    """The preview text, without its last line (which depends on --yes)."""
    out = ["By column:"]
    labels = list(dict.fromkeys(c.label for c in changes))
    w = max(width(lab) for lab in labels) + 3
    for lab in labels:
        mine = [c for c in changes if c.label == lab]
        bits = [_counted(n, _summary_word(r)) for r in RESULTS if (n := sum(c.result == r for c in mine))]
        out.append(f"  {pad(lab, w)}{' · '.join(bits)}")

    applies = [c for c in changes if c.result == "apply"]
    if applies:
        out += ["", "To apply (Mac value → web value):"] + [apply_line(c) for c in applies]
    kept = [c for c in changes if c.result in ("conflict", "skipped")]
    if kept:
        out += ["", "Not applied (Mac values kept):"]
        out += [conflict_line(c) if c.result == "conflict" else f"  skipped: {c.sid} {c.column} — {c.reason}"
                for c in kept]

    done = [c for c in changes if c.result == "already applied"]
    back = [c for c in changes if c.result == "no change"]
    superseded = sum(len(c.lines) - 1 for c in changes)
    out += ["", f"Already applied: {len(done)} · No change: {len(back)} · Replaced by a later edit: {superseded}"]
    for c in done:
        out.append(f"  already applied: {c.label} = {_kv(c.final)}" if c.is_config
                   else f"  already applied: {c.sid} {c.column} = {_v(c.final)}")
    for c in back:
        out.append(f"  no change: {c.label} (edited back to {_kv(c.base)})" if c.is_config
                   else f"  no change: {c.sid} {c.column} (edited back to {_v(c.base)})")
    return out


def _kept_text(changes: list[Change]) -> str:
    """` 1 conflict and 1 skipped are listed above (Mac values kept).`, or "" when there are none."""
    n_c = sum(c.result == "conflict" for c in changes)
    n_s = sum(c.result == "skipped" for c in changes)
    bits = [b for b in (_counted(n_c, "conflict") if n_c else "", f"{n_s} skipped" if n_s else "") if b]
    if not bits:
        return ""
    return f" {' and '.join(bits)} {'is' if n_c + n_s == 1 else 'are'} listed above (Mac values kept)."


# ---- archive -------------------------------------------------------------------------------------------------------
def _record(c: Change) -> dict:
    rec = {"result": "applied" if c.result == "apply" else c.result}
    if c.result == "skipped":
        rec["reason"] = c.reason
    if c.result == "conflict":
        rec["mac"] = c.mac
    return rec


def archived_lines(lines: list[dict], changes: list[Change]) -> list[dict]:
    """Every line read, in journal order, with its result (earlier lines of a cell or part are `superseded`)."""
    result = {}
    for c in changes:
        for line in c.lines[:-1]:
            result[id(line)] = {"result": "superseded"}
        result[id(c.lines[-1])] = _record(c)
    return [{**line, **result[id(line)]} for line in lines]


# ---- the pull ------------------------------------------------------------------------------------------------------
def _check_attendance(course: Path, applies: list[Change]) -> None:
    """Refuses (S11.15) when attendance cells would be written while the xlsx is open or the pair needs a sync."""
    if not any(c.file and c.file.name.endswith("attendance.csv") for c in applies):
        return
    xlsx, _ = attendance.files_of(course)
    if xlsx is not None and attendance.locked(xlsx):
        raise Refused(f"❌ Not applied: data/{xlsx.name} is open in Excel. Close it, then run grader web-pull --yes "
                      "again. Nothing was written.")
    if attendance.warnings(course):
        raise Refused("❌ Not applied: the attendance xlsx and csv differ; run `grader sync` first, then grader "
                      "web-pull --yes again. Nothing was written.")


def _stopped(e: history.Entry, what: str, error: str) -> int:
    entry_id = e.close()
    if entry_id is None:
        print(f"❌ Pull stopped while writing {what}: {error}. Nothing was written or archived; run grader web-pull "
              "--yes again.")
    else:
        print(f"❌ Pull stopped while writing {what}: {error}. What was written can be undone: grader undo "
              f"{entry_id}. Nothing was archived; run grader web-pull --yes again to finish.")
    return 1


def _file_note(file: Path) -> str:
    if file.name.endswith("attendance.csv"):
        return " (attendance xlsx too)" if file.with_suffix(".xlsx").exists() else ""
    return " (total column refreshed)" if any(is_total(h) for h in read_csv_text(file).header) else ""


def copy_to_pull(root: Path, course: Path, semester: str | None = None) -> Path:
    """The Drive copy web-pull reads (SPEC_semester_groups.md D8): the semester copy, or the old flat copy in
    grade_web. When both exist, the one with edits not pulled; both with edits is refused."""
    new, old = webdrive.place_of(root, course, semester)
    found = [p for p in (new, webdrive.old_copy(new, old)) if p and (p / "push.json").is_file()]
    if not found:
        raise Refused(f"❌ {course.name} hasn't been pushed: {webdrive.shown(root, new)} doesn't exist. Push it "
                      "with: grader web-push")
    if len(found) == 1:
        return found[0]
    waiting = [p for p in found if webdrive.unpulled(p)]
    if len(waiting) == 2:
        raise Refused(f"❌ Two Drive copies of {course.name} have web edits not pulled: {webdrive.shown(root, new)} "
                      f"and {webdrive.shown(root, old)}. Nothing was pulled. Keep the edits of one: delete the other "
                      "copy in Drive (its edits are lost), then run again.")
    return waiting[0] if waiting else new


def pull(course: Path, root: Path, yes: bool = False, semester: str | None = None) -> int:
    """Prints as it goes and returns the exit code. Raises Refused (nothing written) when it can't pull."""
    course = Path(course).resolve()
    mirror = copy_to_pull(root, course, semester)
    print(f"🔄 Web pull: {webdrive.shown(root, mirror)} → {course.name}")
    copies = webdrive.conflict_copies(mirror)
    if copies:
        raise Refused(f"❌ Drive has duplicate files in {webdrive.label(mirror)}/: {', '.join(copies)}. Fix "
                      "them as the README's \"Duplicate files\" says, then run again.")
    pushed = json.loads((mirror / "push.json").read_text(encoding="utf-8"))
    config = raw_config(course)
    drive_is = f"{pushed.get('course_id', '')} {pushed.get('term', '')}"
    mac_is = f"{config.get('course_id', '')} {config.get('term', '')}"
    if drive_is != mac_is:
        raise Refused(f"❌ The Drive copy is another course: Drive has {drive_is}, this folder is {mac_is}. Nothing "
                      "was pulled. Check the folder names.")

    lines = webdrive.unpulled(mirror)
    print(f"   {pushed.get('course_name', '')} ({pushed.get('course_id', '')}, {pushed.get('term', '')}) · pushed "
          f"{fmt_time(pushed['pushed_at'])} ({pushed.get('push_id', '')})")
    if not lines:
        print("✅ Nothing to pull: no web edits since the last pull.")
        return 0
    print(f"   Journal: {_counted(len(lines), 'edit')} not pulled · last saved "
          f"{fmt_time(webdrive.last_saved(lines))}")
    print("   (grade_web shows the same two numbers. If not, wait for Drive to sync and run again.)")
    print()

    changes = net_changes(lines)
    classify(course, changes)
    for text in preview(changes):
        print(text)
    applies = [c for c in changes if c.result == "apply"]
    only_done = all(c.result == "already applied" for c in changes)
    print()
    if not yes:
        if not applies and only_done:
            print(f"Nothing to change on the Mac: all {len(changes)} edits are already applied. Run grader web-pull "
                  "--yes to mark them pulled.")
        else:
            print("Preview only: nothing was written. Apply with: grader web-pull --yes")
        return 0

    _check_attendance(course, applies)
    e = history.Entry(course, "grader", "web-pull")
    cells = [c for c in applies if not c.is_config]
    parts = [c for c in applies if c.is_config]
    if cells:
        r = tui_api.apply_edits(course, [{"student_id": c.sid, "column": c.column, "value": c.final,
                                          "original": c.mac} for c in cells], entry=e)
        if r["status"] != "success":
            files = dict.fromkeys(c.file.relative_to(course).as_posix() for c in cells)
            return _stopped(e, ", ".join(files), r["message"])
        for k in r["conflicts"]:  # grade-tui saved one of these cells after the preview read it
            c = next(c for c in cells if c.sid == str(k["student_id"]).strip() and c.column == k["column"])
            c.result, c.mac = "conflict", k["disk_value"] or ""
            print(conflict_line(c))
    if parts:
        cfg = config_file(course)
        e.capture(cfg)
        new = {c.lines[0]["part"]: c.final for c in parts}
        r = tui_api.update_course_config(course, weights_dict=new.get("weights"),
                                         boundaries_dict=new.get("grade_boundaries"))
        if r["status"] != "success":
            return _stopped(e, f"course_info/{cfg.name}", r["message"])

    applied = [c for c in cells if c.result == "apply"]
    per_file = {}
    for c in applied:
        per_file[c.file] = per_file.get(c.file, 0) + 1
    for file, n in per_file.items():
        print(f"  ✍️  {file.relative_to(course).as_posix()}: {_counted(n, 'cell')}{_file_note(file)}")
    if parts:
        print(f"  ✍️  course_info/{cfg.name}: {', '.join(c.label for c in parts)}")

    path = webdrive.archive_path(mirror)
    header = {"kind": "pull", "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
              "tool": "grader web-pull", "mac_folder": course.name, "push": pushed.get("push_id"),
              "lines": len(lines), "history": e.id}
    data = webdrive.archive_bytes(header, archived_lines(lines, changes))
    what = ([_counted(len(applied), "cell")] if applied else []) + [c.label for c in parts]
    if e.files:  # the history copy of the archive; not in the entry's files, so `grader undo` leaves it
        (e.dir / path.name).write_bytes(data)
        e.note = f"web pull: {', '.join(what)}"
        e.close(cells=len(applied), journal=path.name)
    try:
        webdrive.save_archive(path, data)
    except OSError as ex:
        if e.id is None:
            raise
        print(f"⚠️  Applied on the Mac (undo with: grader undo {e.id}) but not archived on Drive: {ex.strerror or ex}.")
        print("   Run grader web-pull --yes again: it finds the cells already applied and only archives.")
        return 1
    print(f"  📦 Archived on Drive: {webdrive.ARCHIVE}/{path.name} ({_counted(len(lines), 'line')})")

    if e.id is None:
        done = sum(c.result == "already applied" for c in changes)
        print(f"✅ Nothing to change on the Mac{f' ({done} already applied)' if only_done else ''}."
              f"{_kept_text(changes)}")
        return 0
    print(f"✅ Pulled {' and '.join(what)}.{_kept_text(changes)}")
    print(f"   Undo with: grader undo {e.id}")
    return 0
