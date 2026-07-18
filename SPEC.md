# Spec: Align Analytics tab data panels ([3] Analytics)

## 1. Boundaries panel — align the `:` in BOUNDARIES LIST

**File:** `rust_tui/src/ui.rs`, function `draw_analytics_boundaries_panel` (~line 1825).

**Problem:** Grade codes vary in width (`A`, `B+`, `B`, `C+`, `C`, `D+`, `D`, `F`), but each row
renders `"   Grade {g} : ≥ {val}"` with `g` unpadded — so the `:` lands in a different column
depending on whether `g` is 1 or 2 characters.

**Fix:**
- Before building `lines`, compute `code_width = sorted_bounds.iter().map(|(g, _)| g.len()).chain(std::iter::once("F".len())).max().unwrap_or(1)` — the width of the longest grade code actually present in this course (dynamic, not hardcoded to 2).
- In the main loop over `sorted_bounds`, pad the grade code to `code_width` *inside* the existing `Span::styled((*g).clone(), ...)` call, e.g. `format!("{:<width$}", g, width = code_width)`, keeping the same color/bold style (trailing spaces in a styled span are visually inert).
- Apply the same padding to the final `F` row's `Span::styled("F", ...)`.
- Leave the literal `" : ≥ "` / `" : < "` and the value formatting (`format!("{:.1}", val)`) untouched — only the code column changes width, values stay as-is (left-flush after the `≥`/`<`).

**Out of scope:** Right-aligning or decimal-aligning the numeric threshold values — explicitly not requested.

## 2. Progress Over Time panel — align ⚡ ATTENDANCE dates

**File:** `src/tui_api.py`, function `_compute_attendance_labels` (~line 86, the label built at line 122).

**Problem:** Labels are built as `f"{d.day} {d.strftime('%b')} {d.year}"`, e.g. `"3 Feb 2026"` vs
`"15 Feb 2026"`. Because `d.day` isn't fixed-width, the month abbreviation (`Feb`) starts at a
different column depending on whether the day-of-month is 1 or 2 digits, which misaligns that
column in the rust-tui's `draw_analytics_progress` panel (`rust_tui/src/ui.rs`, ~line 1868, which
left-pads the whole label string to a fixed width of 14 via `format!("{:<14}", label)` — that outer
padding only aligns the *bars*, not the month text within the label itself).

**Fix:**
- Change line 122 from:
  ```python
  labels[col] = f"{d.day} {d.strftime('%b')} {d.year}"
  ```
  to:
  ```python
  labels[col] = f"{d.day:>2} {d.strftime('%b')} {d.year}"
  ```
  This right-justifies the day-of-month to 2 characters (e.g. `" 3 Feb 2026"`, `"15 Feb 2026"`), so the month abbreviation always starts at the same column across all attendance rows.
- No change needed in `rust_tui/src/ui.rs` — the existing `{:<14}` label padding already accounts for the (now-consistent) label width; `types.rs`'s `HashMap<String, String>` shape is unaffected.

**Out of scope:**
- Any other category's item labels in the Progress Over Time panel (e.g. `hw1`, `q2`) — confirmed already uniform width, not touched.
- Any change to `rust_tui/src/ui.rs` rendering logic for this panel.

## End-to-end verification

1. Pick (or use) a course config with grade codes of mixed width, e.g. `A`, `B+`, `B`, `C+`, `C`,
   `D+`, `D` (already present in `courses/1_test_grading/course_info/1_test_config.yaml`).
2. Rebuild: `cargo build --release --manifest-path rust_tui/Cargo.toml`.
3. Run the TUI (`./rust_tui/target/release/rust_tui`), open that course, go to tab `[3] Analytics`,
   and view the Boundaries panel — confirm every `:` lines up in the same column across all grade
   rows (`A`, `B+`, `B`, `C+`, `C`, `D+`, `D`, `F`).
4. In the same course's config, ensure `term_start_date`, `class_schedule.day`, and enough `a1..aN`
   attendance columns exist so `_compute_attendance_labels` produces at least one single-digit-day
   date and one double-digit-day date (adjust `term_start_date` if needed to land a week on the
   1st–9th).
5. In the Analytics tab's Progress Over Time panel, confirm the `⚡ ATTENDANCE` series' date labels
   all show the month abbreviation starting at the same column, regardless of 1- vs 2-digit day
   (e.g. `" 3 Feb 2026"` and `"15 Feb 2026"` line up on `Feb`).
6. Confirm no other panel (Grade Value Distribution, Item Difficulty & Discrimination, other
   Progress Over Time categories) changed in appearance.
