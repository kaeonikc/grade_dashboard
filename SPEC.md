# Box Plot panel: revert to horizontal orientation, stacked full-width layout

## Goal

Terminal character cells are roughly twice as tall as wide, so for the same panel area a
horizontal layout gets far more resolution (character *columns*) than a vertical one gets
(character *rows*). That asymmetry is the root cause of every collision/nudge/connector problem
the vertical box plot has needed since it was introduced — ~9-15 rows for a 0-100 range is
inherently coarse, while a full-width horizontal chart gets ~75-85 columns for the same range.

Revert the box plot to **horizontal orientation**, and restructure the quadrant from the current
side-by-side split (`Box Plot` 40% | `Outliers` 60%, two separate bordered sub-panels) into a
**single bordered panel, stacked**: the chart on top using the full quadrant width, a plain
horizontal divider line, then the outliers list below (also full width). This both maximizes the
chart's resolution and removes a redundant second border.

Carried forward from the vertical version (these were genuine improvements, not tied to
orientation): the box is background-filled (not just an outline/bracket), mean is a colored tick
*matching the median's glyph*, not a diamond, and outlier dots are not drawn on the chart itself
(the dedicated list below is the one place for who/what they are).

**Dropped**: the nudge/connector system. It existed specifically to solve the vertical layout's
row-scarcity problem. In this design, (a) every value's exact number is always shown on its own
text line regardless of chart position, and (b) ~80 columns of resolution makes true collisions
rare — so when two ticks do round to the same column, simple draw-order precedence (median wins
over mean, matching the original pre-nudge convention) is sufficient, same as the very first
version of this feature had.

## Files / functions involved

- `rust_tui/src/ui.rs::draw_analytics_box_plot` — full rewrite of the rendering body (signature
  and outer title `" 📦 Box Plot "` unchanged). No more internal `Layout::horizontal` split into
  two sub-panels — one `Block` for the whole quadrant.
- No changes to `src/tui_api.py`, `rust_tui/src/types.rs`, or `draw_analytics_summary`'s
  40:60 row/column ratios (those ratios govern this quadrant's size *within the grid*, which is
  unrelated to how this quadrant lays out its own internal content).

## Behavior

### Layout (single panel, stacked)

