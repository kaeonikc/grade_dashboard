use crate::types::*;
use tokio::sync::mpsc::Sender;
use std::collections::HashMap;
// theme

pub const ANALYTICS_CATEGORIES: [&str; 5] = [
    "Overview",
    "Progress Over Time",
    "Item Analysis",
    "Correlation Matrix",
    "At-Risk Students",
];
const AT_RISK_CATEGORY_INDEX: usize = 4;

pub const SUMMARY_CATEGORIES: [&str; 2] = ["Summary Scores", "For Submission"];

/// Attendance codes in picker order; "" clears the cell.
pub const ATTENDANCE_OPTIONS: [&str; 5] = ["P", "L", "X", "A", ""];

/// What the unsaved-changes prompt is guarding.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LeaveAction {
    Quit,
    CourseSelect,
}

/// Which students Fill Column writes to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FillTarget {
    All,
    Marked,
    Rows,
    Group,
}

/// The Fill Column dialog field that has keyboard focus.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FillField {
    Target,
    Rows,
    Groups,
    OnlyEmpty,
    Value,
}

/// Fill Column dialog state (SPEC_batch_editing.md).
pub struct FillDialog {
    pub column: String,
    pub is_attendance: bool,
    pub target: FillTarget,
    pub rows: tui_textarea::TextArea<'static>,
    /// Class Groups from the roster, with whether each is chosen. Empty when the course has < 2.
    pub groups: Vec<(String, bool)>,
    pub group_cursor: usize,
    pub only_empty: bool,
    pub value: tui_textarea::TextArea<'static>,
    pub attendance_index: usize,
    pub focus: FillField,
}

impl FillDialog {
    /// The fields Tab moves through, in order; Rows/Groups only for their target.
    pub fn fields(&self) -> Vec<FillField> {
        let mut f = vec![FillField::Target];
        match self.target {
            FillTarget::Rows => f.push(FillField::Rows),
            FillTarget::Group => f.push(FillField::Groups),
            _ => {}
        }
        f.push(FillField::OnlyEmpty);
        f.push(FillField::Value);
        f
    }

    pub fn targets(&self) -> Vec<FillTarget> {
        let mut t = vec![FillTarget::All, FillTarget::Marked, FillTarget::Rows];
        if !self.groups.is_empty() {
            t.push(FillTarget::Group);
        }
        t
    }
}

/// The editable score cell under the cursor in Raw Details (table or student popup).
#[derive(Debug, Clone)]
pub struct CellRef {
    pub row: usize,
    pub student_id: String,
    pub column: String,
    pub is_attendance: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppState {
    CourseSelect,
    Dashboard,
}

#[derive(Debug, Clone)]
pub enum AppEvent {
    Key(crossterm::event::KeyEvent),
    Resize(u16, u16),
    Tick,
    // Async events
    CoursesLoaded(Result<Vec<Course>, String>),
    CourseDataLoaded(Result<CourseData, String>),
    EditsSaved(Result<SaveReport, String>),
    ConfigUpdated(Result<(), String>),
    ReportsExported(Result<String, String>),
}

pub struct App {
    pub tx: Sender<AppEvent>,
    pub state: AppState,
    
    // Courses list state
    pub courses: Vec<Course>,
    pub course_index: usize,
    
    // Dashboard data
    pub selected_course_path: String,
    pub course_data: Option<CourseData>,
    pub active_tab: usize, // 0: Summary, 1: Raw Details, 2: Analytics, 3: Roundup
    pub show_left_panel: bool, // [s]: hide/show the left panels on every tab
    
    // Global UI state
    pub loading: bool,
    pub loading_msg: String,
    pub error: Option<String>,
    pub info_msg: Option<String>,
    pub width: u16,
    pub height: u16,
    
    // Grid/Table Navigation state
    pub cursor_row: usize,
    pub cursor_col: usize,
    pub scroll_row_offset: usize,
    pub scroll_col_offset: usize,
    
    // Score editing state
    pub editing: bool,
    pub edit_textarea: Option<tui_textarea::TextArea<'static>>,
    pub editing_student_id: String,
    pub editing_column: String,
    pub editing_original_value: String,
    pub editing_row: usize,

    // Unsaved edits, marked students and leaving (SPEC_batch_editing.md)
    pub edits: crate::edits::Edits,
    pub marks: std::collections::BTreeSet<String>,
    pub confirm_leave: Option<LeaveAction>,
    pub leave_after_save: Option<LeaveAction>,
    pub saving: Vec<(crate::edits::CellKey, crate::edits::PendingCell)>,
    pub error_after_reload: Option<String>,
    /// Set when the app should exit; main.rs checks it after each event.
    pub quit: bool,
    
    // Weight/Boundary settings editing state
    pub editing_weights: bool,
    pub editing_boundaries: bool,
    pub settings_keys: Vec<String>,
    pub settings_textareas: Vec<tui_textarea::TextArea<'static>>,
    pub settings_index: usize,

    // Tick tracker (for status message timeouts)
    pub info_msg_ticks: usize,

    // Color theme
    pub theme: crate::style::Theme,

    // Raw Details tab drill-down state
    pub raw_category_index: usize,
    pub raw_right_focused: bool,
    pub raw_selected_category: Option<String>,
    pub raw_selected_student: Option<usize>,

    // Analytics tab drill-down state (raw_selected_student/raw_selected_category are
    // reused to open the existing student popup in read-only mode from At-Risk Students)
    pub analytics_category_index: usize,
    pub analytics_right_focused: bool,

    // Summary tab (Tab [1]) left-panel category state: Summary Scores / For Submission
    pub summary_category_index: usize,
    pub summary_right_focused: bool,

    // Fill Column dialog (Raw Details, L1 sub-column view)
    pub fill: Option<FillDialog>,

    // Attendance picker state
    pub editing_attendance: bool,
    pub attendance_index: usize,

    // Reload behaviour
    pub preserve_nav_on_reload: bool,

    // Viewport height for scroll calculation (updated each render frame)
    pub table_visible_rows: usize,
}

impl App {
    pub fn new(tx: Sender<AppEvent>) -> Self {
        Self {
            tx,
            state: AppState::CourseSelect,
            courses: Vec::new(),
            course_index: 0,
            selected_course_path: String::new(),
            course_data: None,
            active_tab: 0,
            show_left_panel: true,
            loading: false,
            loading_msg: String::new(),
            error: None,
            info_msg: None,
            width: 80,
            height: 24,
            cursor_row: 0,
            cursor_col: 0,
            scroll_row_offset: 0,
            scroll_col_offset: 0,
            editing: false,
            edit_textarea: None,
            editing_student_id: String::new(),
            editing_column: String::new(),
            editing_original_value: String::new(),
            editing_row: 0,
            edits: crate::edits::Edits::default(),
            marks: std::collections::BTreeSet::new(),
            confirm_leave: None,
            leave_after_save: None,
            saving: Vec::new(),
            error_after_reload: None,
            quit: false,
            editing_weights: false,
            editing_boundaries: false,
            settings_keys: Vec::new(),
            settings_textareas: Vec::new(),
            settings_index: 0,
            info_msg_ticks: 0,
            theme: crate::style::load_theme(),
            raw_category_index: 0,
            raw_right_focused: false,
            raw_selected_category: None,
            raw_selected_student: None,
            analytics_category_index: 0,
            analytics_right_focused: false,
            summary_category_index: 0,
            summary_right_focused: false,
            fill: None,
            editing_attendance: false,
            attendance_index: 0,
            preserve_nav_on_reload: false,
            table_visible_rows: 15,
        }
    }

    pub fn sync_raw_category(&mut self) {
        let cats = self.get_categories();
        if cats.is_empty() {
            self.raw_selected_category = None;
        } else {
            if self.raw_category_index >= cats.len() {
                self.raw_category_index = cats.len() - 1;
            }
            self.raw_selected_category = Some(cats[self.raw_category_index].clone());
        }
    }

    pub fn get_categories(&self) -> Vec<String> {
        let data = match &self.course_data {
            Some(d) => d,
            None => return Vec::new(),
        };
        data.summary_columns.iter()
            .filter(|c| c.ends_with("_pct"))
            .map(|c| c.trim_end_matches("_pct").to_string())
            .collect()
    }

    /// Opens the existing (Raw Details) student popup for the At-Risk row under
    /// `cursor_row`, defaulting to that student's weakest category so the most
    /// relevant breakdown is shown first. Read-only: score editing stays scoped
    /// to the Raw Details tab.
    pub fn open_at_risk_student_popup(&mut self) {
        let data = match &self.course_data {
            Some(d) => d,
            None => return,
        };
        let at_risk = &data.analytics.at_risk;
        if self.cursor_row >= at_risk.len() {
            return;
        }
        let raw_idx = at_risk[self.cursor_row].raw_index;
        if raw_idx >= data.student_grades.len() {
            return;
        }
        let record = &data.student_grades[raw_idx];
        let mut weakest: Option<(String, f64)> = None;
        for (k, v) in record.iter() {
            if let Some(cat) = k.strip_suffix("_pct") {
                if let Some(val) = v.as_f64() {
                    let better = weakest.as_ref().map(|(_, wv)| val < *wv).unwrap_or(true);
                    if better {
                        weakest = Some((cat.to_string(), val));
                    }
                }
            }
        }
        self.raw_selected_category = weakest.map(|(c, _)| c);
        self.raw_selected_student = Some(raw_idx);
    }

