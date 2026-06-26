# Spec: Attendance Refinements in Tab [2]

---

## 1 — Fix Thai name cutoff in sub-column view

### Root cause
`format_thai_name` calculates padding width using `UnicodeWidthStr::width`, which
returns 0 for Thai combining vowels (ั, ์, ี, etc.).  The actual terminal renders
each codepoint as one column, so the padding is always too short, and the surname
bleeds past the allocated column width.

### Fix
Change the padding calculation in `format_thai_name` (bottom of `rust_tui/src/ui.rs`)
from:
```rust
let first_width = UnicodeWidthStr::width(first_name);
```
to:
```rust
let first_width = first_name.chars().count();
```
This matches how `draw_summary_tab` already computes name column widths.

Also increase the Name column width in `draw_sub_column_view` and
`draw_student_popup` from `Constraint::Length(28)` to `Constraint::Length(32)`.

---

## 2 — Abbreviate attendance date headers to a1…aN

### Where
`draw_sub_column_view` in `rust_tui/src/ui.rs`, in the header-cell loop.

### Logic
When the current category is attendance (check
`cat.to_lowercase().contains("attendance")`), replace the visible column name with
`format!("a{}", scroll_offset + sc_index + 1)`.  The max-score suffix (`(1 pts)` or
absent) is omitted for attendance headers.

The **Student panel** continues to read `sub_cols[sub_idx]` — the raw column name
(the full date string) — so it still shows e.g. `22 Jun 2026 : P`.

### Out of scope
- Renaming headers for non-attendance categories.
- Changing the underlying data or column names.

---

## 3 — Attendance value picker (modal overlay)

### When triggered
`start_editing_cell` detects attendance cells:
```
active_tab == 1
AND raw_selected_category == "attendance" (case-insensitive)
AND cursor_col maps to a valid attendance sub-column
```
Instead of opening a `tui-textarea`, set `self.editing_attendance = true` and
pre-select the current cell value in `self.attendance_index`.

### Options and order
```
Index 0 : P    (Present)
Index 1 : A    (Absent)
Index 2 : L    (Late)
Index 3 : EA   (Excused Absence)
```
Pre-selection: find the current raw value in this list; default to 0 if not found.

### New App fields (`rust_tui/src/app.rs`)
```rust
pub editing_attendance: bool,
pub attendance_index: usize,
```
Initialise to `false` / `0` in `App::new()`.

### New save function (`app.rs`)
```rust
fn save_attendance_score(&mut self) {
    let options = ["P", "A", "L", "EA"];
    let val = options[self.attendance_index].to_string();
    // same bridge call as save_edited_score but val is fixed
}
```

### Key handling (`app.rs :: update`)
Add a new early-return branch (after `self.editing`, before `editing_weights`):
```rust
if self.editing_attendance {
    match key.code {
        Esc   => { self.editing_attendance = false; }
        Enter => { self.save_attendance_score(); self.editing_attendance = false; }
        Up | Char('k') => { self.attendance_index = self.attendance_index.saturating_sub(1); }
        Down | Char('j') => { if self.attendance_index < 3 { self.attendance_index += 1; } }
        _ => {}
    }
    return;
}
```

### Overlay render (`rust_tui/src/ui.rs`)
Add `draw_attendance_picker(f, app)` — a centred overlay (e.g. 30 × 50 %)
that lists the four options as `List` rows.  Highlighted row = `attendance_index`
(same highlight style as `draw_course_select`).  Title:
`" Select Attendance — <col_name> for <student_name> "`.

Dispatch in `draw()`: add `else if app.editing_attendance { draw_attendance_picker(f, app); }`.

Footer legend: add a branch for `editing_attendance`:
`[▲/▼] Navigate   [Enter] Confirm   [Esc] Cancel`.

---

## 4 — Fix premature column scroll in attendance sub-column view

### Symptom
In tab [2] Raw Details, when the Attendance category is selected and the cursor moves
right past column a6, the panel scrolls left — a1 disappears off-screen — even though
all attendance columns fit comfortably in the available width.

### Root cause
`adjust_scroll_col` in `rust_tui/src/app.rs` (line 587) hardcodes:
```rust
let visible_scrollable_cols = 5;
```
This was sized for regular columns (12 px wide + 1 spacing = 13 px each).  Attendance
columns are only 4 px wide (5 px with spacing), so a typical 160-wide terminal can
show ~14 attendance columns simultaneously — yet the scroll kicks in at cursor_col 7
(i.e. a6).

### Fix — `rust_tui/src/app.rs` only

Replace the hardcoded `5` in `adjust_scroll_col` with a dynamic computation:

```rust
fn adjust_scroll_col(&mut self) {
    if self.active_tab == 1 {
        if self.cursor_col < 2 {
            self.scroll_col_offset = 2;
            return;
        }
        let is_attendance = self.raw_selected_category.as_deref()
            .map(|c| c.to_lowercase().contains("attendance") || c.to_lowercase().contains("att"))
            .unwrap_or(false);
        // student popup = full-width; category view = terminal minus left panel (33) + 2 borders
        let right_inner = if self.raw_selected_student.is_some() {
            (self.width as usize).saturating_sub(2)
        } else {
            (self.width as usize).saturating_sub(35)
        };
        // Frozen columns: StudentID (12) + Name (≈32) + 3 spacing chars = 47
        let frozen_width = 47usize;
        let scrollable_width = right_inner.saturating_sub(frozen_width);
        // column width + column_spacing(1)
        let col_width: usize = if is_attendance { 5 } else { 13 };
        let visible_scrollable_cols = (scrollable_width / col_width).max(1);

        if self.cursor_col < self.scroll_col_offset {
            self.scroll_col_offset = self.cursor_col;
        } else if self.cursor_col >= self.scroll_col_offset + visible_scrollable_cols {
            self.scroll_col_offset = self.cursor_col - visible_scrollable_cols + 1;
        }
        return;
    }
    // non-tab-1 path unchanged
    let visible_cols = 6;
    if self.cursor_col < self.scroll_col_offset {
        self.scroll_col_offset = self.cursor_col;
    } else if self.cursor_col >= self.scroll_col_offset + visible_cols {
        self.scroll_col_offset = self.cursor_col - visible_cols + 1;
    }
}
```

