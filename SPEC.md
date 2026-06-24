# Spec: Student Info Panel Below Categories in Tab [2]

## Summary

Add a small info panel in the **left column** of the tab [2] split view,  
directly below the existing Categories list. The panel shows the currently  
highlighted student's details whenever the right table is focused.

---

## Layout change

The left column (currently a single `draw_raw_left_panel` block) becomes  
a **vertical split**:

```
Left column (Constraint::Length(22))
  ├── Categories panel   Constraint::Percentage(60)
  └── Student Info panel Constraint::Percentage(40)
```

The right panel is unchanged.

---

## Student Info panel content

### When right table is NOT focused (`!raw_right_focused`)

Show placeholder text:
```
 ─ no selection ─
 Navigate → to
 select a student
```
Dim style (`theme.border` or `theme.inactive_tab`).

### When right table IS focused (`raw_right_focused`)

Look up `data.raw_scores[cursor_row]` for raw values,  
and `data.student_grades` (scan for matching `Student ID`) for derived values.

Display (one field per line, inside a bordered block):

```
 Name   : <name>
 ID     : <student_id>
 Score  : <Final Score>
 Grade  : <Grade>
 ─────────────────
 <current cell line>
```

**Current cell line** depends on `cursor_col`:

| `cursor_col` | Display |
|---|---|
| 0 (Student ID) | *(omit line)* |
| 1 (Name) | *(omit line)* |
| 2 … sub_cols.len()+1 | `<col_name>: <raw_value>` |
| sub_cols.len()+2 (Total) | `Total: <sum> pts` |

For attendance, `<raw_value>` is the letter (P / L / A / EA) from the JSON string.  
For other categories it is the number as-is.

Grade is colored by the same grade-color logic used in Summary tab.

---

## Files changed

| File | Change |
|---|---|
| `rust_tui/src/ui.rs` | Split left chunk vertically; add `draw_student_info_panel()`; update `draw_raw_details_tab()` |
| `rust_tui/src/app.rs` | No changes |

---

## Out of scope

- Editing from the info panel.
- Showing info panel inside L2 student popup (full-screen, left column not visible).
- Showing category totals or percentages.
- Auto-scrolling the right table to follow the info panel.

---

## End-to-end verification

1. Build: `PATH="$HOME/.cargo/bin:$PATH" cargo build --release --manifest-path rust_tui/Cargo.toml`
2. Run `./grade-tui`, select PHYS1120.
3. Press **Tab** → Raw Details.
   - Left column: Categories on top, info panel below showing placeholder text.
4. Press **→** to focus right table.
   - Info panel fills in with row 0's Name, ID, Score, Grade.
   - Current cell line shows the hw1 value (or first sub-col of whichever category is selected).
5. Press **↓** twice.
   - Info panel updates to show the new student.
6. Press **←** to unfocus right table.
   - Info panel reverts to placeholder.
7. Press **↓** in left panel to switch to `attendance`.
8. Press **→** to focus right table, then **→→** to land on an attendance date column.
   - Current cell line shows e.g. `22 Jun 2026: A` or `P`.
9. Navigate to Total column (rightmost).
   - Current cell line shows `Total: 0.0 pts`.
10. Navigate to Student ID col (col 0).
    - Current cell line is omitted (only Name, ID, Score, Grade shown).
