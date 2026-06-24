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