The name-col approximation (32) does not need to be pixel-perfect; being slightly
conservative means scroll triggers a column or two earlier than optimal, which is
acceptable.

### Out of scope
- Dynamically measuring the actual name column width from course data.
- Changing any rendering logic in `ui.rs`.
- Fixing scroll for non-attendance regular columns (the current `5` heuristic is close
  enough for 12 px columns at typical terminal widths).

---

## 5 — Compact numeric headers, value-colored cells, reordered picker

### 5a — Header format: `|1|2|...|22|` (no 'a' prefix)

**Where:** `draw_sub_column_view` and `draw_student_popup` in `rust_tui/src/ui.rs`.

**Column width** — change from fixed `4` to dynamic, equal for all attendance columns:
```rust
let sub_col_width: u16 = (1 + format!("{}", sub_cols.len()).len()) as u16;
// e.g. 1–9 sessions → 2, 10–99 sessions → 3
```

**Header cell text** — change from `format!("a{}\n", ...)` to:
```rust
format!("|{}\n", scroll_offset + sc_index + 1)
```
The `|` prefix, with `column_spacing(0)` (see below), makes adjacent cells render as
`|1|2|3|...|22|` naturally.

**Column spacing** — change the Table builder for attendance to `column_spacing(0)`:
```rust
let table = Table::new(rows, widths)
    .header(header)
    .block(block)
    .column_spacing(if is_attendance { 0 } else { 1 });
```

Same changes apply verbatim to `draw_student_popup`.

---

### 5b — Value cell background colors

**New private helper** in `ui.rs`:
```rust
fn att_cell_style(val: &str, is_cursor: bool, theme: &crate::style::Theme) -> Style {
    if is_cursor {
        return Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
    }
    match val.trim() {
        "P"  => Style::default().fg(theme.bg).bg(theme.success).add_modifier(Modifier::BOLD),
        "A"  => Style::default().fg(theme.bg).bg(theme.grade_f).add_modifier(Modifier::BOLD),
        "EA" => Style::default().fg(theme.bg).bg(theme.key_accent).add_modifier(Modifier::BOLD),
        "L"  => Style::default().fg(theme.bg).bg(theme.warning).add_modifier(Modifier::BOLD),
        _    => Style::default().fg(theme.fg),
    }
}
```

Colors map to existing Monokai Pro theme tokens (so they respect user theme overrides):
| Value | Color | Theme field |
|---|---|---|
| P  | Green  | `theme.success` |
| A  | Red    | `theme.grade_f` |
| EA | Yellow | `theme.key_accent` |
| L  | Orange | `theme.warning` |
| (empty / numeric) | Default fg | — |

**Usage** — in the per-cell loop inside `draw_sub_column_view` and `draw_student_popup`,
replace the existing inline style logic with:
```rust
let is_cursor = app.raw_right_focused && r_idx == app.cursor_row && abs_col == app.cursor_col;
let style = if is_attendance {
    att_cell_style(&text, is_cursor, &theme)
} else {
    if is_cursor {
        Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(theme.fg)
    }
};
```

Row highlight (grey) stays on the Row; per-cell colored bg overrides it for attendance
cells (ratatui cell style wins over row style), which is the desired behaviour.

---

### 5c — Attendance picker: new order + per-option colors

**Order change** (in `draw_attendance_picker`, `save_attendance_score`, and the
pre-selection index lookup in the key handler — all three use the same options array):
```
Old: ["P", "A", "L", "EA"]
New: ["P", "L", "EA", "A"]
```

**Per-option colors** in `draw_attendance_picker` (using a `(code, label)` tuple):
```rust
let options = [("P","Present"),("L","Late"),("EA","Excused Absence"),("A","Absent")];
let items: Vec<ListItem> = options.iter().enumerate().map(|(i, &(code, label))| {
    let bullet = if i == app.attendance_index { "●" } else { "○" };
    let text = format!("  {} {:<2}  {}  ", bullet, code, label);
    let base_style = match code {
        "P"  => Style::default().fg(theme.bg).bg(theme.success),
        "L"  => Style::default().fg(theme.bg).bg(theme.warning),
        "EA" => Style::default().fg(theme.bg).bg(theme.key_accent),
        "A"  => Style::default().fg(theme.bg).bg(theme.grade_f),
        _    => Style::default().fg(theme.fg),
    };
    let style = if i == app.attendance_index {
        base_style.add_modifier(Modifier::BOLD | Modifier::UNDERLINED)
    } else {
        base_style
    };
    ListItem::new(text).style(style)
}).collect();
```

---

### 5d — Scroll threshold update (fold-in from spec §4)

In `adjust_scroll_col` (`app.rs`), the attendance `col_width` must match the new
rendered column width (spacing=0, dynamic width):
```rust
// Before:
let col_width: usize = if is_attendance { 5 } else { 13 };

// After:
let col_width: usize = if is_attendance {
    1 + format!("{}", sub_col_count).len() // e.g. 3 for 10–22 cols
} else {
    13
};
```

---

### Out of scope
- Non-attendance categories (homework, midterm, final) — no rendering changes.
- The student info panel in the left column — it already shows the raw date string
  (e.g. `22 Jun 2026 : P`), not `aN`, so no change needed.
- Adding new attendance values beyond P / L / EA / A.

---

## Files changed

| File | Change |
|---|---|
| `rust_tui/src/app.rs` | New fields `editing_attendance`, `attendance_index`; `save_attendance_score`; key handler branch; dynamic `visible_scrollable_cols` in `adjust_scroll_col`; options order → [P,L,EA,A]; scroll col_width update |
| `rust_tui/src/ui.rs` | Fix `format_thai_name`; widen Name col; abbreviate attendance headers; `draw_attendance_picker`; footer branch; dynamic sub_col_width; `|N` header format; `att_cell_style` helper; column_spacing=0 for attendance; picker colors |

