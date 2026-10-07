"""
What a score cell in data/*.csv can hold (INTEGRATION.md, contract 1).

    number        a score
    empty         not entered yet               -> counts as 0
    "ขส"          absent from the exam (ขาดสอบ)  -> counts as 0, reported as absent
    anything else invalid                       -> counts as 0, reported as a warning

exam_projects (`exam submit scores`) writes "ขส" for students on the roster who have no
answer sheet. exam_projects/cli/exam_cli/gradebook.py keeps a copy of
`classify`; both are checked against the table in INTEGRATION.md.
Attendance columns have their own codes (P/A/L/X/EA) and don't go through here.
"""

import math

import pandas as pd

ABSENT = "ขส"


def classify(value):
    """Returns ("num", float) | ("empty", None) | ("absent", None) | ("invalid", text)."""
    if value is None:
        return ("empty", None)
    if isinstance(value, bool):
        return ("invalid", str(value))
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return ("empty", None)
        return ("num", float(value))
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return ("empty", None)
    if text == ABSENT:
        return ("absent", None)
    try:
        x = float(text.replace(",", ""))
    except ValueError:
        return ("invalid", text)
    if math.isnan(x) or math.isinf(x):
        return ("invalid", text)
    return ("num", x)


def numeric_frame(df: pd.DataFrame, cols) -> tuple[pd.DataFrame, list, list]:
    """
    Converts `cols` of `df` to floats (NaN where empty, absent or invalid).
    Returns (numeric_df, absences, invalid) where
      absences = [(row_index, col)]
      invalid  = [(row_index, col, text)]
    """
    out = pd.DataFrame(index=df.index)
    absences, invalid = [], []
    for col in cols:
        vals = []
        for idx, v in df[col].items():
            kind, x = classify(v)
            if kind == "num":
                vals.append(x)
                continue
            vals.append(float("nan"))
            if kind == "absent":
                absences.append((idx, col))
            elif kind == "invalid":
                invalid.append((idx, col, x))
        out[col] = pd.Series(vals, index=df.index, dtype=float)
    return out, absences, invalid
