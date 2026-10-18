"""
The Drive side of grade_web (web/SPEC.md "Data model and file formats", "Mac commands").

A pushed course lives in <My Drive>/grade_web/<Mac course folder name>/. The Mac sees it through Google Drive for
Desktop, so every rule here is about never losing a line of the edit journal (docs/adr/002):

    web_edits.jsonl      written by the web app only; the Mac reads it and at most creates it empty
    archive/*.jsonl      written by the Mac only, always as a new file; a journal line whose `batch#seq` is in
                         any archive file counts as pulled (or discarded)

A journal that can't be read, or holds a line that isn't valid JSON, stops every command: it is never treated as
empty or shortened.
"""

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from src.csvio import atomic_write_bytes

ENV = "GRADE_WEB_DRIVE_ROOT"
FOLDER = "grade_web"
JOURNAL = "web_edits.jsonl"
ARCHIVE = "archive"
_COPY = re.compile(r" \(\d+\)(\.[^.]*)?$")  # Drive for Desktop's conflict copies: `web_edits (1).jsonl`


class Refused(Exception):
    """A refusal: the message (one or more lines) is printed as it is and the command exits 1."""


# ---- where -------------------------------------------------------------------------------------------------------
def drive_root(arg=None) -> Path:
    """--drive-root, else $GRADE_WEB_DRIVE_ROOT, else the one CMRU Google Drive folder under the home folder."""
    if arg:
        root = Path(arg)
    elif os.environ.get(ENV):
        root = Path(os.environ[ENV])
    else:
        found = sorted((Path.home() / "Library" / "CloudStorage").glob("GoogleDrive-*@g.cmru.ac.th/My Drive"))
        if not found:
            raise Refused("❌ No Google Drive folder for an @g.cmru.ac.th account under ~/Library/CloudStorage/. "
                          "Start Drive for Desktop, or pass --drive-root DIR.")
        if len(found) > 1:
            names = ", ".join(p.parent.name for p in found)
            raise Refused(f"❌ Found {len(found)} Google Drive folders: {names}. Choose one with --drive-root DIR "
                          f"(or set {ENV}).")
        root = found[0]
    if not root.is_dir():
        raise Refused(f"❌ Drive folder not found: {root} (is Drive for Desktop running?). Nothing was written. "
                      "Start it, or pass --drive-root DIR.")
    return root


def mirror_of(root, course) -> Path:
    return Path(root) / FOLDER / Path(course).name


def shown(root, path) -> str:
    """A Drive path as printed: under `My Drive/` when the root is a "My Drive" folder, else in full."""
    root = Path(root)
    rel = Path(path).relative_to(root).as_posix()
    return f"My Drive/{rel}/" if root.name == "My Drive" else f"{root / rel}/"


def conflict_copies(mirror) -> list[str]:
    """Files Drive made when two writers met (`… (1).csv`), relative to the mirror; archive/ isn't checked."""
    mirror = Path(mirror)
    if not mirror.is_dir():
        return []
    return [p.relative_to(mirror).as_posix() for p in sorted(mirror.rglob("*"))
            if p.is_file() and _COPY.search(p.name) and p.relative_to(mirror).parts[0] != ARCHIVE]


# ---- the journal -------------------------------------------------------------------------------------------------
def key(line: dict) -> str:
    return f"{line['batch']}#{line['seq']}"


def journal(mirror) -> list[dict]:
    """Every journal line in order ([] when there is no journal). Refuses when it can't be read or has bad lines."""
    path = Path(mirror) / JOURNAL
    if not path.exists():
        return []
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise Refused(f"❌ Couldn't read {FOLDER}/{Path(mirror).name}/{JOURNAL} ({e.strerror or e}). If Drive for "
                      "Desktop shows it as online-only, wait for it to download, then run again.")
    lines, bad = [], []
    for n, text in enumerate(raw.split(b"\n"), 1):
        if not text.strip():
            continue
        try:
            obj = json.loads(text.decode("utf-8"))
        except ValueError:
            obj = None
        if isinstance(obj, dict) and "batch" in obj and "seq" in obj:
            lines.append(obj)
        else:
            bad.append(n)
    if bad:
        raise Refused(f"❌ {JOURNAL} has lines that aren't valid JSON: {', '.join(map(str, bad))}. Nothing was "
                      "applied, archived or pushed. See the README, \"Damaged journal\".")
    return lines


def archived_keys(mirror) -> set:
    """`batch#seq` of every line in every archive file (header lines have no key)."""
    keys = set()
    folder = Path(mirror) / ARCHIVE
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        for text in path.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(text)
            except ValueError:
                continue
            if isinstance(obj, dict) and "batch" in obj and "seq" in obj:
                keys.add(key(obj))
    return keys


def unpulled(mirror) -> list[dict]:
    done = archived_keys(mirror)
    return [line for line in journal(mirror) if key(line) not in done]


def last_saved(lines) -> str:
    return max((str(line.get("ts", "")) for line in lines), default="")


def fmt_time(iso: str) -> str:
    """`2027-01-20T09:15:10+07:00` → `20 Jan 2027 09:15`, in the time's own offset."""
    d = datetime.fromisoformat(iso)
    return f"{d.day} {d:%b} {d.year} {d:%H:%M}"


def archive_path(mirror, suffix: str = "") -> Path:
    """A free name archive/web_edits_<YYYYMMDD-HHMMSS><suffix>.jsonl (`-2`, `-3` … when the name is taken)."""
    folder = Path(mirror) / ARCHIVE
    base = f"web_edits_{datetime.now():%Y%m%d-%H%M%S}{suffix}"
    path, n = folder / f"{base}.jsonl", 2
    while path.exists():
        path, n = folder / f"{base}-{n}.jsonl", n + 1
    return path


def archive_bytes(header: dict, lines: list[dict]) -> bytes:
    text = "".join(json.dumps(o, ensure_ascii=False, separators=(",", ":")) + "\n" for o in [header] + lines)
    return text.encode("utf-8")


def save_archive(path: Path, data: bytes) -> None:
    """Writes a new archive file (never one that exists: the name comes from archive_path)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, data)


def write_archive(mirror, header: dict, lines: list[dict], suffix: str = "") -> Path:
    path = archive_path(mirror, suffix)
    save_archive(path, archive_bytes(header, lines))
    return path


# ---- terminal columns --------------------------------------------------------------------------------------------
def width(text: str) -> int:
    """Display width: Thai vowel and tone marks (Mn/Me) and format characters (Cf) take no column."""
    return sum(1 for c in text if unicodedata.category(c) not in ("Mn", "Me", "Cf"))


def pad(text: str, w: int) -> str:
    return text + " " * max(w - width(text), 0)
