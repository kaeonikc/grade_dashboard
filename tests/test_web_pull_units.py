"""Unit tests for src/webpull.py's net change and config comparison (the acceptance tests are in test_web_pull.py)."""
from src.webpull import archived_lines, net_changes, same_part


def line(batch, seq, sid="9900000001", column="hw2", value="", original="", **extra):
    return {"batch": batch, "seq": seq, "kind": "cell", "student_id": sid, "column": column, "value": value,
            "original": original, **extra}


def test_net_change_takes_first_original_and_last_value():
    a = line("b-1", 0, value="9", original="")
    b = line("b-1", 1, sid=" 9900000002 ", value="5", original="7")
    c = line("b-2", 0, value="8", original="9")
    changes = net_changes([a, b, c])
    assert [ch.lines for ch in changes] == [[a, c], [b]]
    assert (changes[0].base, changes[0].final) == ("", "8")
    assert changes[1].sid == "9900000002"


def test_config_parts_group_by_part():
    w1 = {"batch": "b-1", "seq": 0, "kind": "config", "part": "weights", "value": {"hw": 0.3}, "original": {"hw": 0.2}}
    w2 = {"batch": "b-2", "seq": 0, "kind": "config", "part": "weights", "value": {"hw": 0.25}, "original": {"hw": 0.3}}
    (ch,) = net_changes([w1, w2])
    assert ch.is_config and ch.label == "weights"
    assert (ch.base, ch.final) == ({"hw": 0.2}, {"hw": 0.25})


def test_same_part_compares_keys_and_numbers():
    assert same_part({"A": 80, "B": 70}, {"B": 70.0, "A": 80.0})
    assert not same_part({"A": 80}, {"A": 78})
    assert not same_part({"A": 80}, {"A": 80, "B": 70})
    assert same_part(None, {})


def test_archived_lines_keep_journal_order_and_mark_superseded():
    a, b, c = line("b-1", 0, value="9"), line("b-1", 1, column="hw3", value="4"), line("b-2", 0, value="8", original="9")
    changes = net_changes([a, b, c])
    changes[0].result, changes[1].result, changes[1].reason = "apply", "skipped", "column not in Mac files"
    out = archived_lines([a, b, c], changes)
    assert [o["result"] for o in out] == ["superseded", "skipped", "applied"]
    assert out[1]["reason"] == "column not in Mac files"
    assert [o["batch"] for o in out] == ["b-1", "b-1", "b-2"]
