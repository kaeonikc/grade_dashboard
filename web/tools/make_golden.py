"""
Writes web/tests/golden/ from the fixtures with grade-tui's own code (web/SPEC.md "Golden files", docs/adr/003).

    python3 web/tools/make_golden.py           write the golden files
    python3 web/tools/make_golden.py --check   compare instead; exit 1 on any difference

Per fixture course: course.json from `build_course_json` (what web-push writes) and the expected grades from
`tui_api.get_course_data` (what grade-tui shows), each on its own temp copy, because the loaders write totals and
sync attendance. Variants (fixtures/variants.json) apply their edits with `apply_edits` and their config with
`update_course_config` on another temp copy. Also csv_rows.json (Python's parse of every fixture CSV) and
canonical.json (what apply_edits stores for a typed text, and how cells.classify reads it).
"""

import argparse
import contextlib
import io
import json
import numbers
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src import cells, tui_api  # noqa: E402
from src.csvio import fmt_value, read_csv_text  # noqa: E402
from src.webpush import build_course_json  # noqa: E402

FIXTURES = ROOT / "web" / "tests" / "fixtures"
GOLDEN = ROOT / "web" / "tests" / "golden"
CANONICAL_INPUTS = ["9", "08", "8.50", "8.0", ".5", "5.", "0", " 9 ", "ขส", "", "P", "0.1", "12345678.9",
                    "0.30000000000000004", "0.00001", "10000000000000000.0"]


def _num(v):
    return int(v) if isinstance(v, numbers.Integral) else float(v)


@contextlib.contextmanager
def _copy(fixture: str):
    """A temp copy of a fixture course, keeping its folder name (course.json's `folder`)."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / fixture
        shutil.copytree(FIXTURES / fixture, dest)
        with contextlib.redirect_stderr(io.StringIO()):  # the loaders' warnings are not golden output
            yield dest


def _expected(course: Path) -> list:
    data = tui_api.get_course_data(course)
    if data["status"] != "success":
        raise SystemExit(f"get_course_data failed on {course.name}: {data['message']}")
    out = []
    for s in data["student_grades"]:
        ct = s.get("Coursework Total")
        out.append({
            "student_id": s["Student ID"],
            "name": s["Name"],
            "pct": {cat: _num(s[f"{cat}_pct"]) for cat in data["weights"]},
            "coursework_total": None if ct is None else _num(ct),
            "final_score": _num(s["Final Score"]),
            "grade": s["Grade"],
        })
    return out


def _variant(fixture: str, v: dict) -> list:
    with _copy(fixture) as course:
        if v.get("edits"):
            r = tui_api.apply_edits(course, v["edits"])
            if r["status"] != "success":
                raise SystemExit(f"variant {v['name']}: apply_edits failed: {r}")
        if v.get("weights") or v.get("grade_boundaries"):
            r = tui_api.update_course_config(course, v.get("weights"), v.get("grade_boundaries"))
            if r["status"] != "success":
                raise SystemExit(f"variant {v['name']}: update_course_config failed: {r}")
        return _expected(course)


def golden_course(fixture: str, variants: list) -> dict:
    with _copy(fixture) as course:
        course_json = build_course_json(course)
    with _copy(fixture) as course:
        expected = _expected(course)
    return {"course": course_json, "expected": expected,
            "variants": [{"name": v["name"], "expected": _variant(fixture, v)} for v in variants
                         if v["fixture"] == fixture]}


def csv_rows() -> dict:
    out = {}
    for p in sorted(FIXTURES.rglob("*.csv")):
        doc = read_csv_text(p)
        out[p.relative_to(FIXTURES).as_posix()] = {"header": doc.header, "rows": doc.rows, "bom": doc.bom,
                                                   "eol": doc.eol}
    return out


def canonical() -> list:
    return [{"input": x, "canonical": fmt_value(tui_api._cell_value(x)), "classify": list(cells.classify(x))}
            for x in CANONICAL_INPUTS]


def golden_texts() -> dict:
    """{file name: text} of every golden file."""
    variants = json.loads((FIXTURES / "variants.json").read_text(encoding="utf-8"))
    objs = {f"{d.name}.json": golden_course(d.name, variants) for d in sorted(FIXTURES.glob("*_grading"))}
    objs["csv_rows.json"] = csv_rows()
    objs["canonical.json"] = canonical()
    return {name: json.dumps(obj, ensure_ascii=False, indent=1) + "\n" for name, obj in objs.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Write (or --check) web/tests/golden/ from the fixtures.")
    ap.add_argument("--check", action="store_true", help="compare with the files on disk; exit 1 on a difference")
    args = ap.parse_args()
    texts = golden_texts()
    if args.check:
        stale = [n for n, t in texts.items()
                 if not (GOLDEN / n).is_file() or (GOLDEN / n).read_text(encoding="utf-8") != t]
        for n in stale:
            print(f"❌ web/tests/golden/{n} differs from grade-tui's output. Run: python3 web/tools/make_golden.py")
        if not stale:
            print(f"✅ {len(texts)} golden files match grade-tui.")
        return 1 if stale else 0
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for n, t in texts.items():
        (GOLDEN / n).write_text(t, encoding="utf-8")
        print(f"  ✍️  web/tests/golden/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
