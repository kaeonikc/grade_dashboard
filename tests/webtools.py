"""Helpers for the grade_web Mac-side tests (web/SPEC.md "Test plan", layer 2)."""
import contextlib
import hashlib
import io
import json
import os
import runpy
import shutil
import site
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRADER_PY = ROOT / "grader.py"
GRADER = ROOT / "grader"  # the git-tracked symlink: argparse's prog is "grader"
FIXTURES = ROOT / "web" / "tests" / "fixtures"
JOURNALS = FIXTURES / "journals"
F1 = "9_ฟิสิกส์จำลอง_grading"
F2 = "9_กลศาสตร์ทดลอง_grading"
P1 = "9_ฟิสิกส์จำลอง"


def grader_cli(argv, cwd=None, err=False):
    """Run grader.py in-process as `grader <argv>`. Returns (exit code, stdout) or (code, stdout, stderr)."""
    out, errbuf = io.StringIO(), io.StringIO()
    old_argv, old_cwd = sys.argv, os.getcwd()
    code = 0
    sys.argv = [str(GRADER)] + [str(a) for a in argv]
    try:
        if cwd is not None:
            os.chdir(cwd)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(errbuf):
            try:
                runpy.run_path(str(GRADER_PY), run_name="__main__")
            except SystemExit as e:
                if e.code is None:
                    code = 0
                elif isinstance(e.code, int):
                    code = e.code
                else:
                    print(e.code, file=sys.stderr)
                    code = 1
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
    return (code, out.getvalue(), errbuf.getvalue()) if err else (code, out.getvalue())


def grader_proc(argv, cwd, tty=False, home=None, env=None, unset=()):
    """Run `grader <argv>` as a real subprocess. Returns CompletedProcess (text). tty=True gives it a pty stdin."""
    e = dict(os.environ)
    if home is not None:
        e["HOME"] = str(home)
        e.setdefault("PYTHONUSERBASE", site.getuserbase())
    for k in unset:
        e.pop(k, None)
    e.update(env or {})
    cmd = [sys.executable, str(GRADER)] + [str(a) for a in argv]
    if not tty:
        with open(os.devnull) as dn:
            return subprocess.run(cmd, cwd=cwd, env=e, stdin=dn, capture_output=True, text=True, timeout=120)
    import pty
    master, slave = pty.openpty()
    try:
        return subprocess.run(cmd, cwd=cwd, env=e, stdin=slave, capture_output=True, text=True, timeout=120)
    finally:
        os.close(slave)
        os.close(master)


def tree_sha(path) -> dict:
    """{relative path: sha256} of every file under `path` ({} when it doesn't exist)."""
    path = Path(path)
    if not path.exists():
        return {}
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file()}


def mirror(root, course) -> Path:
    """The Drive mirror folder of a Mac course: <root>/grade_web/<course folder name>/."""
    return Path(root) / "grade_web" / Path(course).name


def journal_text(name, push=None) -> str:
    text = (JOURNALS / name).read_text(encoding="utf-8")
    if push is None:
        return text
    out = []
    for line in text.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        if isinstance(o, dict) and "push" in o:
            o["push"] = push
        out.append(json.dumps(o, ensure_ascii=False, separators=(",", ":")))
    return "".join(l + "\n" for l in out)


def put_journal(mirror_dir, name, push=None) -> Path:
    """Write the fixture journal `name` as the mirror's web_edits.jsonl (push fields rewritten when `push` given)."""
    p = Path(mirror_dir) / "web_edits.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(journal_text(name, push).encode("utf-8"))
    return p


def put_archive(mirror_dir, name="archive_pull_4.jsonl", as_name=None) -> Path:
    d = Path(mirror_dir) / "archive"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / (as_name or ("web_edits_20270121-180000.jsonl" if name == "archive_pull_4.jsonl" else name))
    shutil.copyfile(JOURNALS / name, dest)
    return dest


def csv_cell(path, sid, column):
    """The text of `column` (clean name or header) for the first row of `sid` in a CSV file."""
    import csv
    rows = list(csv.reader(io.StringIO(Path(path).read_bytes().decode("utf-8-sig"), newline="")))
    head = [h.strip() for h in rows[0]]
    idx = next(i for i, h in enumerate(head) if h == column or h.split(" (")[0] == column)
    for r in rows[1:]:
        if r and r[0].strip() == sid:
            return r[idx] if idx < len(r) else ""
    raise KeyError(sid)


def lines_of(text):
    return [l for l in text.splitlines()]