```
┌ 📦 Box Plot ────────────────────────────────────────────────────────────────┐
│  Min: 26.0   Q1: 62.5   Median: 71.5   Q3: 79.8   Max: 93.0                  │
│  Mean: 67.0   IQR: 17.2 · left-skewed                                        │
│                                                                              │
│   ├──────[███████████┃███████████]───────────────────────┤                  │
│   0                25               50               75              100    │
│   ─ Whisker   █ Box   ┃ Median   ┃ Mean                                     │
│ ──────────────────────────────────────────────────────────────────────────  │
│  ⚡ Outliers (4), sorted ascending                                           │
│  69200009  Michael      Carter        26.0                                  │
│  69200029  Steven       Lewis         31.0                                  │
│  69200017  Charlie      Prince        33.0                                  │
│  69200016  Steven       Taylor        34.0                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

One `Block` (unchanged border/title style). Content is a single `Vec<Line>`:
1. Five-number-summary line: `Min`/`Q1`/`Median`/`Q3`/`Max`, each colored (info/box/median/box/info
   — same convention as the original pre-vertical design), using whisker-end wording (`"Min"` vs
   `"Low"`, `"Max"` vs `"High"`) exactly like the vertical version did, since that distinction
   (raw extreme vs. fence-clipped) is still meaningful and there's room to spell it out again.
2. `Mean: {v}   IQR: {q3-q1}   {skew, short form}` line.
3. Blank line.
4. The chart line (see below).
5. Tick label line: `0`, `25`, `50`, `75`, `100` at their proportional columns (fixed 0-100 axis,
   right-aligned overflow guard for `100` — same logic as the original horizontal version).
6. Legend line: `─ Whisker   █ Box   ┃ Median   ┃ Mean` (colored per glyph).
7. A full-width horizontal rule (`─` repeated across inner width) — the divider you asked for,
   separating the chart from its outliers list.
8. `⚡ Outliers (N), sorted ascending` (or `No outliers (beyond 1.5×IQR).` when empty).
9. Outlier rows: `student_id  name  score`, sorted ascending (unchanged), name field widened from
   `format_thai_name(&o.name, 12)` to `format_thai_name(&o.name, 20)` now that the row has the
   full quadrant width instead of ~60% of it. Height-capped with `"+ N more"` exactly as today,
   just computed against the remaining space in this single shared panel instead of a second
   sub-panel's own inner height.

### The chart line itself

Single `Line`, `width` = panel inner width (full quadrant width, no more `Constraint::Length(30)`
budget). `pos(v) = ((v.clamp(0,100)/100) * (width-1)).round()`, unchanged fixed-0-100-axis
principle from every prior version.

Built in this draw order (later writes win — same precedence philosophy as before, just simpler
since there's no nudging):
1. `─` from `whisker_low` to `q1`, and from `q3` to `whisker_high` (thin whisker lines,
   `whisker_style`).
2. `█` fill from `q1` to `q3` inclusive (`box_style`) — this is a real background-color fill
   (`Style::bg(dim_box)`, reusing the exact RGB already validated in the vertical version) under
   the `█` foreground glyph, not just a hollow bracket, per your "filled, no gaps" requirement.
3. `├` at `whisker_low`, `┤` at `whisker_high` (whisker caps).
4. `┃` at `mean`'s column, `mean_style` (purple) — drawn *before* median.
5. `┃` at `median`'s column, `median_style` (green) — drawn last, so on the rare exact-column
   tie, median's glyph and its own `dim_median` background tint win, exactly mirroring the
   vertical version's tie-breaking rule.

No outlier dots are drawn on this line.

### Edge case: `q1 == q3` (IQR == 0)

Box collapses to a single column — `█` fill loop naturally renders just that one column; no
special-casing needed (matches how the original horizontal version already handled this).

## Out of scope

- No changes to `draw_analytics_summary`'s grid ratios, or to any other quadrant/tab.
- No nudge/connector system — intentionally removed, not preserved as dead code.
- No interactivity (still read-only).
- No changes to `src/tui_api.py` / `types.rs` — all needed fields already exist.
- No image/matplotlib rendering path — this stays purely in ratatui/character-cell rendering, per
  your decision to keep this text-based rather than pursue a terminal-graphics-protocol image
  approach.

## End-to-end verification

1. `cargo build --release --manifest-path rust_tui/Cargo.toml`, run, load `0_mock_grading`
   (30 students, 4 low-side outliers, whisker_low 41.0 ≠ min 26.0), go to `[3] Analytics` →
   `Overview`.
2. Confirm the quadrant is now **one bordered panel** (not two side-by-side), with the chart
   spanning the full width, a visible horizontal rule below the legend, and the outliers list
   below that rule using the full width too.
3. Confirm the five-number-summary line reads `Min` as `"Low"`-worded correctly (i.e. shows the
   dynamic wording) and the chart's bottom-left whisker cap position corresponds to 41.0, not
   26.0 — with 26.0 only appearing in the outliers list below.
4. Confirm the box is visibly filled (background color), not just an outline, and that median
   (green `┃`) and mean (purple `┃`) render as distinct, separately-colored tick marks at their
   correct proportional positions — check they're clearly separated (not overlapping) given the
   much higher column resolution.
5. Load `2026_S1_Cosmology_grading` (mean 85.2 / median 86.0 — the pair that collided constantly
   in the vertical version) and confirm they now render as two distinct, separately-visible ticks
   a couple columns apart, without needing any merge/nudge handling.
6. Confirm the outliers list shows full names without the aggressive 12-char truncation from
   before (verify against a course with longer names, e.g. one of the Thai-language courses).
7. Resize the terminal narrower and confirm the chart's tick labels (`0`...`100`) still fit without
   overlapping garbage, and the box/whisker still render sensibly at reduced width.
