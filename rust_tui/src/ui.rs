use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style, Stylize},
    text::{Line, Span},
    widgets::{Bar, BarChart, Block, BorderType, Borders, Cell, Clear, List, ListItem, Paragraph, Row, Table, TableState, Wrap},
    Frame,
};
use crate::app::{App, AppState, ANALYTICS_CATEGORIES, SUMMARY_CATEGORIES};
use unicode_width::UnicodeWidthStr;

pub fn draw(f: &mut Frame, app: &mut App) {
    let theme = app.theme;
    
    // Clear whole screen with theme background
    let bg_block = Block::default().style(Style::default().bg(theme.bg));
    f.render_widget(bg_block, f.area());

    // The legend wraps onto as many rows as the terminal width needs
    let (footer_line, footer_kind) = footer_line(app);
    let footer_rows = wrap_legend(footer_line.spans, f.area().width);

    // Master Layout: Header + Content + Footer (Legend)
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Header
            Constraint::Min(5),    // Content Workspace
            Constraint::Length(footer_rows.len().max(1) as u16), // Footer (Legend)
        ])
        .split(f.area());

    // 1. Draw Header
    draw_header(f, app, chunks[0]);

    // 2. Draw Content Workspace
    match app.state {
        AppState::CourseSelect => draw_course_select(f, app, chunks[1]),
        AppState::Dashboard => draw_dashboard(f, app, chunks[1]),
    }

    // 3. Draw Footer (Legend)
    draw_footer(f, app, chunks[2], footer_rows, footer_kind);

    // 4. Overlays
    // A save shows in the footer and leaves the table in view; other loads use the overlay
    if app.loading && app.saving.is_empty() {
        draw_loading_overlay(f, app);
    } else if app.confirm_leave.is_some() {
        draw_confirm_leave(f, app);
    } else if app.editing_attendance {
        draw_attendance_picker(f, app);
    } else if app.fill.is_some() {
        draw_fill_dialog(f, app);
    } else if app.editing_weights || app.editing_boundaries {
        draw_settings_overlay(f, app);
    }
}

fn draw_header(f: &mut Frame, app: &App, area: Rect) {
    let theme = app.theme;
    
    let (header_text, title_style) = match app.state {
        AppState::CourseSelect => (
            " ⚡  UNIVERSITY GRADE DASHBOARD  ⚡ ".to_string(),
            Style::default().fg(theme.title).add_modifier(Modifier::BOLD)
        ),
        AppState::Dashboard => {
            if let Some(ref data) = app.course_data {
                (
                    format!(
                        " ⚡  {}  |  Term: {}{} ",
                        data.course_name.to_uppercase(),
                        data.term.to_uppercase(),
                        if data.absences.is_empty() {
                            String::new()
                        } else {
                            format!("  |  {}: {}", ABSENT, data.absences.len())
                        }
                    ),
                    Style::default().fg(theme.info).add_modifier(Modifier::BOLD)
                )
            } else {
                (
                    " ⚡  LOADING COURSE DATABASE...  ⚡ ".to_string(),
                    Style::default().fg(theme.warning).add_modifier(Modifier::BOLD)
                )
            }
        }
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.title))
        .title(" ⚡ Grade Dashboard TUI (Rust) ⚡ ")
        .title_style(Style::default().fg(theme.key_accent).bold())
        .title_alignment(Alignment::Center);

    let mut header_line = vec![Span::styled(header_text, title_style)];
    if app.state == AppState::Dashboard && !app.edits.is_empty() {
        header_line.push(Span::styled(
            format!(" ● {} unsaved ", app.edits.len()),
            Style::default().fg(theme.bg).bg(theme.warning).add_modifier(Modifier::BOLD),
        ));
    }
    let paragraph = Paragraph::new(Line::from(header_line))
        .block(block)
        .alignment(Alignment::Center)
        .style(title_style);

    f.render_widget(paragraph, area);
}

fn draw_course_select(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(45), Constraint::Percentage(55)])
        .split(area);

    // Left Panel: Course List
    let list_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(Style::default().fg(theme.border))
        .title(" 📂 Select Course Directory ")
        .title_style(Style::default().fg(theme.info).bold());

    let items: Vec<ListItem> = app
        .courses
        .iter()
        .enumerate()
        .map(|(i, c)| {
            let style = if i == app.course_index {
                Style::default()
                    .fg(theme.active_tab)
                    .bg(theme.highlight)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme.fg)
            };
            ListItem::new(format!("  ⚡  {}", c.name)).style(style)
        })
        .collect();

    let list = List::new(items).block(list_block);
    f.render_widget(list, chunks[0]);

    // Right Panel: Welcome Info
    let info_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" ℹ️ Instructions ")
        .title_style(Style::default().fg(theme.key_accent).bold());

    use ratatui::text::{Line, Span};
    let mut info_lines = vec![
        Line::from(""),
        Line::from(Span::styled(" Welcome to the Grade Dashboard TUI (Rust/Ratatui)!", Style::default().fg(theme.title).bold())),
        Line::from(""),
        Line::from(Span::styled(" Keyboard Shortcuts for Course Selection:", Style::default().fg(theme.key_accent).bold())),
        Line::from(vec![
            Span::styled("   ▲ / ▼ or k / j ", Style::default().fg(theme.info).bold()),
            Span::raw(" : Navigate course list"),
        ]),
        Line::from(vec![
            Span::styled("   Enter          ", Style::default().fg(theme.success).bold()),
            Span::raw(" : Load selected course"),
        ]),
        Line::from(vec![
            Span::styled("   q              ", Style::default().fg(theme.grade_f).bold()),
            Span::raw(" : Exit program"),
        ]),
        Line::from(""),
        Line::from(Span::styled(" Description:", Style::default().fg(theme.key_accent).bold())),
        Line::from(Span::raw("   Calculates student weighted coursework percentages, applies pro-student")),
        Line::from(Span::raw("   ceil rounding, manages config boundaries, and updates CSV databases.")),
        Line::from(""),
    ];

    if let Some(ref err) = app.error {
        info_lines.push(Line::from(Span::styled(format!(" ❌ Error: {}", err), Style::default().fg(theme.grade_f).bold())));
    } else {
        info_lines.push(Line::from(Span::styled(" Status: Ready to load course database", Style::default().fg(theme.success).bold())));
    }

    let paragraph = Paragraph::new(info_lines)
        .block(info_block)
        .wrap(Wrap { trim: false });
    f.render_widget(paragraph, chunks[1]);
}

fn draw_dashboard(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    
    // Divide workspace vertically to hold Tabs + Main Content + Warning Bar
    let warning_height = if let Some(ref data) = app.course_data {
        if !data.warnings.is_empty() { 3 } else { 0 }
    } else {
        0
    };

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Tab navigation bar
            Constraint::Min(5),    // Active tab panel workspace
            Constraint::Length(warning_height), // Warnings drawer
        ])
        .split(area);

    // Draw Tab Navigation Bar — 4 individual bordered boxes
    let tab_labels = [" [1] Summary ", " [2] Raw Details ", " [3] Analytics ", " [4] Roundup "];
    let tab_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(25),
            Constraint::Percentage(25),
            Constraint::Percentage(25),
            Constraint::Percentage(25),
        ])
        .split(chunks[0]);

    for (i, (label, &tab_area)) in tab_labels.iter().zip(tab_chunks.iter()).enumerate() {
        let is_active = i == app.active_tab;
        let border_color = if is_active { theme.success } else { theme.border };
        let text_style = if is_active {
            Style::default().fg(theme.success).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(theme.inactive_tab)
        };
        let block = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(border_color));
        let para = Paragraph::new(*label)
            .block(block)
            .style(text_style)
            .alignment(Alignment::Center);
        f.render_widget(para, tab_area);
    }

    // Draw Main Content Pane depending on tab selection
    match app.active_tab {
        0 => draw_summary_tab_container(f, app, chunks[1]),
        1 => draw_raw_details_tab(f, app, chunks[1]),
        2 => draw_analytics_tab(f, app, chunks[1]),
        3 => draw_roundup_tab(f, app, chunks[1]),
        _ => {}
    }

    // Draw warnings drawer if warnings exist
    if warning_height > 0 {
        if let Some(ref data) = app.course_data {
            let warn_text = data.warnings.join(" | ");
            let warn_p = Paragraph::new(format!(" ⚠️ WARNING: {}", warn_text))
                .style(Style::default().fg(theme.warning).add_modifier(Modifier::BOLD))
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .border_type(BorderType::Rounded)
                        .border_style(Style::default().fg(theme.warning))
                        .title(" Data Inconsistency Warnings ")
                )
                .wrap(Wrap { trim: true });
            f.render_widget(warn_p, chunks[2]);
        }
    }
}

fn draw_summary_tab(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    // area.height - 2 borders - 3 header (height=2 + bottom_margin=1)
    app.table_visible_rows = (area.height as usize).saturating_sub(5).max(1);

    let num_col_width = format!("{}", data.student_grades.len()).len().max(1) as u16 + 1;

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

    // Prepare table headers
    let sep_cell_header = || Cell::from("│\n").style(Style::default().fg(theme.border).add_modifier(Modifier::DIM));
    let num_header = Cell::from("#\n")
        .style(Style::default().fg(theme.inactive_tab).add_modifier(Modifier::BOLD));
    let mut header_cells: Vec<Cell> = vec![num_header];
    for h in &data.summary_columns {
        let cell = if h.ends_with("_pct") {
            let cat = h.trim_end_matches("_pct");
            let cat_lower = cat.to_lowercase();
            let weight_pts = data.weights.get(cat).copied().unwrap_or(0.0) * 100.0;
            let label = format!("{}\n({:.0} pts)", cat, weight_pts);
            let color = if cat_lower.contains("homework") || cat_lower.contains("hw") || cat_lower.contains("project") {
                theme.info
            } else if cat_lower.contains("attendance") || cat_lower.contains("att") {
                theme.success
            } else if cat_lower.contains("midterm") || cat_lower.contains("mid") {
                theme.warning
            } else if cat_lower.contains("final") {
                Color::Indexed(33)
            } else {
                theme.purple
            };
            Cell::from(label).style(Style::default().fg(color).add_modifier(Modifier::BOLD))
        } else if h == "Final Score" {
            Cell::from("Final Score\n(100 pts)")
                .style(Style::default().fg(theme.title).add_modifier(Modifier::BOLD))
        } else if h == "Grade" {
            Cell::from("Grade\n")
                .style(Style::default().fg(theme.success).add_modifier(Modifier::BOLD))
        } else if h == "Student ID" {
            Cell::from("ID\n")
                .style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        } else {
            Cell::from(format!("{}\n", h))
                .style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        };
        header_cells.push(cell);
        if h == "Name" {
            header_cells.push(sep_cell_header());
        }
    }

    let header = Row::new(header_cells).height(2).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    // Prepare rows
    let sep_cell_data = || Cell::from("│").style(Style::default().fg(theme.border).add_modifier(Modifier::DIM));
    let rows: Vec<Row> = data
        .student_grades
        .iter()
        .enumerate()
        .map(|(r_idx, record)| {
            let num_cell = Cell::from(format!("{}", r_idx + 1))
                .style(Style::default().fg(theme.inactive_tab));
            let mut cells: Vec<Cell> = vec![num_cell];
            for col_name in &data.summary_columns {
                let cell_val = record.get(col_name.as_str()).unwrap_or(&serde_json::Value::Null);
                let text = match cell_val {
                    serde_json::Value::Null => "".to_string(),
                    serde_json::Value::Number(n) => format!("{:.1}", n.as_f64().unwrap_or(0.0)),
                    serde_json::Value::String(s) => {
                        if col_name == "Name" {
                            format_thai_name(s, 18)
                        } else {
                            s.clone()
                        }
                    }
                    _ => cell_val.to_string(),
                };

                let mut cell_style = Style::default().fg(theme.fg);

                if col_name == "Student ID" {
                    cell_style = cell_style.fg(theme.info);
                } else if col_name == "Final Score" {
                    cell_style = cell_style.fg(theme.key_accent).bold();
                } else if col_name == "Grade" {
                    cell_style = cell_style.fg(grade_color_for(&text, &theme)).add_modifier(Modifier::BOLD);
                }

                cells.push(Cell::from(text).style(cell_style));
                if col_name == "Name" {
                    cells.push(sep_cell_data());
                }
            }

            let mut row_style = Style::default();
            if r_idx == app.cursor_row {
                row_style = row_style.bg(theme.highlight);
            } else if r_idx % 2 == 1 {
                row_style = row_style.bg(theme.alt_row);
            }

            Row::new(cells).style(row_style).height(1)
        })
        .collect();

    // Thai combining vowels (ั, ์, ี …) are 0-width in unicode-width but many terminals
    // advance the cursor by 1 for each. chars().count() treats every codepoint as 1 col,
    // which matches real terminal rendering for Thai text.
    let name_col_width = data
        .student_grades
        .iter()
        .filter_map(|r| {
            r.get("Name")
                .and_then(|v| v.as_str())
                .map(|s| format_thai_name(s, 18).chars().count())
        })
        .max()
        .unwrap_or(20)
        .max(8) as u16;

    // Size score columns dynamically so the total table width == inner area width.
    // This eliminates layout overflow, guaranteeing Name gets its full allocation.
    let inner_width = area.width.saturating_sub(2) as usize; // subtract block borders
    let n_cols = data.summary_columns.len();
    let n_other_cols = n_cols.saturating_sub(3); // all cols except StudentID, Name, Grade
    let spacings = n_cols + 1;                    // column_spacing(1) × (n_cols+2 total cols − 1); +1 for separator
    let fixed = num_col_width as usize + 9usize + name_col_width as usize + 7 + 1; // +1 for separator col
    let score_col_width = if n_other_cols > 0 && inner_width > fixed + spacings {
        ((inner_width - fixed - spacings) / n_other_cols).max(6) as u16
    } else {
        6u16
    };

    let mut widths = vec![Constraint::Length(num_col_width)];
    for col_name in &data.summary_columns {
        if col_name == "Student ID" {
            widths.push(Constraint::Length(9));
        } else if col_name == "Name" {
            widths.push(Constraint::Length(name_col_width));
            widths.push(Constraint::Length(1)); // separator
        } else if col_name == "Grade" {
            widths.push(Constraint::Length(7));
        } else {
            widths.push(Constraint::Length(score_col_width));
        }
    }

    let table = Table::new(rows, widths)
        .header(header)
        .block(block)
        .column_spacing(1);

    let mut table_state = TableState::default().with_offset(app.scroll_row_offset);
    f.render_stateful_widget(table, area, &mut table_state);
}

