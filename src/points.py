"""
Default points per category and the header a score column gets (SPEC_default_points.md, INTEGRATION.md).

A category can give all its columns one points value:

    data_mapping:
      lab:
        pts_each: 10
        columns: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

`lab` has 10 built in, so a plain list (`- 1: 10` or `- 1`) works too. A column's points are its own config value
(`- 5: 20`), else the category default. A column at the default gets a bare header (`4`); any other column keeps
`name (Npts)`. exam_projects/cli/exam_cli/gradebook.py has the same rule; both test the table in INTEGRATION.md.

No imports from the rest of src/, so data_loader, sync and grader.py can all use it.
"""

BUILTIN_DEFAULTS = {"lab": 10.0}


def fmt_pts(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def category_default(category, value) -> float | None:
    """The default points of one data_mapping category (`value` is its raw config entry): pts_each, else built-in."""
    if isinstance(value, dict) and value.get("pts_each") is not None:
        try:
            return float(value["pts_each"])
        except (TypeError, ValueError):
            pass
    return BUILTIN_DEFAULTS.get(str(category))


def defaults(config: dict) -> dict:
    """{category: default points} for the categories that have one (raw config, not load_config's cleaned one)."""
    out = {}
    for cat, value in (config.get("data_mapping") or {}).items():
        d = category_default(cat, value)
        if d is not None:
            out[str(cat)] = d
    return out


def resolve(pts, default):
    """A column's points: its own config value, else the category default (None when neither)."""
    return pts if pts is not None else default


def at_default(pts, default) -> bool:
    return pts is not None and default is not None and abs(float(pts) - float(default)) < 1e-9


def header_for(name, pts, default) -> str:
    """The canonical header: bare at the category default, `name (Npts)` otherwise, `name` when there are no points."""
    name = str(name)
    if pts is None or at_default(pts, default):
        return name
    return f"{name} ({fmt_pts(float(pts))}pts)"
