import math

import pandas as pd
import pytest

from src.cells import ABSENT, classify, numeric_frame

# The same table is in INTEGRATION.md and in exam_projects' contract test.
CASES = [
    ("12", ("num", 12.0)),
    (" 12.5 ", ("num", 12.5)),
    ("0", ("num", 0.0)),
    ("", ("empty", None)),
    ("  ", ("empty", None)),
    ("nan", ("empty", None)),
    ("ขส", ("absent", None)),
    (" ขส ", ("absent", None)),
    ("abs", ("invalid", "abs")),
    ("ข ส", ("invalid", "ข ส")),
    ("12a", ("invalid", "12a")),
]


@pytest.mark.parametrize("value,expected", CASES)
def test_classify_text(value, expected):
    assert classify(value) == expected


def test_classify_python_values():
    assert classify(None) == ("empty", None)
    assert classify(float("nan")) == ("empty", None)
    assert classify(7) == ("num", 7.0)
    assert classify(ABSENT) == ("absent", None)


def test_numeric_frame_marks_absent_and_invalid():
    df = pd.DataFrame({"a": ["1", "ขส", "x", None]})
    num, absences, invalid = numeric_frame(df, ["a"])
    assert num["a"].iloc[0] == 1.0
    assert all(math.isnan(v) for v in num["a"].iloc[1:])
    assert absences == [(1, "a")]
    assert invalid == [(2, "a", "x")]