/// Splits a tab area into (left panel, main view). The left panel is None when hidden with [s].
fn split_left(app: &App, area: Rect, left: Constraint) -> (Option<Rect>, Rect) {
    if !app.show_left_panel {
        return (None, area);
    }
    let h_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([left, Constraint::Min(40)])
        .split(area);
    (Some(h_chunks[0]), h_chunks[1])
}

fn draw_summary_tab_container(f: &mut Frame, app: &mut App, area: Rect) {
    let (left, main) = split_left(app, area, Constraint::Length(33));

    if let Some(left) = left {
        let left_chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
            .split(left);

        draw_summary_left_panel(f, app, left_chunks[0]);
        draw_summary_status_panel(f, app, left_chunks[1]);
    }

    if app.summary_category_index == 0 {
        draw_summary_tab(f, app, main);
    } else {
        draw_submission_table(f, app, main);
    }
}

fn draw_summary_left_panel(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let border_color = if !app.summary_right_focused { theme.border_focus } else { theme.border };
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .title(" Categories ")
        .title_style(Style::default().fg(theme.info).bold());

    let idx = app.summary_category_index;
    let right_focused = app.summary_right_focused;

    let items: Vec<ListItem> = SUMMARY_CATEGORIES
        .iter()
        .enumerate()
        .map(|(i, name)| {
            let is_highlighted = i == idx;
            let style = if is_highlighted && !right_focused {
                Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD)
            } else if is_highlighted {
                Style::default().fg(theme.active_tab).add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme.fg)
            };
            ListItem::new(Line::from(Span::styled(format!("  {}", name), style)))
        })
        .collect();

    let list = List::new(items).block(block);
    f.render_widget(list, area);
}

fn draw_summary_status_panel(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" Student ")
        .title_style(Style::default().fg(theme.info).bold());

    if !app.summary_right_focused {
        let placeholder = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled(
                "  ─ no selection ─",
                Style::default().fg(theme.inactive_tab),
            )),
            Line::from(""),
            Line::from(Span::styled(
                "  → to focus table",
                Style::default().fg(theme.inactive_tab),
            )),
        ])
        .block(block);
        f.render_widget(placeholder, area);
        return;
    }

    let data = match &app.course_data {
        Some(d) => d,
        None => { f.render_widget(block, area); return; }
    };

    if app.cursor_row >= data.student_grades.len() {
        f.render_widget(block, area);
        return;
    }

    let record = &data.student_grades[app.cursor_row];
    let name_raw = record.get("Name").and_then(|v| v.as_str()).unwrap_or("—");
    let sid = record.get("Student ID").and_then(|v| v.as_str()).unwrap_or("—");
    let name_display: String = name_raw.chars().take(27).collect();

    let fmt_int = |key: &str| -> String {
        record.get(key)
            .and_then(|v| v.as_f64())
            .map(|n| format!("{}", n as i64))
            .unwrap_or_else(|| "—".into())
    };
    let grade_str = record.get("Grade").and_then(|v| v.as_str()).unwrap_or("—").to_string();
    let grade_color = grade_color_for(grade_str.trim(), &theme);

    let mut lines = vec![
        Line::from(Span::styled(
            format!("  {}", name_display),
            Style::default().fg(theme.fg).bold(),
        )),
        Line::from(Span::styled(
            format!("  {}", sid),
            Style::default().fg(theme.info),
        )),
    ];

    if app.summary_category_index == 1 {
        lines.push(Line::from(vec![
            Span::styled("  Cumulative : ", Style::default().fg(theme.key_accent)),
            Span::styled(fmt_int("Coursework Total"), Style::default().fg(theme.fg).bold()),
        ]));
        lines.push(Line::from(vec![
            Span::styled("  Midterm    : ", Style::default().fg(theme.key_accent)),
            Span::styled(fmt_int("midterm_pct"), Style::default().fg(theme.warning).bold()),
        ]));
        lines.push(Line::from(vec![
            Span::styled("  Final      : ", Style::default().fg(theme.key_accent)),
            Span::styled(fmt_int("final_pct"), Style::default().fg(Color::Indexed(33)).bold()),
        ]));
    }

    let mut cats: Vec<&String> = data.category_totals.keys().collect();
    cats.sort();
    for c in cats {
        if let Some(t) = data.category_totals.get(c).and_then(|m| m.get(sid)) {
            lines.push(Line::from(vec![
                Span::styled(format!("  {:<11}: ", c.chars().take(11).collect::<String>()),
                             Style::default().fg(theme.inactive_tab)),
                Span::styled(format!("{:.1}/{:.0}  ({:.1}%)", t.raw, t.max, t.pct), Style::default().fg(theme.fg)),
            ]));
        }
    }

    let absent_cols: Vec<&str> = data.absences.iter()
        .filter(|a| a.student_id == sid)
        .map(|a| a.column.as_str())
        .collect();
    if !absent_cols.is_empty() {
        lines.push(Line::from(vec![
            Span::styled(format!("  {} (absent): ", ABSENT), Style::default().fg(theme.warning).bold()),
            Span::styled(absent_cols.join(", "), Style::default().fg(theme.warning)),
        ]));
    }

    lines.push(Line::from(vec![
        Span::styled("  Score      : ", Style::default().fg(theme.key_accent)),
        Span::styled(fmt_int("Final Score"), Style::default().fg(theme.key_accent).bold()),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  Grade      : ", Style::default().fg(theme.key_accent)),
        Span::styled(
            format!(" {} ", grade_str),
            Style::default().fg(theme.bg).bg(grade_color).bold(),
        ),
    ]));

    let paragraph = Paragraph::new(lines).block(block);
    f.render_widget(paragraph, area);
}

struct SubmissionBlock {
    label: &'static str,
    key: &'static str,
    pts: f64,
    color: Color,
}

fn draw_submission_table(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    app.table_visible_rows = (area.height as usize).saturating_sub(5).max(1);

    let show_cumulative = data.student_grades.first()
        .map(|r| r.contains_key("Coursework Total"))
        .unwrap_or(false);
    let show_midterm = data.summary_columns.iter().any(|c| c == "midterm_pct");
    let show_final = data.summary_columns.iter().any(|c| c == "final_pct");

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 🎓 For Submission — final, rounded scores ")
        .title_style(Style::default().fg(theme.info).bold())
        .title_top(
            Line::from(Span::styled(
                format!(" [{}/{}] ", app.cursor_row + 1, data.student_grades.len()),
                Style::default().fg(theme.key_accent).bold(),
            ))
            .right_aligned(),
        );

    if !show_cumulative && !show_midterm && !show_final {
        let msg = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled(
                "  No gradable categories configured for submission.",
                Style::default().fg(theme.inactive_tab),
            )),
        ])
        .block(block);
        f.render_widget(msg, area);
        return;
    }

    let cumulative_pts: f64 = data.weights.iter()
        .filter(|(k, _)| k.as_str() != "midterm" && k.as_str() != "final")
        .map(|(_, v)| *v)
        .sum::<f64>() * 100.0;
    let midterm_pts = data.weights.get("midterm").copied().unwrap_or(0.0) * 100.0;
    let final_pts = data.weights.get("final").copied().unwrap_or(0.0) * 100.0;

    let mut blocks: Vec<SubmissionBlock> = Vec::new();
    if show_cumulative {
        blocks.push(SubmissionBlock { label: "Cumulative Scores", key: "Coursework Total", pts: cumulative_pts, color: theme.purple });
    }
    if show_midterm {
        blocks.push(SubmissionBlock { label: "Midterm", key: "midterm_pct", pts: midterm_pts, color: theme.warning });
    }
    if show_final {
        blocks.push(SubmissionBlock { label: "Final", key: "final_pct", pts: final_pts, color: Color::Indexed(33) });
    }

    let num_col_width = format!("{}", data.student_grades.len()).len().max(1) as u16 + 1;
    let sep_style = Style::default().fg(theme.border).add_modifier(Modifier::DIM);

    let mut header_cells = vec![
        Cell::from("#\n").style(Style::default().fg(theme.inactive_tab).add_modifier(Modifier::BOLD)),
    ];
    let mut widths = vec![Constraint::Length(num_col_width)];
    for (b_idx, b) in blocks.iter().enumerate() {
        if b_idx > 0 {
            header_cells.push(Cell::from("│\n").style(sep_style));
            widths.push(Constraint::Length(1));
        }
        header_cells.push(
            Cell::from("ID\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        );
        widths.push(Constraint::Length(9));

        let pts_str = if b.pts.fract() == 0.0 { format!("{}", b.pts as i64) } else { format!("{:.1}", b.pts) };
        header_cells.push(
            Cell::from(format!("{}\n({} pts)", b.label, pts_str))
                .style(Style::default().fg(b.color).add_modifier(Modifier::BOLD))
        );
        let value_width = (b.label.chars().count() + 2).max(12) as u16;
        widths.push(Constraint::Length(value_width));
    }
    let header = Row::new(header_cells).height(2).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    let rows: Vec<Row> = data.student_grades.iter().enumerate().map(|(r_idx, record)| {
        let mut cells = vec![
            Cell::from(format!("{}", r_idx + 1)).style(Style::default().fg(theme.inactive_tab)),
        ];
        for (b_idx, b) in blocks.iter().enumerate() {
            if b_idx > 0 {
                cells.push(Cell::from("│").style(sep_style));
            }
            let sid = record.get("Student ID").and_then(|v| v.as_str()).unwrap_or("—").to_string();
            cells.push(Cell::from(sid).style(Style::default().fg(theme.info)));

            let val_text = record.get(b.key)
                .and_then(|v| v.as_f64())
                .map(|n| format!("{}", n as i64))
                .unwrap_or_else(|| "—".into());
            cells.push(Cell::from(val_text).style(Style::default().fg(theme.fg).bold()));
        }

        let mut row_style = Style::default();
        if r_idx == app.cursor_row {
            row_style = row_style.bg(theme.highlight);
        } else if r_idx % 2 == 1 {
            row_style = row_style.bg(theme.alt_row);
        }

        Row::new(cells).style(row_style).height(1)
    }).collect();

    let table = Table::new(rows, widths)
        .header(header)
        .block(block)
        .column_spacing(1);

    let mut table_state = TableState::default().with_offset(app.scroll_row_offset);
    f.render_stateful_widget(table, area, &mut table_state);
}

fn draw_raw_left_panel(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let cats = app.get_categories();

    let border_color = if !app.raw_right_focused { theme.border_focus } else { theme.border };
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .title(" Categories ")
        .title_style(Style::default().fg(theme.info).bold());

    let raw_category_index = app.raw_category_index;
    let raw_right_focused = app.raw_right_focused;
    let data_opt = app.course_data.as_ref();

    let items: Vec<ListItem> = cats
        .iter()
        .enumerate()
        .map(|(i, cat)| {
            let is_highlighted = i == raw_category_index;

            let pts_tag = data_opt.map(|data| {
                let cols = data.data_mapping.get(cat.as_str()).cloned().unwrap_or_default();
                let raw_max: f64 = if cols.is_empty() {
                    data.weights.get(cat.as_str()).copied().unwrap_or(0.0) * 100.0
                } else {
                    cols.iter()
                        .map(|c| data.max_scores.get(c).copied().unwrap_or(1.0))
                        .sum()
                };
                let pts_str = if raw_max.fract() == 0.0 {
                    format!("{}", raw_max as u32)
                } else {
                    format!("{:.1}", raw_max)
                };
                format!("[{} pts]", pts_str)
            });

            let (name_style, pts_style) = if is_highlighted && !raw_right_focused {
                (
                    Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD),
                    Style::default().fg(theme.bg).bg(theme.active_tab),
                )
            } else if is_highlighted {
                (
                    Style::default().fg(category_color(cat, &theme)).add_modifier(Modifier::BOLD),
                    Style::default().fg(theme.info),
                )
            } else {
                (
                    Style::default().fg(theme.fg),
                    Style::default().fg(theme.inactive_tab),
                )
            };

            let name_part = format!("  {:<13}", cat);
            if let Some(tag) = pts_tag {
                ListItem::new(Line::from(vec![
                    Span::styled(name_part, name_style),
                    Span::styled(tag, pts_style),
                ]))
            } else {
                ListItem::new(Line::from(Span::styled(format!("  {}", cat), name_style)))
            }
        })
        .collect();

    let list = List::new(items).block(block);
    f.render_widget(list, area);
}

