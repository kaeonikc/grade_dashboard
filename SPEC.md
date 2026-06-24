# Spec: Raw Details Tab — Three-Level Drill-Down with Student Popup

## Summary

Extend the **[2] Raw Details** tab from two levels to three, with dynamic breadcrumb
titles at every level.

### Navigation hierarchy

```
Level 0 — Category Overview
    │  Enter on any category column (col ≥ 2)
    ▼
Level 1 — Sub-Column View  (selected category)
    │  Enter on any student row
    ▼
Level 2 — Student Popup  (selected category × selected student)
    │  Enter on any sub-column cell (col ≥ 2)
    ▼
Level 3 — Cell Editor  (existing tui-textarea overlay)
```

Esc ascends one level at a time.  
Esc at Level 0 → CourseSelect screen (existing behaviour).

---

## Level descriptions

### Level 0 — Category Overview (unchanged)
- Full-screen table: `Student ID | Name | homework | midterm | final | attendance | …`
- Each category cell = sum of sub-scores (using `score_value()` for P/A/L/EA).
- Title: `"📋 Raw Details  (Enter: drill into category)"`
- Enter on col ≥ 2 → sets `raw_selected_category`, resets `cursor_col = 2`, `scroll_col_offset = 0`.

### Level 1 — Sub-Column View (minor update)
- Full-screen table: `Student ID | Name | sub1 | sub2 | … | [Total (pts)]`
- For attendance categories only, a "Total (pts)" column is appended (existing).
- Title: `"📋 Raw Details  ›  {category}  (Enter: open student  Esc: back)"`
- Enter on any row → sets `raw_selected_student = Some(cursor_row)`, resets `cursor_col = 2`.
- Esc → clears `raw_selected_category`, returns to Level 0.

### Level 2 — Student Popup (new)
- Full-screen table: same column structure as Level 1 (`sub1 | sub2 | … | [Total]`),
  but renders **only the one selected student's row** (plus the header row).
- Title: `"📋 Raw Details  ›  {category}  ›  {student_name}  ({student_id})  (Enter: edit  Esc: back)"`
- Vertical navigation (j/k/↑/↓) is disabled — single row.
- Enter on col ≥ 2 → triggers `start_editing_cell()` (existing logic; `cursor_row` is the
  student's index in `raw_scores`, so no changes needed in `start_editing_cell()`).
- Esc (when not in edit mode) → clears `raw_selected_student`, returns to Level 1.

### Level 3 — Cell Editor (unchanged)
- Existing tui-textarea overlay on top of whatever is rendered behind it.
- Enter saves, Esc cancels; both return to Level 2.

---

## State fields

### `app.rs` — changes to `App` struct

| Field | Type | Meaning |
|---|---|---|
| `raw_selected_category` | `Option<String>` | Already present. `Some(cat)` = at Level 1 or 2. |
| `raw_selected_student` | `Option<usize>` | **New.** `Some(row_idx)` = at Level 2. |

### Key-handler changes (`App::update()`)

**Enter key** (tab 1, not editing):
- If `raw_selected_student.is_some()` → already at L2: `start_editing_cell()` (col ≥ 2 guard).
- Else if `raw_selected_category.is_some()` → at L1: set `raw_selected_student = Some(cursor_row)`, reset `cursor_col = 2`, `scroll_col_offset = 0`.
- Else → at L0: existing logic (set `raw_selected_category`, reset cursor).

**Esc key** (tab 1, not editing):
- If `raw_selected_student.is_some()` → at L2: clear `raw_selected_student` (return to L1).
- Else if `raw_selected_category.is_some()` → at L1: clear `raw_selected_category` (return to L0).
- Else → at L0: `app.state = CourseSelect` (existing).

**Vertical navigation** (j/k/↑/↓, tab 1):
- If `raw_selected_student.is_some()` → no-op (single row, nowhere to move vertically).

**Horizontal navigation** (`move_right()`/`move_left()`, tab 1):
- At L2: `max_cols = data_mapping[cat].len() + 2` (same as L1 sub-column calculation).

**Reset on tab switch / course reload:**
- Clear both `raw_selected_category` and `raw_selected_student` (already handled for `raw_selected_category`; add `raw_selected_student` to the same reset sites).

---

## UI (`ui.rs`) — changes

### `draw_raw_details_tab()`
```
if raw_selected_student.is_some() → draw_student_popup()
else if raw_selected_category.is_some() → draw_sub_column_view()
else → draw_category_view()
```

### `draw_student_popup()` (new function)
- Shares most code with `draw_sub_column_view()`.
- `let student_row_idx = app.raw_selected_student.unwrap();`
- Renders only `data.raw_scores[student_row_idx]` as the sole data row.
- Header: sub-column names + max_scores (same as L1).
- For attendance: append "Total (pts)" cell (same `show_total` logic).
- Cursor highlight: `cursor_col` only (no row highlight needed — single row).
- Block title: `"📋 Raw Details  ›  {cat}  ›  {name}  ({sid})  (Enter: edit  Esc: back)"`.
- Border color: `category_color(&cat, &theme)`.

### Title strings updated
- Level 0: `" 📋 Raw Details — Category Overview (Enter: drill in) "` ← unchanged
- Level 1: `format!(" 📋 Raw Details  ›  {}  —  sub-columns (Enter: open student  Esc: back) ", cat)`
- Level 2: `format!(" 📋 Raw Details  ›  {}  ›  {}  ({})  (Enter: edit  Esc: back) ", cat, name, sid)`

### `draw_footer()` — legend for tab 1
| State | Legend |
|---|---|
| L0 | `[Enter] Drill Into Category` |
| L1 | `[Enter] Open Student  [Esc] Back to Categories` |
| L2 | `[Enter] Edit Score  [Esc] Back to Sub-columns` |

---

## Out of scope
- Floating/overlay popup (non-full-screen) — user chose full-screen.
- "All categories" view for a single student (full student card).
- Keyboard shortcut to jump from L0 directly to L2.
- Search/filter students by ID or name.

---

## Files changed

| File | Change |
|---|---|
| `rust_tui/src/app.rs` | Add `raw_selected_student: Option<usize>`; update Enter/Esc/move handlers |
| `rust_tui/src/ui.rs` | Add `draw_student_popup()`; update titles in L1; update footer legends |

No changes needed to `bridge.rs`, `types.rs`, `style.rs`, or any Python files.

---

## End-to-end verification

1. Build and run from project root.
2. Select PHYS1120 course.
3. Press **Tab** → Raw Details (L0). Title: "Category Overview".
4. Press **→** three times to highlight the `attendance` column; press **Enter**.
   - Title changes to "Raw Details › attendance — sub-columns".
5. Press **↓** twice to reach student 69143303. Press **Enter**.
   - Title changes to "Raw Details › attendance › นางสาวสุปวีร์ … (69143303)".
   - Table shows one row: P, P, L, …, Total = 2.8.
6. Press **→** to col 2 (8 Jun 2026); press **Enter**.
   - Cell editor opens with current value "P".
7. Clear and type `A`; press **Enter** to save.
   - Student popup refreshes showing `A` in that cell and Total changes to 1.8.
8. Press **Esc** → back to L1 sub-column view (attendance).
9. Press **Esc** → back to L0 category overview.
10. Press **Esc** → back to CourseSelect screen.
