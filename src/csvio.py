"""
Cell-level CSV reading/writing for data/*.csv.

Score files are edited as text, so a write only changes the cells it means to
change: no "12" -> "12.0" reformatting, the BOM and line endings stay as they
were, and the file is replaced atomically (temp file + os.replace), so a reader
(grade-tui, `exam submit scores`) never sees half a file.
"""

import csv
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

BOM = b"\xef\xbb\xbf"


@dataclass
class CsvText:
    header: list
    rows: list = field(default_factory=list)
    bom: bool = False
    eol: str = "\n"

    def col(self, name: str) -> int | None:
        for i, h in enumerate(self.header):
            if h.strip() == name:
                return i
        return None


def read_csv_text(path) -> CsvText:
    raw = Path(path).read_bytes()
    bom = raw.startswith(BOM)
    text = raw[len(BOM):].decode("utf-8") if bom else raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        return CsvText(header=[], rows=[], bom=bom, eol=eol)
    header = rows[0]
    width = len(header)
    body = [r + [""] * (width - len(r)) if len(r) < width else r for r in rows[1:]]
    return CsvText(header=header, rows=body, bom=bom, eol=eol)


def render_csv_text(doc: CsvText) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator=doc.eol)
    w.writerow(doc.header)
    w.writerows(doc.rows)
    data = buf.getvalue().encode("utf-8")
    return BOM + data if doc.bom else data


def atomic_write_bytes(path, data: bytes) -> None:
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_csv_text(path, doc: CsvText) -> None:
    atomic_write_bytes(path, render_csv_text(doc))


def fmt_value(value) -> str:
    """How a Python value is written into a cell (None -> empty)."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)