    /// New course data from a load or a save: keeps the cursor/category when `preserve_nav_on_reload`.
    fn apply_course_data(&mut self, data: CourseData) {
        self.course_data = Some(data);
        self.state = AppState::Dashboard;
        if let Some(msg) = self.error_after_reload.take() {
            self.error = Some(msg);
        }
        if self.preserve_nav_on_reload {
            self.preserve_nav_on_reload = false;
            // Clamp cursor_row if student count shrank
            let max_rows = self.course_data.as_ref()
                .map(|d| d.raw_scores.len())
                .unwrap_or(0);
            if max_rows > 0 && self.cursor_row >= max_rows {
                self.cursor_row = max_rows - 1;
            }
            self.sync_raw_category();
        } else {
            self.cursor_row = 0;
            self.cursor_col = 0;
            self.scroll_row_offset = 0;
            self.scroll_col_offset = 0;
            self.raw_selected_category = None;
            self.raw_selected_student = None;
            self.raw_category_index = 0;
            self.raw_right_focused = false;
            self.analytics_category_index = 0;
            self.analytics_right_focused = false;
            self.summary_category_index = 0;
            self.summary_right_focused = false;
            self.sync_raw_category();
        }
    
    }

    pub fn load_courses(&mut self) {
        self.loading = true;
        self.loading_msg = "Scanning directory for courses...".to_string();
        self.error = None;
        let tx = self.tx.clone();
        tokio::spawn(async move {
            let res = crate::bridge::get_courses().await;
            let event = AppEvent::CoursesLoaded(res.map(|r| r.courses));
            let _ = tx.send(event).await;
        });
    }

    pub fn load_course_data(&mut self) {
        if self.selected_course_path.is_empty() {
            return;
        }
        self.loading = true;
        self.loading_msg = "Loading course data...".to_string();
        self.error = None;
        let path = self.selected_course_path.clone();
        let tx = self.tx.clone();
        tokio::spawn(async move {
            let res = crate::bridge::get_course_data(&path).await;
            let event = AppEvent::CourseDataLoaded(res);
            let _ = tx.send(event).await;
        });
    }

    /// The editable cell under the cursor: Raw Details only (table with the right panel focused, or
    /// the student popup opened there), on a score column, not while loading.
    pub fn current_cell(&self) -> Option<CellRef> {
        if self.state != AppState::Dashboard || self.active_tab != 1 || self.loading {
            return None;
        }
        let data = self.course_data.as_ref()?;
        let cat = self.raw_selected_category.as_ref()?;
        let row = match self.raw_selected_student {
            Some(r) => r,
            None if self.raw_right_focused => self.cursor_row,
            None => return None,
        };
        let sub_cols = data.data_mapping.get(cat)?;
        if self.cursor_col < 2 || self.cursor_col - 2 >= sub_cols.len() || row >= data.raw_scores.len() {
            return None;
        }
        let student_id = data.raw_scores[row].get("Student ID")?.as_str()?.to_string();
        Some(CellRef {
            row,
            student_id,
            column: sub_cols[self.cursor_col - 2].clone(),
            is_attendance: cat.to_lowercase().contains("attendance"),
        })
    }

    /// A cell as loaded from the files.
    pub fn loaded_text(&self, row: usize, column: &str) -> String {
        self.course_data
            .as_ref()
            .and_then(|d| d.raw_scores.get(row))
            .and_then(|r| r.get(column))
            .map(crate::edits::cell_text)
            .unwrap_or_default()
    }

    /// A cell as it will be after saving: the unsaved value if there is one.
    pub fn cell_value(&self, row: usize, column: &str) -> String {
        let sid = self.student_id_at(row);
        match self.edits.get(&sid, column) {
            Some(p) => p.value.clone(),
            None => self.loaded_text(row, column),
        }
    }

