# Spec: Restore SPEC.md Three-Level Drill-Down on Raw Details Tab

## Problem

A collaborator ("Antigravity") replaced the full-screen three-level drill-down on the
Raw Details tab with a left-panel + right-table layout.  
The student popup (Level 2) exists in `ui.rs` but is currently unreachable because
`raw_selected_student` is never set by the Enter handler.  
This spec restores the original navigation hierarchy from the previous SPEC.md.

---

## Navigation hierarchy (to restore)

```
Level 0 — Category Overview      (full screen)
    │  Enter on col ≥ 2
    ▼
Level 1 — Sub-Column View        (full screen)
    │  Enter on any student row
    ▼
Level 2 — Student Popup          (full screen, single row)
    │  Enter on col ≥ 2
    ▼
Level 3 — Cell Editor            (overlay, already correct)
```

Esc ascends one level.  Esc at Level 0 → CourseSelect.

---

## What to keep (no rollback)

| Item | Why |
|---|---|
| `draw_edit_overlay` redesign (student info + live grade preview) | Useful; keep as-is |
| `show_total = true` in `draw_sub_column_view` | Always show Total column |
| Total max pts in header (`"Total\n({:.0} pts)"`) | Keep |
| Total column cursor-highlight code | Keep |
| `draw_student_popup` function | Already correct; just needs to be reachable |
| Footer legend text (already references L0/L1/L2 correctly) | Keep |

---

## Files changed

| File | Change |
|---|---|
| `rust_tui/src/app.rs` | Remove left-panel state; fix Enter/Esc/move handlers |
| `rust_tui/src/ui.rs` | Remove `draw_raw_left_panel`; add `draw_category_view`; fix `draw_sub_column_view`; fix `draw_raw_details_tab` dispatch |

No changes to `bridge.rs`, `types.rs`, `style.rs`, or Python files.

---

## app.rs changes

### Fields to remove from `App` struct

```rust
// DELETE these two fields:
pub raw_category_index: usize,
pub raw_right_focused: bool,
```

Remove their initializers in `App::new()` and all reset sites (`CourseDataLoaded`,
`Tab`, `BackTab`).

### `sync_raw_category()` — delete entirely

This method was only used to keep `raw_selected_category` in sync with
`raw_category_index`.  After removal, `raw_selected_category` is set exclusively
by the Enter handler at Level 0.

### `move_up` / `move_down`

Remove the branch that checks `!self.raw_right_focused` for left-panel navigation:

```rust
// DELETE these blocks from move_up and move_down:
if self.active_tab == 1 && !self.raw_right_focused {
    // Left panel is focused: navigate categories
    ...
    return;
}
```

The remaining `cursor_row` movement already handles Level 0, 1, and 2 correctly
(Level 2 still has the `raw_selected_student.is_some()` early-return guard).

### `move_left`

Remove the entire `if self.active_tab == 1 { ... return; }` early-return block that
handled left/right panel focus.  Replace with standard col-boundary movement:

```rust
pub fn move_left(&mut self) {
    if self.state == AppState::Dashboard && !self.editing && !self.editing_weights && !self.editing_boundaries {
        if self.cursor_col > 0 {
            self.cursor_col -= 1;
            self.adjust_scroll_col();
        }
    }
}
```

### `move_right`

Replace the tab-1 branch with three-level aware max_cols:

```rust
if self.active_tab == 1 {
    let max_cols = match &self.course_data {
        Some(data) => {
            if self.raw_selected_student.is_some() || self.raw_selected_category.is_some() {
                // Level 1 or 2: Student ID + Name + sub_cols + Total
                let cat = self.raw_selected_category.as_deref().unwrap_or("");
                data.data_mapping.get(cat).map(|v| v.len()).unwrap_or(0) + 3
            } else {
                // Level 0: Student ID + Name + one col per category
                self.get_categories().len() + 2
            }
        }
        None => 0,
    };
    if self.cursor_col + 1 < max_cols {
        self.cursor_col += 1;
        self.adjust_scroll_col();
    }
    return;
}
```

### Enter handler (tab 1)

Replace the current block with:

```rust
if self.active_tab == 1 {
    if self.raw_selected_student.is_some() {
        // Level 2 → edit cell (col ≥ 2 guard is already in start_editing_cell)
        self.start_editing_cell();
    } else if self.raw_selected_category.is_some() {
        // Level 1 → open student popup
        self.raw_selected_student = Some(self.cursor_row);
        self.cursor_col = 2;
        self.scroll_col_offset = 2;
    } else {
        // Level 0 → drill into category (only if on a category column)
        if self.cursor_col >= 2 {
            let cats = self.get_categories();
            let cat_idx = self.cursor_col - 2;
            if cat_idx < cats.len() {
                self.raw_selected_category = Some(cats[cat_idx].clone());
                self.cursor_col = 2;
                self.scroll_col_offset = 2;
            }
        }
    }
}
```