---

## End-to-end verification

1. Build & copy binary.
2. Run `./grade-tui`, select PHYS1120, Tab to Raw Details.
3. **Name fix**: check that full surnames appear without cutoff in the right table.
4. **Header abbreviation**: attendance columns show `a1 a2 a3 …`.  Student panel
   (when right table focused + cursor on an attendance col) shows the full date
   like `22 Jun 2026 : ` not `a1 : `.
5. **Picker**: focus right table, move to an attendance sub-column, press Enter
   on a student row to open L2 popup, then Enter on an attendance cell.
   - Picker overlay appears with four rows `[P, A, L, EA]`, current value highlighted.
   - ↑/↓ changes selection; Enter saves and reloads; Esc dismisses without saving.
   - For a non-attendance cell (homework), the existing text editor still appears.
6. **Scroll fix**: focus the right table on Attendance, press → repeatedly through
   a1 → a8 → a15.
   - At a typical wide terminal (≥140 cols) the panel must **not** scroll at all until
     the cursor approaches columns that genuinely overflow the right edge.
   - At a narrow terminal (~100 cols) scroll should kick in only near the right edge,
     not at a6.
7. **Compact headers**: attendance column headers show `|1|2|3|...|22|` (no 'a' prefix).
   All header cells and value cells have the same horizontal width.
8. **Value colors**: P cells have green bg, A cells red, EA yellow, L orange. The color
   persists on non-cursor cells even when their row is highlighted (grey bg on row;
   per-cell color wins). The cursor cell overrides to blue/active_tab.
9. **Picker order + colors**: pressing Enter on an attendance cell opens the picker with
   options in order P / L / EA / A, each with its associated background color. The
   selected option shows bold + underline. Saving P after L produces the correct score
   (P=1.0, not L=0.8).
11. **No error on attendance save**: saving an attendance value reloads data cleanly with
    no error overlay.
10. **Direct picker from L1**: in the attendance right panel (L1), pressing Enter on a
    data cell (`|1|`…`|22|`) opens the picker immediately — no intermediate L2 popup.
    - Pressing Enter on Student ID, Name, or Total in L1 still opens L2 (unchanged).
    - Non-attendance categories (homework, etc.) still use Enter → L2 (unchanged).
    - Esc from the picker returns to L1 cleanly.

---

## 6 — Skip L2 for attendance data cells (direct picker from L1)

### Current flow
Left panel → Enter → L1 right panel → cursor on a row → Enter → L2 student popup →
cursor on attendance cell → Enter → picker overlay.

### New flow
Left panel → Enter → L1 right panel → cursor on attendance data cell → Enter →
picker overlay directly.

Frozen/Total columns (Student ID, Name, Total) in L1 keep the old Enter → L2 behavior.
Non-attendance categories keep the old Enter → L2 behavior.

### Changes

#### `rust_tui/src/app.rs` — Enter key handler

In the `KeyCode::Enter` branch, the L1 case currently unconditionally opens L2:
```rust
} else if self.raw_right_focused {
    self.raw_selected_student = Some(self.cursor_row);
    self.cursor_col = 2;
    self.scroll_col_offset = 2;
}
```

Replace with:
```rust
} else if self.raw_right_focused {
    let is_att = self.raw_selected_category.as_deref()
        .map(|c| c.to_lowercase().contains("attendance") || c.to_lowercase().contains("att"))
        .unwrap_or(false);
    let sub_col_count = self.raw_selected_category.as_ref()
        .and_then(|cat| self.course_data.as_ref().and_then(|d| d.data_mapping.get(cat)))
        .map(|v| v.len())
        .unwrap_or(0);
    // Data cells: col 2 … (sub_col_count + 1); frozen/total: 0, 1, sub_col_count+2
    let on_data_cell = self.cursor_col >= 2 && self.cursor_col < sub_col_count + 2;

    if is_att && on_data_cell {
        self.start_editing_cell();   // opens picker directly
    } else {
        self.raw_selected_student = Some(self.cursor_row);
        self.cursor_col = 2;
        self.scroll_col_offset = 2;
    }
}
```

#### `rust_tui/src/ui.rs` — `draw_attendance_picker`

The picker title currently fetches the student name via `app.raw_selected_student`, which
is `None` when the picker is opened from L1. Change the lookup to use `app.cursor_row`:

```rust
// Before:
let student_name = {
    app.course_data.as_ref()
        .and_then(|d| {
            let idx = app.raw_selected_student?;
            let row = d.raw_scores.get(idx)?;
            row.get("Name").and_then(|v| v.as_str()).map(|s| s.to_string())
        })
        .unwrap_or_default()
};

// After:
let student_name = app.course_data.as_ref()
    .and_then(|d| d.raw_scores.get(app.cursor_row))
    .and_then(|r| r.get("Name").and_then(|v| v.as_str()).map(|s| s.to_string()))
    .unwrap_or_default();
```

`cursor_row` equals the student index in both L1 and L2 contexts, so this is safe.

### Out of scope
- Removing L2 entirely — it is still reachable for non-attendance categories and for
  frozen/Total columns in attendance.
- Changing Esc behaviour — existing Esc chain is unchanged (picker Esc → L1, L1 Esc →
  left panel, left panel Esc → course select).

### Files changed
| File | Change |
|---|---|
| `rust_tui/src/app.rs` | Enter handler L1 branch: detect att + data cell → `start_editing_cell()` |
| `rust_tui/src/ui.rs` | `draw_attendance_picker`: student name from `cursor_row` not `raw_selected_student` |

---

## 8 — Direct edit popup from L1 for all categories (homework, project, midterm, final)

### Problem
In tab [2] Raw Details, pressing Enter on a data cell for any non-attendance category
(homework, project, midterm, final) navigates to the L2 student popup instead of
opening the edit dialog directly. Attendance was already fixed (§6); this extends that
fix to all remaining categories.

### Desired flow (all categories)
```
L1 right panel, cursor on data cell (col 2…sub_col_count+1)  →  Enter  →  edit popup
L1 right panel, cursor on Student ID / Name / Total           →  Enter  →  nothing
```