    pub fn student_id_at(&self, row: usize) -> String {
        self.course_data
            .as_ref()
            .and_then(|d| d.raw_scores.get(row))
            .and_then(|r| r.get("Student ID"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string()
    }

    pub fn max_of(&self, column: &str) -> Option<f64> {
        self.course_data.as_ref().and_then(|d| d.max_scores.get(column).copied())
    }

    /// Records unsaved values for (row, column) cells as ONE undo step; returns how many changed.
    pub fn set_cells(&mut self, cells: Vec<(usize, String, String)>) -> usize {
        let items = cells
            .into_iter()
            .map(|(row, col, value)| (self.student_id_at(row), col.clone(), value, self.loaded_text(row, &col)))
            .collect();
        self.edits.set(items)
    }

    /// After a cell is set: next student in the table, next item in the student popup.
    fn advance(&mut self) {
        if self.raw_selected_student.is_some() {
            self.move_right();
        } else {
            self.move_down();
        }
    }

    /// Sets the cell under the cursor (unsaved) and moves on.
    fn set_current(&mut self, value: &str, advance: bool) {
        if let Some(cell) = self.current_cell() {
            self.set_cells(vec![(cell.row, cell.column, value.to_string())]);
            self.error = None;
            if advance {
                self.advance();
            }
        }
    }

    /// Opens the inline editor on the cell under the cursor: starting from `first` (a typed
    /// character that replaces the value) or from the current value. Attendance opens the picker.
    pub fn start_editing_cell_with(&mut self, first: Option<char>) {
        if self.editing || self.editing_attendance {
            return;
        }
        let Some(cell) = self.current_cell() else { return };
        let current = self.cell_value(cell.row, &cell.column);
        self.editing_student_id = cell.student_id.clone();
        self.editing_column = cell.column.clone();
        self.editing_original_value = current.clone();
        self.editing_row = cell.row;

        if cell.is_attendance {
            let lookup = if current == "EA" { "X" } else { current.as_str() };
            // Unknown/empty values default to Clear (index 4)
            self.attendance_index = ATTENDANCE_OPTIONS.iter().position(|&o| o == lookup).unwrap_or(4);
            self.editing_attendance = true;
            return;
        }
        let text = first.map(|c| c.to_string()).unwrap_or(current);
        let mut ta = tui_textarea::TextArea::new(vec![text]);
        ta.move_cursor(tui_textarea::CursorMove::End);
        self.edit_textarea = Some(ta);
        self.editing = true;
    }

    /// Keeps the inline editor's value (unsaved) and moves: `step` 1 = next (Enter), 2 = down, -1 = up.
    /// A value that isn't a score keeps the editor open with an error.
    pub fn commit_inline_edit(&mut self, step: i8) {
        let Some(ta) = self.edit_textarea.as_ref() else { return };
        let text = ta.lines()[0].trim().to_string();
        let column = self.editing_column.clone();
        let max = self.max_of(&column);
        match crate::edits::validate_score(&text, max) {
            Err(msg) => {
                self.error = Some(msg);
                return;
            }
            Ok(over) => {
                self.error = None;
                if over {
                    self.info_msg = Some(format!("{} = {} is above the maximum {} (kept)", column, text, max.unwrap_or(0.0)));
                    self.info_msg_ticks = 0;
                }
            }
        }
        self.editing = false;
        self.edit_textarea = None;
        self.set_cells(vec![(self.editing_row, column, text)]);
        match step {
            1 => self.advance(),
            2 => self.move_down(),
            -1 => self.move_up(),
            _ => {}
        }
    }

    pub fn cancel_inline_edit(&mut self) {
        self.editing = false;
        self.edit_textarea = None;
        self.error = None;
    }

    /// The attendance picker's choice becomes an unsaved edit; the cursor moves on.
    pub fn save_attendance_score(&mut self) {
        let val = ATTENDANCE_OPTIONS[self.attendance_index].to_string();
        self.editing_attendance = false;
        self.set_cells(vec![(self.editing_row, self.editing_column.clone(), val)]);
        self.advance();
    }

    /// Ctrl+S: sends every unsaved edit to `tui_api.py apply-edits` in one call.
    pub fn save_pending(&mut self) {
        if self.edits.is_empty() || self.loading {
            if self.edits.is_empty() {
                self.info_msg = Some("No unsaved changes.".to_string());
                self.info_msg_ticks = 0;
            }
            return;
        }
        self.saving = self.edits.snapshot();
        let json = crate::edits::Edits::to_json(&self.saving);
        self.loading = true;
        self.loading_msg = format!("Saving {} cell{}...", self.saving.len(), if self.saving.len() == 1 { "" } else { "s" });
        let path = self.selected_course_path.clone();
        let tx = self.tx.clone();
        tokio::spawn(async move {
            let res = crate::bridge::apply_edits(&path, json).await;
            let _ = tx.send(AppEvent::EditsSaved(res)).await;
        });
    }

    /// q / Ctrl+C / Esc to the course list: asks first when there are unsaved edits.
    pub fn request_leave(&mut self, action: LeaveAction) {
        if self.edits.is_empty() {
            self.do_leave(action);
        } else {
            self.confirm_leave = Some(action);
        }
    }

    fn do_leave(&mut self, action: LeaveAction) {
        match action {
            LeaveAction::Quit => self.quit = true,
            LeaveAction::CourseSelect => self.leave_course(),
        }
    }

    fn leave_course(&mut self) {
        self.state = AppState::CourseSelect;
        self.course_data = None;
        self.edits.clear();
        self.marks.clear();
        self.load_courses();
    }

    /// Marks or unmarks the student on `row`.
    pub fn toggle_mark(&mut self, row: usize) {
        let sid = self.student_id_at(row);
        if sid.is_empty() {
            return;
        }
        if !self.marks.remove(&sid) {
            self.marks.insert(sid);
        }
    }

    /// Shift+↑/↓ (or K/J): marks this row, moves, marks the next.
    pub fn extend_marks(&mut self, down: bool) {
        let sid = self.student_id_at(self.cursor_row);
        if !sid.is_empty() {
            self.marks.insert(sid);
        }
        if down { self.move_down() } else { self.move_up() }
        let sid = self.student_id_at(self.cursor_row);
        if !sid.is_empty() {
            self.marks.insert(sid);
        }
    }

    fn marking_allowed(&self) -> bool {
        self.state == AppState::Dashboard
            && self.active_tab == 1
            && self.raw_right_focused
            && self.raw_selected_student.is_none()
            && self.course_data.is_some()
            && !self.loading
    }

    pub fn save_config(&mut self) {
        let path = self.selected_course_path.clone();
        let mut weights_map = HashMap::new();
        let mut boundaries_map = HashMap::new();

        if self.editing_weights {
            for (i, key) in self.settings_keys.iter().enumerate() {
                let val_str = self.settings_textareas[i].lines()[0].trim();
                if let Ok(val) = val_str.parse::<f64>() {
                    weights_map.insert(key.clone(), val);
                } else {
                    self.error = Some(format!("Invalid weight float value for key '{}': {}", key, val_str));
                    self.editing_weights = false;
                    return;
                }
            }
        } else if self.editing_boundaries {
            for (i, key) in self.settings_keys.iter().enumerate() {
                let val_str = self.settings_textareas[i].lines()[0].trim();
                if let Ok(val) = val_str.parse::<f64>() {
                    boundaries_map.insert(key.clone(), val);
                } else {
                    self.error = Some(format!("Invalid boundary float value for grade '{}': {}", key, val_str));
                    self.editing_boundaries = false;
                    return;
                }
            }
        }

        self.loading = true;
        self.loading_msg = "Saving updated configuration...".to_string();
        
        let editing_w = self.editing_weights;
        self.editing_weights = false;
        self.editing_boundaries = false;
        
        let tx = self.tx.clone();
        tokio::spawn(async move {
            let (weights_json, boundaries_json) = if editing_w {
                (serde_json::to_string(&weights_map).unwrap(), "null".to_string())
            } else {
                ("null".to_string(), serde_json::to_string(&boundaries_map).unwrap())
            };
            let res = crate::bridge::update_config(&path, &weights_json, &boundaries_json).await;
            let event = AppEvent::ConfigUpdated(res.map(|_| ()));
            let _ = tx.send(event).await;
        });
    }

    pub fn export_reports(&mut self) {
        if self.selected_course_path.is_empty() {
            return;
        }
        self.loading = true;
        self.loading_msg = "Exporting final grades & copy-friendly scores...".to_string();
        let path = self.selected_course_path.clone();
        let tx = self.tx.clone();
        tokio::spawn(async move {
            let res = crate::bridge::export_reports(&path).await;
            let event = AppEvent::ReportsExported(res.map(|r| r.message));
            let _ = tx.send(event).await;
        });
    }

    /// `f`: opens Fill Column for the column under the cursor (Raw Details table only).
    pub fn start_bulk_fill(&mut self) {
        if self.editing || self.fill.is_some() || self.loading || self.raw_selected_student.is_some() {
            return;
        }
        let Some(cell) = self.current_cell() else { return };
        let data = self.course_data.as_ref().unwrap();
        let mut groups: Vec<String> = data.raw_scores.iter()
            .filter_map(|r| r.get("Class Group").and_then(|v| v.as_str()))
            .filter(|g| !g.is_empty())
            .map(|g| g.to_string())
            .collect();
        groups.sort();
        groups.dedup();
        let groups = if groups.len() >= 2 { groups.into_iter().map(|g| (g, false)).collect() } else { Vec::new() };

        self.fill = Some(FillDialog {
            column: cell.column,
            is_attendance: cell.is_attendance,
            target: if self.marks.is_empty() { FillTarget::All } else { FillTarget::Marked },
            rows: tui_textarea::TextArea::default(),
            groups,
            group_cursor: 0,
            only_empty: false,
            value: tui_textarea::TextArea::default(),
            attendance_index: 0,
            focus: FillField::Value,
        });
    }

    /// The rows Fill Column would write, or why it can't.
    pub fn fill_rows(&self) -> Result<Vec<usize>, String> {
        let Some(fill) = self.fill.as_ref() else { return Ok(Vec::new()) };
        let Some(data) = self.course_data.as_ref() else { return Ok(Vec::new()) };
        let n = data.raw_scores.len();
        let rows: Vec<usize> = match fill.target {
            FillTarget::All => (0..n).collect(),
            FillTarget::Marked => {
                if self.marks.is_empty() {
                    return Err("no rows marked (Space marks a row)".to_string());
                }
                (0..n).filter(|&r| self.marks.contains(&self.student_id_at(r))).collect()
            }
            FillTarget::Rows => crate::edits::parse_row_ranges(&fill.rows.lines()[0], n)?,
            FillTarget::Group => {
                let chosen: Vec<&str> = fill.groups.iter().filter(|(_, on)| *on).map(|(g, _)| g.as_str()).collect();
                if chosen.is_empty() {
                    return Err("choose a group (Space)".to_string());
                }
                (0..n)
                    .filter(|&r| {
                        let g = data.raw_scores[r].get("Class Group").and_then(|v| v.as_str()).unwrap_or("");
                        chosen.contains(&g)
                    })
                    .collect()
            }
        };
        Ok(if fill.only_empty {
            rows.into_iter().filter(|&r| self.cell_value(r, &fill.column).trim().is_empty()).collect()
        } else {
            rows
        })
    }

    /// Enter in Fill Column: the chosen students' cells become unsaved edits (one undo step).
    pub fn apply_fill(&mut self) {
        let Some(fill) = self.fill.as_ref() else { return };
        let column = fill.column.clone();
        let value = if fill.is_attendance {
            ATTENDANCE_OPTIONS[fill.attendance_index].to_string()
        } else {
            let v = fill.value.lines()[0].trim().to_string();
            // The value starts empty, so a stray Enter must not blank the column: empty = cancel.
            if v.is_empty() {
                self.fill = None;
                return;
            }
            if let Err(msg) = crate::edits::validate_score(&v, self.max_of(&column)) {
                self.error = Some(msg);
                return;
            }
            v
        };
        let rows = match self.fill_rows() {
            Ok(r) if r.is_empty() => {
                self.error = Some("No students match.".to_string());
                return;
            }
            Ok(r) => r,
            Err(msg) => {
                self.error = Some(msg);
                return;
            }
        };
        let n_rows = rows.len();
        let changed = self.set_cells(rows.into_iter().map(|r| (r, column.clone(), value.clone())).collect());
        self.fill = None;
        self.error = None;
        let shown = if value.is_empty() { "blank".to_string() } else { value };
        self.info_msg = Some(format!(
            "Filled {} = {} for {} student{} ({} changed, unsaved). Ctrl+S saves, u undoes.",
            column, shown, n_rows, if n_rows == 1 { "" } else { "s" }, changed
        ));
        self.info_msg_ticks = 0;
    }

    /// Keys while the Fill Column dialog is open.
    fn fill_key(&mut self, key: crossterm::event::KeyEvent) {
        use crossterm::event::KeyCode;
        let Some(fill) = self.fill.as_mut() else { return };
        match key.code {
            KeyCode::Esc => {
                self.fill = None;
                self.error = None;
                return;
            }
            KeyCode::Enter => {
                self.apply_fill();
                return;
            }
            KeyCode::Tab | KeyCode::BackTab => {
                let fields = fill.fields();
                let i = fields.iter().position(|f| *f == fill.focus).unwrap_or(0);
                let n = fields.len();
                let j = if key.code == KeyCode::Tab { (i + 1) % n } else { (i + n - 1) % n };
                fill.focus = fields[j];
                return;
            }
            _ => {}
        }
        match fill.focus {
            FillField::Target => {
                let targets = fill.targets();
                let i = targets.iter().position(|t| *t == fill.target).unwrap_or(0);
                let n = targets.len();
                match key.code {
                    KeyCode::Right | KeyCode::Char(' ') | KeyCode::Down => fill.target = targets[(i + 1) % n],
                    KeyCode::Left | KeyCode::Up => fill.target = targets[(i + n - 1) % n],
                    _ => {}
                }
            }
            FillField::Rows => {
                fill.rows.input(key);
            }
            FillField::Groups => match key.code {
                KeyCode::Right | KeyCode::Down if !fill.groups.is_empty() => {
                    fill.group_cursor = (fill.group_cursor + 1) % fill.groups.len();
                }
                KeyCode::Left | KeyCode::Up if !fill.groups.is_empty() => {
                    fill.group_cursor = (fill.group_cursor + fill.groups.len() - 1) % fill.groups.len();
                }
                KeyCode::Char(' ') => {
                    if let Some(g) = fill.groups.get_mut(fill.group_cursor) {
                        g.1 = !g.1;
                    }
                }
                _ => {}
            },
            FillField::OnlyEmpty => {
                if key.code == KeyCode::Char(' ') {
                    fill.only_empty = !fill.only_empty;
                }
            }
            FillField::Value => {
                if fill.is_attendance {
                    match key.code {
                        KeyCode::Right | KeyCode::Down => fill.attendance_index = (fill.attendance_index + 1) % 5,
                        KeyCode::Left | KeyCode::Up => fill.attendance_index = (fill.attendance_index + 4) % 5,
                        KeyCode::Char(c) => {
                            if let Some(i) = "plxac".find(c.to_ascii_lowercase()) {
                                fill.attendance_index = i;
                            }
                        }
                        KeyCode::Backspace | KeyCode::Delete => fill.attendance_index = 4,
                        _ => {}
                    }
                } else {
                    fill.value.input(key);
                }
            }
        }
    }

    pub fn start_editing_weights(&mut self) {
        let data = match &self.course_data {
            Some(d) => d,
            None => return,
        };
        self.editing_weights = true;
        self.settings_index = 0;
        self.settings_keys.clear();
        self.settings_textareas.clear();

        // Preserving insertion order by sorting or grabbing from weights
        let mut sorted_keys: Vec<String> = data.weights.keys().cloned().collect();
        sorted_keys.sort();

        for key in sorted_keys {
            let val = data.weights.get(&key).copied().unwrap_or(0.0);
            let mut ta = tui_textarea::TextArea::new(vec![format!("{:.2}", val)]);
            ta.move_cursor(tui_textarea::CursorMove::End);
            ta.set_cursor_line_style(ratatui::style::Style::default().bg(self.theme.highlight));
            ta.set_style(
                ratatui::style::Style::default()
                    .fg(self.theme.key_accent)
                    .bg(self.theme.panel_bg)
            );
            self.settings_keys.push(key);
            self.settings_textareas.push(ta);
        }
    }

    pub fn start_editing_boundaries(&mut self) {
        let data = match &self.course_data {
            Some(d) => d,
            None => return,
        };
        self.editing_boundaries = true;
        self.settings_index = 0;
        self.settings_keys.clear();
        self.settings_textareas.clear();

        for (grade, val) in &data.grade_boundaries {
            let mut ta = tui_textarea::TextArea::new(vec![format!("{:.1}", val)]);
            ta.move_cursor(tui_textarea::CursorMove::End);
            ta.set_cursor_line_style(ratatui::style::Style::default().bg(self.theme.highlight));
            ta.set_style(
                ratatui::style::Style::default()
                    .fg(self.theme.info)
                    .bg(self.theme.panel_bg)
            );
            self.settings_keys.push(grade.clone());
            self.settings_textareas.push(ta);
        }
    }

    pub fn move_up(&mut self) {
        if self.state == AppState::CourseSelect {
            if self.course_index > 0 {
                self.course_index -= 1;
            }
        } else if self.state == AppState::Dashboard {
            if self.editing_weights || self.editing_boundaries {
                if self.settings_index > 0 {
                    self.settings_index -= 1;
                }
            } else if !self.editing {
                if self.active_tab == 1 && self.raw_selected_student.is_some() {
                    return;
                }
                if self.active_tab == 2 && self.raw_selected_student.is_some() {
                    return;
                }
                if self.active_tab == 1 && !self.raw_right_focused {
                    if self.raw_category_index > 0 {
                        self.raw_category_index -= 1;
                        self.sync_raw_category();
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
                        self.cursor_col = 0;
                        self.scroll_col_offset = 0;
                    }
                    return;
                }
                if self.active_tab == 2 && !self.analytics_right_focused {
                    if self.analytics_category_index > 0 {
                        self.analytics_category_index -= 1;
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
                    }
                    return;
                }
                if self.active_tab == 0 && !self.summary_right_focused {
                    if self.summary_category_index > 0 {
                        self.summary_category_index -= 1;
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
                        self.cursor_col = 0;
                        self.scroll_col_offset = 0;
                    }
                    return;
                }
                if self.cursor_row > 0 {
                    self.cursor_row -= 1;
                    self.adjust_scroll_row();
                }
            }
        }
    }

    pub fn move_down(&mut self) {
        if self.state == AppState::CourseSelect {
            if self.course_index + 1 < self.courses.len() {
                self.course_index += 1;
            }
        } else if self.state == AppState::Dashboard {
            if self.editing_weights || self.editing_boundaries {
                if self.settings_index + 1 < self.settings_keys.len() {
                    self.settings_index += 1;
                }
            } else if !self.editing {
                if self.active_tab == 1 && self.raw_selected_student.is_some() {
                    return;
                }
                if self.active_tab == 2 && self.raw_selected_student.is_some() {
                    return;
                }
                if self.active_tab == 1 && !self.raw_right_focused {
                    let cat_count = self.get_categories().len();
                    if self.raw_category_index + 1 < cat_count {
                        self.raw_category_index += 1;
                        self.sync_raw_category();
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
                        self.cursor_col = 0;
                        self.scroll_col_offset = 0;
                    }
                    return;
                }
                if self.active_tab == 2 && !self.analytics_right_focused {
                    if self.analytics_category_index + 1 < ANALYTICS_CATEGORIES.len() {
                        self.analytics_category_index += 1;
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
                    }
                    return;
                }
                if self.active_tab == 0 && !self.summary_right_focused {
                    if self.summary_category_index + 1 < SUMMARY_CATEGORIES.len() {
                        self.summary_category_index += 1;
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
                        self.cursor_col = 0;
                        self.scroll_col_offset = 0;
                    }
                    return;
                }
                let max_rows = match &self.course_data {
                    Some(data) => {
                        if self.active_tab == 0 {
                            data.student_grades.len()
                        } else if self.active_tab == 1 {
                            data.raw_scores.len()
                        } else if self.active_tab == 2 {
                            data.analytics.at_risk.len()
                        } else if self.active_tab == 3 {
                            data.roundup_summary.improved_students.len()
                        } else {
                            0
                        }
                    }
                    None => 0,
                };
                if self.cursor_row + 1 < max_rows {
                    self.cursor_row += 1;
                    self.adjust_scroll_row();
                }
            }
        }
    }

    pub fn move_half_page_down(&mut self) {
        if self.state != AppState::Dashboard { return; }
        if self.active_tab == 1 && !self.raw_right_focused { return; }
        if self.active_tab == 2 && !self.analytics_right_focused { return; }
        let max_rows = match &self.course_data {
            Some(data) => match self.active_tab {
                0 => data.student_grades.len(),
                1 => data.raw_scores.len(),
                2 => data.analytics.at_risk.len(),
                3 => data.roundup_summary.improved_students.len(),
                _ => 0,
            },
            None => 0,
        };
        if max_rows == 0 { return; }
        let half = (self.table_visible_rows / 2).max(1);
        self.cursor_row = (self.cursor_row + half).min(max_rows - 1);
        let max_scroll = max_rows.saturating_sub(self.table_visible_rows);
        self.scroll_row_offset = (self.scroll_row_offset + half).min(max_scroll);
        self.adjust_scroll_row();
    }

    pub fn move_half_page_up(&mut self) {
        if self.state != AppState::Dashboard { return; }
        if self.active_tab == 1 && !self.raw_right_focused { return; }
        if self.active_tab == 2 && !self.analytics_right_focused { return; }
        let half = (self.table_visible_rows / 2).max(1);
        self.cursor_row = self.cursor_row.saturating_sub(half);
        self.scroll_row_offset = self.scroll_row_offset.saturating_sub(half);
        self.adjust_scroll_row();
    }

    pub fn move_left(&mut self) {
        if self.state == AppState::Dashboard && !self.editing && !self.editing_weights && !self.editing_boundaries {
            if self.active_tab == 0 {
                if self.summary_right_focused {
                    if self.summary_category_index == 0 && self.cursor_col > 0 {
                        self.cursor_col -= 1;
                        self.adjust_scroll_col();
                    } else {
                        // Category 1 (For Submission) has no column cursor — ← always
                        // returns focus to the left panel, matching category 0 at col 0.
                        self.summary_right_focused = false;
                    }
                }
                return;
            }
            if self.active_tab == 1 {
                if self.raw_right_focused {
                    if self.cursor_col > 0 {
                        self.cursor_col -= 1;
                        self.adjust_scroll_col();
                    } else if self.raw_selected_student.is_none() {
                        // L1 right panel: return focus to left panel
                        self.raw_right_focused = false;
                    }
                }
                return;
            }
            if self.active_tab == 2 {
                if self.analytics_right_focused && self.raw_selected_student.is_none() {
                    self.analytics_right_focused = false;
                    self.cursor_row = 0;
                    self.scroll_row_offset = 0;
                }
                return;
            }
            // Tabs 0-2 all return early above; nothing else has a column cursor.
        }
    }

    pub fn move_right(&mut self) {
        if self.state == AppState::Dashboard && !self.editing && !self.editing_weights && !self.editing_boundaries {
            if self.active_tab == 0 {
                if !self.summary_right_focused {
                    self.summary_right_focused = true;
                    self.cursor_col = 0;
                    self.scroll_col_offset = 0;
                } else if self.summary_category_index == 0 {
                    let max_cols = self.course_data.as_ref().map(|d| d.summary_columns.len()).unwrap_or(0);
                    if self.cursor_col + 1 < max_cols {
                        self.cursor_col += 1;
                        self.adjust_scroll_col();
                    }
                }
                // Category 1 (For Submission) is row-only — → is a no-op once focused.
                return;
            }
            if self.active_tab == 2 {
                if !self.analytics_right_focused
                    && self.analytics_category_index == AT_RISK_CATEGORY_INDEX
                    && self.raw_selected_student.is_none()
                {
                    self.analytics_right_focused = true;
                    self.cursor_row = 0;
                    self.scroll_row_offset = 0;
                }
                return;
            }
            if self.active_tab == 1 {
                if !self.raw_right_focused {
                    // Left panel → focus right panel
                    self.raw_right_focused = true;
                    self.cursor_col = 2;
                    self.scroll_col_offset = 2;
                } else {
                    // Right panel (L1 or L2): navigate cols
                    let max_cols = match &self.course_data {
                        Some(data) => {
                            let cat = self.raw_selected_category.as_deref().unwrap_or("");
                            data.data_mapping.get(cat).map(|v| v.len()).unwrap_or(0) + 3
                        }
                        None => 0,
                    };
                    if self.cursor_col + 1 < max_cols {
                        self.cursor_col += 1;
                        self.adjust_scroll_col();
                    }
                }
                return;
            }
            // Tabs 0-2 all return early above; nothing else has a column cursor.
        }
    }

    fn adjust_scroll_row(&mut self) {
        let visible_rows = self.table_visible_rows.max(1);
        if self.cursor_row < self.scroll_row_offset {
            self.scroll_row_offset = self.cursor_row;
        } else if self.cursor_row >= self.scroll_row_offset + visible_rows {
            self.scroll_row_offset = self.cursor_row - visible_rows + 1;
        }
    }

    /// Inner width of the Raw Details table: the full terminal for the student popup or when the
    /// left panel is hidden, otherwise the terminal minus the left panel (33) — both minus 2 borders.
    pub fn raw_table_inner_width(&self) -> usize {
        if self.raw_selected_student.is_some() || !self.show_left_panel {
            (self.width as usize).saturating_sub(2)
        } else {
            (self.width as usize).saturating_sub(35)
        }
    }

    fn adjust_scroll_col(&mut self) {
        if self.active_tab == 1 {
            if self.cursor_col < 2 {
                self.scroll_col_offset = 2;
                return;
            }
            // Total column is always rendered last — navigating to it never needs a scroll
            let sub_col_count = self.raw_selected_category.as_ref()
                .and_then(|cat| self.course_data.as_ref().and_then(|d| d.data_mapping.get(cat)))
                .map(|v| v.len())
                .unwrap_or(0);
            if self.cursor_col == sub_col_count + 2 {
                return;
            }

            if self.cursor_col < self.scroll_col_offset {
                self.scroll_col_offset = self.cursor_col;
                return;
            }
            // Same widths as the drawing (ui::fitting_sub_cols): move the first visible column right until the
            // cursor's column fits beside ID, Name and Total.
            let cat = self.raw_selected_category.clone().unwrap_or_default();
            let inner = self.raw_table_inner_width();
            let cursor_sub = self.cursor_col - 2;
            let mut start = self.scroll_col_offset.saturating_sub(2);
            while start < cursor_sub && start + crate::ui::fitting_sub_cols(self, &cat, start, inner) <= cursor_sub {
                start += 1;
            }
            self.scroll_col_offset = start + 2;
            return;
        }

        let visible_cols = 6;
        if self.cursor_col < self.scroll_col_offset {
            self.scroll_col_offset = self.cursor_col;
        } else if self.cursor_col >= self.scroll_col_offset + visible_cols {
            self.scroll_col_offset = self.cursor_col - visible_cols + 1;
        }
    }

    pub fn update(&mut self, event: AppEvent) {
        match event {
            AppEvent::Tick => {
                self.info_msg_ticks = self.info_msg_ticks.wrapping_add(1);
                if self.info_msg.is_some() && self.info_msg_ticks % 15 == 0 {
                    self.info_msg = None;
                }
            }
            AppEvent::Resize(w, h) => {
                self.width = w;
                self.height = h;
            }
            AppEvent::CoursesLoaded(res) => {
                self.loading = false;
                match res {
                    Ok(list) => {
                        self.courses = list;
                        if self.course_index >= self.courses.len() {
                            self.course_index = 0;
                        }
                    }
                    Err(e) => {
                        self.error = Some(e);
                    }
                }
            }
            AppEvent::CourseDataLoaded(res) => {
                self.loading = false;
                match res {
                    Ok(data) => self.apply_course_data(data),
                    Err(e) => {
                        self.error = Some(e);
                    }
                }
            }
            AppEvent::EditsSaved(res) => {
                self.loading = false;
                let sent = std::mem::take(&mut self.saving);
                let leave = self.leave_after_save.take();
                match res {
                    Ok(mut report) => {
                        let fresh = report.course_data.take();
                        self.edits.settle(&sent, &report);
                        self.marks.clear();
                        if report.conflicts.is_empty() {
                            self.info_msg = Some(report.message.clone());
                            self.info_msg_ticks = 0;
                            if let Some(action) = leave {
                                self.do_leave(action);
                                return;
                            }
                        } else {
                            let listed: Vec<String> = report.conflicts.iter().take(4)
                                .map(|c| format!("{} {}", c.student_id, c.column))
                                .collect();
                            let more = report.conflicts.len().saturating_sub(4);
                            self.error_after_reload = Some(format!(
                                "Saved {} · {} not saved (changed on disk or not found, still unsaved): {}{}",
                                report.saved,
                                report.conflicts.len(),
                                listed.join(", "),
                                if more > 0 { format!(" +{} more", more) } else { String::new() }
                            ));
                        }
                        self.preserve_nav_on_reload = true;
                        match fresh {
                            // Swap in the reloaded course together with settling the edits: no gap
                            // where the old values show, and no second python start.
                            Some(data) => self.apply_course_data(*data),
                            None if report.saved > 0 => self.load_course_data(),
                            None => {
                                self.preserve_nav_on_reload = false;
                                if let Some(msg) = self.error_after_reload.take() {
                                    self.error = Some(msg);
                                }
                            }
                        }
                    }
                    Err(e) => {
                        self.error = Some(format!("Save failed, nothing written: {}", e));
                    }
                }
            }
            AppEvent::ConfigUpdated(res) => {
                self.loading = false;
                match res {
                    Ok(_) => {
                        self.info_msg = Some("Configuration successfully updated!".to_string());
                        self.info_msg_ticks = 0;
                        self.preserve_nav_on_reload = true;
                        self.load_course_data();
                    }
                    Err(e) => {
                        self.error = Some(format!("Failed to save config: {}", e));
                    }
                }
            }
            AppEvent::ReportsExported(res) => {
                self.loading = false;
                match res {
                    Ok(msg) => {
                        self.info_msg = Some(if self.edits.is_empty() {
                            msg
                        } else {
                            format!("{} (saved scores only; {} edits unsaved)", msg, self.edits.len())
                        });
                        self.info_msg_ticks = 0;
                    }
                    Err(e) => {
                        self.error = Some(format!("Export failed: {}", e));
                    }
                }
            }
            AppEvent::Key(key) => {
                use crossterm::event::{KeyCode, KeyModifiers};
                // Ctrl+C: close whatever is open, then quit (asking first when edits are unsaved)
                if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
                    self.cancel_inline_edit();
                    self.editing_attendance = false;
                    self.fill = None;
                    self.editing_weights = false;
                    self.editing_boundaries = false;
                    self.request_leave(LeaveAction::Quit);
                    return;
                }

                // Unsaved-changes prompt
                if let Some(action) = self.confirm_leave {
                    match key.code {
                        KeyCode::Char('s') | KeyCode::Char('S') => {
                            self.confirm_leave = None;
                            self.leave_after_save = Some(action);
                            self.save_pending();
                        }
                        KeyCode::Char('d') | KeyCode::Char('D') => {
                            self.confirm_leave = None;
                            self.edits.clear();
                            self.do_leave(action);
                        }
                        KeyCode::Esc => self.confirm_leave = None,
                        _ => {}
                    }
                    return;
                }

                // Inline cell editor
                if self.editing {
                    match key.code {
                        KeyCode::Enter => self.commit_inline_edit(1),
                        KeyCode::Down => self.commit_inline_edit(2),
                        KeyCode::Up => self.commit_inline_edit(-1),
                        KeyCode::Esc => self.cancel_inline_edit(),
                        _ => {
                            if let Some(ta) = self.edit_textarea.as_mut() {
                                ta.input(key);
                            }
                        }
                    }
                    return;
                }

                if self.fill.is_some() {
                    self.fill_key(key);
                    return;
                }

                if self.editing_attendance {
                    match key.code {
                        crossterm::event::KeyCode::Esc => {
                            self.editing_attendance = false;
                        }
                        crossterm::event::KeyCode::Enter => {
                            self.save_attendance_score();
                            self.editing_attendance = false;
                        }
                        crossterm::event::KeyCode::Up | crossterm::event::KeyCode::Char('k') => {
                            self.attendance_index = self.attendance_index.saturating_sub(1);
                        }
                        crossterm::event::KeyCode::Down | crossterm::event::KeyCode::Char('j') => {
                            if self.attendance_index < 4 {
                                self.attendance_index += 1;
                            }
                        }
                        // One-key quick-pick: immediately jump to option and save
                        crossterm::event::KeyCode::Char('p') | crossterm::event::KeyCode::Char('P') => {
                            self.attendance_index = 0;
                            self.save_attendance_score();
                            self.editing_attendance = false;
                        }
                        crossterm::event::KeyCode::Char('l') | crossterm::event::KeyCode::Char('L') => {
                            self.attendance_index = 1;
                            self.save_attendance_score();
                            self.editing_attendance = false;
                        }
                        crossterm::event::KeyCode::Char('x') | crossterm::event::KeyCode::Char('X') => {
                            self.attendance_index = 2;
                            self.save_attendance_score();
                            self.editing_attendance = false;
                        }
                        crossterm::event::KeyCode::Char('a') | crossterm::event::KeyCode::Char('A') => {
                            self.attendance_index = 3;
                            self.save_attendance_score();
                            self.editing_attendance = false;
                        }
                        crossterm::event::KeyCode::Char('c') | crossterm::event::KeyCode::Char('C')
                        | crossterm::event::KeyCode::Delete | crossterm::event::KeyCode::Backspace => {
                            self.attendance_index = 4;
                            self.save_attendance_score();
                            self.editing_attendance = false;
                        }
                        _ => {}
                    }
                    return;
                }

                if self.editing_weights || self.editing_boundaries {
                    match key.code {
                        crossterm::event::KeyCode::Esc => {
                            self.editing_weights = false;
                            self.editing_boundaries = false;
                        }
                        crossterm::event::KeyCode::Enter => {
                            self.save_config();
                        }
                        crossterm::event::KeyCode::Up => {
                            self.move_up();
                        }
                        crossterm::event::KeyCode::Down => {
                            self.move_down();
                        }
                        _ => {
                            if self.settings_index < self.settings_textareas.len() {
                                self.settings_textareas[self.settings_index].input(key);
                            }
                        }
                    }
                    return;
                }

                // Half-page jump (Ctrl+D / Ctrl+U), save (Ctrl+S)
                if key.modifiers.contains(KeyModifiers::CONTROL) {
                    match key.code {
                        KeyCode::Char('d') => { self.move_half_page_down(); return; }
                        KeyCode::Char('u') => { self.move_half_page_up(); return; }
                        KeyCode::Char('s') => {
                            if self.state == AppState::Dashboard {
                                self.save_pending();
                            }
                            return;
                        }
                        _ => {}
                    }
                }

                // Marking students (Raw Details table)
                if self.marking_allowed() {
                    let shift = key.modifiers.contains(KeyModifiers::SHIFT);
                    match key.code {
                        KeyCode::Char(' ') => { self.toggle_mark(self.cursor_row); return; }
                        KeyCode::Down if shift => { self.extend_marks(true); return; }
                        KeyCode::Up if shift => { self.extend_marks(false); return; }
                        KeyCode::Char('J') => { self.extend_marks(true); return; }
                        KeyCode::Char('K') => { self.extend_marks(false); return; }
                        _ => {}
                    }
                }

                // Typing into the score cell under the cursor (SPEC_batch_editing.md)
                if let Some(cell) = self.current_cell() {
                    match key.code {
                        KeyCode::Char(c) if !cell.is_attendance && (c.is_ascii_digit() || c == '.') => {
                            self.start_editing_cell_with(Some(c));
                            return;
                        }
                        KeyCode::Char('-') if !cell.is_attendance => {
                            self.set_current(crate::edits::ABSENT, true);
                            return;
                        }
                        KeyCode::Char(c) if cell.is_attendance && "PLAXplax".contains(c) => {
                            self.set_current(&c.to_ascii_uppercase().to_string(), true);
                            return;
                        }
                        KeyCode::Char('c') | KeyCode::Char('C') if cell.is_attendance => {
                            self.set_current("", false);
                            return;
                        }
                        KeyCode::Backspace | KeyCode::Delete => {
                            self.set_current("", false);
                            return;
                        }
                        _ => {}
                    }
                }

                // Standard navigation
                match key.code {
                    KeyCode::Char('q') => {
                        self.request_leave(LeaveAction::Quit);
                    }
                    KeyCode::Char('u') => {
                        if self.state == AppState::Dashboard {
                            let undone = self.edits.undo();
                            self.info_msg = Some(if undone { "Undid the last change." } else { "Nothing to undo." }.to_string());
                            self.info_msg_ticks = 0;
                        }
                    }
                    KeyCode::Char('m') => {
                        if self.state == AppState::Dashboard && !self.marks.is_empty() {
                            self.info_msg = Some(format!("Cleared {} marks.", self.marks.len()));
                            self.info_msg_ticks = 0;
                            self.marks.clear();
                        }
                    }
                    crossterm::event::KeyCode::Char('s') | crossterm::event::KeyCode::Char('S') => {
                        if self.state == AppState::Dashboard && self.raw_selected_student.is_none() {
                            self.show_left_panel = !self.show_left_panel;
                        }
                    }
                    crossterm::event::KeyCode::Char('e') | crossterm::event::KeyCode::Char('E') => {
                        if self.state == AppState::Dashboard {
                            self.export_reports();
                        }
                    }
                    crossterm::event::KeyCode::Char('w') | crossterm::event::KeyCode::Char('W') => {
                        if self.state == AppState::Dashboard {
                            self.start_editing_weights();
                        }
                    }
                    crossterm::event::KeyCode::Char('b') | crossterm::event::KeyCode::Char('B') => {
                        if self.state == AppState::Dashboard {
                            self.start_editing_boundaries();
                        }
                    }
                    crossterm::event::KeyCode::Char('f') | crossterm::event::KeyCode::Char('F') => {
                        if self.state == AppState::Dashboard {
                            self.start_bulk_fill();
                        }
                    }
                    crossterm::event::KeyCode::Tab => {
                        if self.state == AppState::Dashboard {
                            self.active_tab = (self.active_tab + 1) % 4;
                            self.cursor_row = 0;
                            self.cursor_col = 0;
                            self.scroll_row_offset = 0;
                            self.scroll_col_offset = 0;
                            self.raw_selected_category = None;
                            self.raw_selected_student = None;
                            self.raw_category_index = 0;
                            self.raw_right_focused = false;
                            self.analytics_category_index = 0;
                            self.analytics_right_focused = false;
                            self.summary_category_index = 0;
                            self.summary_right_focused = false;
                            self.sync_raw_category();
                        }
                    }
                    crossterm::event::KeyCode::BackTab => {
                        if self.state == AppState::Dashboard {
                            if self.active_tab == 0 {
                                self.active_tab = 3;
                            } else {
                                self.active_tab -= 1;
                            }
                            self.cursor_row = 0;
                            self.cursor_col = 0;
                            self.scroll_row_offset = 0;
                            self.scroll_col_offset = 0;
                            self.raw_selected_category = None;
                            self.raw_selected_student = None;
                            self.raw_category_index = 0;
                            self.raw_right_focused = false;
                            self.analytics_category_index = 0;
                            self.analytics_right_focused = false;
                            self.summary_category_index = 0;
                            self.summary_right_focused = false;
                            self.sync_raw_category();
                        }
                    }
                    crossterm::event::KeyCode::Char('[') => {
                        if self.active_tab == 1
                            && !self.editing
                            && !self.editing_weights
                            && !self.editing_boundaries
                            && self.raw_selected_student.is_none()
                            && self.raw_category_index > 0
                        {
                            self.raw_category_index -= 1;
                            self.sync_raw_category();
                            self.cursor_row = 0;
                            self.scroll_row_offset = 0;
                            let col_start = if self.raw_right_focused { 2 } else { 0 };
                            self.cursor_col = col_start;
                            self.scroll_col_offset = col_start;
                        } else if self.active_tab == 2
                            && !self.editing
                            && !self.editing_weights
                            && !self.editing_boundaries
                            && self.raw_selected_student.is_none()
                            && self.analytics_category_index > 0
                        {
                            self.analytics_category_index -= 1;
                            self.cursor_row = 0;
                            self.scroll_row_offset = 0;
                        } else if self.active_tab == 0
                            && !self.editing
                            && !self.editing_weights
                            && !self.editing_boundaries
                            && self.summary_category_index > 0
                        {
                            self.summary_category_index -= 1;
                            self.cursor_row = 0;
                            self.scroll_row_offset = 0;
                            self.cursor_col = 0;
                            self.scroll_col_offset = 0;
                        }
                    }
                    crossterm::event::KeyCode::Char(']') => {
                        if self.active_tab == 1
                            && !self.editing
                            && !self.editing_weights
                            && !self.editing_boundaries
                            && self.raw_selected_student.is_none()
                        {
                            let cat_count = self.get_categories().len();
                            if self.raw_category_index + 1 < cat_count {
                                self.raw_category_index += 1;
                                self.sync_raw_category();
                                self.cursor_row = 0;
                                self.scroll_row_offset = 0;
                                let col_start = if self.raw_right_focused { 2 } else { 0 };
                                self.cursor_col = col_start;
                                self.scroll_col_offset = col_start;
                            }
                        } else if self.active_tab == 2
                            && !self.editing
                            && !self.editing_weights
                            && !self.editing_boundaries
                            && self.raw_selected_student.is_none()
                        {
                            if self.analytics_category_index + 1 < ANALYTICS_CATEGORIES.len() {
                                self.analytics_category_index += 1;
                                self.cursor_row = 0;
                                self.scroll_row_offset = 0;
                            }
                        } else if self.active_tab == 0
                            && !self.editing
                            && !self.editing_weights
                            && !self.editing_boundaries
                        {
                            if self.summary_category_index + 1 < SUMMARY_CATEGORIES.len() {
                                self.summary_category_index += 1;
                                self.cursor_row = 0;
                                self.scroll_row_offset = 0;
                                self.cursor_col = 0;
                                self.scroll_col_offset = 0;
                            }
                        }
                    }
                    crossterm::event::KeyCode::Up | crossterm::event::KeyCode::Char('k') => {
                        self.move_up();
                    }
                    crossterm::event::KeyCode::Down | crossterm::event::KeyCode::Char('j') => {
                        self.move_down();
                    }
                    crossterm::event::KeyCode::Left | crossterm::event::KeyCode::Char('h') => {
                        self.move_left();
                    }
                    crossterm::event::KeyCode::Right | crossterm::event::KeyCode::Char('l') => {
                        self.move_right();
                    }
                    crossterm::event::KeyCode::Esc => {
                        if self.state == AppState::Dashboard {
                            if self.active_tab == 1 {
                                if self.raw_selected_student.is_some() {
                                    // L2 student popup → back to right panel
                                    self.raw_selected_student = None;
                                    self.cursor_col = 2;
                                    self.scroll_col_offset = 2;
                                } else if self.raw_right_focused {
                                    // Right panel → back to left panel
                                    self.raw_right_focused = false;
                                } else {
                                    // Left panel → CourseSelect
                                    self.request_leave(LeaveAction::CourseSelect);
                                }
                            } else if self.active_tab == 2 {
                                if self.raw_selected_student.is_some() {
                                    // Student popup → back to At-Risk table
                                    self.raw_selected_student = None;
                                    self.raw_selected_category = None;
                                } else if self.analytics_right_focused {
                                    // At-Risk table → back to category list
                                    self.analytics_right_focused = false;
                                } else {
                                    // Category list → CourseSelect
                                    self.request_leave(LeaveAction::CourseSelect);
                                }
                            } else if self.active_tab == 0 {
                                if self.summary_right_focused {
                                    // Right panel → back to left panel
                                    self.summary_right_focused = false;
                                } else {
                                    // Left panel → CourseSelect
                                    self.request_leave(LeaveAction::CourseSelect);
                                }
                            } else {
                                self.request_leave(LeaveAction::CourseSelect);
                            }
                        }
                    }
                    crossterm::event::KeyCode::Enter => {
                        if self.state == AppState::CourseSelect {
                            if self.course_index < self.courses.len() {
                                self.selected_course_path = self.courses[self.course_index].path.clone();
                                self.load_course_data();
                            }
                        } else if self.state == AppState::Dashboard {
                            if self.active_tab == 1 {
                                if self.raw_selected_student.is_some() {
                                    // L2 student popup → edit cell
                                    self.start_editing_cell_with(None);
                                } else if self.raw_right_focused {
                                    // Right panel: data cell → edit/picker directly; ID/Name/Total → no-op
                                    let sub_col_count = self.raw_selected_category.as_ref()
                                        .and_then(|cat| self.course_data.as_ref().and_then(|d| d.data_mapping.get(cat)))
                                        .map(|v| v.len())
                                        .unwrap_or(0);
                                    let on_data_cell = self.cursor_col >= 2 && self.cursor_col < sub_col_count + 2;
                                    if on_data_cell {
                                        self.start_editing_cell_with(None);
                                    }
                                } else {
                                    // Left panel → focus right panel
                                    self.raw_right_focused = true;
                                    self.cursor_col = 2;
                                    self.scroll_col_offset = 2;
                                }
                            } else if self.active_tab == 2 {
                                if self.raw_selected_student.is_some() {
                                    self.info_msg = Some("Switch to Raw Details to edit scores".to_string());
                                    self.info_msg_ticks = 0;
                                } else if self.analytics_right_focused
                                    && self.analytics_category_index == AT_RISK_CATEGORY_INDEX
                                {
                                    self.open_at_risk_student_popup();
                                } else if !self.analytics_right_focused
                                    && self.analytics_category_index == AT_RISK_CATEGORY_INDEX
                                {
                                    // Category list, on At-Risk Students → focus its table
                                    self.analytics_right_focused = true;
                                    self.cursor_row = 0;
                                    self.scroll_row_offset = 0;
                                }
                            } else if self.active_tab == 0 {
                                if !self.summary_right_focused {
                                    // Left panel → focus right panel
                                    self.summary_right_focused = true;
                                    self.cursor_col = 0;
                                    self.scroll_col_offset = 0;
                                }
                                // Right panel: read-only in both categories — no-op.
                            } else {
                                self.start_editing_cell_with(None);
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

    fn dashboard_app() -> App {
        let (tx, _rx) = tokio::sync::mpsc::channel(8);
        let mut app = App::new(tx);
        app.state = AppState::Dashboard;
        app
    }

    fn press(app: &mut App, code: KeyCode) {
        app.update(AppEvent::Key(KeyEvent::new(code, KeyModifiers::NONE)));
    }

    fn press_mod(app: &mut App, code: KeyCode, m: KeyModifiers) {
        app.update(AppEvent::Key(KeyEvent::new(code, m)));
    }

    fn type_str(app: &mut App, text: &str) {
        for c in text.chars() {
            press(app, KeyCode::Char(c));
        }
    }

    /// The mock course (30 students, hw1..hw3 out of 10, 15 attendance sessions, 2 Class Groups),
    /// opened in Raw Details on `category`, right panel focused, cursor on `column`, `row`.
    fn course_app(category: &str, column: &str, row: usize) -> App {
        let mut app = dashboard_app();
        app.course_data = Some(serde_json::from_str(include_str!("../tests/fixtures/course.json")).unwrap());
        app.selected_course_path = "/nonexistent/course".to_string();
        app.active_tab = 1;
        app.raw_category_index = app.get_categories().iter().position(|c| c == category).unwrap();
        app.sync_raw_category();
        app.raw_right_focused = true;
        let cols = app.course_data.as_ref().unwrap().data_mapping[category].clone();
        app.cursor_col = 2 + cols.iter().position(|c| c == column).unwrap();
        app.cursor_row = row;
        app
    }

    fn pending(app: &App, row: usize, col: &str) -> Option<String> {
        app.edits.get(&app.student_id_at(row), col).map(|p| p.value.clone())
    }

    #[test]
    fn typing_a_score_keeps_it_unsaved_and_moves_down() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "8.5");
        assert!(app.editing);
        press(&mut app, KeyCode::Enter);
        assert!(!app.editing && !app.loading, "nothing is written yet");
        assert_eq!(pending(&app, 0, "hw1").as_deref(), Some("8.5"));
        assert_eq!(app.cursor_row, 1);
        assert_eq!(app.edits.len(), 1);
    }

    #[test]
    fn typing_the_saved_value_back_drops_the_edit() {
        let mut app = course_app("homework", "hw1", 0); // loaded 10
        type_str(&mut app, "7");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Up);
        type_str(&mut app, "10");
        press(&mut app, KeyCode::Enter);
        assert!(app.edits.is_empty());
    }

    #[test]
    fn non_scores_are_refused_and_over_max_is_kept() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "1..5");
        press(&mut app, KeyCode::Enter);
        assert!(app.editing && app.error.is_some(), "stays in the editor");
        press(&mut app, KeyCode::Esc);
        assert!(!app.editing && app.edits.is_empty());

        type_str(&mut app, "3");
        press(&mut app, KeyCode::Home);
        press(&mut app, KeyCode::Char('-'));
        press(&mut app, KeyCode::Enter);
        assert!(app.editing && app.error.is_some(), "negative refused");
        press(&mut app, KeyCode::Esc);

        type_str(&mut app, "12");
        press(&mut app, KeyCode::Enter);
        assert_eq!(pending(&app, 0, "hw1").as_deref(), Some("12"));
        assert_eq!(app.edits.over_max(|c| app.max_of(c)), 1);
    }

    #[test]
    fn dash_marks_absent_and_backspace_blanks_in_place() {
        let mut app = course_app("homework", "hw2", 3);
        press(&mut app, KeyCode::Char('-'));
        assert_eq!(pending(&app, 3, "hw2").as_deref(), Some("ขส"));
        assert_eq!(app.cursor_row, 4);
        press(&mut app, KeyCode::Backspace);
        assert_eq!(pending(&app, 4, "hw2").as_deref(), Some(""));
        assert_eq!(app.cursor_row, 4);
    }

    #[test]
    fn attendance_letters_set_the_code_and_move_down() {
        let mut app = course_app("attendance", "13 Jan 2027", 0); // loaded P
        press(&mut app, KeyCode::Char('l'));
        assert_eq!(pending(&app, 0, "13 Jan 2027").as_deref(), Some("L"));
        assert_eq!((app.cursor_row, app.cursor_col), (1, 2), "l means Late here, not move right");
        press(&mut app, KeyCode::Char('c'));
        assert_eq!(pending(&app, 1, "13 Jan 2027").as_deref(), Some(""));
    }

    #[test]
    fn undo_reverses_a_cell_and_a_whole_fill() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Char('f'));
        type_str(&mut app, "0");
        press(&mut app, KeyCode::Enter);
        assert!(app.fill.is_none());
        assert_eq!(app.edits.len(), 30);
        press(&mut app, KeyCode::Char('u'));
        assert_eq!(app.edits.len(), 1);
        assert_eq!(pending(&app, 0, "hw1").as_deref(), Some("5"));
        press(&mut app, KeyCode::Char('u'));
        assert!(app.edits.is_empty());
    }

    #[test]
    fn space_shift_and_j_mark_rows_and_m_clears() {
        let mut app = course_app("homework", "hw1", 0);
        press(&mut app, KeyCode::Char(' '));
        press(&mut app, KeyCode::Char('J'));
        press_mod(&mut app, KeyCode::Down, KeyModifiers::SHIFT);
        assert_eq!(app.marks.len(), 3);
        assert_eq!(app.cursor_row, 2);
        press(&mut app, KeyCode::Char(' '));
        assert_eq!(app.marks.len(), 2, "space unmarks");
        press(&mut app, KeyCode::Char('m'));
        assert!(app.marks.is_empty());
    }

    #[test]
    fn fill_marked_rows_only() {
        let mut app = course_app("homework", "hw3", 5);
        press(&mut app, KeyCode::Char(' '));
        press(&mut app, KeyCode::Char('J'));
        press(&mut app, KeyCode::Char('J'));
        press(&mut app, KeyCode::Char('f'));
        assert_eq!(app.fill.as_ref().unwrap().target, FillTarget::Marked);
        type_str(&mut app, "7");
        press(&mut app, KeyCode::Enter);
        assert_eq!(app.edits.len(), 3);
        for r in 5..8 {
            assert_eq!(pending(&app, r, "hw3").as_deref(), Some("7"));
        }
        assert_eq!(app.marks.len(), 3, "a fill keeps the marks");
    }

    #[test]
    fn fill_typed_row_range() {
        let mut app = course_app("homework", "hw2", 0);
        press(&mut app, KeyCode::Char('f'));
        press(&mut app, KeyCode::Tab); // Value -> Target
        press(&mut app, KeyCode::Right); // All -> Marked
        press(&mut app, KeyCode::Right); // -> Rows
        press(&mut app, KeyCode::Tab); // -> Rows field
        type_str(&mut app, "1-3, 5");
        press(&mut app, KeyCode::Tab); // -> Only empty
        press(&mut app, KeyCode::Tab); // -> Value
        type_str(&mut app, "9.5");
        assert_eq!(app.fill_rows(), Ok(vec![0, 1, 2, 4]));
        press(&mut app, KeyCode::Enter);
        assert_eq!(app.edits.len(), 4);
        assert_eq!(pending(&app, 4, "hw2").as_deref(), Some("9.5"));
        assert!(pending(&app, 3, "hw2").is_none());
    }

    #[test]
    fn fill_by_class_group() {
        let mut app = course_app("homework", "hw1", 0);
        press(&mut app, KeyCode::Char('f'));
        press(&mut app, KeyCode::Tab);
        press(&mut app, KeyCode::Left); // All -> Group (wraps)
        assert_eq!(app.fill.as_ref().unwrap().target, FillTarget::Group);
        assert!(app.fill_rows().is_err(), "no group chosen yet");
        press(&mut app, KeyCode::Tab); // -> Groups
        press(&mut app, KeyCode::Right); // cursor on MOCK.SEC.2
        press(&mut app, KeyCode::Char(' '));
        press(&mut app, KeyCode::Tab);
        press(&mut app, KeyCode::Tab);
        type_str(&mut app, "0");
        press(&mut app, KeyCode::Enter);
        assert_eq!(app.edits.len(), 15);
        let data = app.course_data.as_ref().unwrap();
        for (r, rec) in data.raw_scores.iter().enumerate() {
            let in_group = rec["Class Group"] == "MOCK.SEC.2";
            assert_eq!(app.edits.get(&app.student_id_at(r), "hw1").is_some(), in_group, "row {r}");
        }
    }

    #[test]
    fn fill_only_empty_counts_unsaved_blanks() {
        let mut app = course_app("final", "final_exam", 0);
        let blanks = (0..30).filter(|&r| app.loaded_text(r, "final_exam").is_empty()).count();
        // make row 0 non-blank (unsaved), so it must be skipped
        type_str(&mut app, "20");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Char('f'));
        press(&mut app, KeyCode::BackTab); // Value -> Only empty
        press(&mut app, KeyCode::Char(' '));
        press(&mut app, KeyCode::Tab);
        type_str(&mut app, "0");
        let expected = blanks - usize::from(app.loaded_text(0, "final_exam").is_empty());
        assert_eq!(app.fill_rows().unwrap().len(), expected);
        press(&mut app, KeyCode::Enter);
        assert_eq!(pending(&app, 0, "final_exam").as_deref(), Some("20"));
    }

