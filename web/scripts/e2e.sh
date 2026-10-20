#!/usr/bin/env bash
# grade_web end-to-end check (web/SPEC.md "End-to-end verification"). Fixtures and tmp folders only.
# Real entry points: python3 grader.py web-push|web-pull|undo|history, and node web/scripts/gas_run.js, which runs
# the real web/apps_script/ server code over the same tmp Drive folder the Mac commands use.
# Last line "E2E OK" and exit 0, or "E2E FAIL: step N: <what>" and exit 1.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$REPO"
STEP=0
fail() { echo "E2E FAIL: step $STEP: $*"; exit 1; }
step() { STEP="$1"; shift; echo "== step $STEP: $*"; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
RT="$(cd "$T" && pwd -P)"
case "$RT/" in
  "$HOME/Library/CloudStorage/"*|"$HOME/cmru/"*) echo "E2E FAIL: step 0: temp dir $RT is under a real data folder"; exit 1 ;;
esac

GIT_BEFORE="$(git status --porcelain 2>/dev/null || true)"
F1="9_ฟิสิกส์จำลอง_grading"
P1="9_ฟิสิกส์จำลอง"
SEM="2569-1"                    # the Mac course sits in a semester folder (SPEC_semester_groups.md)
C="$T/teachings/$SEM/$F1"
DRIVE="$T/MyDrive"
M="$DRIVE/grade_courses/$SEM/$F1"
P="$SEM/$F1"                    # the course's path in grade_web, through the semester shortcut
PROPS="$T/props.json"
export GRADE_WEB_DRIVE_ROOT="$DRIVE"
# Step 6e needs saveConfig (T10). Until Code.js has it, 6e is skipped and the journal holds 6 lines, not 7.
if grep -q '^function saveConfig(' web/apps_script/Code.js; then CONFIG=1; LINES=7; else CONFIG=0; LINES=6; fi

shalist() { (cd "$1" && find . -type f ! -name '*.bak' -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256); }
gas() { local now="$1"; shift; node web/scripts/gas_run.js --drive "$DRIVE" --props "$PROPS" --now "$now" "$@"; }
check() { # check <json file> <python asserts on r>
  python3 - "$1" "$2" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
exec(sys.argv[2])
PY
}

# ---------------------------------------------------------------------------------------------------------------------
step 1 "copy fixture F1 to a tmp Mac course"
mkdir -p "$T/teachings/$SEM" "$DRIVE"
cp -R "web/tests/fixtures/$F1" "$C"
[ -d "$C/course_info" ] || fail "fixture copy"

step 2 "attendance xlsx from the csv codes, plus a sync baseline"
python3 - "$C" <<'PY' >/dev/null || fail "building the attendance xlsx"
import csv, io, sys
from pathlib import Path
sys.path.insert(0, ".")
import grader, openpyxl, pandas as pd
course = Path(sys.argv[1])
p = next((course / "data").glob("*_attendance.csv"))
rows = list(csv.reader(io.StringIO(p.read_bytes().decode("utf-8-sig"), newline="")))
sessions = [h for h in rows[0][2:] if not h.lower().startswith("total")]
reg = pd.read_csv(next((course / "course_info").glob("*_student_info.csv")), dtype=str)
x = p.with_suffix(".xlsx")
grader.save_attendance_excel(x, reg, sessions)
wb = openpyxl.load_workbook(x); ws = wb.worksheets[0]
head = [c.value for c in ws[1]]
codes = {r[0]: r for r in rows[1:]}
for r in range(2, ws.max_row + 1):
    src = codes.get(str(ws.cell(row=r, column=1).value))
    for s in sessions:
        ws.cell(row=r, column=head.index(s) + 1).value = (src[rows[0].index(s)] if src else "") or None
wb.save(x)
grader.sync_cmd(str(course), yes=True)
PY
[ -f "$C/data/${P1}_attendance.xlsx" ] || fail "attendance xlsx missing"
[ -f "$C/history/attendance_sync.json" ] || fail "attendance baseline missing"

step 3 "grader web-push"
S0="$(shalist "$C")"
code=0; out="$(python3 grader.py web-push "$C" --drive-root "$DRIVE" 2>&1)" || code=$?
echo "$out"
[ "$code" = 0 ] || fail "web-push exit $code"
grep -q '^✅ Pushed' <<<"$out" || fail "no '✅ Pushed' line"
want="$(printf '%s\n' course.json "course_info/${P1}_student_info.csv" "data/${P1}_attendance.csv" \
  "data/${P1}_final.csv" "data/${P1}_homework.csv" "data/${P1}_midterm.csv" push.json web_edits.jsonl | LC_ALL=C sort)"