L2 (student popup) remains as dead code but is not deleted — it is simply never
entered during normal navigation after this change.

### Change — `rust_tui/src/app.rs` only

In the `KeyCode::Enter` handler, the `raw_right_focused` branch currently is:

```rust
} else if self.raw_right_focused {
    let is_att = self.raw_selected_category.as_deref()
        .map(|c| c.to_lowercase().contains("attendance") || c.to_lowercase().contains("att"))
        .unwrap_or(false);
    let sub_col_count = self.raw_selected_category.as_ref()
        .and_then(|cat| self.course_data.as_ref().and_then(|d| d.data_mapping.get(cat)))
        .map(|v| v.len())
        .unwrap_or(0);
    let on_data_cell = self.cursor_col >= 2 && self.cursor_col < sub_col_count + 2;
    if is_att && on_data_cell {
        self.start_editing_cell();
    } else {
        self.raw_selected_student = Some(self.cursor_row);
        self.cursor_col = 2;
        self.scroll_col_offset = 2;
    }
}
```

Replace with (remove `is_att &&`, drop the L2-navigation else branch):

```rust
} else if self.raw_right_focused {
    let sub_col_count = self.raw_selected_category.as_ref()
        .and_then(|cat| self.course_data.as_ref().and_then(|d| d.data_mapping.get(cat)))
        .map(|v| v.len())
        .unwrap_or(0);
    let on_data_cell = self.cursor_col >= 2 && self.cursor_col < sub_col_count + 2;
    if on_data_cell {
        self.start_editing_cell();
    }
    // ID / Name / Total: no-op
}
```

`start_editing_cell()` already branches internally on whether the category is attendance
(opens picker) or not (opens text editor), so no changes to that function are needed.

### Out of scope
- Removing the L2 student popup rendering code (`draw_student_popup`, `raw_selected_student`).
- Changing `start_editing_cell()`.
- Changing Esc / Left-arrow behaviour.
- Any change to `ui.rs`.

### Files changed
| File | Change |
|---|---|
| `rust_tui/src/app.rs` | Enter handler: remove `is_att &&` guard; remove L2-navigation else branch |

### End-to-end verification
1. Build the binary (`cargo build --release` inside `rust_tui/`).
2. Run from project root, load a course, switch to tab [2] Raw Details.
3. Navigate to **homework** category (left panel), press → to focus the right table.
4. Move cursor to a data cell (col 3+), press Enter.
   - The **edit text overlay** must appear immediately — no intermediate L2 popup.
   - Esc closes the overlay and returns to L1.
5. Repeat for **project**, **midterm**, and **final** categories — same behaviour.
6. Move cursor to col 0 (Student ID) or col 1 (Name), press Enter — nothing happens.
7. Move cursor to the Total column (last col), press Enter — nothing happens.
8. **Attendance regression check**: navigate to Attendance, press Enter on a data cell —
   the attendance picker must still appear directly (no L2 popup, unchanged from §6).

---

## 7 — Fix stdout pollution from diagnostic prints in data_loader.py

### Root cause

`src/data_loader.py` contains five `print()` calls for diagnostic status messages
(sync confirmations and warnings). The Rust bridge (`bridge.rs`) captures **all of
stdout** from each Python subprocess and feeds it directly into `serde_json::from_str`.
Any non-JSON text prepended to the JSON response causes a parse failure at byte 0.

**Exact failure chain:**
1. User saves an attendance value → bridge calls `update-score` → Python saves CSV then
   XLSX (xlsx mtime now > csv mtime).
2. Rust calls `load_course_data()` → bridge calls `get-course-data` → Python runs
   `check_and_sync_attendance()` → xlsx is newer → `sync_attendance_xlsx_to_csv()`
   → **`print("✅ Synced attendance database CSV at: ...")`** writes to stdout.
3. Main runner then writes `print(json.dumps(...))` to stdout.
4. Bridge reads combined stdout `"✅ Synced ...\n{...JSON...}"` and fails:
   `JSON parse error: expected value at line 1 column 1`.

### Fix — `src/data_loader.py` only

Change all five diagnostic `print()` calls to write to `sys.stderr` instead of
stdout. `sys` is already imported (line 1 of the file, or add if missing).

```python
# Before
print(f"✅ Synced attendance database CSV at: {csv_path.name}")
print(f"⚠️ Error syncing attendance XLSX to CSV: {e}")
print(f"⚠️ Warning: Could not auto-detect attendance headers: {e}")
print(f"⚠️ Error reading student info file {file.name}: {e}")
print(f"⚠️ Error reading data file {file.name}: {e}")

# After (add file=sys.stderr to each)
print(f"✅ Synced attendance database CSV at: {csv_path.name}", file=sys.stderr)
print(f"⚠️ Error syncing attendance XLSX to CSV: {e}", file=sys.stderr)
print(f"⚠️ Warning: Could not auto-detect attendance headers: {e}", file=sys.stderr)
print(f"⚠️ Error reading student info file {file.name}: {e}", file=sys.stderr)
print(f"⚠️ Error reading data file {file.name}: {e}", file=sys.stderr)
```

The bridge already captures stderr separately (`Stdio::piped()` on both channels) and
only shows it on subprocess failure — no Rust changes needed.

### Out of scope
- The intentional `print(json.dumps(...))` calls in `tui_api.py` — those stay on
  stdout; they ARE the JSON response.
- Any prints in `src/dashboard.py` — none reach stdout during bridge calls.

### End-to-end verification
1. Navigate to Attendance in tab [2], press Enter on a cell, pick a new value, press
   Enter to save.
2. The loading spinner appears briefly, then data reloads.
3. **No error overlay appears.**
4. The cell in the table reflects the new value immediately after reload.

---

## 9 — Preserve navigation state across score-save reloads

### Problem

After saving a score (any category), the app calls `load_course_data()` which fires
`CourseDataLoaded`. That handler unconditionally resets all navigation state:
`raw_category_index = 0`, `raw_right_focused = false`, `cursor_row/col = 0`, scroll
offsets = 0. The user is sent back to the left panel on the first category (homework).