fn draw_student_info_panel(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" Student ")
        .title_style(Style::default().fg(theme.info).bold());

    if !app.raw_right_focused {
        let placeholder = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled(
                "  ─ no selection ─",
                Style::default().fg(theme.inactive_tab),
            )),
            Line::from(""),
            Line::from(Span::styled(
                "  → to focus table",
                Style::default().fg(theme.inactive_tab),
            )),
        ])
        .block(block);
        f.render_widget(placeholder, area);
        return;
    }

    let data = match &app.course_data {
        Some(d) => d,
        None => { f.render_widget(block, area); return; }
    };

    if app.cursor_row >= data.raw_scores.len() {
        f.render_widget(block, area);
        return;
    }

    let record = &data.raw_scores[app.cursor_row];
    let sid = record.get("Student ID").and_then(|v| v.as_str()).unwrap_or("—");
    let name_raw = record.get("Name").and_then(|v| v.as_str()).unwrap_or("—");

    // Look up Final Score and Grade from student_grades
    let (final_score_str, grade_str) = data.student_grades.iter()
        .find(|r| r.get("Student ID").and_then(|v| v.as_str()) == Some(sid))
        .map(|r| {
            let fs = r.get("Final Score")
                .and_then(|v| v.as_f64())
                .map(|n| format!("{:.1}", n))
                .unwrap_or_else(|| "—".into());
            let g = r.get("Grade")
                .and_then(|v| v.as_str())
                .unwrap_or("—")
                .to_string();
            (fs, g)
        })
        .unwrap_or_else(|| ("—".into(), "—".into()));

    let grade_color = grade_color_for(grade_str.trim(), &theme);

    // Build current-cell line
    let cat = app.raw_selected_category.as_deref().unwrap_or("");
    let sub_cols = data.data_mapping.get(cat).cloned().unwrap_or_default();
    let total_col = sub_cols.len() + 2;

    let cell_line: Option<Line> = if app.cursor_col >= 2 {
        if app.cursor_col == total_col {
            let total: f64 = sub_cols.iter()
                .filter_map(|sc| record.get(sc))
                .map(|v| score_value(v))
                .sum();
            let is_att = cat.to_lowercase().contains("attendance");
            let max = category_max(data, &sub_cols, is_att);
            Some(Line::from(vec![
                Span::styled("  Total            : ", Style::default().fg(theme.key_accent)),
                Span::styled(
                    format!("{:.1} / {:.0} pts", total, max)
                        + &if max > 0.0 { format!("  ({:.1}%)", total / max * 100.0) } else { String::new() },
                    Style::default().fg(theme.success).bold(),
                ),
            ]))
        } else {
            let sub_idx = app.cursor_col.saturating_sub(2);
            if sub_idx < sub_cols.len() {
                let col_name = &sub_cols[sub_idx];
                let raw_val = record.get(col_name)
                    .map(|v| match v {
                        serde_json::Value::Number(n) => format!("{}", n.as_f64().unwrap_or(0.0)),
                        serde_json::Value::String(s) => s.clone(),
                        serde_json::Value::Null => "—".into(),
                        _ => v.to_string(),
                    })
                    .unwrap_or_else(|| "—".into());
                let display_name = data.attendance_labels
                    .get(col_name)
                    .cloned()
                    .unwrap_or_else(|| col_name.clone());
                let short_name = if display_name.chars().count() > 16 {
                    format!("{}…", &display_name.chars().take(15).collect::<String>())
                } else {
                    display_name
                };
                Some(Line::from(vec![
                    Span::styled(
                        format!("  {:<16}: ", short_name),
                        Style::default().fg(theme.key_accent),
                    ),
                    Span::styled(raw_val, Style::default().fg(theme.fg).bold()),
                ]))
            } else {
                None
            }
        }
    } else {
        None
    };

    // Truncate name to fit wider panel (inner width ~29 chars after borders+padding)
    let name_display: String = name_raw.chars().take(27).collect();

    let mut lines = vec![
        Line::from(Span::styled(
            format!("  {}", name_display),
            Style::default().fg(theme.fg).bold(),
        )),
        Line::from(Span::styled(
            format!("  {}", sid),
            Style::default().fg(theme.info),
        )),
        Line::from(vec![
            Span::styled("  Score : ", Style::default().fg(theme.key_accent)),
            Span::styled(final_score_str, Style::default().fg(theme.key_accent).bold()),
        ]),
        Line::from(vec![
            Span::styled("  Grade : ", Style::default().fg(theme.key_accent)),
            Span::styled(
                format!(" {} ", grade_str),
                Style::default().fg(theme.bg).bg(grade_color).bold(),
            ),
        ]),
    ];

    if let Some(cl) = cell_line {
        lines.push(Line::from(Span::styled(
            "  ─────────────────────────────",
            Style::default().fg(theme.border),
        )));
        lines.push(cl);
    }

    let paragraph = Paragraph::new(lines).block(block);
    f.render_widget(paragraph, area);
}

fn draw_raw_details_tab(f: &mut Frame, app: &mut App, area: Rect) {
    if app.raw_selected_student.is_some() {
        draw_student_popup(f, app, area);
        return;
    }

    let (left, main) = split_left(app, area, Constraint::Length(33));

    if let Some(left) = left {
        let left_chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
            .split(left);

        draw_raw_left_panel(f, app, left_chunks[0]);
        draw_student_info_panel(f, app, left_chunks[1]);
    }
    draw_sub_column_view(f, app, main);
}

/// "35.0 · 78%": a raw category total and its share of the category's maximum.
fn total_with_pct(total: f64, max: f64) -> String {
    if max > 0.0 {
        format!("{:.1} · {:.0}%", total + 0.0, total / max * 100.0)
    } else {
        format!("{:.1}", total + 0.0)
    }
}

/// The maximum of a category: sessions for attendance, else the sum of its columns' points.
fn category_max(data: &crate::types::CourseData, sub_cols: &[String], is_attendance: bool) -> f64 {
    if is_attendance {
        sub_cols.len() as f64
    } else {
        sub_cols.iter().filter_map(|sc| data.max_scores.get(sc)).sum()
    }
}

/// Marker for "absent from the exam" in a score cell (counts as 0); see INTEGRATION.md.
const ABSENT: &str = "ขส";

fn score_value(v: &serde_json::Value) -> f64 {
    match v {
        serde_json::Value::Number(n) => n.as_f64().unwrap_or(0.0),
        serde_json::Value::String(s) => match s.trim().to_uppercase().as_str() {
            "P" | "EA" | "X" => 1.0,
            "L"  => 0.8,
            "A"  => 0.0,
            other => other.parse::<f64>().unwrap_or(0.0),
        },
        _ => 0.0,
    }
}

fn category_color(cat: &str, theme: &crate::style::Theme) -> Color {
    let lower = cat.to_lowercase();
    if lower.contains("homework") || lower.contains("hw") || lower.contains("project") {
        theme.info
    } else if lower.contains("attendance") || lower.contains("att") {
        theme.success
    } else if lower.contains("midterm") || lower.contains("mid") {
        theme.warning
    } else if lower.contains("final") {
        Color::Indexed(33)
    } else {
        theme.purple
    }
}

fn att_cell_style(val: &str, is_cursor: bool, theme: &crate::style::Theme) -> Style {
    if is_cursor {
        return Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
    }
    match val.trim().to_uppercase().as_str() {
        "P"        => Style::default().fg(theme.success).add_modifier(Modifier::BOLD),
        "A"        => Style::default().fg(theme.grade_f).add_modifier(Modifier::BOLD),
        "EA" | "X" => Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD),
        "L"        => Style::default().fg(theme.warning).add_modifier(Modifier::BOLD),
        _          => Style::default().fg(theme.fg),
    }
}

fn att_symbol(val: &str) -> &'static str {
    match val.trim().to_uppercase().as_str() {
        "P"        => "🅟",
        "L"        => "🅛",
        "A"        => "🅐",
        "EA" | "X" => "🅧",
        _          => " ",
    }
}

fn circled_number(n: usize) -> String {
    match n {
        0 => "\u{24EA}".to_string(), // ⓪
        1..=20 => {
            const CHARS: [char; 20] = [
                '\u{2460}','\u{2461}','\u{2462}','\u{2463}','\u{2464}',
                '\u{2465}','\u{2466}','\u{2467}','\u{2468}','\u{2469}',
                '\u{246A}','\u{246B}','\u{246C}','\u{246D}','\u{246E}',
                '\u{246F}','\u{2470}','\u{2471}','\u{2472}','\u{2473}',
            ];
            CHARS[n - 1].to_string()
        }
        21..=50 => {
            // U+3251 (㉑) through U+32BF (㊿) — East Asian wide (2 cells)
            char::from_u32('\u{3251}' as u32 + (n - 21) as u32)
                .map(|c| c.to_string())
                .unwrap_or_else(|| n.to_string())
        }
        _ => n.to_string(),
    }
}


fn draw_sub_column_view(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let cat = match &app.raw_selected_category {
        Some(c) => c.clone(),
        None => return,
    };

    // area.height - 2 borders - 3 header (height=2 + bottom_margin=1)
    app.table_visible_rows = (area.height as usize).saturating_sub(5).max(1);

    // +1 for the ▸ of a marked row
    let num_col_width = format!("{}", data.raw_scores.len()).len().max(1) as u16 + 2;

    let sub_cols = data.data_mapping.get(&cat).cloned().unwrap_or_default();
    let show_total = true;
    let is_attendance = cat.to_lowercase().contains("attendance");
    // 3 visual cells: emoji (2-wide) + 1 space, or circled-number (1-wide) + 2 spaces


    // Compute name alignment from actual data (display widths so Thai combining vowels are 0-width)
    let max_first_display = data.raw_scores.iter()
        .filter_map(|r| r.get("Name").and_then(|v| v.as_str()))
        .map(|n| n.split_whitespace().next().map(|p| UnicodeWidthStr::width(p)).unwrap_or(0))
        .max()
        .unwrap_or(12);
    let max_surname_display = data.raw_scores.iter()
        .filter_map(|r| r.get("Name").and_then(|v| v.as_str()))
        .map(|n| { let mut it = n.split_whitespace(); it.next(); UnicodeWidthStr::width(it.collect::<Vec<_>>().join(" ").as_str()) })
        .max()
        .unwrap_or(8);
    // +2: minimum gap of 2 spaces after the longest first name
    let alignment_target = max_first_display + 2;
    let name_col_width = (alignment_target + max_surname_display + 2).max(20) as u16;

    let border_color = if app.raw_right_focused { category_color(&cat, &theme) } else { theme.border };
    let title_text = if app.raw_right_focused {
        format!(" 📋 Raw Details  ›  {}  —  type a score · Space: mark · f: fill ", cat)
    } else {
        format!(" 📋 Raw Details  ›  {}  (→ / Enter: focus table) ", cat)
    };

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

    // Build visible column indices: frozen (0,1) + scrollable sub-cols
    let frozen_count = 2usize;
    let scroll_offset = app.scroll_col_offset.saturating_sub(frozen_count);
    let scroll_end = std::cmp::min(scroll_offset + sub_cols.len(), sub_cols.len());
    let visible_sub: &[String] = &sub_cols[scroll_offset..scroll_end];
    let sub_col_widths: Vec<u16> = visible_sub.iter().map(|sc| {
        if is_attendance { 2u16 } else { (sc.len() + 2).max(12) as u16 }
    }).collect();

    // Header
    let sep_style = Style::default().fg(theme.border).add_modifier(Modifier::DIM);
    let mut header_cells = vec![
        Cell::from("#\n").style(Style::default().fg(theme.inactive_tab).add_modifier(Modifier::BOLD)),
        Cell::from("ID\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Name\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("│\n").style(sep_style),
    ];
    for (sc_index, sc) in visible_sub.iter().enumerate() {
        let header_text = if is_attendance {
            format!("{}\n", circled_number(scroll_offset + sc_index + 1))
        } else {
            let max_text = if let Some(max_s) = data.max_scores.get(sc) {
                format!("\n({:.0} pts)", max_s)
            } else {
                "\n".to_string()
            };
            format!("{}{}", sc, max_text)
        };
        header_cells.push(
            Cell::from(header_text)
                .style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        );
    }
    if show_total {
        // Attendance max = 1 pt/session × n sessions; other categories sum explicit max_scores
        let total_max: f64 = if is_attendance {
            sub_cols.len() as f64
        } else {
            sub_cols.iter().filter_map(|sc| data.max_scores.get(sc)).sum()
        };
        let total_header = if total_max > 0.0 {
            format!("Total\n({:.0} pts)", total_max)
        } else {
            "Total\n(pts)".to_string()
        };
        header_cells.push(
            Cell::from(total_header)
                .style(Style::default().fg(theme.success).add_modifier(Modifier::BOLD))
        );
    }
    let header = Row::new(header_cells).height(2).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    // Rows
    let rows: Vec<Row> = data.raw_scores.iter().enumerate().map(|(r_idx, record)| {
        let sid = record.get("Student ID")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let marked = app.marks.contains(&sid);
        let mut cells = vec![if marked {
            Cell::from(format!("▸{}", r_idx + 1)).style(Style::default().fg(theme.purple).add_modifier(Modifier::BOLD))
        } else {
            Cell::from(format!(" {}", r_idx + 1)).style(Style::default().fg(theme.inactive_tab))
        }];

        let mut sid_style = Style::default().fg(if marked { theme.purple } else { theme.info });
        if app.raw_right_focused && r_idx == app.cursor_row && app.cursor_col == 0 {
            sid_style = Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
        }
        cells.push(Cell::from(sid.clone()).style(sid_style));

        let name = record.get("Name")
            .map(|v| match v {
                serde_json::Value::String(s) => format_thai_name(s, alignment_target),
                _ => v.to_string(),
            })
            .unwrap_or_default();
        let mut name_style = Style::default().fg(theme.fg);
        if app.raw_right_focused && r_idx == app.cursor_row && app.cursor_col == 1 {
            name_style = Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
        }
        cells.push(Cell::from(name).style(name_style));
        cells.push(Cell::from("│").style(sep_style));

        for (sc_offset, sc) in visible_sub.iter().enumerate() {
            let abs_col = frozen_count + scroll_offset + sc_offset;
            let is_cursor = app.raw_right_focused && r_idx == app.cursor_row && abs_col == app.cursor_col;
            let editing_here = app.editing && app.raw_selected_student.is_none()
                && app.editing_row == r_idx && app.editing_column == *sc;
            cells.push(score_cell(app, record, &sid, sc, is_attendance, is_cursor, editing_here));
        }

        if show_total {
            let total: f64 = sub_cols.iter()
                .filter_map(|sc| record.get(sc))
                .map(|v| score_value(v))
                .sum();
            let mut total_style = Style::default().fg(theme.success).add_modifier(Modifier::BOLD);
            if app.raw_right_focused && r_idx == app.cursor_row && app.cursor_col == sub_cols.len() + 2 {
                total_style = Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
            }
            let total_text = total_with_pct(total, category_max(data, &sub_cols, is_attendance));
            cells.push(Cell::from(total_text).style(total_style));
        }

        let mut row_style = Style::default();
        if app.raw_right_focused && r_idx == app.cursor_row {
            row_style = row_style.bg(theme.highlight);
        } else if r_idx % 2 == 1 {
            row_style = row_style.bg(theme.alt_row);
        }
        Row::new(cells).style(row_style).height(1)
    }).collect();

    // Widths
    let mut widths = vec![
        Constraint::Length(num_col_width),
        Constraint::Length(9),
        Constraint::Length(name_col_width),
        Constraint::Length(1), // separator
    ];
    for &w in &sub_col_widths {
        widths.push(Constraint::Length(w));
    }
    if show_total {
        widths.push(Constraint::Length(14));
    }

    let table = Table::new(rows, widths)
        .header(header)
        .block(block)
        .column_spacing(1);

    let mut table_state = TableState::default().with_offset(app.scroll_row_offset);
    f.render_stateful_widget(table, area, &mut table_state);
}

/// One score cell in Raw Details (table or student popup): the unsaved value if there is one
/// (underlined, red when above the max), or the inline editor's text while editing it.
fn score_cell(
    app: &App,
    record: &std::collections::HashMap<String, serde_json::Value>,
    sid: &str,
    column: &str,
    is_attendance: bool,
    is_cursor: bool,
    editing_here: bool,
) -> Cell<'static> {
    let theme = app.theme;
    if editing_here {
        if let Some(ta) = app.edit_textarea.as_ref() {
            let (_, cur) = ta.cursor();
            let mut text: Vec<char> = ta.lines()[0].chars().collect();
            text.insert(cur.min(text.len()), '▏');
            return Cell::from(text.into_iter().collect::<String>())
                .style(Style::default().fg(theme.bg).bg(theme.purple).add_modifier(Modifier::BOLD));
        }
    }
    let pending = app.edits.get(sid, column);
    let text = match pending {
        Some(p) => p.value.clone(),
        None => crate::edits::cell_text(record.get(column).unwrap_or(&serde_json::Value::Null)),
    };
    let display_text = if is_attendance { att_symbol(&text).to_string() } else { text.clone() };
    let mut style = if is_attendance {
        att_cell_style(&text, is_cursor, &theme)
    } else if text.trim() == ABSENT && !is_cursor {
        Style::default().fg(theme.warning).add_modifier(Modifier::BOLD)
    } else if is_cursor {
        Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(theme.fg)
    };
    if pending.is_some() {
        style = style.add_modifier(Modifier::UNDERLINED | Modifier::BOLD);
        if !is_cursor && !is_attendance {
            style = style.fg(theme.warning);
        }
        if crate::edits::is_over_max(&text, app.max_of(column)) {
            style = style.fg(theme.grade_f);
        }
    }
    let display_text = if pending.is_some() && is_attendance && text.is_empty() { "·".to_string() } else { display_text };
    Cell::from(display_text).style(style)
}