got="$(cd "$M" && find . -type f | sed 's#^\./##' | LC_ALL=C sort)"
[ "$got" = "$want" ] || fail "Drive file list differs: $got"
[ ! -s "$M/web_edits.jsonl" ] || fail "journal not empty"
for f in "course_info/${P1}_student_info.csv" "data/${P1}_attendance.csv" "data/${P1}_final.csv" \
         "data/${P1}_homework.csv" "data/${P1}_midterm.csv"; do
  cmp -s "$C/$f" "$M/$f" || fail "$f differs from the Mac file"
done
[ "$(shalist "$C")" = "$S0" ] || fail "web-push changed the Mac course folder"
[ ! -e "$DRIVE/grade_web" ] || fail "web-push wrote into grade_web"
grep -q "shortcut to grade_courses/$SEM" <<<"$out" || fail "no shortcut hint"
cp -R "$M" "$T/pushed"

step 3b "the teacher adds the semester shortcut grade_web/$SEM"
mkdir -p "$DRIVE/grade_web"
ln -s "$DRIVE/grade_courses/$SEM" "$DRIVE/grade_web/$SEM"

step 4 "a grade-tui edit on the Mac after the push"
python3 - "$C" <<'PY' || fail "apply_edits on the Mac"
import sys; sys.path.insert(0, ".")
from src import tui_api
r = tui_api.apply_edits(sys.argv[1], [{"student_id": "9900000003", "column": "hw2", "value": "7", "original": ""}])
assert r["status"] == "success" and r["saved"] == 1, r
PY
S1="$(shalist "$C")"

step 5 "gas_run listCourses"
gas 2027-01-20T09:00:00+07:00 listCourses > "$T/r.json" || fail "gas_run listCourses"
check "$T/r.json" '
c = [x for x in r["courses"] if x["folder"] == "'"$P"'"][0]
assert r["ok"] and c["available"] and c["unpulled"] == 0, r' || fail "course not available with 0 unpulled"

step 6a "gas_run saveBatch: 4 cells"
E6A='[{"student_id":"9900000001","column":"hw2","value":"9","original":""},{"student_id":"9900000001","column":"20 Jan 2027","value":"P","original":""},{"student_id":"9900000002","column":"20 Jan 2027","value":"A","original":""},{"student_id":"9900000003","column":"hw2","value":"5","original":""}]'
gas 2027-01-20T09:15:00+07:00 saveBatch "\"$P\"" "$E6A" > "$T/r.json" || fail "gas_run saveBatch"
check "$T/r.json" '
assert r["ok"] and len(r["saved"]) == 4 and r["conflicts"] == [] and r["journal"]["unpulled"] == 4, r' || fail "save of 4 cells"
python3 - "$M" "$T/pushed" "$P1" <<'PY' || fail "Drive CSVs or journal after the save"
import csv, io, json, sys
from pathlib import Path
m, pushed, p = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
lines = [json.loads(l) for l in (m / "web_edits.jsonl").read_text(encoding="utf-8").splitlines()]
assert len(lines) == 4 and len({l["batch"] for l in lines}) == 1, lines
def cell(path, sid, col):
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"), newline="")))
    i = next(k for k, h in enumerate(rows[0]) if h.split(" (")[0] == col)
    return next(r[i] for r in rows[1:] if r[0] == sid)
hw, att = m / f"data/{p}_homework.csv", m / f"data/{p}_attendance.csv"
assert cell(hw, "9900000001", "hw2") == "9" and cell(hw, "9900000003", "hw2") == "5"
assert cell(att, "9900000001", "20 Jan 2027") == "P" and cell(att, "9900000002", "20 Jan 2027") == "A"
for f, targets in ((hw, {"9900000001", "9900000003"}), (att, {"9900000001", "9900000002"})):
    old = (pushed / f.relative_to(m)).read_bytes().split(b"\n")
    new = f.read_bytes().split(b"\n")
    assert len(old) == len(new)
    for a, b in zip(old, new):
        if a != b:
            assert a.split(b",")[0].decode() in targets, (a, b)
PY

step 6b "gas_run saveBatch from a stale device"
gas 2027-01-20T09:16:00+07:00 saveBatch "\"$P\"" '[{"student_id":"9900000001","column":"hw2","value":"6","original":""}]' > "$T/r.json" || fail "gas_run saveBatch"
check "$T/r.json" '
assert r["saved"] == [] and len(r["conflicts"]) == 1, r
c = r["conflicts"][0]
assert c["reason"] == "changed" and c["now"] == "9" and r["journal"]["unpulled"] == 4, r' || fail "stale save not a conflict"