### Desired behaviour

After a successful score save (or config save), the view feels like an in-place refresh:
- Same category selected in the left panel
- Same row highlighted in the right table
- Same column cursor, same scroll position
- Right panel still focused (if it was focused before the save)

An initial course load (coming from CourseSelect) continues to reset everything.

### Implementation — `rust_tui/src/app.rs` only

#### 1. New field on `App`

```rust
pub preserve_nav_on_reload: bool,
```

Initialise to `false` in `App::new()`.

#### 2. Set the flag before reloads triggered by edits

In `ScoreUpdated` and `ConfigUpdated` handlers, set the flag before calling
`load_course_data()`:

```rust
// ScoreUpdated Ok branch
self.info_msg = Some("Score successfully saved and database updated!".to_string());
self.info_msg_ticks = 0;
self.preserve_nav_on_reload = true;   // ← add this
self.load_course_data();

// ConfigUpdated Ok branch
self.info_msg = Some("Configuration successfully updated!".to_string());
self.info_msg_ticks = 0;
self.preserve_nav_on_reload = true;   // ← add this
self.load_course_data();
```

#### 3. Conditional reset in `CourseDataLoaded`

```rust
AppEvent::CourseDataLoaded(res) => {
    self.loading = false;
    match res {
        Ok(data) => {
            self.course_data = Some(data);
            self.state = AppState::Dashboard;
            if self.preserve_nav_on_reload {
                self.preserve_nav_on_reload = false;
                // Clamp cursor_row in case student count changed
                let max_rows = self.course_data.as_ref()
                    .map(|d| d.raw_scores.len())
                    .unwrap_or(0);
                if self.cursor_row >= max_rows && max_rows > 0 {
                    self.cursor_row = max_rows - 1;
                }
                // Re-sync category name from preserved index
                self.sync_raw_category();
            } else {
                // Initial load — full reset
                self.cursor_row = 0;
                self.cursor_col = 0;
                self.scroll_row_offset = 0;
                self.scroll_col_offset = 0;
                self.raw_selected_category = None;
                self.raw_selected_student = None;
                self.raw_category_index = 0;
                self.raw_right_focused = false;
                self.sync_raw_category();
            }
        }
        Err(e) => {
            self.error = Some(e);
        }
    }
}
```

`sync_raw_category()` already clamps `raw_category_index` if the category list shrank,
so no extra clamping is needed there.

### Out of scope
- Preserving state across tab switches (Tab key still resets, as intended).
- Preserving `raw_selected_student` — L2 popup is no longer reachable so this is always None.
- Any changes to `ui.rs`.

### Files changed
| File | Change |
|---|---|
| `rust_tui/src/app.rs` | New field `preserve_nav_on_reload`; set it in `ScoreUpdated` and `ConfigUpdated`; conditional branch in `CourseDataLoaded` |

### End-to-end verification
1. Load a course, switch to tab [2] Raw Details.
2. Navigate to **project** (or any non-first category), move to row 3, column 4.
3. Press Enter on a score cell, change the value, press Enter to save.
4. Loading spinner appears and disappears.
5. **After reload:** left panel still shows **project**, right panel is still focused,
   cursor is still on row 3 / column 4, scroll position unchanged.
6. The edited cell displays the new value.
7. **Initial load regression:** press Esc back to course select, reload the course.
   The view resets to the left panel on the first category (homework) — no state carryover.

---

## 10 — Fix student row cut-off in Tab [1] and Tab [2] when student count exceeds window height

### Root cause

Both `draw_summary_tab` (Tab [1]) and `draw_sub_column_view` (Tab [2] right panel) use
`f.render_widget(table, area)`. Ratatui's non-stateful `Table` render simply clips rows
that don't fit in the area — students beyond the visible height are silently dropped.

`App` already tracks `cursor_row` and `scroll_row_offset`, and `adjust_scroll_row()`
keeps them in sync, but the offset is never passed to the renderer. Additionally,
`adjust_scroll_row()` hard-codes `visible_rows = 15` instead of using the actual
rendered area height, so scrolling triggers at the wrong point on short or tall terminals.

### Desired behaviour

- Up/Down (or j/k) in Tab [1] and Tab [2] scrolls the table so the student list is always
  fully reachable regardless of class size or terminal height.
- Tab [1] has no visible row-cursor highlight (it is a read-only summary view); scrolling
  moves the viewport without highlighting a row.
- Tab [2] right panel keeps its existing cursor highlight on `cursor_row`.
- Scroll tracks the real terminal height — no magic numbers.

### Changes

#### `rust_tui/src/app.rs`

**New field on `App`:**
```rust
pub table_visible_rows: usize,
```
Initialise to `15` in `App::new()` (safe fallback before the first render).

**`adjust_scroll_row()` — replace hard-coded constant:**
```rust
fn adjust_scroll_row(&mut self) {
    let visible_rows = self.table_visible_rows.max(1);
    if self.cursor_row < self.scroll_row_offset {
        self.scroll_row_offset = self.cursor_row;
    } else if self.cursor_row >= self.scroll_row_offset + visible_rows {
        self.scroll_row_offset = self.cursor_row - visible_rows + 1;
    }
}
```

#### `rust_tui/src/ui.rs`

**New import** — add `TableState` to the existing ratatui `widgets` import line:
```rust
widgets::{Block, BorderType, Borders, Cell, Clear, List, ListItem, Paragraph, Row, Table, TableState, Wrap},
```

**`draw_summary_tab`:**

1. Before building rows, store the visible row count in app state:
   ```rust
   // area.height - 2 borders - 3 header (height=2 + bottom_margin=1)
   app.table_visible_rows = (area.height as usize).saturating_sub(5).max(1);
   ```

