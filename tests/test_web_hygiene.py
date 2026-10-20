"""Repo hygiene for grade_web (S13.3): no secrets, Drive IDs or account names; existing tests and rust_tui untouched
(except the approved grade-order change)."""
import re
import subprocess

import pytest

from webtools import ROOT

BASE = "7a233a4"  # "docs: requirements for grade_web", the last commit before build work
SCANNED = ["web/apps_script", "web/tools", "web/scripts", "web/tests"]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def in_checkout():
    r = git("rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and r.stdout.strip() == "true" and git("cat-file", "-e", BASE).returncode == 0


needs_git = pytest.mark.skipif(not in_checkout(), reason="not inside the grade_dashboard git checkout")


def scanned_files():
    files = []
    for d in SCANNED:
        files += [p for p in (ROOT / d).rglob("*") if p.is_file() and "node_modules" not in p.parts]
    files += sorted((ROOT / "src").glob("web*.py"))
    return files


TOKENS = ["ya29.", '"refresh_token"', '"scriptId"']
DRIVE_ID = re.compile(r"""(?i)(?:id|folder|file)\w*["']?\s*[:=(,]\s*["']([-\w]{28,})["']""")
CMRU_ADDR = re.compile(r"[\w.+-]+@g\.cmru\.ac\.th")


@needs_git
def test_ac13_3_no_secrets_or_real_data():
    tracked = git("ls-files", "web").stdout.splitlines()
    for f in tracked:
        name = f.rsplit("/", 1)[-1]
        assert name not in (".clasp.json", ".clasprc.json"), f
        assert not name.lower().endswith((".xlsx", ".xls")), f
    for p in scanned_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = p.relative_to(ROOT).as_posix()
        for t in TOKENS:
            assert t not in text, f"{rel}: token-like string {t!r}"
        m = DRIVE_ID.search(text)
        assert m is None, f"{rel}: Drive-ID-like string {m.group(1)!r}"
        m = CMRU_ADDR.search(text)
        assert m is None, f"{rel}: account address {m.group(0)!r}"


@needs_git
def test_existing_tests_unchanged():
    # Modified or deleted only (--diff-filter=MD): test files added later (e.g. test_completion.py) are not edits.
    r = git("diff", "--quiet", "--diff-filter=MD", BASE, "--", "tests/", ":(exclude)tests/conftest.py",
            ":(exclude)tests/webtools.py", ":(exclude)tests/test_web_*.py")
    assert r.returncode == 0, git("diff", "--stat", BASE, "--", "tests/").stdout


@needs_git
def test_existing_conftest_fixtures_unchanged():
    """tests/conftest.py may only grow: every line it had at BASE is still there, in order, at the top."""
    old = git("show", f"{BASE}:tests/conftest.py").stdout
    now = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert now.startswith(old.rstrip("\n")), "existing conftest.py content was edited"


# The one approved grade-tui change on this branch: the boundaries dialog's letter order and check
# (SPEC_grade_order.md D7). Anything else under rust_tui/ is still off limits.
RUST_TUI_APPROVED = {"rust_tui/src/grades.rs", "rust_tui/src/app.rs", "rust_tui/src/main.rs"}


@needs_git
def test_rust_tui_untouched():
    changed = set(git("diff", "--name-only", BASE, "--", "rust_tui/").stdout.split())
    changed |= set(git("ls-files", "--others", "--exclude-standard", "rust_tui/").stdout.split())
    assert changed <= RUST_TUI_APPROVED, sorted(changed - RUST_TUI_APPROVED)