step 6c "resend 6a (Retry after a lost reply)"
J6="$(shasum -a 256 "$M/web_edits.jsonl")"
gas 2027-01-20T09:17:00+07:00 saveBatch "\"$P\"" "$E6A" > "$T/r.json" || fail "gas_run saveBatch"
check "$T/r.json" '
assert r["batch"] is None and len(r["already"]) == 4 and r["saved"] == [] and r["journal"]["unpulled"] == 4, r' || fail "retry not all already"
[ "$(shasum -a 256 "$M/web_edits.jsonl")" = "$J6" ] || fail "retry changed the journal"

step 6d "save hw1, then Undo last save"
gas 2027-01-20T09:20:00+07:00 saveBatch "\"$P\"" '[{"student_id":"9900000002","column":"hw1","value":"4","original":"10"}]' > "$T/r.json" || fail "gas_run saveBatch"
check "$T/r.json" 'assert len(r["saved"]) == 1, r' || fail "hw1 save"
B6D="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["batch"])' "$T/r.json")"
gas 2027-01-20T09:21:00+07:00 undoLastSave "\"$P\"" "\"$B6D\"" > "$T/r.json" || fail "gas_run undoLastSave"
check "$T/r.json" '
assert r["ok"] and len(r["saved"]) == 1 and r["undoes"] == "'"$B6D"'" and r["journal"]["unpulled"] == 6, r' || fail "undo"
python3 - "$M" "$P1" "$B6D" <<'PY' || fail "undo lines or Drive value"
import csv, io, json, sys
from pathlib import Path
m, p, b = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = [json.loads(l) for l in (m / "web_edits.jsonl").read_text(encoding="utf-8").splitlines()]
undo = [l for l in lines if "undoes" in l]
assert len(undo) == 1 and undo[0]["undoes"] == b, undo
rows = list(csv.reader(io.StringIO((m / f"data/{p}_homework.csv").read_text(encoding="utf-8-sig"), newline="")))
assert next(r[2] for r in rows[1:] if r[0] == "9900000002") == "10"
PY

if [ "$CONFIG" = 1 ]; then
step 6e "gas_run saveConfig grade_boundaries A 78"
B0='{"A":80,"B+":75,"B":70,"C+":65,"C":60,"D+":55,"D":50}'
B1='{"A":"78","B+":"75","B":"70","C+":"65","C":"60","D+":"55","D":"50"}'
gas 2027-01-20T09:30:00+07:00 saveConfig "\"$P\"" '"grade_boundaries"' "$B1" "$B0" > "$T/r.json" || fail "gas_run saveConfig"
check "$T/r.json" 'assert r["ok"] and r["warning"] is None and r["journal"]["unpulled"] == 7, r' || fail "config save"
python3 - "$M/course.json" <<'PY' || fail "course.json boundaries"
import json, sys
gb = json.load(open(sys.argv[1], encoding="utf-8"))["grade_boundaries"]
assert list(gb) == ["A", "B+", "B", "C+", "C", "D+", "D"] and gb["A"] == 78, gb
PY
else
step 6e "skipped: saveConfig arrives in T10"
fi

step 7 "grader web-pull (preview)"
code=0; out="$(python3 grader.py web-pull "$C" </dev/null 2>&1)" || code=$?
echo "$out"
[ "$code" = 0 ] || fail "web-pull preview exit $code"
grep -q "^   Journal: $LINES edits not pulled · last saved " <<<"$out" || fail "journal count line"
for line in '  9900000001 hw2: (blank) → 9' '  9900000001 20 Jan 2027: (blank) → P' '  9900000002 20 Jan 2027: (blank) → A' \
            '  conflict: 9900000003 hw2 — Mac 7, web 5 (not applied)' \
            '  no change: 9900000002 hw1 (edited back to 10)' \
            'Preview only: nothing was written. Apply with: grader web-pull --yes'; do
  grep -qxF -- "$line" <<<"$out" || fail "preview lacks: $line"
done
if [ "$CONFIG" = 1 ]; then
  grep -qxF -- '  grade boundaries: A 80 → 78' <<<"$out" || fail "preview lacks: grade boundaries"
fi
[ "$(shalist "$C")" = "$S1" ] || fail "the preview changed the Mac course"