2. In the row-building loop, remove the cursor-row highlight (Tab [1] is read-only).
   Change:
   ```rust
   if r_idx == app.cursor_row {
       row_style = row_style.bg(theme.highlight);
   } else if r_idx % 2 == 1 {
       row_style = row_style.bg(theme.alt_row);
   }
   ```
   To:
   ```rust
   if r_idx % 2 == 1 {
       row_style = row_style.bg(theme.alt_row);
   }
   ```

3. Replace the final render call:
   ```rust
   // Before:
   f.render_widget(table, area);

   // After:
   let mut table_state = TableState::default().with_offset(app.scroll_row_offset);
   f.render_stateful_widget(table, area, &mut table_state);
   ```

**`draw_sub_column_view`:**

1. Before building rows, store the visible row count:
   ```rust
   app.table_visible_rows = (area.height as usize).saturating_sub(5).max(1);
   ```
   Place this after the `cat` and `sub_cols` bindings, before any row construction.

2. Replace the final render call:
   ```rust
   // Before:
   f.render_widget(table, area);

   // After:
   let mut table_state = TableState::default().with_offset(app.scroll_row_offset);
   f.render_stateful_widget(table, area, &mut table_state);
   ```
   The existing per-row cursor highlight (`row_style.bg(theme.highlight)`) is unchanged
   — it continues to work because all rows are still in the `rows` Vec; ratatui only
   adjusts which slice is rendered from the given offset.

### Out of scope

- Tab [3] (Distribution) and Tab [4] (Roundup) — neither displays a per-student scrollable
  list, so no changes needed.
- The left category panel in Tab [2] — the category count is small enough that overflow is
  not a practical issue.
- Horizontal (column) scrolling — that is handled separately by `scroll_col_offset` and is
  already working.
- The `draw_student_popup` (L2) — that view is no longer reachable via normal navigation
  (per §8), but if triggered, it renders a single student row so no scrolling is needed.

### Files changed

| File | Change |
|---|---|
| `rust_tui/src/app.rs` | New field `table_visible_rows`; `adjust_scroll_row` uses it instead of hard-coded `15` |
| `rust_tui/src/ui.rs` | Add `TableState` import; `draw_summary_tab`: set visible rows, remove cursor highlight, use `render_stateful_widget`; `draw_sub_column_view`: set visible rows, use `render_stateful_widget` |

### End-to-end verification

1. Build: `cargo build --release` inside `rust_tui/`.
2. Run from project root with a course that has ≥20 students.
3. **Tab [1] — Summary:**
   - Press Down (or j) repeatedly.
   - Students below the initial visible area scroll into view; no rows are clipped.
   - No row is highlighted as the cursor moves (read-only view).
   - Press Up (or k) to scroll back — the first student returns to the top.
4. **Tab [2] — Raw Details:**
   - Enter the right panel for any category, press Down repeatedly.
   - The cursor row stays highlighted and visible; students below the fold scroll in.
   - The cursor never disappears off the bottom of the table.
5. **Terminal resize:** shrink the terminal to ~20 rows, then scroll through students in
   both tabs — viewport adjusts to the real height (no off-by-15 artifacts).
6. **Regression — Tab [2] edit:** edit a score cell; after reload, cursor position is
   preserved (§9 behaviour unchanged).

---

## 11 — Replace stale `grade-tui` binary copy with a symlink

### Root cause

`grade-tui` is a binary copy of a previous release build (Jun 25 01:11). Every
`cargo build --release` writes to `rust_tui/target/release/rust_tui` but does NOT
update `grade-tui`, so the shortcut silently runs an outdated binary.

This is the reason the §10 scroll fix appeared to have no effect: the user ran
`./grade-tui`, which still contains the pre-fix code. The new binary was never
executed.

### Fix

Replace the binary copy with a symlink that always resolves to the latest release
build:

```bash
rm grade-tui
ln -s rust_tui/target/release/rust_tui grade-tui
```

After this, `cargo build --release` inside `rust_tui/` is the only step required to
deploy any future change.

### Files changed

| Path | Change |
|---|---|
| `grade-tui` | Replaced binary copy with relative symlink → `rust_tui/target/release/rust_tui` |

### Out of scope

- The `rust_tui/Cargo.toml` build configuration — no changes needed.
- Any changes to `app.rs` or `ui.rs` — §10 already contains the scroll fix; this
  spec only ensures the fix is deployed via the shortcut binary.
- The CLAUDE.md instruction "run from project root" — a symlink does not affect CWD.

### End-to-end verification

1. Run `rm grade-tui && ln -s rust_tui/target/release/rust_tui grade-tui` from the
   project root.
2. Confirm: `ls -la grade-tui` shows `grade-tui -> rust_tui/target/release/rust_tui`.
3. Run `./grade-tui` from project root, load a course with ≥20 students.
4. **Tab [1] — Summary:** press Down/j repeatedly past the initial viewport. Students
   that were previously cut off scroll into view; the top rows scroll off. No row is
   permanently frozen or missing.
5. **Tab [2] — Raw Details:** select a category, focus the right panel (→). Press Down
   past the last visible row. The cursor row stays visible at the bottom of the
   viewport; overflow student rows scroll into view. The 'Student' info panel updates
   correctly throughout.
6. Press Up/k — the list scrolls back toward the top without gaps or jumps.
7. **No regression:** tab-switch resets the position to row 0 (correct); editing a
   cell still preserves position after reload (§9 behaviour).

---

## 12 — Restore cursor row highlight in Tab [1] Summary

### Context

§10 removed the cursor row highlight from Tab [1] under the assumption that the
tab was "read-only with no row selection." In practice this made Tab [1] feel broken:
pressing Up/Down had no visual feedback. The user wants the same highlight behaviour
as Tab [2].

### Root cause / what to change

In `draw_summary_tab` (`rust_tui/src/ui.rs`), the per-row style block currently is:

```rust
let mut row_style = Style::default();
if r_idx % 2 == 1 {
    row_style = row_style.bg(theme.alt_row);
}
```

The `if r_idx == app.cursor_row` branch was removed in §10 and must be restored.

### Fix

Replace that block with:

```rust
let mut row_style = Style::default();
if r_idx == app.cursor_row {
    row_style = row_style.bg(theme.highlight);
} else if r_idx % 2 == 1 {
    row_style = row_style.bg(theme.alt_row);
}
```