fn draw_student_popup(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let cat = match &app.raw_selected_category {
        Some(c) => c.clone(),
        None => return,
    };
    let student_idx = match app.raw_selected_student {
        Some(idx) => idx,
        None => return,
    };
    if student_idx >= data.raw_scores.len() {
        return;
    }

    let record = &data.raw_scores[student_idx].clone();
    let sid = record.get("Student ID").and_then(|v| v.as_str()).unwrap_or("?").to_string();
    let name = record.get("Name").and_then(|v| v.as_str()).unwrap_or("?").to_string();

    let sub_cols = data.data_mapping.get(&cat).cloned().unwrap_or_default();
    let show_total = true;

    let (tab_label, hint) = if app.active_tab == 2 {
        ("Analytics", "(Esc: back)")
    } else {
        ("Raw Details", "(type a score · Enter: edit  Esc: back)")
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(category_color(&cat, &theme)))
        .title(format!(
            " 📋 {}  ›  {}  ›  {}  ({})  {} ",
            tab_label, cat, name, sid, hint
        ))
        .title_style(Style::default().fg(category_color(&cat, &theme)).bold());

    let is_attendance_popup = cat.to_lowercase().contains("attendance");


    let max_first_display_popup = data.raw_scores.iter()
        .filter_map(|r| r.get("Name").and_then(|v| v.as_str()))
        .map(|n| n.split_whitespace().next().map(|p| UnicodeWidthStr::width(p)).unwrap_or(0))
        .max()
        .unwrap_or(12);
    let max_surname_display_popup = data.raw_scores.iter()
        .filter_map(|r| r.get("Name").and_then(|v| v.as_str()))
        .map(|n| { let mut it = n.split_whitespace(); it.next(); UnicodeWidthStr::width(it.collect::<Vec<_>>().join(" ").as_str()) })
        .max()
        .unwrap_or(8);
    let alignment_target_popup = max_first_display_popup + 2;
    let name_col_width_popup = (alignment_target_popup + max_surname_display_popup + 2).max(20) as u16;

    let frozen_count = 2usize;
    let scroll_offset = app.scroll_col_offset.saturating_sub(frozen_count);
    let scroll_end = std::cmp::min(scroll_offset + sub_cols.len(), sub_cols.len());
    let visible_sub: Vec<String> = sub_cols[scroll_offset..scroll_end].to_vec();
    let sub_col_widths_popup: Vec<u16> = visible_sub.iter().map(|sc| {
        if is_attendance_popup { 2u16 } else { (sc.len() + 2).max(12) as u16 }
    }).collect();

    // Header
    let sep_style_popup = Style::default().fg(theme.border).add_modifier(Modifier::DIM);
    let mut header_cells = vec![
        Cell::from("ID\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Name\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("│\n").style(sep_style_popup),
    ];
    for (sc_index, sc) in visible_sub.iter().enumerate() {
        let header_text = if is_attendance_popup {
            format!("{}\n", circled_number(scroll_offset + sc_index + 1))
        } else {
            let max_text = if let Some(max_s) = data.max_scores.get(sc) {
                format!("\n({:.0} pts)", max_s)
            } else {
                "\n".to_string()
            };
            format!("{}{}", sc, max_text)
        };
        header_cells.push(
            Cell::from(header_text)
                .style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        );
    }
    if show_total {
        let total_max: f64 = if is_attendance_popup {
            sub_cols.len() as f64
        } else {
            sub_cols.iter().filter_map(|sc| data.max_scores.get(sc)).sum()
        };
        let total_header = if total_max > 0.0 {
            format!("Total\n({:.0} pts)", total_max)
        } else {
            "Total\n(pts)".to_string()
        };
        header_cells.push(
            Cell::from(total_header)
                .style(Style::default().fg(theme.success).add_modifier(Modifier::BOLD))
        );
    }
    let header = Row::new(header_cells).height(2).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    // Single data row
    let mut cells = vec![];
    cells.push(Cell::from(sid.clone()).style(Style::default().fg(theme.info)));
    cells.push(Cell::from(format_thai_name(&name, alignment_target_popup)).style(Style::default().fg(theme.fg)));
    cells.push(Cell::from("│").style(sep_style_popup));

    for (sc_offset, sc) in visible_sub.iter().enumerate() {
        let abs_col = frozen_count + scroll_offset + sc_offset;
        let is_cursor = abs_col == app.cursor_col;
        let editing_here = app.editing && app.editing_column == *sc;
        cells.push(score_cell(app, record, &sid, sc, is_attendance_popup, is_cursor, editing_here));
    }

    if show_total {
        let total: f64 = sub_cols.iter()
            .filter_map(|sc| record.get(sc))
            .map(|v| score_value(v))
            .sum();
        cells.push(
            Cell::from(total_with_pct(total, category_max(data, &sub_cols, is_attendance_popup)))
                .style(Style::default().fg(theme.success).add_modifier(Modifier::BOLD))
        );
    }

    let row = Row::new(cells).style(Style::default().bg(theme.highlight)).height(1);

    let mut widths = vec![Constraint::Length(9), Constraint::Length(name_col_width_popup), Constraint::Length(1)];
    for &w in &sub_col_widths_popup {
        widths.push(Constraint::Length(w));
    }
    if show_total {
        widths.push(Constraint::Length(14));
    }

    let table = Table::new(vec![row], widths)
        .header(header)
        .block(block)
        .column_spacing(1);

    f.render_widget(table, area);
}

fn draw_analytics_tab(f: &mut Frame, app: &mut App, area: Rect) {
    if app.raw_selected_student.is_some() {
        draw_student_popup(f, app, area);
        return;
    }

    let (left, main) = split_left(app, area, Constraint::Length(33));

    if let Some(left) = left {
        let n_bounds = app.course_data.as_ref()
            .map(|d| d.grade_boundaries.len() + 1) // +1 for the synthetic "F" row
            .unwrap_or(8) as u16;
        let boundaries_height = n_bounds + 5; // borders(2) + blank + header + blank
        let left_chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Min(10), Constraint::Length(boundaries_height)])
            .split(left);

        draw_analytics_left_panel(f, app, left_chunks[0]);
        draw_analytics_boundaries_panel(f, app, left_chunks[1]);
    }

    match app.analytics_category_index {
        0 => draw_analytics_summary(f, app, main),
        1 => draw_analytics_progress(f, app, main),
        2 => draw_analytics_item_analysis(f, app, main),
        3 => draw_analytics_correlation(f, app, main),
        4 => draw_analytics_at_risk(f, app, main),
        _ => {}
    }
}

fn draw_analytics_summary(f: &mut Frame, app: &mut App, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);
    let top = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(rows[0]);
    let bottom = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(rows[1]);

    draw_analytics_overview(f, app, top[0]);
    draw_analytics_grade_distribution(f, app, top[1]);
    draw_analytics_histogram(f, app, bottom[0]);
    draw_analytics_box_plot(f, app, bottom[1]);
}

fn draw_analytics_left_panel(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let border_color = if !app.analytics_right_focused { theme.border_focus } else { theme.border };
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .title(" Categories ")
        .title_style(Style::default().fg(theme.info).bold());

    let idx = app.analytics_category_index;
    let right_focused = app.analytics_right_focused;

    let items: Vec<ListItem> = ANALYTICS_CATEGORIES
        .iter()
        .enumerate()
        .map(|(i, name)| {
            let is_highlighted = i == idx;
            let style = if is_highlighted && !right_focused {
                Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD)
            } else if is_highlighted {
                Style::default().fg(theme.active_tab).add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme.fg)
            };
            ListItem::new(Line::from(Span::styled(format!("  {}", name), style)))
        })
        .collect();

    let list = List::new(items).block(block);
    f.render_widget(list, area);
}

fn draw_analytics_overview(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let ov = &data.analytics.overview;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 📈 Overview ")
        .title_style(Style::default().fg(theme.info).bold());

    let lines = vec![
        Line::from(""),
        Line::from(Span::styled("  ⚡ CLASS-WIDE STATISTICS", Style::default().fg(theme.title).bold())),
        Line::from(""),
        Line::from(vec![
            Span::raw("   Total Enrolled : "),
            Span::styled(format!("{} students", ov.total_count), Style::default().fg(theme.info).bold()),
        ]),
        Line::from(vec![
            Span::raw("   Mean           : "),
            Span::styled(format!("{:.2} pts", ov.mean), Style::default().fg(theme.key_accent).bold()),
        ]),
        Line::from(vec![
            Span::raw("   Median         : "),
            Span::styled(format!("{:.2} pts", ov.median), Style::default().fg(theme.key_accent).bold()),
        ]),
        Line::from(vec![
            Span::raw("   Std. Deviation : "),
            Span::styled(format!("{:.2} pts", ov.std_dev), Style::default().fg(theme.key_accent).bold()),
        ]),
        Line::from(""),
        Line::from(vec![
            Span::raw("   Pass Rate      : "),
            Span::styled(format!("{:.1}%", ov.pass_rate), Style::default().fg(theme.success).bold()),
            Span::raw(format!("  ({}/{} passing)", ov.passing_count, ov.total_count)),
        ]),
    ];

    let p = Paragraph::new(lines).block(block);
    f.render_widget(p, area);
}

fn draw_analytics_histogram(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let bins = &data.analytics.histogram;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 📊 Final Score Histogram ")
        .title_style(Style::default().fg(theme.info).bold());

    if bins.is_empty() {
        let p = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled("   No data available.", Style::default().fg(theme.inactive_tab))),
        ])
        .block(block);
        f.render_widget(p, area);
        return;
    }

    // Render the block first, then draw the chart into a horizontally-centered sub-area
    // that is only ~70% of the inner width, so bars leave a visible margin instead of
    // stretching edge-to-edge in the (now smaller) quadrant.
    let inner = block.inner(area);
    f.render_widget(block, area);
    let chart_width = ((inner.width as f64) * 0.7) as u16;
    let chart_area = Rect {
        x: inner.x + (inner.width.saturating_sub(chart_width)) / 2,
        y: inner.y,
        width: chart_width,
        height: inner.height,
    };

    // Auto-fit bar width/gap to the (already narrowed) chart area so all bins render
    // without clipping.
    let inner_width = chart_area.width;
    let n = bins.len() as u16;
    let bar_gap: u16 = if inner_width > n * 2 { 1 } else { 0 };
    let bar_width = ((inner_width.saturating_sub(n.saturating_sub(1) * bar_gap)) / n).max(1);

    let bars: Vec<Bar> = bins
        .iter()
        .map(|bin| {
            let short_label = bin.label.split('-').next().unwrap_or(&bin.label).to_string();
            Bar::default()
                .value(bin.count as u64)
                .label(Line::from(short_label))
                .style(Style::default().fg(theme.key_accent))
                .value_style(
                    Style::default()
                        .fg(theme.bg)
                        .bg(theme.key_accent)
                        .add_modifier(Modifier::BOLD),
                )
        })
        .collect();

    let chart = BarChart::vertical(bars)
        .bar_width(bar_width)
        .bar_gap(bar_gap)
        .label_style(Style::default().fg(theme.info));

    f.render_widget(chart, chart_area);
}

