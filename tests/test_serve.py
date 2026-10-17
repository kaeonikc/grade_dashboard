"""`tui_api.py serve`: the long-running worker grade-tui talks to (one JSON line in, one out)."""
import io
import json
import subprocess
import sys

from src import tui_api

API = [sys.executable, str(tui_api.Path(tui_api.__file__))]


def ask(proc, cmd, *args, stdin=None):
    ask.n += 1
    req = {"id": ask.n, "cmd": cmd, "args": list(args)}
    if stdin is not None:
        req["stdin"] = stdin
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    assert line.startswith(f'{{"id": {ask.n},'), line[:40]
    return json.loads(line)


ask.n = 0


def test_worker_answers_many_requests_in_one_process(course):
    proc = subprocess.Popen(API + ["serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        data = ask(proc, "get-course-data", str(course))
        assert data["status"] == "success"
        hw1 = next(r for r in data["raw_scores"] if r["Student ID"] == "69000002")["hw1"]
        edits = json.dumps({"edits": [{"student_id": "69000002", "column": "hw1", "value": "22", "original": str(hw1)}]})
        r = ask(proc, "apply-edits", str(course), stdin=edits)
        assert r["saved"] == 1, r
        assert next(x for x in r["course_data"]["raw_scores"] if x["Student ID"] == "69000002")["hw1"] == 22
        assert ask(proc, "no-such-command")["status"] == "error"
        assert proc.poll() is None, "still running between requests"
    finally:
        proc.stdin.close()
        assert proc.wait(timeout=10) == 0, "exits cleanly when grade-tui closes the pipe"


def test_stray_prints_and_bad_lines_cannot_break_the_protocol(monkeypatch):
    def noisy(cmd, args, stdin_text=""):
        print("some library chatter")  # would corrupt the JSON stream if it reached stdout
        return {"status": "success", "cmd": cmd}

    monkeypatch.setattr(tui_api, "run_command", noisy)
    out = io.StringIO()
    tui_api.serve(io.StringIO('{"cmd": "a"}\nnot json\n\n{"cmd": "b"}\n'), out)
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [x.get("cmd") for x in lines] == ["a", None, "b"]
    assert lines[1]["status"] == "error"


def test_one_shot_cli_still_works(course):
    out = subprocess.run(API + ["get-course-data", str(course)], capture_output=True, text=True)
    assert json.loads(out.stdout)["status"] == "success"