This is identical to the original code that existed before §10 and matches the
highlight style used in Tab [2].

### Why this works with `render_stateful_widget`

The highlight style is baked into each `Row`'s style at build time (using the
absolute `r_idx`). The `render_stateful_widget` call with
`TableState::default().with_offset(scroll_row_offset)` renders rows starting from
`scroll_row_offset`, so the row whose `r_idx == cursor_row` appears at the correct
visual position inside the viewport — same mechanism Tab [2] already uses.

### Files changed

| File | Change |
|---|---|
| `rust_tui/src/ui.rs` | `draw_summary_tab`: restore `if r_idx == app.cursor_row` highlight block |

### Out of scope

- Any change to Tab [2] — it already has the correct highlight.
- Adding a Student info panel to Tab [1] — not requested.
- Making Tab [1] editable — it remains read-only (no edit key handler).

### End-to-end verification

1. Build: `cargo build --release` inside `rust_tui/`.
2. Run `./grade-tui` from project root, load a course.
3. Switch to Tab [1] (Summary).
4. Press Down/j: the **first row is highlighted** at launch; the highlight moves to
   the next row on each key press.
5. Press Down past the last visible row: the viewport scrolls and the cursor stays
   visible at the bottom (§10 scroll behaviour preserved).
6. Press Up/k: the highlight moves back up; the viewport scrolls back toward the top.
7. **Alternating rows:** non-highlighted rows still alternate between default and
   `alt_row` background — the highlight overrides only the cursor row.
8. **Tab switch:** switching to Tab [2] and back resets cursor to row 0 with
   highlight on the first row.

---

## 13 — Row number column in Tab [1] and Tab [2]

### Summary

Add a `#` column as the leftmost column in both the Summary tab (Tab [1]) and the
Raw Details right panel (Tab [2]). Each cell shows the student's 1-based absolute
position in the list (student at index 0 → "1", index 1 → "2", …). The number is
fixed to the student, not to the viewport position, so scrolling does not reset it.
Style: `theme.inactive_tab` (dim) to visually separate reference numbers from data.

### Column properties

| Property | Value |
|---|---|
| Header | `#` (two-line header: `"#\n"` to match `height(2)`) |
| Values | `r_idx + 1` (1-based, absolute) |
| Style | `Style::default().fg(theme.inactive_tab)` |
| Width | `format!("{}", total_students).len().max(1) as u16 + 1` |
| Min width | 3 (covers `#` header + students up to 99) |
| Position | Leftmost column, before Student ID |
| Navigation | Visual only — `cursor_col` and edit logic unchanged |

Width examples: 25 students → `len("25")=2 + 1 = 3`; 100 students → `4`.

---

### `rust_tui/src/ui.rs` — `draw_summary_tab`

#### 1. Compute column width (after `app.table_visible_rows` line)

```rust
let num_col_width = format!("{}", data.student_grades.len()).len().max(1) as u16 + 1;
```

#### 2. Header — prepend `#` cell

The existing code builds `header_cells` via `.map()` on `data.summary_columns`. Change
to collect into a `Vec` and prepend:

```rust
let num_header = Cell::from("#\n")
    .style(Style::default().fg(theme.inactive_tab).add_modifier(Modifier::BOLD));
let data_header_cells = data.summary_columns.iter().map(|h| { /* unchanged */ });
let header_cells: Vec<Cell> = std::iter::once(num_header)
    .chain(data_header_cells)
    .collect();
```

#### 3. Rows — prepend `#` cell per row

Inside the `.enumerate().map(|(r_idx, record)| { … })` closure:

```rust
let num_cell = Cell::from(format!("{}", r_idx + 1))
    .style(Style::default().fg(theme.inactive_tab));
// build existing `cells` iterator as before ...
let all_cells: Vec<Cell> = std::iter::once(num_cell).chain(cells).collect();
// ...
Row::new(all_cells).style(row_style).height(1)
```

#### 4. Update dynamic width calculation

The current fixed-width constants assume columns: StudentID (12) + Name + Grade (7).
The `#` column adds `num_col_width` to the fixed total and one more spacing unit.

```rust
// Before:
let spacings = n_cols.saturating_sub(1);
let fixed = 12usize + name_col_width as usize + 7;

// After (total rendered columns = n_cols + 1):
let spacings = n_cols; // (n_cols + 1) columns → n_cols spacings
let fixed = num_col_width as usize + 12usize + name_col_width as usize + 7;
```

#### 5. Widths vec — insert `#` width first

```rust
let mut widths = vec![Constraint::Length(num_col_width)]; // # column
for col_name in &data.summary_columns {
    // existing Student ID / Name / Grade / score_col_width logic unchanged
}
```

---

### `rust_tui/src/ui.rs` — `draw_sub_column_view`

#### 1. Compute column width (after `app.table_visible_rows` line)

```rust
let num_col_width = format!("{}", data.raw_scores.len()).len().max(1) as u16 + 1;
```

#### 2. Header — prepend `#` cell

Locate the `header_cells` vec construction (the lines building
`Cell::from("Student ID\n")` and `Cell::from("Name\n")`). Prepend:

```rust
let mut header_cells = vec![
    Cell::from("#\n").style(Style::default().fg(theme.inactive_tab).add_modifier(Modifier::BOLD)),
    // existing Student ID and Name header cells follow unchanged
];
```

#### 3. Rows — prepend `#` cell per row

Inside the row-building loop, before the existing `cells` vec is built:

```rust
let num_cell = Cell::from(format!("{}", r_idx + 1))
    .style(Style::default().fg(theme.inactive_tab));
// prepend to the row's cells vec
let mut cells = vec![num_cell, /* existing StudentID cell */, /* existing Name cell */, ...];
```

In practice: build the `num_cell` first, then `.chain()` or `insert(0, ...)` into the
existing cells construction — whichever fits the local pattern cleanly.

#### 4. Widths vec — insert `#` width first