fn draw_analytics_box_plot(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let bp = &data.analytics.box_plot;

    let whisker_style = Style::default().fg(theme.key_accent);
    let box_style = Style::default().fg(theme.key_accent).bold();
    let median_style = Style::default().fg(theme.success).bold();
    let mean_style = Style::default().fg(theme.purple).bold();
    let outlier_style = Style::default().fg(theme.warning).bold();
    let outlier_dot_style = Style::default().fg(theme.warning).bold();
    let dim_box = Color::Rgb(59, 50, 22);
    let dim_median = Color::Rgb(34, 54, 34);
    let dim_mean = Color::Rgb(44, 34, 64);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 📦 Box Plot ")
        .title_style(Style::default().fg(theme.info).bold());

    let inner = block.inner(area);
    // Horizontal orientation: a terminal cell is roughly twice as tall as wide, so this gets
    // far more resolution (columns) than the vertical layout ever could (rows) — collisions
    // that needed a whole nudge/connector system there are rare enough here to not need one.
    let width = inner.width.saturating_sub(2).max(10) as usize;
    let last = width.saturating_sub(1);
    let pos = |v: f64| -> usize {
        ((v.clamp(0.0, 100.0) / 100.0) * last as f64).round() as usize
    };
    let (p_wlo, p_q1, p_med, p_mean, p_q3, p_whi) = (
        pos(bp.whisker_low), pos(bp.q1), pos(bp.median), pos(bp.mean), pos(bp.q3), pos(bp.whisker_high),
    );

    // Chart line: whisker stems, a real background-filled box (not just an outline), caps,
    // median/mean ticks, and outlier dots beyond the whiskers.
    let mut spans: Vec<Span<'static>> = (0..width).map(|_| Span::raw(" ")).collect();
    let (lo, hi) = (p_wlo.min(p_q1), p_wlo.max(p_q1).min(last));
    if lo <= hi { for i in lo..=hi { spans[i] = Span::styled("─", whisker_style); } }
    let (lo2, hi2) = (p_q3.min(p_whi), p_q3.max(p_whi).min(last));
    if lo2 <= hi2 { for i in lo2..=hi2 { spans[i] = Span::styled("─", whisker_style); } }
    let (blo, bhi) = (p_q1.min(p_q3), p_q1.max(p_q3).min(last));
    for i in blo..=bhi { spans[i] = Span::styled("█", box_style.bg(dim_box)); }
    if p_wlo < width { spans[p_wlo] = Span::styled("├", whisker_style); }
    if p_whi < width { spans[p_whi] = Span::styled("┤", whisker_style); }
    if p_mean < width { spans[p_mean] = Span::styled("┃", mean_style.bg(dim_mean)); }
    if p_med < width { spans[p_med] = Span::styled("┃", median_style.bg(dim_median)); } // median wins on a tie
    for o in &bp.outliers {
        let c = pos(o.final_score);
        if c < width { spans[c] = Span::styled("∙", outlier_dot_style); }
    }

    let mut tick_chars: Vec<char> = vec![' '; width];
    for (label, val) in [("0", 0.0), ("25", 25.0), ("50", 50.0), ("75", 75.0), ("100", 100.0)] {
        let p = pos(val);
        let start = if p + label.len() > width { width.saturating_sub(label.len()) } else { p };
        for (j, c) in label.chars().enumerate() {
            if start + j < width { tick_chars[start + j] = c; }
        }
    }
    let tick_line: String = tick_chars.into_iter().collect();

    let mut lines: Vec<Line> = vec![
        Line::from(vec![
            Span::raw(" Min: "), Span::styled(format!("{:.1}", bp.min), Style::default().fg(theme.info).bold()),
            Span::raw("   Q1: "), Span::styled(format!("{:.1}", bp.q1), box_style),
            Span::raw("   Median: "), Span::styled(format!("{:.1}", bp.median), median_style),
            Span::raw("   Q3: "), Span::styled(format!("{:.1}", bp.q3), box_style),
            Span::raw("   Max: "), Span::styled(format!("{:.1}", bp.max), Style::default().fg(theme.info).bold()),
        ]),
        Line::from(vec![
            Span::raw(" Mean: "), Span::styled(format!("{:.1}", bp.mean), mean_style),
            Span::raw("   IQR: "), Span::styled(format!("{:.1}", bp.q3 - bp.q1), box_style),
            Span::raw("   "),
            Span::styled(bp.skew_label.split(" (").next().unwrap_or(&bp.skew_label).to_string(), Style::default().fg(theme.warning)),
        ]),
        Line::from(""),
        Line::from({ let mut v = vec![Span::raw(" ")]; v.extend(spans); v }),
        Line::from(Span::styled(format!(" {}", tick_line), Style::default().fg(theme.inactive_tab))),
        Line::from(Span::styled("─".repeat(inner.width as usize), Style::default().fg(theme.border))),
    ];

    if bp.outliers.is_empty() {
        lines.push(Line::from(Span::styled(" No outliers (beyond 1.5×IQR).", Style::default().fg(theme.inactive_tab))));
    } else {
        lines.push(Line::from(Span::styled(
            format!(" ⚡ Outliers ({}), sorted ascending", bp.outliers.len()),
            Style::default().fg(theme.title).bold(),
        )));

        let remaining = (inner.height as usize).saturating_sub(lines.len());
        let total = bp.outliers.len();
        let (show_n, more) = if total <= remaining {
            (total, 0)
        } else {
            let show_n = remaining.saturating_sub(1);
            (show_n, total - show_n)
        };

        for o in bp.outliers.iter().take(show_n) {
            lines.push(Line::from(vec![
                Span::raw(" "),
                Span::styled(o.student_id.clone(), Style::default().fg(theme.info)),
                Span::raw(" "),
                Span::styled(format_thai_name(&o.name, 20), Style::default().fg(theme.fg)),
                Span::raw(" "),
                Span::styled(format!("{:.1}", o.final_score), outlier_style),
            ]));
        }
        if more > 0 {
            lines.push(Line::from(Span::styled(
                format!(" + {} more (see Analytics → At-Risk tab)", more),
                Style::default().fg(theme.inactive_tab),
            )));
        }
    }

    let p = Paragraph::new(lines).block(block);
    f.render_widget(p, area);
}

fn draw_analytics_grade_distribution(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 📊 Letter Grade Distribution ")
        .title_style(Style::default().fg(theme.info).bold());

    let mut grade_key_pairs: Vec<(String, f64)> = data.grade_boundaries
        .iter()
        .map(|(k, v)| (k.clone(), *v))
        .collect();
    grade_key_pairs.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let mut grade_keys: Vec<String> = grade_key_pairs.into_iter().map(|(k, _)| k).collect();
    grade_keys.push("F".to_string());

    let mut max_count = 0;
    for g in &grade_keys {
        if let Some(stats) = data.grade_distribution.get(g) {
            if stats.count > max_count {
                max_count = stats.count;
            }
        }
    }

    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled("  GRADE VALUE DISTRIBUTION BAR CHART", Style::default().fg(theme.title).bold())),
        Line::from(""),
    ];

    // Bars stretch to fill all the space left over after the fixed-width prefix
    // ("  A │ ") and suffix ("  NN students (NN.N%)"), with a one-line gap between grades —
    // but only if the panel is tall enough for every grade to stay visible with that gap.
    // Never sacrifice visibility for spacing: below that threshold, pack tight instead.
    let prefix_len = 6usize;
    let suffix_len = 24usize;
    let inner = block.inner(area);
    let inner_width = inner.width as usize;
    let avail = inner_width.saturating_sub(prefix_len + suffix_len);
    let max_bar_length = avail.max(5);

    let header_rows = 3usize;
    let rows_with_gap = header_rows + grade_keys.len() * 2 - 1;
    let use_gap = (inner.height as usize) >= rows_with_gap;

    for (i, g) in grade_keys.iter().enumerate() {
        let stats = data.grade_distribution.get(g);
        let count = stats.map(|s| s.count).unwrap_or(0);
        let pct = stats.map(|s| s.pct).unwrap_or(0.0);

        let bar_len = if max_count > 0 {
            (count * max_bar_length) / max_count
        } else {
            0
        };

        let bar_filled = "▇".repeat(bar_len);
        let bar_empty = "░".repeat(max_bar_length - bar_len);

        let g_color = grade_color_for(g, &theme);

        let bar_line = Line::from(vec![
            Span::raw(" "),
            Span::styled(format!("{:<2}", g), Style::default().fg(g_color).bold()),
            Span::styled(" │ ", Style::default().fg(theme.border)),
            Span::styled(bar_filled, Style::default().fg(g_color)),
            Span::styled(bar_empty, Style::default().fg(theme.border)),
            Span::raw("  "),
            Span::styled(format!("{:>2} students", count), Style::default().fg(theme.fg)),
            Span::styled(format!(" ({:>4.1}%)", pct), Style::default().fg(theme.info)),
        ]);
        lines.push(bar_line);
        if use_gap && i + 1 < grade_keys.len() {
            lines.push(Line::from(""));
        }
    }

    let chart_p = Paragraph::new(lines)
        .block(block);
    f.render_widget(chart_p, area);
}

fn draw_analytics_boundaries_panel(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" Boundaries ")
        .title_style(Style::default().fg(theme.info).bold());

    let mut sorted_bounds: Vec<(&String, &f64)> = data.grade_boundaries.iter().collect();
    sorted_bounds.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap_or(std::cmp::Ordering::Equal));

    let code_width = sorted_bounds
        .iter()
        .map(|(g, _)| g.len())
        .chain(std::iter::once("F".len()))
        .max()
        .unwrap_or(1);

    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled("  ⚡ BOUNDARIES LIST", Style::default().fg(theme.title).bold())),
        Line::from(""),
    ];
    for (g, val) in &sorted_bounds {
        lines.push(Line::from(vec![
            Span::raw("   Grade "),
            Span::styled(format!("{:<code_width$}", g), Style::default().fg(grade_color_for(g, &theme)).bold()),
            Span::raw(" : ≥ "),
            Span::styled(format!("{:.1}", val), Style::default().fg(theme.fg)),
        ]));
    }
    if let Some((_, min_val)) = sorted_bounds.last() {
        lines.push(Line::from(vec![
            Span::raw("   Grade "),
            Span::styled(format!("{:<code_width$}", "F"), Style::default().fg(grade_color_for("F", &theme)).bold()),
            Span::raw(" : < "),
            Span::styled(format!("{:.1}", min_val), Style::default().fg(theme.fg)),
        ]));
    }

    let p = Paragraph::new(lines).block(block);
    f.render_widget(p, area);
}

/// Right-pads a leading 1-2 digit day-of-month to a fixed width (e.g. "3 Feb 2027" ->
/// " 3 Feb 2027") so the month text lines up across attendance date labels, regardless of
/// whether the label came from `attendance_labels` or a raw "D Mon YYYY" CSV column header.
fn pad_attendance_day(label: &str) -> String {
    match label.split_once(' ') {
        Some((day, rest)) if !day.is_empty() && day.len() <= 2 && day.chars().all(|c| c.is_ascii_digit()) => {
            format!("{:>2} {}", day, rest)
        }
        _ => label.to_string(),
    }
}

fn draw_analytics_progress(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 📈 Progress Over Time (by item order) ")
        .title_style(Style::default().fg(theme.info).bold());

    let bar_len_max = 20usize;
    let mut lines = vec![Line::from("")];
    for series in &data.analytics.progress {
        let color = category_color(&series.category, &theme);
        lines.push(Line::from(Span::styled(
            format!("  ⚡ {}", series.category.to_uppercase()),
            Style::default().fg(color).bold(),
        )));
        for item in &series.items {
            let filled = ((item.avg_pct.clamp(0.0, 100.0) / 100.0) * bar_len_max as f64).round() as usize;
            let bar_filled = "▇".repeat(filled);
            let bar_empty = "░".repeat(bar_len_max - filled);
            let mut label = data.attendance_labels.get(&item.label).cloned().unwrap_or_else(|| item.label.clone());
            if series.category.eq_ignore_ascii_case("attendance") {
                label = pad_attendance_day(&label);
            }
            lines.push(Line::from(vec![
                Span::styled(format!("   {:<14}", label), Style::default().fg(theme.fg)),
                Span::styled(bar_filled, Style::default().fg(color)),
                Span::styled(bar_empty, Style::default().fg(theme.border)),
                Span::raw(format!("  {:>5.1}%", item.avg_pct)),
            ]));
        }
        lines.push(Line::from(""));
    }
    if data.analytics.progress.is_empty() {
        lines.push(Line::from(Span::styled("   No data available.", Style::default().fg(theme.inactive_tab))));
    }

    let p = Paragraph::new(lines).block(block);
    f.render_widget(p, area);
}

fn draw_analytics_item_analysis(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let items = &data.analytics.item_analysis;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 🎯 Item Difficulty & Discrimination ")
        .title_style(Style::default().fg(theme.info).bold());

    if items.is_empty() {
        let p = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled("   No categories with 2+ scored items to analyze.", Style::default().fg(theme.inactive_tab))),
        ]).block(block);
        f.render_widget(p, area);
        return;
    }

    let header = Row::new(vec![
        Cell::from("Category").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Item").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Difficulty").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Level").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Discrimination").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("n").style(Style::default().fg(theme.key_accent).bold()),
    ]).height(1).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    let rows: Vec<Row> = items.iter().enumerate().map(|(i, it)| {
        let level_color = match it.difficulty_label.as_str() {
            "Easy" => theme.success,
            "Hard" => theme.grade_f,
            _ => theme.warning,
        };
        let mut row_style = Style::default();
        if i % 2 == 1 { row_style = row_style.bg(theme.alt_row); }
        Row::new(vec![
            Cell::from(it.category.clone()).fg(category_color(&it.category, &theme)),
            Cell::from(it.item.clone()).fg(theme.fg),
            Cell::from(format!("{:.1}%", it.difficulty)).fg(theme.key_accent),
            Cell::from(it.difficulty_label.clone()).fg(level_color).add_modifier(Modifier::BOLD),
            Cell::from(format!("{:.3}", it.discrimination)).fg(theme.info),
            Cell::from(format!("{}", it.n)).fg(theme.inactive_tab),
        ]).style(row_style).height(1)
    }).collect();

    let widths = vec![
        Constraint::Length(14),
        Constraint::Length(14),
        Constraint::Length(12),
        Constraint::Length(10),
        Constraint::Length(15),
        Constraint::Length(6),
    ];

    let table = Table::new(rows, widths).header(header).block(block).column_spacing(1);
    f.render_widget(table, area);
}