### Esc handler (tab 1)

```rust
if self.active_tab == 1 {
    if self.raw_selected_student.is_some() {
        // Level 2 → back to Level 1
        self.raw_selected_student = None;
        self.cursor_col = 2;
        self.scroll_col_offset = 2;
    } else if self.raw_selected_category.is_some() {
        // Level 1 → back to Level 0
        self.raw_selected_category = None;
        self.cursor_col = 2;
        self.scroll_col_offset = 0;
    } else {
        // Level 0 → CourseSelect
        self.state = AppState::CourseSelect;
        self.course_data = None;
        self.load_courses();
    }
}
```

### Reset sites (Tab / BackTab / CourseDataLoaded)

Remove `raw_category_index = 0`, `raw_right_focused = false`, and
`sync_raw_category()` calls.  Keep `raw_selected_category = None` and
`raw_selected_student = None` resets.

---

## ui.rs changes

### Delete `draw_raw_left_panel`

Remove the entire function (lines ~415–450).

### `draw_raw_details_tab` — full-screen dispatch

```rust
fn draw_raw_details_tab(f: &mut Frame, app: &mut App, area: Rect) {
    if app.raw_selected_student.is_some() {
        draw_student_popup(f, app, area);
    } else if app.raw_selected_category.is_some() {
        draw_sub_column_view(f, app, area);
    } else {
        draw_category_view(f, app, area);
    }
}
```

### `draw_sub_column_view` — remove `raw_right_focused` references

Replace every occurrence of `app.raw_right_focused` in this function:

1. **Border color** → always `category_color(&cat, &theme)` (was conditional)
2. **Title** → `format!(" 📋 Raw Details  ›  {}  —  sub-columns (Enter: open student  Esc: back) ", cat)`
3. **Cursor/row highlights** → remove the `app.raw_right_focused &&` guard; always highlight
   on `r_idx == app.cursor_row` and the matching column

### `draw_category_view` (new — Level 0)

Full-screen table: `Student ID | Name | cat1 | cat2 | …`

- Each category cell = sum of sub-scores via `score_value()`.
- Columns Student ID and Name are pinned (not scrolled); category columns follow the
  same `scroll_col_offset` logic as `draw_sub_column_view`.
- Cursor highlight on (cursor_row, cursor_col); row highlight on cursor_row.
- Alternating row bg on even/odd rows.
- Block title: `" 📋 Raw Details — Category Overview (Enter: drill in) "` in `theme.info` color.
- Border color: `theme.info` always.
- Column widths: Student ID 12, Name 28, each category 12.

Skeleton:

```rust
fn draw_category_view(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data { Some(d) => d, None => return };
    let cats = app.get_categories();

    let frozen_count = 2usize;
    let scroll_offset = app.scroll_col_offset.saturating_sub(frozen_count);
    let max_scroll_cats = 5usize;
    let scroll_end = std::cmp::min(scroll_offset + max_scroll_cats, cats.len());
    let visible_cats = &cats[scroll_offset..scroll_end];

    // header: Student ID | Name | visible category names
    // rows: one per raw_scores entry, category cell = sum via score_value()
    // widths: [12, 28, 12 × visible_cats.len()]
    // highlight: same cursor_row / cursor_col logic as draw_sub_column_view
}
```

---

## Out of scope

- Left-panel layout (removed, not restored).
- "All categories" card for a single student.
- Jump shortcut from L0 to L2.

---

## End-to-end verification

1. `cd rust_tui && cargo build --release && cd ..`
2. Run `./rust_tui/target/release/rust_tui`, select PHYS1120 course.
3. Press **Tab** to reach Raw Details tab.
   - Screen shows full-width table: Student ID | Name | homework | midterm | final | attendance.
   - Title: "Category Overview (Enter: drill in)".
4. Press **→** to highlight `attendance` column (col 4 or wherever it falls); press **Enter**.
   - Title changes to "📋 Raw Details  ›  attendance — sub-columns (Enter: open student  Esc: back)".
5. Press **↓** twice; press **Enter**.
   - Title changes to "📋 Raw Details  ›  attendance  ›  {name}  ({sid})  (Enter: edit  Esc: back)".
   - Table shows ONE student row only.
6. Press **→** to col 2; press **Enter**.
   - Cell editor opens over the student popup.
7. Type a new value; press **Enter** to save.
8. Press **Esc** → back to Level 1 (sub-column view).
9. Press **Esc** → back to Level 0 (category overview).
10. Press **Esc** → back to CourseSelect screen.
