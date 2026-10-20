"""zsh Tab completion for grader (SPEC.md Part A): the generator, the dynamic lists, install/refresh, and Tab
pressed in a real zsh (clean `zsh -f` on a pty, only the generated _grader on fpath; skipped without zsh)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src import complete, history
import zshtab
from conftest import PREFIX, write

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import grader  # noqa: E402  (its parser; the CLI itself runs only under __main__)

PARSER = grader.build_parser()
HELPER = [sys.executable, str(ROOT / "src" / "complete.py")]


# ---- generator --------------------------------------------------------------------------------------------
def test_tables_name_real_subcommands_and_dests():
    subs = complete._subcommands(PARSER)
    for cmd, dest in complete.VALUES:
        assert cmd in subs and dest in {a.dest for a in subs[cmd]._actions}, (cmd, dest)
    for cmd, groups in complete.EXCLUSIVE.items():
        for group in groups:
            for dest in group:
                assert dest in {a.dest for a in subs[cmd]._actions}, (cmd, dest)


def test_script_has_every_subcommand_and_option():
    script = complete.zsh_script(PARSER)
    for name, sp in complete._subcommands(PARSER).items():
        assert f"'{name}:" in script and f"_grader_cmd_{name.replace('-', '_')}()" in script
        for a in sp._actions:
            for s in a.option_strings:
                assert s in script, (name, s)
    assert script.startswith("#compdef grader\n")


def test_summary_cuts_at_first_clause_and_width():
    sync = complete._help_of(PARSER, "sync")
    assert complete._summary(sync) == "After editing score CSVs or the attendance sheet by hand"
    purge = next(a.help for a in complete._subcommands(PARSER)["update"]._actions if a.dest == "purge_empty_orphans")
    s = complete._summary(purge)
    assert len(s) <= 70 and s.endswith("…") and s.startswith("Remove category-CSV columns")
    assert complete._summary("Path to file (e.g. repclasslist.xls)") == "Path to file (e.g. repclasslist.xls)"
    assert complete._summary("Course folder (default: here)") == "Course folder (default: here)"
    assert complete._q("a [b]: it's") == "a \\[b\\]\\: it'\\''s"


# ---- dynamic lists ----------------------------------------------------------------------------------------
def _run(args, cwd):
    return subprocess.run(HELPER + args, cwd=cwd, capture_output=True, text=True, check=True).stdout.splitlines()


def test_courses_lists_course_folders_here_and_under_courses(tmp_path):
    for d in ("A_grading", "courses/B"):
        (tmp_path / d / "course_info").mkdir(parents=True)
    (tmp_path / "not_a_course").mkdir()
    assert _run(["courses"], tmp_path) == ["A_grading", "courses/B"]


@pytest.fixture
def with_history(course):
    hw = course / "data" / f"{PREFIX}_homework.csv"
    old = history.snapshot(course, [hw], "grade-tui", "edit", cells=1)
    history.restore(course, old)                                   # an undo of an earlier edit
    for _ in range(25):
        history.snapshot(course, [hw], "grader", "update")
    last = history.snapshot(course, [hw], "grade-tui", "edit", cells=2)
    history.snapshot(course, [hw], "grade-tui", "totals")          # automatic: never listed
    return course, old, last


def test_undo_ids_newest_20_undoable_with_descriptions(with_history):
    course, old, last = with_history
    lines = _run(["undo-ids"], course)
    assert len(lines) == 20
    ids = [l.split("\t")[0] for l in lines]
    assert ids[0] == last and old not in ids
    assert not any("totals" in i or "_undo" in i for i in ids)
    assert lines[0] == f"{last}\t[grade-tui edit, 2 cells] homework.csv"
    assert ids == [e["id"] for e in history.undoable(course)][:20]


def test_undo_ids_course_resolution(with_history, tmp_path):
    course, _, last = with_history
    assert _run(["undo-ids", str(course)], tmp_path)[0].startswith(last)       # --course
    assert _run(["undo-ids"], course.parent)[0].startswith(last)              # the course under ./
    other = tmp_path / "courses" / "Other"
    write(other / "course_info" / "Other_config.yaml", "term: x\n")
    write(other / "x.csv", "a\n")
    newer = history.snapshot(other, [other / "x.csv"], "grader", "sync")
    assert _run(["undo-ids"], tmp_path)[0].startswith(newer)                  # the most recently changed
    assert _run(["undo-ids", str(tmp_path / "nope")], tmp_path) == []


def test_helper_loads_no_third_party_module(tmp_path):
    out = subprocess.run([sys.executable, "-I", "-X", "importtime", *HELPER[1:], "courses"], cwd=tmp_path,
                         capture_output=True, text=True, check=True)
    loaded = {l.split("|")[-1].strip().split(".")[0] for l in out.stderr.splitlines() if "|" in l}
    assert not loaded & {"pandas", "yaml", "numpy", "openpyxl"}


# ---- install and refresh ----------------------------------------------------------------------------------
@pytest.fixture
def comp_dir(tmp_path, monkeypatch):
    d = tmp_path / "comp"
    monkeypatch.setenv("GRADER_ZSH_COMPLETIONS", str(d))
    return d


def test_install_writes_and_refuses_a_foreign_file(comp_dir, capsys):
    assert complete.install(PARSER) == 0
    path = comp_dir / "_grader"
    assert path.read_text(encoding="utf-8") == complete.zsh_script(PARSER)
    assert "wrote" in capsys.readouterr().out
    assert not list(comp_dir.glob(".*tmp*"))                       # written via a temp file + rename
    path.write_text("#compdef grader\n# someone else's\n", encoding="utf-8")
    assert complete.install(PARSER) == 1
    assert "someone else" in path.read_text(encoding="utf-8")


def test_cli_install_and_zsh(comp_dir, tmp_path):
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "grader.py"), "completion", *a], cwd=tmp_path,
                                    capture_output=True, text=True, env=os.environ.copy())
    assert run("zsh").stdout == complete.zsh_script(PARSER)
    assert run("install").returncode == 0 and (comp_dir / "_grader").exists()


@pytest.fixture
def copies(tmp_path, monkeypatch, comp_dir):
    """complete.py as if grader.py and itself lived in tmp_path, so their mtimes can be moved."""
    g, h = tmp_path / "grader.py", tmp_path / "complete.py"
    g.write_text("", encoding="utf-8")
    h.write_text("", encoding="utf-8")
    monkeypatch.setattr(complete, "GRADER", g)
    monkeypatch.setattr(complete, "HERE", h)
    return g, h


def test_refresh_needs_an_installed_file(copies, comp_dir):
    complete.refresh_installed(PARSER)
    assert not (comp_dir / "_grader").exists()


def test_refresh_regenerates_when_grader_is_newer(copies, comp_dir):
    g, _ = copies
    complete.install(PARSER)
    path = comp_dir / "_grader"
    path.write_text(path.read_text(encoding="utf-8").replace("Launch the grade dashboard", "STALE"),
                    encoding="utf-8")
    os.utime(path, (1_000_000, 1_000_000))
    complete.refresh_installed(PARSER)
    assert path.read_text(encoding="utf-8") == complete.zsh_script(PARSER)


def test_refresh_touches_when_unchanged_and_skips_when_fresh(copies, comp_dir):
    complete.install(PARSER)
    path = comp_dir / "_grader"
    os.utime(path, (1_000_000, 1_000_000))
    complete.refresh_installed(PARSER)
    assert path.stat().st_mtime > 1_000_000                       # touched, so the next check is one stat
    path.write_text(path.read_text(encoding="utf-8") + "# kept\n", encoding="utf-8")
    complete.refresh_installed(PARSER)                             # newer than grader.py: left alone
    assert path.read_text(encoding="utf-8").endswith("# kept\n")


def test_refresh_leaves_foreign_files_and_swallows_errors(copies, comp_dir, monkeypatch):
    comp_dir.mkdir()
    path = comp_dir / "_grader"
    path.write_text("#compdef grader\n# mine\n", encoding="utf-8")
    os.utime(path, (1_000_000, 1_000_000))
    complete.refresh_installed(PARSER)
    assert path.read_text(encoding="utf-8") == "#compdef grader\n# mine\n"
    path.unlink()
    complete.install(PARSER)
    os.utime(path, (1_000_000, 1_000_000))
    monkeypatch.setattr(complete, "zsh_script", lambda p: 1 / 0)
    complete.refresh_installed(PARSER)                             # no exception escapes


# ---- Tab in a real zsh ------------------------------------------------------------------------------------
zsh_only = pytest.mark.skipif(not zshtab.zsh_available(), reason="zsh not installed")


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    root = tmp_path_factory.mktemp("tab")
    comp = root / "comp"
    comp.mkdir()
    (comp / "_grader").write_text(complete.zsh_script(PARSER), encoding="utf-8")
    term = root / "term"
    c = term / f"{PREFIX}_grading"
    write(c / "course_info" / f"{PREFIX}_config.yaml", "term: 2026_S1\n")
    write(c / "data" / f"{PREFIX}_homework.csv", "Student ID,Name\n")
    for _ in range(22):
        history.snapshot(c, [c / "data" / f"{PREFIX}_homework.csv"], "grader", "update")
    (term / "courses" / "Second" / "course_info").mkdir(parents=True)
    for f in ("repclasslist_X.xls", "notes.txt"):
        (term / f).write_text("", encoding="utf-8")
    return {"comp": comp, "term": term, "course": c}


def tab(fx, line, cwd=None):
    out = zshtab.complete(line, cwd or fx["term"], fx["comp"], [])
    return out[out.index("READY #"):]


def group(out: str, title: str) -> list[str]:
    """The lines listed under one [[group]] heading."""
    lines, on = [], False
    for l in out.splitlines():
        if l.startswith("[[") or l.startswith("% ") or l.startswith("BUF<"):
            on = l == f"[[{title}]]"
            continue
        if on:
            lines.append(l.rstrip())
    return lines


def names(lines: list[str]) -> set[str]:
    return {w for l in lines for w in l.split(" -- ")[0].split()}


@zsh_only
def test_tab_lists_subcommands_with_summaries(fx):
    out = tab(fx, "grader ")
    cmds = group(out, "grader command")
    assert names(cmds) == set(complete._subcommands(PARSER))
    assert any(l.startswith("sync") and l.endswith("After editing score CSVs or the attendance sheet by hand")
               for l in cmds)
    assert names(group(out, "option")) == {"-h", "--help"}


@zsh_only
def test_undo_bare_tab_shows_entries_and_options(fx):
    out = tab(fx, "grader undo ", cwd=fx["course"])
    entries = group(out, "history entry")
    assert len(entries) == 20 and all("[grader update] homework.csv" in l for l in entries)
    assert names(group(out, "option")) == {"--course", "-y", "--yes", "-h", "--help"}


@zsh_only
def test_init_input_offers_class_lists_and_folders(fx):
    listed = names(group(tab(fx, "grader init -i "), "input"))
    assert "repclasslist_X.xls" in listed and "courses/" in listed and "notes.txt" not in listed


@zsh_only
def test_init_modes_exclude_each_other(fx):
    after_i = names(group(tab(fx, "grader init -i x.xls -"), "option"))
    assert "--term" not in after_i and "--course_id" not in after_i
    after_term = names(group(tab(fx, "grader init --term 2026_S1 -"), "option"))
    assert "--course_id" in after_term and "-i" not in after_term and "--input" not in after_term


@zsh_only
def test_update_roster_mode_hides_config_mode(fx):
    out = tab(fx, "grader update -i x.xls ")
    assert not group(out, "config file")
    assert names(group(out, "option")) == {"-h", "--help"}


@zsh_only
def test_course_options_list_course_folders(fx):
    listed = names(group(tab(fx, "grader sync --course "), "course folder"))
    assert listed == {f"{PREFIX}_grading", "courses/Second"}


@zsh_only
def test_text_values_list_no_files(fx):
    out = tab(fx, "grader history -n ")
    assert "notes.txt" not in out and "repclasslist_X.xls" not in out


@zsh_only
def test_completion_words(fx):
    assert names(group(tab(fx, "grader completion "), "what")) == {"install", "zsh"}