    #[test]
    fn empty_fill_value_cancels_and_bad_value_is_refused() {
        let mut app = course_app("homework", "hw1", 0);
        press(&mut app, KeyCode::Char('f'));
        press(&mut app, KeyCode::Enter);
        assert!(app.fill.is_none() && app.edits.is_empty());
        press(&mut app, KeyCode::Char('f'));
        type_str(&mut app, "x");
        press(&mut app, KeyCode::Enter);
        assert!(app.fill.is_some() && app.error.is_some() && app.edits.is_empty());
    }

    #[test]
    fn quit_asks_when_edits_are_unsaved() {
        let mut app = course_app("homework", "hw1", 0);
        press(&mut app, KeyCode::Char('q'));
        assert!(app.quit, "nothing unsaved: quits at once");

        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Char('q'));
        assert!(!app.quit);
        assert_eq!(app.confirm_leave, Some(LeaveAction::Quit));
        press(&mut app, KeyCode::Esc);
        assert!(app.confirm_leave.is_none() && !app.quit && app.edits.len() == 1);
        press_mod(&mut app, KeyCode::Char('c'), KeyModifiers::CONTROL);
        assert_eq!(app.confirm_leave, Some(LeaveAction::Quit));
        press(&mut app, KeyCode::Char('d'));
        assert!(app.quit);
    }