```rust
let mut widths = vec![
    Constraint::Length(num_col_width), // # column (new)
    Constraint::Length(12),            // Student ID (unchanged)
    Constraint::Length(name_col_width), // Name (unchanged)
];
// sub-col widths and Total follow unchanged
```

---

### What does NOT change

- `app.rs` — no state changes; `cursor_col` indexing is unchanged (col 0 = Student ID).
- `draw_student_popup` (L2) — not reachable via normal navigation (§8); no change.
- Tab [3] Distribution, Tab [4] Roundup — not requested.
- Column cursor navigation in Tab [2] — `cursor_col == 0` still means Student ID,
  `cursor_col == 1` still means Name. The `#` column is never a cursor target.
- Edit key handling — unchanged; editing still uses `cursor_col` relative to the data.

---

### Files changed

| File | Change |
|---|---|
| `rust_tui/src/ui.rs` | `draw_summary_tab`: compute `num_col_width`; prepend `#` header + row cell; adjust `fixed`/`spacings`; insert `#` constraint in `widths` |
| `rust_tui/src/ui.rs` | `draw_sub_column_view`: compute `num_col_width`; prepend `#` header + row cell; insert `#` constraint in `widths` |

---

### End-to-end verification

1. Build: `cargo build --release` inside `rust_tui/`.
2. Run `./grade-tui`, load a course with ≥10 students.
3. **Tab [1] — Summary:**
   - A `#` column appears as the leftmost column with a dim color.
   - First student shows `1`, second `2`, etc.
   - Scroll down: row numbers continue from where the visible rows start
     (e.g., if scrolled to show students 6–20, the numbers shown are 6–20, not 1–15).
   - The remaining score columns still fill the available width (no layout overflow).
4. **Tab [2] — Raw Details:**
   - Select any category, focus the right panel.
   - A `#` column appears leftmost with a dim color.
   - Row numbers match Tab [1] for the same students.
   - Navigating with Up/Down does not move the cursor into the `#` column.
   - Editing (pressing Enter on a data cell) still works correctly.
5. **Column widths:** for a course with ≥100 students, the `#` column is 4 characters
   wide; for <100 students, 3 characters wide.
6. **No layout overflow:** the table fits within the terminal width (score columns
   shrink to accommodate the new `#` column).

---

## 14 — Scroll position indicator `[N/Total]` in the block title

### Summary

Display a dynamic `[18/48]` indicator on the **right side of the top border** of the
table block in Tab [1] (Summary) and Tab [2] (Raw Details right panel). The number
updates on every cursor move. Color: `theme.key_accent` (yellow/gold), bold.

- `N` = `app.cursor_row + 1` (1-based, absolute, same value as the `#` column)
- `Total` = total number of students in the course

### How ratatui 0.30 supports this

`block::Title` was removed in ratatui 0.30. Right-aligned block titles are now created
by passing a `Line` with `.right_aligned()` to `.title_top()`. Both the left-side
`.title(text)` and a right-side `.title_top(line.right_aligned())` can coexist on the
same block border — ratatui renders them at their respective edges.

No new imports are required: `Line`, `Span`, `Style`, and `Alignment` are already
imported in `ui.rs`.

### Changes — `rust_tui/src/ui.rs` only

#### `draw_summary_tab`

Append `.title_top(...)` to the existing block builder chain:

```rust
let block = Block::default()
    .borders(Borders::ALL)
    .border_type(BorderType::Rounded)
    .border_style(Style::default().fg(theme.border))
    .title(" 📋 Course Grades Summary ")
    .title_style(Style::default().fg(theme.info).bold())
    .title_top(
        Line::from(Span::styled(
            format!(" [{}/{}] ", app.cursor_row + 1, data.student_grades.len()),
            Style::default().fg(theme.key_accent).bold(),
        ))
        .right_aligned(),
    );
```

#### `draw_sub_column_view`

The block is built from a dynamic `title_text` string. Append `.title_top(...)`:

```rust
let block = Block::default()
    .borders(Borders::ALL)
    .border_type(BorderType::Rounded)
    .border_style(Style::default().fg(border_color))
    .title(title_text)
    .title_style(Style::default().fg(border_color).bold())
    .title_top(
        Line::from(Span::styled(
            format!(" [{}/{}] ", app.cursor_row + 1, data.raw_scores.len()),
            Style::default().fg(theme.key_accent).bold(),
        ))
        .right_aligned(),
    );
```

### What does NOT change

- `app.rs` — no state changes; the indicator reads existing `cursor_row`.
- Tab [3] Distribution, Tab [4] Roundup — not requested.
- The footer legend bar — no changes.
- The `#` row-number column (§13) — the indicator duplicates the current row's `#`
  value as a quick glance without needing to look at the leftmost column.

### Files changed

| File | Change |
|---|---|
| `rust_tui/src/ui.rs` | `draw_summary_tab`: add `.title_top(right-aligned position span)` to block |
| `rust_tui/src/ui.rs` | `draw_sub_column_view`: same addition to its block |

### End-to-end verification

1. Build: `cargo build --release` inside `rust_tui/`.
2. Run `./grade-tui`, load a course with ≥20 students.
3. **Tab [1] — Summary:**
   - The block's top-right corner shows `[1/N]` on launch.
   - Press Down: indicator changes to `[2/N]`, `[3/N]`, … in real time.
   - Scroll past viewport: indicator continues incrementing (e.g. `[18/48]`).
   - Press Up: indicator decrements.
   - The left-side title (" 📋 Course Grades Summary ") is unaffected.
4. **Tab [2] — Raw Details:**
   - Select a category, focus the right panel.
   - The right panel block's top-right corner shows `[1/N]`.
   - Navigate up/down: indicator updates to match the cursor row.
   - The indicator is visible regardless of whether the left or right panel is focused.
5. **Color:** the indicator text is yellow/gold (`theme.key_accent`), distinct from the
   block's border color and from the left-side title color.
6. **Consistency with `#` column:** when the cursor is on row `k`, the `#` cell of
   that row shows `k` and the indicator shows `[k/N]`.