fn corr_color(v: f64, theme: &crate::style::Theme) -> Color {
    if v >= 0.99 {
        theme.inactive_tab
    } else if v >= 0.5 {
        theme.success
    } else if v >= 0.2 {
        theme.info
    } else if v <= -0.2 {
        theme.grade_f
    } else {
        theme.fg
    }
}

fn draw_analytics_correlation(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let corr = &data.analytics.correlation;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 🔗 Correlation Matrix (category %) ")
        .title_style(Style::default().fg(theme.info).bold());

    if corr.categories.is_empty() {
        let p = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled("   No category data to correlate.", Style::default().fg(theme.inactive_tab))),
        ]).block(block);
        f.render_widget(p, area);
        return;
    }

    let mut header_cells = vec![Cell::from("")];
    for cat in &corr.categories {
        header_cells.push(Cell::from(cat.clone()).style(Style::default().fg(theme.key_accent).bold()));
    }
    let header = Row::new(header_cells).height(1).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    let rows: Vec<Row> = corr.categories.iter().enumerate().map(|(i, cat)| {
        let mut cells = vec![Cell::from(cat.clone()).style(Style::default().fg(theme.key_accent).bold())];
        for j in 0..corr.categories.len() {
            let v = corr.matrix.get(i).and_then(|row| row.get(j)).copied().unwrap_or(0.0);
            let color = corr_color(v, &theme);
            cells.push(Cell::from(format!("{:.2}", v)).style(Style::default().fg(color)));
        }
        Row::new(cells).height(1)
    }).collect();

    let mut widths = vec![Constraint::Length(12)];
    for _ in &corr.categories {
        widths.push(Constraint::Length(8));
    }

    let table = Table::new(rows, widths).header(header).block(block).column_spacing(1);
    f.render_widget(table, area);
}

fn draw_analytics_at_risk(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };
    let at_risk = &data.analytics.at_risk;

    app.table_visible_rows = (area.height as usize).saturating_sub(4).max(1);

    let border_color = if app.analytics_right_focused { theme.border_focus } else { theme.border };
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .title(format!(" ⚠️  At-Risk Students ({}) ", at_risk.len()))
        .title_style(Style::default().fg(theme.warning).bold());

    if at_risk.is_empty() {
        let p = Paragraph::new(vec![
            Line::from(""),
            Line::from(Span::styled("   No students currently at risk.", Style::default().fg(theme.success))),
        ]).block(block);
        f.render_widget(p, area);
        return;
    }

    let header = Row::new(vec![
        Cell::from("ID").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Name").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Final Score").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Grade").style(Style::default().fg(theme.key_accent).bold()),
        Cell::from("Reason").style(Style::default().fg(theme.key_accent).bold()),
    ]).height(1).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    let cursor_row = app.cursor_row;
    let right_focused = app.analytics_right_focused;
    let rows: Vec<Row> = at_risk.iter().enumerate().map(|(i, s)| {
        let g_color = grade_color_for(&s.grade, &theme);
        let mut row_style = Style::default();
        if right_focused && i == cursor_row {
            row_style = row_style.bg(theme.highlight);
        } else if i % 2 == 1 {
            row_style = row_style.bg(theme.alt_row);
        }
        Row::new(vec![
            Cell::from(s.student_id.clone()).fg(theme.info),
            Cell::from(format_thai_name(&s.name, 18)).fg(theme.fg),
            Cell::from(format!("{:.1}", s.final_score)).fg(theme.key_accent).add_modifier(Modifier::BOLD),
            Cell::from(s.grade.clone()).fg(g_color).add_modifier(Modifier::BOLD),
            Cell::from(s.reasons.join(", ")).fg(theme.warning),
        ]).style(row_style).height(1)
    }).collect();

    let widths = vec![
        Constraint::Length(10),
        Constraint::Length(30),
        Constraint::Length(12),
        Constraint::Length(7),
        Constraint::Length(22),
    ];

    let table = Table::new(rows, widths).header(header).block(block).column_spacing(1);
    let mut table_state = TableState::default().with_offset(app.scroll_row_offset);
    f.render_stateful_widget(table, area, &mut table_state);
}

fn draw_roundup_tab(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    let (left, main) = split_left(app, area, Constraint::Percentage(35));

    // Left panel: roundup distribution table
    let summary = &data.roundup_summary;
    let left_lines = vec![
        Line::from(""),
        Line::from(Span::styled("  🔥 PRO-STUDENT ROUNDING EFFECTS", Style::default().fg(theme.purple).bold())),
        Line::from(""),
        Line::from(vec![
            Span::raw("   Total Students Improved : "),
            Span::styled(format!("{}", summary.improved_count), Style::default().fg(theme.success).bold()),
        ]),
        Line::from(""),
        Line::from(Span::styled("  How it works:", Style::default().fg(theme.key_accent).bold())),
        Line::from(Span::raw("   Components like midterm, final,")),
        Line::from(Span::raw("   and Coursework Total are ceil()'ed")),
        Line::from(Span::raw("   prior to accumulating the final score.")),
        Line::from(Span::raw("   This helps lift borderline scores.")),
    ];

    let left_block = Block::default()
        .borders(Borders::RIGHT)
        .border_style(Style::default().fg(theme.border));
    let left_p = Paragraph::new(left_lines)
        .block(left_block);
    if let Some(left) = left {
        f.render_widget(left_p, left);
    }

    // Right panel: Table of students whose grades improved
    let right_block = Block::default()
        .borders(Borders::NONE)
        .title(" Improved Students Register ")
        .title_style(Style::default().fg(theme.info).bold());

    let headers = vec![
        Cell::from("Student ID").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Name").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Orig Score").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Final Score").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Orig Grade").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("New Grade").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
    ];
    let header_row = Row::new(headers).height(1).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    let rows: Vec<Row> = summary
        .improved_students
        .iter()
        .enumerate()
        .map(|(r_idx, stud)| {
            let orig_g_color = grade_color_for(&stud.original_grade, &theme);
            let new_g_color = grade_color_for(&stud.grade, &theme);

            let cells = vec![
                Cell::from(stud.student_id.clone()).fg(theme.info),
                Cell::from(format_thai_name(&stud.name, 18)).fg(theme.fg),
                Cell::from(format!("{:.1}", stud.original_final_score)).fg(theme.inactive_tab),
                Cell::from(format!("{:.1}", stud.final_score)).fg(theme.key_accent).add_modifier(Modifier::BOLD),
                Cell::from(stud.original_grade.clone()).fg(orig_g_color),
                Cell::from(stud.grade.clone()).fg(new_g_color).add_modifier(Modifier::BOLD),
            ];
            
            let mut row_style = Style::default();
            if r_idx == app.cursor_row {
                row_style = row_style.bg(theme.highlight);
            } else if r_idx % 2 == 1 {
                row_style = row_style.bg(theme.alt_row);
            }
            Row::new(cells).style(row_style).height(1)
        })
        .collect();

    let widths = vec![
        Constraint::Length(12),
        Constraint::Length(38),
        Constraint::Length(12),
        Constraint::Length(12),
        Constraint::Length(11),
        Constraint::Length(11),
    ];

    let table = Table::new(rows, widths)
        .header(header_row)
        .block(right_block)
        .column_spacing(1);

    f.render_widget(table, main);
}

