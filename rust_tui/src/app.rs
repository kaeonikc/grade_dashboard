use crate::types::*;
use tokio::sync::mpsc::Sender;
use std::collections::HashMap;
// theme

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
    ScoreUpdated(Result<(), String>),
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
    pub active_tab: usize, // 0: Summary, 1: Raw Details, 2: Distribution, 3: Roundup
    pub use_weighted: bool,
    
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
            use_weighted: true,
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
        self.loading_msg = format!("Loading course data (weighted: {})...", self.use_weighted);
        self.error = None;
        let path = self.selected_course_path.clone();
        let use_weighted = self.use_weighted;
        let tx = self.tx.clone();
        tokio::spawn(async move {
            let res = crate::bridge::get_course_data(&path, use_weighted).await;
            let event = AppEvent::CourseDataLoaded(res);
            let _ = tx.send(event).await;
        });
    }

    pub fn save_edited_score(&mut self) {
        if let Some(ref ta) = self.edit_textarea {
            let val = ta.lines()[0].trim().to_string();
            if val == self.editing_original_value {
                self.editing = false;
                self.edit_textarea = None;
                return;
            }
            self.loading = true;
            self.loading_msg = format!("Saving score to CSV: Student {}'s {} = {}...", self.editing_student_id, self.editing_column, val);
            self.editing = false;
            self.edit_textarea = None;

            let path = self.selected_course_path.clone();
            let student_id = self.editing_student_id.clone();
            let col = self.editing_column.clone();
            let tx = self.tx.clone();

            tokio::spawn(async move {
                let res = crate::bridge::update_score(&path, &student_id, &col, &val).await;
                let event = AppEvent::ScoreUpdated(res.map(|_| ()));
                let _ = tx.send(event).await;
            });
        }
    }

    pub fn save_attendance_score(&mut self) {
        let options = ["P", "L", "EA", "A"];
        let val = options[self.attendance_index].to_string();

        if val == self.editing_original_value {
            return;
        }

        self.loading = true;
        self.loading_msg = format!("Saving attendance for {}: {} = {}...", self.editing_student_id, self.editing_column, val);

        let path = self.selected_course_path.clone();
        let student_id = self.editing_student_id.clone();
        let col = self.editing_column.clone();
        let tx = self.tx.clone();

        tokio::spawn(async move {
            let res = crate::bridge::update_score(&path, &student_id, &col, &val).await;
            let event = AppEvent::ScoreUpdated(res.map(|_| ()));
            let _ = tx.send(event).await;
        });
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
        let use_weighted = self.use_weighted;
        let tx = self.tx.clone();
        tokio::spawn(async move {
            let res = crate::bridge::export_reports(&path, use_weighted).await;
            let event = AppEvent::ReportsExported(res.map(|r| r.message));
            let _ = tx.send(event).await;
        });
    }

    pub fn start_editing_cell(&mut self) {
        if self.editing || self.loading {
            return;
        }
        let data = match &self.course_data {
            Some(d) => d,
            None => return,
        };

        if self.active_tab == 0 {
            // Summary columns: Student ID (0), Name (1), ... (read-only)
            // Go TUI does not support editing derived summary columns (which are aggregates)
            // But we can let them edit if it falls under raw score columns.
            // Let's only allow editing in raw columns tab (tabRawDetails) to keep logic clean and robust.
            self.info_msg = Some("To edit scores, please switch to the 'Raw Details' tab".to_string());
            self.info_msg_ticks = 0;
            return;
        }

        if self.active_tab == 1 {
            // Raw Details Tab — only editable in sub-column view
            if self.raw_selected_category.is_none() {
                return;
            }
            if self.cursor_col < 2 {
                return;
            }
            if self.cursor_row >= data.raw_scores.len() {
                return;
            }

            let cat = self.raw_selected_category.as_deref().unwrap().to_string();
            let (col_name, raw_val) = {
                let sub_cols = data.data_mapping.get(&cat).cloned().unwrap_or_default();
                let sub_idx = self.cursor_col - 2;
                if sub_idx >= sub_cols.len() { return; }
                let cn = sub_cols[sub_idx].clone();
                let student_row = &data.raw_scores[self.cursor_row];
                let rv = match student_row.get(&cn) {
                    Some(v) => {
                        if v.is_f64() {
                            format!("{}", v.as_f64().unwrap())
                        } else if v.is_i64() {
                            format!("{}", v.as_i64().unwrap())
                        } else {
                            v.as_str().unwrap_or("").to_string()
                        }
                    }
                    None => "".to_string(),
                };
                (cn, rv)
            };

            let student_row = &data.raw_scores[self.cursor_row];
            let student_id = match student_row.get("Student ID") {
                Some(v) => v.as_str().unwrap_or("").to_string(),
                None => return,
            };

            self.editing_student_id = student_id;
            self.editing_column = col_name.clone();
            self.editing_original_value = raw_val.clone();

            let is_attendance = cat.to_lowercase().contains("attendance");
            if is_attendance {
                let options = ["P", "L", "EA", "A"];
                let current_idx = options.iter().position(|&o| o == raw_val.as_str()).unwrap_or(0);
                self.attendance_index = current_idx;
                self.editing_attendance = true;
            } else {
                self.editing = true;
                let mut ta = tui_textarea::TextArea::new(vec![raw_val]);
                ta.move_cursor(tui_textarea::CursorMove::End);
                ta.set_cursor_line_style(ratatui::style::Style::default().bg(self.theme.highlight));
                ta.set_style(
                    ratatui::style::Style::default()
                        .fg(self.theme.info)
                        .bg(self.theme.panel_bg)
                );
                ta.set_block(
                    ratatui::widgets::Block::default()
                        .borders(ratatui::widgets::Borders::ALL)
                        .border_style(ratatui::style::Style::default().fg(self.theme.border_focus))
                        .title(format!(" Edit: {} for ID {} ", col_name, self.editing_student_id))
                );
                self.edit_textarea = Some(ta);
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
                if self.active_tab == 1 && !self.raw_right_focused {
                    if self.raw_category_index > 0 {
                        self.raw_category_index -= 1;
                        self.sync_raw_category();
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
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
                if self.active_tab == 1 && !self.raw_right_focused {
                    let cat_count = self.get_categories().len();
                    if self.raw_category_index + 1 < cat_count {
                        self.raw_category_index += 1;
                        self.sync_raw_category();
                        self.cursor_row = 0;
                        self.scroll_row_offset = 0;
                    }
                    return;
                }
                let max_rows = match &self.course_data {
                    Some(data) => {
                        if self.active_tab == 0 {
                            data.student_grades.len()
                        } else if self.active_tab == 1 {
                            data.raw_scores.len()
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

    pub fn move_left(&mut self) {
        if self.state == AppState::Dashboard && !self.editing && !self.editing_weights && !self.editing_boundaries {
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
            if self.cursor_col > 0 {
                self.cursor_col -= 1;
                self.adjust_scroll_col();
            }
        }
    }

    pub fn move_right(&mut self) {
        if self.state == AppState::Dashboard && !self.editing && !self.editing_weights && !self.editing_boundaries {
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
            let max_cols = match &self.course_data {
                Some(data) => {
                    if self.active_tab == 0 {
                        data.summary_columns.len()
                    } else {
                        0
                    }
                }
                None => 0,
            };
            if self.cursor_col + 1 < max_cols {
                self.cursor_col += 1;
                self.adjust_scroll_col();
            }
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

            let is_attendance = self.raw_selected_category.as_deref()
                .map(|c| c.to_lowercase().contains("attendance") || c.to_lowercase().contains("att"))
                .unwrap_or(false);
            // popup = full-width; category view = terminal minus left panel (33) + 2 borders
            let right_inner = if self.raw_selected_student.is_some() {
                (self.width as usize).saturating_sub(2)
            } else {
                (self.width as usize).saturating_sub(35)
            };
            // Frozen cols: StudentID (12) + Name (≈32) + 3 spacing = 47
            let scrollable_width = right_inner.saturating_sub(47);
            // col width (attendance uses column_spacing=0, so no extra spacing)
            let col_width: usize = if is_attendance {
                3 + format!("{}", sub_col_count).len() // matches sub_col_width = max_digits + 3
            } else { 13 };
            let visible_scrollable_cols = (scrollable_width / col_width).max(1);

            if self.cursor_col < self.scroll_col_offset {
                self.scroll_col_offset = self.cursor_col;
            } else if self.cursor_col >= self.scroll_col_offset + visible_scrollable_cols {
                self.scroll_col_offset = self.cursor_col - visible_scrollable_cols + 1;
            }
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
                    Ok(data) => {
                        self.course_data = Some(data);
                        self.state = AppState::Dashboard;
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
                            self.sync_raw_category();
                        }
                    }
                    Err(e) => {
                        self.error = Some(e);
                    }
                }
            }
            AppEvent::ScoreUpdated(res) => {
                self.loading = false;
                match res {
                    Ok(_) => {
                        self.info_msg = Some("Score successfully saved and database updated!".to_string());
                        self.info_msg_ticks = 0;
                        self.preserve_nav_on_reload = true;
                        self.load_course_data();
                    }
                    Err(e) => {
                        self.error = Some(format!("Failed to update score: {}", e));
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
                        self.info_msg = Some(msg);
                        self.info_msg_ticks = 0;
                    }
                    Err(e) => {
                        self.error = Some(format!("Export failed: {}", e));
                    }
                }
            }
            AppEvent::Key(key) => {
                // Modal or text editing capture
                if self.editing {
                    if let Some(ref mut ta) = self.edit_textarea {
                        match key.code {
                            crossterm::event::KeyCode::Enter => {
                                self.save_edited_score();
                            }
                            crossterm::event::KeyCode::Esc => {
                                self.editing = false;
                                self.edit_textarea = None;
                            }
                            _ => {
                                ta.input(key);
                            }
                        }
                    }
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
                            if self.attendance_index < 3 {
                                self.attendance_index += 1;
                            }
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

                // Standard navigation
                match key.code {
                    crossterm::event::KeyCode::Char('q') => {
                        // Exit handled in main loop
                    }
                    crossterm::event::KeyCode::Char('c') | crossterm::event::KeyCode::Char('C') => {
                        if self.state == AppState::Dashboard {
                            self.use_weighted = !self.use_weighted;
                            self.load_course_data();
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
                            self.sync_raw_category();
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
                                    self.state = AppState::CourseSelect;
                                    self.course_data = None;
                                    self.load_courses();
                                }
                            } else {
                                self.state = AppState::CourseSelect;
                                self.course_data = None;
                                self.load_courses();
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
                                    self.start_editing_cell();
                                } else if self.raw_right_focused {
                                    // Right panel: data cell → edit/picker directly; ID/Name/Total → no-op
                                    let sub_col_count = self.raw_selected_category.as_ref()
                                        .and_then(|cat| self.course_data.as_ref().and_then(|d| d.data_mapping.get(cat)))
                                        .map(|v| v.len())
                                        .unwrap_or(0);
                                    let on_data_cell = self.cursor_col >= 2 && self.cursor_col < sub_col_count + 2;
                                    if on_data_cell {
                                        self.start_editing_cell();
                                    }
                                } else {
                                    // Left panel → focus right panel
                                    self.raw_right_focused = true;
                                    self.cursor_col = 2;
                                    self.scroll_col_offset = 2;
                                }
                            } else {
                                self.start_editing_cell();
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }
}