step 8 "grader web-pull --yes"
JSHA="$(shasum -a 256 "$M/web_edits.jsonl" | cut -d' ' -f1)"
HIST0="$(python3 grader.py history --course "$C" -n 1000 | grep -c 'web-pull' || true)"
code=0; out="$(python3 grader.py web-pull "$C" --yes 2>&1)" || code=$?
echo "$out"
[ "$code" = 0 ] || fail "web-pull --yes exit $code"
grep -qxF -- "  ✍️  data/${P1}_attendance.csv: 2 cells (attendance xlsx too)" <<<"$out" || fail "attendance write line"
grep -qE "^  📦 Archived on Drive: archive/web_edits_[0-9]{8}-[0-9]{6}\\.jsonl \\($LINES lines\\)\$" <<<"$out" || fail "archive line"
grep -q '^✅ Pulled 3 cells' <<<"$out" || fail "result line"
HID="$(grep -oE '^   Undo with: grader undo [0-9]{8}-[0-9]{6}_grader_web-pull$' <<<"$out" | awk '{print $NF}')"
[ -n "$HID" ] || fail "undo line"
HIST1="$(python3 grader.py history --course "$C" -n 1000 | grep -c 'web-pull' || true)"
[ "$HIST1" = "$((HIST0 + 1))" ] || fail "history has $HIST1 web-pull lines (expected $((HIST0 + 1)))"
[ "$(shasum -a 256 "$M/web_edits.jsonl" | cut -d' ' -f1)" = "$JSHA" ] || fail "web-pull rewrote the journal"
python3 - "$C" "$M" "$P1" "$HID" "$CONFIG" <<'PY' || fail "Mac files after the pull"
import csv, io, sys, yaml, openpyxl
from pathlib import Path
c, m, p, hid = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
config = sys.argv[5] == "1"
def cell(path, sid, col):
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"), newline="")))
    i = next(k for k, h in enumerate(rows[0]) if h == col or h.split(" (")[0] == col)
    return next(r[i] for r in rows[1:] if r[0] == sid)
hw, att = c / f"data/{p}_homework.csv", c / f"data/{p}_attendance.csv"
assert cell(hw, "9900000001", "hw2") == "9" and cell(hw, "9900000001", "total (30pts)") == "17"
assert cell(hw, "9900000003", "hw2") == "7"
assert cell(att, "9900000001", "20 Jan 2027") == "P" and cell(att, "9900000002", "20 Jan 2027") == "A"
ws = openpyxl.load_workbook(c / f"data/{p}_attendance.xlsx").worksheets[0]
head = [x.value for x in ws[1]]
col = head.index("20 Jan 2027") + 1
tot = next(i for i, h in enumerate(head, 1) if str(h).lower().startswith("total"))
vals = {str(ws.cell(row=r, column=1).value): ws.cell(row=r, column=col).value for r in range(2, ws.max_row + 1)}
assert vals["9900000001"] == "P" and vals["9900000002"] == "A", vals
assert all(str(ws.cell(row=r, column=tot).value).startswith("=") for r in range(2, ws.max_row + 1))
cfg = yaml.safe_load((c / f"course_info/{p}_config.yaml").read_text(encoding="utf-8"))
assert float(cfg["grade_boundaries"]["A"]) == (78 if config else 80)
assert cfg["weights"] == {"attendance": 0.1, "homework": 0.2, "midterm": 0.3, "final": 0.4}
assert cfg["course_id"] == "MOCK" and cfg["term"] == "2027_S1"
arch = sorted((m / "archive").glob("web_edits_*.jsonl"))
assert len(arch) == 1
copies = list((c / "history" / hid).glob("web_edits_*.jsonl"))
assert len(copies) == 1 and copies[0].read_bytes() == arch[0].read_bytes()
PY

step 9 "grade-tui's loader on a copy shows S4.1"
cp -R "$C" "$T/check"
python3 - "$T/check" <<'PY' 2>/dev/null || fail "S4.1 values through grade-tui"
import sys; sys.path.insert(0, ".")
from src import tui_api
d = tui_api.get_course_data(sys.argv[1])
s = next(x for x in d["student_grades"] if x["Student ID"] == "9900000001")
got = (s["attendance_pct"], s["homework_pct"], s["Coursework Total"], s["midterm_pct"], s["final_pct"], s["Final Score"], s["Grade"])
assert got == (9.33, 17, 27, 21, 0, 48, "F"), got
PY

step 10 "grader web-pull --yes again"
code=0; out="$(python3 grader.py web-pull "$C" --yes 2>&1)" || code=$?
[ "$code" = 0 ] || fail "second pull exit $code"
grep -qxF '✅ Nothing to pull: no web edits since the last pull.' <<<"$out" || fail "second pull: $out"
[ "$(python3 grader.py history --course "$C" -n 1000 | grep -c 'web-pull' || true)" = "$HIST1" ] || fail "second pull wrote history"