/// The footer's content as one line, plus its kind: 0 key legend, 1 info, 2 error.
fn footer_line(app: &App) -> (Line<'static>, u8) {
    let theme = app.theme;
    
    // Bottom status line showing helpful messages or key legends
    let (status_line, is_special) = if !app.saving.is_empty() {
        (
            Line::from(vec![
                Span::styled(" ⏳ ", Style::default().fg(theme.bg).bg(theme.warning).bold()),
                Span::styled(format!(" {} ", app.loading_msg), Style::default().fg(theme.warning).bold()),
            ]),
            1
        )
    } else if let Some(ref info) = app.info_msg {
        (
            Line::from(vec![
                Span::styled(" ℹ️ INFO ", Style::default().fg(theme.bg).bg(theme.success).bold()),
                Span::styled(format!(" {} ", info), Style::default().fg(theme.success).bold()),
            ]),
            1
        )
    } else if let Some(ref err) = app.error {
        (
            Line::from(vec![
                Span::styled(" ❌ ERROR ", Style::default().fg(theme.bg).bg(theme.grade_f).bold()),
                Span::styled(format!(" {} ", err), Style::default().fg(theme.grade_f).bold()),
            ]),
            2
        )
    } else {
        // Render dynamic legends depending on context
        let spans = match app.state {
            AppState::CourseSelect => vec![
                Span::styled(" [▲/▼/j/k] ", Style::default().fg(theme.key_accent).bold()),
                Span::raw("Navigate  "),
                Span::styled(" [Enter] ", Style::default().fg(theme.active_tab).bold()),
                Span::raw("Select Course  "),
                Span::styled(" [q] ", Style::default().fg(theme.grade_f).bold()),
                Span::raw("Quit"),
            ],
            AppState::Dashboard => {
                if app.confirm_leave.is_some() {
                    vec![
                        Span::raw(" Unsaved changes: "),
                        Span::styled(" [S] ", Style::default().fg(theme.success).bold()),
                        Span::raw("Save  "),
                        Span::styled(" [D] ", Style::default().fg(theme.grade_f).bold()),
                        Span::raw("Discard  "),
                        Span::styled(" [Esc] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Keep editing"),
                    ]
                } else if app.editing {
                    let mut v = vec![
                        Span::raw(format!(" Editing {}: ", app.editing_column)),
                        Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()),
                        Span::raw("Keep & next  "),
                        Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()),
                        Span::raw("Keep & move  "),
                        Span::styled(" [Esc] ", Style::default().fg(theme.grade_f).bold()),
                        Span::raw("Cancel  "),
                    ];
                    if let (Some(data), Some(ta)) = (app.course_data.as_ref(), app.edit_textarea.as_ref()) {
                        let (score, grade) = calculate_instant_score_and_grade(
                            data, &app.editing_student_id, &app.editing_column, &ta.lines()[0]);
                        v.push(Span::styled(
                            format!(" → final {:.1} ({}) ", score, grade.trim()),
                            Style::default().fg(theme.info).bold(),
                        ));
                    }
                    v
                } else if let Some(fill) = app.fill.as_ref() {
                    vec![
                        Span::raw(format!(" Fill {}: ", fill.column)),
                        Span::styled(" [Tab] ", Style::default().fg(theme.active_tab).bold()),
                        Span::raw("Next field  "),
                        Span::styled(" [Space/◀/▶] ", Style::default().fg(theme.active_tab).bold()),
                        Span::raw("Choose  "),
                        Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()),
                        Span::raw("Fill  "),
                        Span::styled(" [Esc] ", Style::default().fg(theme.grade_f).bold()),
                        Span::raw("Cancel"),
                    ]
                } else if app.editing_attendance {
                    vec![
                        Span::raw(" Select Attendance: "),
                        Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()),
                        Span::raw("Navigate  "),
                        Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()),
                        Span::raw("Confirm  "),
                        Span::styled(" [Esc] ", Style::default().fg(theme.grade_f).bold()),
                        Span::raw("Cancel"),
                    ]
                } else if app.editing_weights || app.editing_boundaries {
                    vec![
                        Span::raw(" Editing Configurations: "),
                        Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()),
                        Span::raw("Navigate Fields  "),
                        Span::styled(" [Type Value] ", Style::default().fg(theme.active_tab).bold()),
                        Span::raw("  "),
                        Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()),
                        Span::raw("Save Config  "),
                        Span::styled(" [Esc] ", Style::default().fg(theme.grade_f).bold()),
                        Span::raw("Cancel"),
                    ]
                } else {
                    let mut leg = Vec::new();
                    if !app.edits.is_empty() {
                        leg.push(Span::styled(format!(" [Ctrl+S] Save {} ", app.edits.len()), Style::default().fg(theme.bg).bg(theme.warning).bold()));
                        leg.push(Span::raw("  "));
                        leg.push(Span::styled(" [u] ", Style::default().fg(theme.warning).bold()));
                        leg.push(Span::raw("Undo  "));
                    }
                    if !app.marks.is_empty() {
                        leg.push(Span::styled(" [m] ", Style::default().fg(theme.purple).bold()));
                        leg.push(Span::raw(format!("Clear {} marks  ", app.marks.len())));
                    }
                    leg.extend([
                        Span::styled(" [Tab] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Next Tab  "),
                        Span::styled(" [Esc] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Courses Menu  "),
                        Span::styled(" [s] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw(if app.show_left_panel { "Hide Panel  " } else { "Show Panel  " }),
                        Span::styled(" [e] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Export CSV  "),
                    ]);
                    if app.active_tab == 0 {
                        if app.summary_right_focused {
                            if app.summary_category_index == 0 {
                                leg.push(Span::styled(" [▲/▼/◀/▶] ", Style::default().fg(theme.active_tab).bold()));
                            } else {
                                leg.push(Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()));
                            }
                            leg.push(Span::raw("Move  "));
                            leg.push(Span::styled(" [/] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Jump Category  "));
                            leg.push(Span::styled(" [←/Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Back to Categories  "));
                        } else {
                            leg.push(Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Navigate  "));
                            leg.push(Span::styled(" [/] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Jump Category  "));
                            leg.push(Span::styled(" [→/Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Focus Table  "));
                            leg.push(Span::styled(" [Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Course Select  "));
                        }
                    }
                    if app.active_tab == 1 {
                        if app.raw_selected_student.is_some() {
                            // L2: student popup
                            leg.push(Span::styled(" [◀/▶] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Move  "));
                            leg.push(Span::styled(" [0-9/Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Edit  "));
                            leg.push(Span::styled(" [-] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw(format!("{}  ", ABSENT)));
                            leg.push(Span::styled(" [Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Back  "));
                        } else if app.raw_right_focused {
                            // L1: right table focused
                            leg.push(Span::styled(" [▲/▼/◀/▶] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Move  "));
                            leg.push(Span::styled(" [0-9/Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Edit  "));
                            leg.push(Span::styled(" [-] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw(format!("{}  ", ABSENT)));
                            leg.push(Span::styled(" [Space/⇧▲▼] ", Style::default().fg(theme.purple).bold()));
                            leg.push(Span::raw("Mark  "));
                            leg.push(Span::styled(" [f] ", Style::default().fg(theme.title).bold()));
                            leg.push(Span::raw("Fill Column  "));
                            leg.push(Span::styled(" [←/Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Back to Categories  "));
                        } else {
                            // Left panel focused
                            leg.push(Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Navigate  "));
                            leg.push(Span::styled(" [→/Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Focus Table  "));
                            leg.push(Span::styled(" [Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Course Select  "));
                        }
                    }
                    if app.active_tab == 2 {
                        if app.raw_selected_student.is_some() {
                            // Student popup opened from At-Risk Students (read-only)
                            leg.push(Span::styled(" [Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Back  "));
                        } else if app.analytics_right_focused {
                            // At-Risk Students table focused
                            leg.push(Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Move  "));
                            leg.push(Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Open Student  "));
                            leg.push(Span::styled(" [/] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Jump Category  "));
                            leg.push(Span::styled(" [←/Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Back to Categories  "));
                        } else {
                            // Category list focused
                            leg.push(Span::styled(" [▲/▼] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Navigate  "));
                            leg.push(Span::styled(" [/] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Jump Category  "));
                            leg.push(Span::styled(" [→/Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Focus Table (At-Risk only)  "));
                            leg.push(Span::styled(" [Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Course Select  "));
                        }
                    }
                    if app.active_tab == 0 || app.active_tab == 1 {
                        leg.push(Span::styled(" [w] ", Style::default().fg(theme.title).bold()));
                        leg.push(Span::raw("Edit Weights  "));
                        leg.push(Span::styled(" [b] ", Style::default().fg(theme.title).bold()));
                        leg.push(Span::raw("Edit Boundaries"));
                    }
                    leg
                }
            }
        };
        (Line::from(spans), 0)
    };
    (status_line, is_special)
}

/// Packs footer spans into rows no wider than `width`. Each `[key]` span starts an item that keeps its
/// label with it; an item too wide for one row (a long info or error message) breaks between words.
fn wrap_legend<'a>(spans: Vec<Span<'a>>, width: u16) -> Vec<Line<'a>> {
    let width = width as usize;
    let trimmed_width = |item: &[Span]| -> usize {
        let n = item.len();
        item[..n - 1].iter().map(|s| s.width()).sum::<usize>()
            + UnicodeWidthStr::width(item[n - 1].content.trim_end())
    };

    let mut items: Vec<Vec<Span<'a>>> = Vec::new();
    for span in spans {
        match items.last_mut() {
            Some(item) if !span.content.starts_with(" [") => item.push(span),
            _ => items.push(vec![span]),
        }
    }
    let items: Vec<Vec<Span<'a>>> = items
        .into_iter()
        .flat_map(|item| {
            if trimmed_width(&item) <= width {
                vec![item]
            } else {
                item.into_iter()
                    .flat_map(|s| {
                        s.content
                            .split_inclusive(' ')
                            .map(|w| vec![Span::styled(w.to_string(), s.style)])
                            .collect::<Vec<_>>()
                    })
                    .collect()
            }
        })
        .collect();

    let mut rows: Vec<Vec<Span<'a>>> = Vec::new();
    let mut row_width = 0;
    for item in items {
        let fits = row_width + trimmed_width(&item) <= width;
        if rows.is_empty() || (!fits && row_width > 0) {
            rows.push(Vec::new());
            row_width = 0;
        }
        row_width += item.iter().map(|s| s.width()).sum::<usize>();
        rows.last_mut().unwrap().extend(item);
    }

    rows.into_iter()
        .map(|mut row| {
            if let Some(last) = row.last_mut() {
                let trimmed = last.content.trim_end().to_string();
                last.content = trimmed.into();
            }
            Line::from(row)
        })
        .collect()
}

fn draw_footer(f: &mut Frame, app: &App, area: Rect, rows: Vec<Line>, is_special: u8) {
    let theme = app.theme;
    let style = match is_special {
        1 => Style::default().bg(theme.bg),
        2 => Style::default().bg(theme.bg),
        _ => Style::default().fg(theme.fg).bg(theme.panel_bg), // Monokai dark grey status bar (#1c1a1d)
    };
    
    let paragraph = Paragraph::new(rows)
        .style(style)
        .alignment(Alignment::Center);

    f.render_widget(paragraph, area);
}

fn draw_loading_overlay(f: &mut Frame, app: &App) {
    let theme = app.theme;
    
    // Draw in center of screen
    let area = centered_rect(50, 20, f.area());
    f.render_widget(Clear, area);

    // Make custom spinning icon
    let tick = (app.info_msg_ticks % 4) as usize;
    let spinners = [" / ", " - ", " \\ ", " | "];
    let spin = spinners[tick];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(Style::default().fg(theme.active_tab))
        .style(Style::default().bg(theme.panel_bg))
        .title(" Please Wait ");

    let content = format!(
        "\n  {} {}\n\n  Processing background task...",
        spin, app.loading_msg
    );
    let paragraph = Paragraph::new(content)
        .block(block)
        .style(Style::default().fg(theme.fg))
        .alignment(Alignment::Center);

    f.render_widget(paragraph, area);
}

fn calculate_instant_score_and_grade(
    data: &crate::types::CourseData,
    editing_student_id: &str,
    editing_column: &str,
    new_value_str: &str,
) -> (f64, String) {
    let record = match data.raw_scores.iter().find(|r| {
        r.get("Student ID").and_then(|v| v.as_str()) == Some(editing_student_id)
    }) {
        Some(r) => r,
        None => return (0.0, "F".to_string()),
    };

    let new_val_parsed = match new_value_str.trim().to_uppercase().as_str() {
        "P" | "EA" | "X" => Some(1.0),
        "L" => Some(0.8),
        "A" => Some(0.0),
        "" => Some(0.0),
        other => other.parse::<f64>().ok(),
    };

    let get_val = |col: &str| -> f64 {
        if col == editing_column {
            return new_val_parsed.unwrap_or(0.0);
        }
        if let Some(v) = record.get(col) {
            match v {
                serde_json::Value::Number(n) => n.as_f64().unwrap_or(0.0),
                serde_json::Value::String(s) => match s.trim().to_uppercase().as_str() {
                    "P" | "EA" | "X" => 1.0,
                    "L" => 0.8,
                    "A" => 0.0,
                    other => other.parse::<f64>().unwrap_or(0.0),
                },
                _ => 0.0,
            }
        } else {
            0.0
        }
    };

    let mut coursework_total = 0.0;
    let mut midterm_pct = 0.0;
    let mut final_pct = 0.0;

    let drop_lowest_homework = if let Some(ref rules) = data.rules {
        rules.get("drop_lowest_homework")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    } else {
        false
    };

    for (category, weight) in &data.weights {
        let columns = match data.data_mapping.get(category) {
            Some(cols) => cols,
            None => continue,
        };
        if columns.is_empty() {
            continue;
        }

        let cat_lower = category.to_lowercase();
        
        let category_pct = if cat_lower == "attendance" {
            let sum: f64 = columns.iter().map(|col| {
                if col == editing_column {
                    new_val_parsed.unwrap_or(0.0)
                } else if let Some(v) = record.get(col) {
                    match v {
                        serde_json::Value::String(s) => match s.trim().to_uppercase().as_str() {
                            "P" | "EA" | "X" => 1.0,
                            "L" => 0.8,
                            "A" => 0.0,
                            _ => 0.0,
                        },
                        _ => 0.0,
                    }
                } else {
                    0.0
                }
            }).sum();
            let possible_max = columns.len() as f64;
            if possible_max > 0.0 { sum / possible_max } else { 0.0 }
        } else if cat_lower == "homework" && drop_lowest_homework && columns.len() > 1 {
            let mut lowest_idx: Option<usize> = None;
            let mut lowest_pct = f64::MAX;
            for (idx, col) in columns.iter().enumerate() {
                let score = get_val(col);
                let max_s = data.max_scores.get(col).cloned().unwrap_or(100.0);
                let pct = if max_s > 0.0 { score / max_s } else { 0.0 };
                if pct < lowest_pct {
                    lowest_pct = pct;
                    lowest_idx = Some(idx);
                }
            }

            let mut sum = 0.0;
            let mut possible_max = 0.0;
            for (idx, col) in columns.iter().enumerate() {
                if Some(idx) == lowest_idx {
                    continue;
                }
                sum += get_val(col);
                possible_max += data.max_scores.get(col).cloned().unwrap_or(100.0);
            }
            if possible_max > 0.0 { sum / possible_max } else { 0.0 }
        } else {
            let sum: f64 = columns.iter().map(|col| get_val(col)).sum();
            let possible_max: f64 = columns.iter().map(|col| data.max_scores.get(col).cloned().unwrap_or(100.0)).sum();
            if possible_max > 0.0 { sum / possible_max } else { 0.0 }
        };

        let category_weighted = category_pct * 100.0 * weight;

        if cat_lower == "midterm" {
            midterm_pct = category_weighted;
        } else if cat_lower == "final" {
            final_pct = category_weighted;
        } else {
            coursework_total += category_weighted;
        }
    }

    let cw_rounded = coursework_total.ceil();
    let midterm_rounded = midterm_pct.ceil();
    let final_rounded = final_pct.ceil();

    let final_score = cw_rounded + midterm_rounded + final_rounded;
    let final_score_int = final_score.round() as i64;

    let mut sorted_bounds: Vec<(&String, &f64)> = data.grade_boundaries.iter().collect();
    sorted_bounds.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap_or(std::cmp::Ordering::Equal));
    
    let mut grade = "F".to_string();
    for (g, threshold) in sorted_bounds {
        if final_score_int as f64 >= *threshold {
            grade = g.clone();
            break;
        }
    }

    (final_score, grade)
}

fn draw_settings_overlay(f: &mut Frame, app: &mut App) {
    let theme = app.theme;
    let area = centered_rect(55, 60, f.area());
    f.render_widget(Clear, area);

    let title = if app.editing_weights { " Edit Category Weights (Sum must be 1.0) " } else { " Edit Grade Boundaries " };
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(Style::default().fg(theme.info))
        .style(Style::default().bg(theme.panel_bg))
        .title(title);

    f.render_widget(block, area);

    // Draw fields inside overlay
    let inner_area = area;
    let vertical_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2), // Top margin
            Constraint::Min(4),    // Fields
            Constraint::Length(3), // Footer buttons
        ])
        .split(inner_area);

    // Layout each key/value field
    let field_count = app.settings_keys.len();
    let mut constraints = vec![];
    for _ in 0..field_count {
        constraints.push(Constraint::Length(3));
    }
    let field_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints(constraints)
        .split(vertical_chunks[1]);

    for i in 0..field_count {
        let field_area = field_chunks[i];
        
        // Split key and value field
        let row_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
            .split(field_area);

        // Renders label
        let label = format!("  {:<15} : ", app.settings_keys[i]);
        let label_style = if i == app.settings_index {
            Style::default().fg(theme.active_tab).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(theme.fg)
        };
        let label_p = Paragraph::new(label).style(label_style);
        f.render_widget(label_p, row_chunks[0]);

        // Renders text area widget
        let ta = &mut app.settings_textareas[i];
        let ta_border_color = if i == app.settings_index { theme.active_tab } else { theme.border };
        ta.set_block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(ta_border_color))
        );
        f.render_widget(ta.widget(), row_chunks[1]);
    }

    // Draw buttons bottom
    let footer_block = Block::default()
        .borders(Borders::TOP)
        .border_style(Style::default().fg(theme.border))
        .style(Style::default().bg(theme.panel_bg));
    let buttons_text = " [Enter] Save Configuration    [Esc] Cancel Changes ";
    let buttons_p = Paragraph::new(buttons_text)
        .block(footer_block)
        .style(Style::default().fg(theme.fg))
        .alignment(Alignment::Center);
    f.render_widget(buttons_p, vertical_chunks[2]);
}

fn draw_attendance_picker(f: &mut Frame, app: &mut App) {
    let theme = app.theme;
    let area = centered_rect(36, 48, f.area());
    f.render_widget(Clear, area);

    let col_name = app.editing_column.clone();
    let student_name = app.course_data.as_ref()
        .and_then(|d| d.raw_scores.get(app.cursor_row))
        .and_then(|r| r.get("Name").and_then(|v| v.as_str()).map(|s| s.to_string()))
        .unwrap_or_default();

    let title = format!(" Attendance  {}  {} ", col_name, student_name);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(Style::default().fg(theme.active_tab))
        .style(Style::default().bg(theme.panel_bg))
        .title(title)
        .title_style(Style::default().fg(theme.key_accent).bold());

    let options: &[(&str, &str, Color)] = &[
        ("P", "Present", theme.success),
        ("L", "Late",    theme.warning),
        ("X", "Excused", theme.key_accent),
        ("A", "Absent",  theme.grade_f),
        ("",  "Clear",   theme.inactive_tab),
    ];
    let mut items: Vec<ListItem> = options.iter().enumerate().map(|(i, &(code, label, opt_color))| {
        let selected = i == app.attendance_index;
        let bullet = if selected { "●" } else { "○" };
        let tag = if code.is_empty() {
            String::new()
        } else {
            format!("  [{}]", code)
        };
        let line = Line::from(vec![
            Span::raw("  "),
            Span::styled(format!("{} {}{}", bullet, label, tag),
                if selected {
                    Style::default().fg(opt_color).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(theme.fg)
                }),
            Span::raw("  "),
        ]);
        ListItem::new(line)
    }).collect();

    // Key-hint row at the bottom of the list
    items.push(ListItem::new(Line::from(Span::styled(
        "  P L X A / C  ·  ↑↓ nav  ·  Enter  ·  Esc  ",
        Style::default().fg(theme.inactive_tab),
    ))));

    let list = List::new(items).block(block);
    f.render_widget(list, area);
}