    #[tokio::test]
    async fn esc_to_course_list_asks_then_discards() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Esc); // table -> categories
        press(&mut app, KeyCode::Esc); // categories -> course list?
        assert_eq!(app.confirm_leave, Some(LeaveAction::CourseSelect));
        assert_eq!(app.state, AppState::Dashboard);
        press(&mut app, KeyCode::Char('D'));
        assert_eq!(app.state, AppState::CourseSelect);
        assert!(app.edits.is_empty());
    }

    #[test]
    fn analytics_student_popup_stays_read_only() {
        let mut app = course_app("homework", "hw1", 0);
        app.active_tab = 2;
        app.raw_selected_student = Some(0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Char('-'));
        assert!(!app.editing && app.edits.is_empty());
    }

    #[test]
    fn student_popup_edit_moves_right() {
        let mut app = course_app("homework", "hw1", 2);
        app.raw_selected_student = Some(2);
        type_str(&mut app, "4");
        press(&mut app, KeyCode::Enter);
        assert_eq!(pending(&app, 2, "hw1").as_deref(), Some("4"));
        assert_eq!(app.cursor_col, 3, "next item for the same student");
    }

    #[tokio::test]
    async fn save_sends_everything_and_keeps_conflicts() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Enter);
        type_str(&mut app, "6");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Char(' '));
        press_mod(&mut app, KeyCode::Char('s'), KeyModifiers::CONTROL);
        assert!(app.loading);
        assert_eq!(app.saving.len(), 2);

        let sid1 = app.student_id_at(1);
        app.update(AppEvent::EditsSaved(Ok(SaveReport {
            status: "success".into(),
            saved: 1,
            files: vec![],
            conflicts: vec![crate::types::Conflict {
                student_id: sid1.clone(), column: "hw1".into(), reason: "changed".into(), disk_value: Some("3".into()),
            }],
            message: "Saved 1 cell (1 file).".into(), course_data: None,
        })));
        assert_eq!(app.edits.len(), 1, "the conflict stays unsaved");
        assert_eq!(app.edits.get(&sid1, "hw1").unwrap().original, "3");
        assert!(app.marks.is_empty(), "a save clears marks");
        assert!(app.error_after_reload.as_deref().unwrap().contains(&sid1));
    }

    fn fixture_with(row: usize, col: &str, value: serde_json::Value) -> CourseData {
        let mut data: CourseData = serde_json::from_str(include_str!("../tests/fixtures/course.json")).unwrap();
        data.raw_scores[row].insert(col.to_string(), value);
        data
    }

    #[tokio::test]
    async fn save_reply_with_course_data_swaps_in_without_a_second_load() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Enter);
        press_mod(&mut app, KeyCode::Char('s'), KeyModifiers::CONTROL);
        assert!(app.loading);
        assert_eq!(pending(&app, 0, "hw1").as_deref(), Some("5"), "still shown while saving");

        app.update(AppEvent::EditsSaved(Ok(SaveReport {
            status: "success".into(), saved: 1, files: vec![], conflicts: vec![],
            message: "Saved 1 cell (1 file).".into(),
            course_data: Some(Box::new(fixture_with(0, "hw1", serde_json::json!(5.0)))),
        })));
        assert!(!app.loading, "no second python call");
        assert!(app.edits.is_empty());
        assert_eq!(app.cell_value(0, "hw1"), "5", "new value at once: no flash of the old one");
        assert_eq!((app.active_tab, app.cursor_row, app.raw_right_focused), (1, 1, true), "navigation kept");
    }

    #[tokio::test]
    async fn save_and_quit_from_the_prompt() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Char('q'));
        press(&mut app, KeyCode::Char('s'));
        assert!(app.loading && !app.quit);
        app.update(AppEvent::EditsSaved(Ok(SaveReport {
            status: "success".into(), saved: 1, files: vec![], conflicts: vec![], message: "Saved 1 cell (1 file).".into(), course_data: None,
        })));
        assert!(app.quit && app.edits.is_empty());
    }

    #[tokio::test]
    async fn failed_save_keeps_everything_and_does_not_quit() {
        let mut app = course_app("homework", "hw1", 0);
        type_str(&mut app, "5");
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Char('q'));
        press(&mut app, KeyCode::Char('s'));
        app.update(AppEvent::EditsSaved(Err("disk full".into())));
        assert!(!app.quit && app.edits.len() == 1 && app.error.is_some());
    }

    #[test]
    fn s_toggles_left_panel_and_survives_tab_switches() {
        let mut app = dashboard_app();
        assert!(app.show_left_panel);
        press(&mut app, KeyCode::Char('s'));
        assert!(!app.show_left_panel);
        press(&mut app, KeyCode::Tab);
        press(&mut app, KeyCode::Tab);
        press(&mut app, KeyCode::BackTab);
        assert!(!app.show_left_panel);
        press(&mut app, KeyCode::Char('S'));
        assert!(app.show_left_panel);
    }

    #[test]
    fn s_is_ignored_in_student_popup_and_course_select() {
        let mut app = dashboard_app();
        app.raw_selected_student = Some(0);
        press(&mut app, KeyCode::Char('s'));
        assert!(app.show_left_panel);

        let mut app = dashboard_app();
        app.state = AppState::CourseSelect;
        press(&mut app, KeyCode::Char('s'));
        assert!(app.show_left_panel);
    }

    #[tokio::test]
    async fn c_off_an_attendance_cell_does_nothing() {
        let mut app = dashboard_app();
        app.selected_course_path = "/nonexistent/course".to_string();
        press(&mut app, KeyCode::Char('c'));
        assert!(!app.loading, "c must no longer reload the course");
    }

    #[test]
    fn hidden_panel_gives_raw_table_the_full_width() {
        let mut app = dashboard_app();
        app.width = 120;
        assert_eq!(app.raw_table_inner_width(), 85);
        app.show_left_panel = false;
        assert_eq!(app.raw_table_inner_width(), 118);
        app.raw_selected_student = Some(0);
        app.show_left_panel = true;
        assert_eq!(app.raw_table_inner_width(), 118);
    }
}