step 11 "grader undo (no ID)"
code=0; out="$(python3 grader.py undo --course "$C" --yes 2>&1)" || code=$?
[ "$code" = 0 ] || fail "undo exit $code: $out"
filt() { grep -E '\./(data|course_info)/|\./history/attendance_sync\.json$' || true; }
[ "$(filt <<<"$(shalist "$C")")" = "$(filt <<<"$S1")" ] || fail "undo did not restore every pre-pull file"

step 12 "gas_run listCourses (the next locked call trims)"
gas 2027-01-21T19:00:00+07:00 listCourses > "$T/r.json" || fail "gas_run listCourses"
check "$T/r.json" '
c = [x for x in r["courses"] if x["folder"] == "'"$P"'"][0]
assert c["unpulled"] == 0, c' || fail "unpulled after pull"
[ ! -s "$M/web_edits.jsonl" ] || fail "journal still holds lines after the trim"
python3 - "$M" "$LINES" <<'PY' || fail "conflict line missing from the archive"
import json, sys
from pathlib import Path
lines = [json.loads(l) for a in sorted((Path(sys.argv[1]) / "archive").glob("*.jsonl"))
         for l in a.read_text(encoding="utf-8").splitlines()[1:]]
assert len(lines) == int(sys.argv[2])
assert any(l.get("student_id") == "9900000003" and l.get("column") == "hw2" and l.get("result") == "conflict" for l in lines)
PY

step 13 "grader web-push again"
ARCH="$(shalist "$M/archive")"
OLDPUSH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["push_id"])' "$M/push.json")"
sleep 1
code=0; out="$(python3 grader.py web-push "$C" 2>&1)" || code=$?
[ "$code" = 0 ] || fail "second push exit $code: $out"
grep -q '0 edits waiting to be pulled' <<<"$out" || fail "second push line"
NEWPUSH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["push_id"])' "$M/push.json")"
[ "$NEWPUSH" != "$OLDPUSH" ] || fail "push.json has the old push_id"
[ "$(shalist "$M/archive")" = "$ARCH" ] || fail "web-push touched archive/"

step 13b "the semester shortcut removed: the course leaves the list, its copy stays"
rm "$DRIVE/grade_web/$SEM"
gas 2027-01-21T19:10:00+07:00 listCourses > "$T/r.json" || fail "gas_run listCourses"
check "$T/r.json" 'assert r["ok"] and r["courses"] == [] and r["groups"] == [], r' || fail "course still listed"
[ -s "$M/push.json" ] || fail "the Drive copy went with the shortcut"
ln -s "$DRIVE/grade_courses/$SEM" "$DRIVE/grade_web/$SEM"
gas 2027-01-21T19:11:00+07:00 listCourses > "$T/r.json" || fail "gas_run listCourses"
check "$T/r.json" 'assert [c["folder"] for c in r["courses"]] == ["'"$P"'"] and r["groups"] == [{"name": "'"$SEM"'", "count": 1}], r' \
  || fail "course not back with the shortcut"

step 13c "an old flat copy with an unpulled edit makes web-push refuse"
cp -R "$M" "$DRIVE/grade_web/$F1"
python3 - "$DRIVE/grade_web/$F1" <<'PY' || fail "making the old copy"
import json, sys
from pathlib import Path
m = Path(sys.argv[1])
push = json.loads((m / "push.json").read_text(encoding="utf-8"))
push["push_id"] = "p-20270101-080000"
(m / "push.json").write_text(json.dumps(push), encoding="utf-8")
(m / "web_edits.jsonl").write_text(json.dumps({"batch": "b-old", "seq": 1, "ts": "2027-01-02T08:00:00+07:00",
  "kind": "cell", "push": push["push_id"], "student_id": "9900000001", "column": "hw2", "value": "4",
  "original": ""}) + "\n", encoding="utf-8")
PY
D0="$(shalist "$DRIVE/grade_courses")"
code=0; out="$(python3 grader.py web-push "$C" 2>&1)" || code=$?
[ "$code" = 1 ] || fail "web-push exit $code with an old copy holding edits: $out"
grep -q "The old copy .*grade_web/$F1/ has 1 web edit not pulled" <<<"$out" || fail "old-copy message: $out"
[ "$(shalist "$DRIVE/grade_courses")" = "$D0" ] || fail "the refused push wrote to Drive"
rm -rf "$DRIVE/grade_web/$F1"

step 14 "node tests"
node --test 'web/tests/*.test.js' >"$T/node.log" 2>&1 || { tail -40 "$T/node.log"; fail "node --test"; }

STEP=end
[ "$(git status --porcelain 2>/dev/null || true)" = "$GIT_BEFORE" ] || fail "the repo changed during the run"
echo "E2E OK"