/// A centred rect of fixed size (clamped to the screen).
fn fixed_centered(width: u16, height: u16, r: Rect) -> Rect {
    let w = width.min(r.width.saturating_sub(2));
    let h = height.min(r.height.saturating_sub(2));
    Rect { x: r.x + (r.width - w) / 2, y: r.y + (r.height - h) / 2, width: w, height: h }
}

/// Text with a ▏ cursor, for single-line inputs drawn inside a Line.
fn input_text(ta: &tui_textarea::TextArea, focused: bool) -> String {
    let mut chars: Vec<char> = ta.lines()[0].chars().collect();
    if focused {
        let (_, cur) = ta.cursor();
        chars.insert(cur.min(chars.len()), '▏');
    }
    chars.into_iter().collect()
}

fn draw_fill_dialog(f: &mut Frame, app: &mut App) {
    let theme = app.theme;
    let Some(fill) = app.fill.as_ref() else { return };
    let n_students = app.course_data.as_ref().map(|d| d.raw_scores.len()).unwrap_or(0);
    let max_text = app.max_of(&fill.column).map(|m| format!(" ({:.0} pts)", m)).unwrap_or_default();

    let label = |field: crate::app::FillField, text: &str| {
        if fill.focus == field {
            Span::styled(format!("▶ {}", text), Style::default().fg(theme.active_tab).add_modifier(Modifier::BOLD))
        } else {
            Span::styled(format!("  {}", text), Style::default().fg(theme.key_accent))
        }
    };
    let radio = |on: bool, text: String| {
        Span::styled(
            format!("{} {}   ", if on { "(•)" } else { "( )" }, text),
            if on { Style::default().fg(theme.success).add_modifier(Modifier::BOLD) } else { Style::default().fg(theme.fg) },
        )
    };
    use crate::app::{FillField, FillTarget};

    let mut lines = vec![Line::from("")];
    let mut target_spans = vec![label(FillField::Target, "Students: ")];
    for t in fill.targets() {
        let text = match t {
            FillTarget::All => format!("All {}", n_students),
            FillTarget::Marked => format!("Marked {}", app.marks.len()),
            FillTarget::Rows => "Rows".to_string(),
            FillTarget::Group => "Class Group".to_string(),
        };
        target_spans.push(radio(fill.target == t, text));
    }
    lines.push(Line::from(target_spans));
    match fill.target {
        FillTarget::Rows => lines.push(Line::from(vec![
            label(FillField::Rows, "Rows:     "),
            Span::styled(format!("[{}]", input_text(&fill.rows, fill.focus == FillField::Rows)), Style::default().fg(theme.info)),
            Span::styled("  e.g. 1-10, 15  (the # column)", Style::default().fg(theme.inactive_tab)),
        ])),
        FillTarget::Group => {
            let mut spans = vec![label(FillField::Groups, "Groups:   ")];
            for (i, (g, on)) in fill.groups.iter().enumerate() {
                let mut st = if *on { Style::default().fg(theme.success).bold() } else { Style::default().fg(theme.fg) };
                if fill.focus == FillField::Groups && i == fill.group_cursor {
                    st = st.add_modifier(Modifier::REVERSED);
                }
                spans.push(Span::styled(format!("[{}] {}", if *on { "x" } else { " " }, g), st));
                spans.push(Span::raw("   "));
            }
            lines.push(Line::from(spans));
        }
        _ => lines.push(Line::from("")),
    }
    lines.push(Line::from(vec![
        label(FillField::OnlyEmpty, ""),
        Span::styled(
            format!("[{}] Only empty cells", if fill.only_empty { "x" } else { " " }),
            if fill.only_empty { Style::default().fg(theme.success).bold() } else { Style::default().fg(theme.fg) },
        ),
    ]));
    let mut value_spans = vec![label(FillField::Value, "Value:    ")];
    if fill.is_attendance {
        for (i, (code, name)) in [("P", "Present"), ("L", "Late"), ("X", "Excused"), ("A", "Absent"), ("", "Clear")].iter().enumerate() {
            let text = if code.is_empty() { name.to_string() } else { format!("{} {}", code, name) };
            value_spans.push(radio(i == fill.attendance_index, text));
        }
    } else {
        value_spans.push(Span::styled(
            format!("[{:<8}]", input_text(&fill.value, fill.focus == FillField::Value)),
            Style::default().fg(theme.info).bold(),
        ));
        value_spans.push(Span::styled(format!("{}  number, - for {}", max_text, ABSENT), Style::default().fg(theme.inactive_tab)));
    }
    lines.push(Line::from(value_spans));
    lines.push(Line::from(""));
    lines.push(match app.fill_rows() {
        Ok(rows) => Line::from(Span::styled(
            format!("  → {} cell{} will be set (unsaved until Ctrl+S)", rows.len(), if rows.len() == 1 { "" } else { "s" }),
            Style::default().fg(theme.success).bold(),
        )),
        Err(msg) => Line::from(Span::styled(format!("  ⚠ {}", msg), Style::default().fg(theme.grade_f).bold())),
    });

    let area = fixed_centered(84, lines.len() as u16 + 2, f.area());
    f.render_widget(Clear, area);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(Style::default().fg(theme.warning))
        .style(Style::default().bg(theme.panel_bg))
        .title(format!(" Fill Column: {}{} ", fill.column, max_text))
        .title_style(Style::default().fg(theme.key_accent).bold());
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn draw_confirm_leave(f: &mut Frame, app: &mut App) {
    let theme = app.theme;
    let Some(action) = app.confirm_leave else { return };
    let over = app.edits.over_max(|c| app.max_of(c));
    let verb = match action {
        crate::app::LeaveAction::Quit => "quit",
        crate::app::LeaveAction::CourseSelect => "leave course",
    };
    let lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            format!(
                "  {} unsaved score{}{}.",
                app.edits.len(),
                if app.edits.len() == 1 { "" } else { "s" },
                if over > 0 { format!(" ({} above max)", over) } else { String::new() }
            ),
            Style::default().fg(theme.warning).bold(),
        )),
        Line::from(""),
        Line::from(vec![
            Span::styled("  [S] ", Style::default().fg(theme.success).bold()),
            Span::raw(format!("Save and {}   ", verb)),
            Span::styled("[D] ", Style::default().fg(theme.grade_f).bold()),
            Span::raw(format!("Discard and {}", verb)),
        ]),
        Line::from(vec![
            Span::styled("  [Esc] ", Style::default().fg(theme.key_accent).bold()),
            Span::raw("Keep editing"),
        ]),
    ];
    let area = fixed_centered(56, lines.len() as u16 + 2, f.area());
    f.render_widget(Clear, area);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(Style::default().fg(theme.warning))
        .style(Style::default().bg(theme.panel_bg))
        .title(" Unsaved changes ")
        .title_style(Style::default().fg(theme.warning).bold());
    f.render_widget(Paragraph::new(lines).block(block), area);
}

// Helper to center overlay rects on the terminal screen
fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}

fn format_thai_name(name: &str, target_first_name_width: usize) -> String {
    let parts: Vec<&str> = name.split_whitespace().collect();
    if parts.len() >= 2 {
        let first_name = parts[0];
        let surname = parts[1..].join(" ");
        let first_width = UnicodeWidthStr::width(first_name);
        let padding = if first_width < target_first_name_width {
            target_first_name_width - first_width
        } else {
            1
        };
        format!("{}{}{}", first_name, " ".repeat(padding), surname)
    } else {
        name.to_string()
    }
}

fn grade_color_for(grade: &str, theme: &crate::style::Theme) -> ratatui::style::Color {
    match grade.trim() {
        g if g.starts_with("A") => theme.grade_a,
        "B+"                    => theme.grade_bplus,
        g if g.starts_with("B") => theme.grade_b,
        "C+"                    => theme.grade_cplus,
        g if g.starts_with("C") => theme.grade_c,
        "D+"                    => theme.grade_dplus,
        g if g.starts_with("D") => theme.grade_d,
        _                       => theme.grade_f,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn legend() -> Vec<Span<'static>> {
        vec![
            Span::raw(" [Tab] "), Span::raw("Next Tab  "),       // 17
            Span::raw(" [Esc] "), Span::raw("Courses Menu  "),   // 21
            Span::raw(" [s] "), Span::raw("Hide Panel  "),       // 17
            Span::raw(" [e] "), Span::raw("Export CSV  "),       // 17
        ]
    }

    fn texts(lines: &[Line]) -> Vec<String> {
        lines.iter().map(|l| l.spans.iter().map(|s| s.content.as_ref()).collect()).collect()
    }

    #[test]
    fn wide_terminal_keeps_one_row() {
        let lines = wrap_legend(legend(), 200);
        assert_eq!(lines.len(), 1);
    }

    #[test]
    fn narrow_terminal_wraps_whole_items_into_rows() {
        let lines = wrap_legend(legend(), 40);
        assert_eq!(
            texts(&lines),
            vec![
                " [Tab] Next Tab   [Esc] Courses Menu".to_string(),
                " [s] Hide Panel   [e] Export CSV".to_string(),
            ]
        );
    }

    #[test]
    fn rows_never_split_a_key_from_its_label() {
        for width in 20..60 {
            for line in wrap_legend(legend(), width) {
                assert!(line.spans.len() % 2 == 0, "width {width}: {:?}", texts(&[line]));
                assert!(line.width() <= width as usize, "width {width}");
            }
        }
    }

    fn render(width: u16, height: u16) -> Vec<String> {
        let (tx, _rx) = tokio::sync::mpsc::channel(8);
        let mut app = App::new(tx);
        app.state = AppState::Dashboard;
        let mut terminal = ratatui::Terminal::new(ratatui::backend::TestBackend::new(width, height)).unwrap();
        terminal.draw(|f| draw(f, &mut app)).unwrap();
        let buf = terminal.backend().buffer().clone();
        (0..height)
            .map(|y| (0..width).map(|x| buf[(x, y)].symbol().to_string()).collect())
            .collect()
    }

    fn screen(app: &mut App, width: u16, height: u16) -> Vec<String> {
        let mut terminal = ratatui::Terminal::new(ratatui::backend::TestBackend::new(width, height)).unwrap();
        terminal.draw(|f| draw(f, app)).unwrap();
        let buf = terminal.backend().buffer().clone();
        (0..height)
            .map(|y| (0..width).map(|x| buf[(x, y)].symbol().to_string()).collect())
            .collect()
    }

    fn raw_details_app() -> App {
        let (tx, _rx) = tokio::sync::mpsc::channel(8);
        let mut app = App::new(tx);
        app.state = AppState::Dashboard;
        app.course_data = Some(serde_json::from_str(include_str!("../tests/fixtures/course.json")).unwrap());
        app.active_tab = 1;
        app.raw_category_index = app.get_categories().iter().position(|c| c == "homework").unwrap();
        app.sync_raw_category();
        app.raw_right_focused = true;
        app.cursor_col = 2;
        app
    }

    fn key(app: &mut App, code: crossterm::event::KeyCode) {
        app.update(crate::app::AppEvent::Key(crossterm::event::KeyEvent::new(code, crossterm::event::KeyModifiers::NONE)));
    }

    #[test]
    fn unsaved_edits_marks_editor_fill_and_prompt_render() {
        use crossterm::event::KeyCode;
        let mut app = raw_details_app();
        key(&mut app, KeyCode::Char(' '));
        for c in "12".chars() { key(&mut app, KeyCode::Char(c)); }
        key(&mut app, KeyCode::Enter);
        for c in "8.".chars() { key(&mut app, KeyCode::Char(c)); }
        app.info_msg = None; // the 3-second "above the maximum" note would cover the legend
        let s = screen(&mut app, 140, 30);
        if std::env::var("SHOW").is_ok() { eprintln!("{}", s.join("\n")); }
        let all = s.join("\n");
        assert!(all.contains("● 1 unsaved"));
        assert!(all.contains("▸1"), "marked row");
        assert!(all.contains("8.▏"), "inline editor in the cell");
        assert!(all.contains("Editing hw1"));

        key(&mut app, KeyCode::Esc);
        key(&mut app, KeyCode::Char('f'));
        let s = screen(&mut app, 140, 30);
        if std::env::var("SHOW").is_ok() { eprintln!("{}", s.join("\n")); }
        let all = s.join("\n");
        assert!(all.contains("Fill Column: hw1") && all.contains("Marked 1") && all.contains("Class Group"));

        key(&mut app, KeyCode::Esc);
        key(&mut app, KeyCode::Char('q'));
        let s = screen(&mut app, 140, 30);
        if std::env::var("SHOW").is_ok() { eprintln!("{}", s.join("\n")); }
        let all = s.join("\n");
        assert!(all.contains("1 unsaved score (1 above max)"));
        assert!(all.contains("Save and quit"));
    }

    #[tokio::test]
    async fn saving_shows_in_the_footer_not_as_a_blocking_overlay() {
        use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
        let mut app = raw_details_app();
        key(&mut app, KeyCode::Char('5'));
        key(&mut app, KeyCode::Enter);
        app.update(crate::app::AppEvent::Key(KeyEvent::new(KeyCode::Char('s'), KeyModifiers::CONTROL)));
        assert!(app.loading);
        let all = screen(&mut app, 140, 30).join("\n");
        assert!(!all.contains("Please Wait"), "no overlay over the table");
        assert!(all.contains("Saving 1 cell"));
    }

    #[test]
    fn narrow_window_shows_every_legend_item_on_extra_rows() {
        let wide = render(220, 30);
        assert!(wide[29].contains("Export CSV") && !wide[28].contains("Next Tab"));

        let narrow = render(60, 30);
        let footer = narrow[26..].join("\n");
        for label in ["Next Tab", "Courses Menu", "Hide Panel", "Export CSV", "Edit Weights", "Edit Boundaries"] {
            assert!(footer.contains(label), "missing {label} in:\n{footer}");
        }
    }

    #[test]
    fn long_message_wraps_by_words() {
        let spans = vec![
            Span::raw(" ℹ️ INFO "),
            Span::raw(" Exported final_grades.csv and copy_friendly_scores.csv to reports "),
        ];
        let lines = wrap_legend(spans, 30);
        assert!(lines.len() >= 3);
        assert!(lines.iter().all(|l| l.width() <= 30));
    }
}
