use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style, Stylize},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Cell, Clear, List, ListItem, Paragraph, Row, Table, Wrap},
    Frame,
};
use crate::app::{App, AppState};
// theme
use unicode_width::UnicodeWidthStr;

pub fn draw(f: &mut Frame, app: &mut App) {
    let theme = app.theme;
    
    // Clear whole screen with theme background
    let bg_block = Block::default().style(Style::default().bg(theme.bg));
    f.render_widget(bg_block, f.area());

    // Master Layout: Header + Content + Footer (Legend)
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Header
            Constraint::Min(5),    // Content Workspace
            Constraint::Length(1), // Footer (Legend)
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
    draw_footer(f, app, chunks[2]);

    // 4. Overlays
    if app.loading {
        draw_loading_overlay(f, app);
    } else if app.editing {
        draw_edit_overlay(f, app);
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
                        " ⚡  {}  |  Term: {}  |  Mode: {} ",
                        data.course_name.to_uppercase(),
                        data.term.to_uppercase(),
                        if app.use_weighted { "WEIGHTED PERCENTAGES" } else { "RAW SCORES" }
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

    let paragraph = Paragraph::new(header_text)
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
    let tab_labels = [" [1] Summary ", " [2] Raw Details ", " [3] Distribution ", " [4] Roundup "];
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
        0 => draw_summary_tab(f, app, chunks[1]),
        1 => draw_raw_details_tab(f, app, chunks[1]),
        2 => draw_distribution_tab(f, app, chunks[1]),
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

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 📋 Course Grades Summary ")
        .title_style(Style::default().fg(theme.info).bold());

    // Prepare table headers
    let header_cells = data.summary_columns.iter().map(|h| {
        if h.ends_with("_pct") {
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
        } else {
            Cell::from(format!("{}\n", h))
                .style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        }
    });
    
    let header = Row::new(header_cells).height(2).bottom_margin(1).style(Style::default().bg(theme.alt_row));

    // Prepare rows
    let rows: Vec<Row> = data
        .student_grades
        .iter()
        .enumerate()
        .map(|(r_idx, record)| {
            let cells = data.summary_columns.iter().map(|col_name| {
                let cell_val = record.get(col_name).unwrap_or(&serde_json::Value::Null);
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
                    let grade_color = if text.starts_with("A") {
                        theme.grade_a
                    } else if text.starts_with("B") {
                        theme.grade_b
                    } else if text.starts_with("C") {
                        theme.grade_c
                    } else if text.starts_with("D") {
                        theme.grade_d
                    } else if text == "F" {
                        theme.grade_f
                    } else {
                        theme.info
                    };
                    cell_style = cell_style.fg(grade_color).add_modifier(Modifier::BOLD);
                }

                Cell::from(text).style(cell_style)
            });

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
    let spacings = n_cols.saturating_sub(1);     // column_spacing(1) × (n_cols - 1)
    let fixed = 12usize + name_col_width as usize + 7;
    let score_col_width = if n_other_cols > 0 && inner_width > fixed + spacings {
        ((inner_width - fixed - spacings) / n_other_cols).max(6) as u16
    } else {
        6u16
    };

    let mut widths = vec![];
    for col_name in &data.summary_columns {
        if col_name == "Student ID" {
            widths.push(Constraint::Length(12));
        } else if col_name == "Name" {
            widths.push(Constraint::Length(name_col_width));
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

    f.render_widget(table, area);
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

    let items: Vec<ListItem> = cats
        .iter()
        .enumerate()
        .map(|(i, cat)| {
            let is_highlighted = i == app.raw_category_index;
            let style = if is_highlighted && !app.raw_right_focused {
                Style::default()
                    .fg(theme.bg)
                    .bg(theme.active_tab)
                    .add_modifier(Modifier::BOLD)
            } else if is_highlighted {
                Style::default()
                    .fg(category_color(cat, &theme))
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme.fg)
            };
            ListItem::new(format!("  {}", cat)).style(style)
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

    let grade_color = match grade_str.trim() {
        g if g.starts_with("A") => theme.grade_a,
        g if g.starts_with("B") => theme.grade_b,
        g if g.starts_with("C") => theme.grade_c,
        g if g.starts_with("D") => theme.grade_d,
        _ => theme.grade_f,
    };

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
            Some(Line::from(vec![
                Span::styled("  Total            : ", Style::default().fg(theme.key_accent)),
                Span::styled(
                    format!("{:.1} pts", total),
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
                // Truncate col name to fit wider panel
                let short_name = if col_name.chars().count() > 16 {
                    format!("{}…", &col_name.chars().take(15).collect::<String>())
                } else {
                    col_name.clone()
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

    let h_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Length(33), Constraint::Min(40)])
        .split(area);

    let left_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(h_chunks[0]);

    draw_raw_left_panel(f, app, left_chunks[0]);
    draw_student_info_panel(f, app, left_chunks[1]);
    draw_sub_column_view(f, app, h_chunks[1]);
}

fn score_value(v: &serde_json::Value) -> f64 {
    match v {
        serde_json::Value::Number(n) => n.as_f64().unwrap_or(0.0),
        serde_json::Value::String(s) => match s.trim().to_uppercase().as_str() {
            "P"  => 1.0,
            "EA" => 1.0,
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

    let sub_cols = data.data_mapping.get(&cat).cloned().unwrap_or_default();
    let show_total = true;

    let border_color = if app.raw_right_focused { category_color(&cat, &theme) } else { theme.border };
    let title_text = if app.raw_right_focused {
        format!(" 📋 Raw Details  ›  {}  —  sub-columns (Enter: open student  Esc: back) ", cat)
    } else {
        format!(" 📋 Raw Details  ›  {}  (→ / Enter: focus table) ", cat)
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .title(title_text)
        .title_style(Style::default().fg(border_color).bold());

    // Build visible column indices: frozen (0,1) + scrollable sub-cols
    let frozen_count = 2usize;
    let scroll_offset = app.scroll_col_offset.saturating_sub(frozen_count);
    let max_scroll_cols = 5usize;
    let scroll_end = std::cmp::min(scroll_offset + max_scroll_cols, sub_cols.len());
    let visible_sub: &[String] = &sub_cols[scroll_offset..scroll_end];

    // Header
    let mut header_cells = vec![
        Cell::from("Student ID\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Name\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
    ];
    for sc in visible_sub {
        let max_text = if let Some(max_s) = data.max_scores.get(sc) {
            format!("\n({:.0} pts)", max_s)
        } else {
            "\n".to_string()
        };
        header_cells.push(
            Cell::from(format!("{}{}", sc, max_text))
                .style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        );
    }
    if show_total {
        let total_max: f64 = sub_cols.iter()
            .filter_map(|sc| data.max_scores.get(sc))
            .sum();
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
        let mut cells = vec![];

        let sid = record.get("Student ID")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let mut sid_style = Style::default().fg(theme.info);
        if app.raw_right_focused && r_idx == app.cursor_row && app.cursor_col == 0 {
            sid_style = Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
        }
        cells.push(Cell::from(sid).style(sid_style));

        let name = record.get("Name")
            .map(|v| match v {
                serde_json::Value::String(s) => format_thai_name(s, 18),
                _ => v.to_string(),
            })
            .unwrap_or_default();
        let mut name_style = Style::default().fg(theme.fg);
        if app.raw_right_focused && r_idx == app.cursor_row && app.cursor_col == 1 {
            name_style = Style::default().fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
        }
        cells.push(Cell::from(name).style(name_style));

        for (sc_offset, sc) in visible_sub.iter().enumerate() {
            let cell_val = record.get(sc).unwrap_or(&serde_json::Value::Null);
            let text = match cell_val {
                serde_json::Value::Null => "".to_string(),
                serde_json::Value::Number(n) => format!("{}", n.as_f64().unwrap_or(0.0)),
                serde_json::Value::String(s) => s.clone(),
                _ => cell_val.to_string(),
            };

            let abs_col = frozen_count + scroll_offset + sc_offset;
            let mut style = Style::default().fg(theme.fg);
            if app.raw_right_focused && r_idx == app.cursor_row && abs_col == app.cursor_col {
                style = style.fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
            }
            cells.push(Cell::from(text).style(style));
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
            cells.push(
                Cell::from(format!("{:.1}", total)).style(total_style)
            );
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
    let mut widths = vec![Constraint::Length(12), Constraint::Length(28)];
    for _ in visible_sub {
        widths.push(Constraint::Length(12));
    }
    if show_total {
        widths.push(Constraint::Length(8));
    }

    let table = Table::new(rows, widths)
        .header(header)
        .block(block)
        .column_spacing(1);

    f.render_widget(table, area);
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

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(category_color(&cat, &theme)))
        .title(format!(
            " 📋 Raw Details  ›  {}  ›  {}  ({})  (Enter: edit  Esc: back) ",
            cat, name, sid
        ))
        .title_style(Style::default().fg(category_color(&cat, &theme)).bold());

    let frozen_count = 2usize;
    let scroll_offset = app.scroll_col_offset.saturating_sub(frozen_count);
    let max_scroll_cols = 5usize;
    let scroll_end = std::cmp::min(scroll_offset + max_scroll_cols, sub_cols.len());
    let visible_sub: Vec<String> = sub_cols[scroll_offset..scroll_end].to_vec();

    // Header
    let mut header_cells = vec![
        Cell::from("Student ID\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
        Cell::from("Name\n").style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD)),
    ];
    for sc in &visible_sub {
        let max_text = if let Some(max_s) = data.max_scores.get(sc) {
            format!("\n({:.0} pts)", max_s)
        } else {
            "\n".to_string()
        };
        header_cells.push(
            Cell::from(format!("{}{}", sc, max_text))
                .style(Style::default().fg(theme.key_accent).add_modifier(Modifier::BOLD))
        );
    }
    if show_total {
        let total_max: f64 = sub_cols.iter()
            .filter_map(|sc| data.max_scores.get(sc))
            .sum();
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
    cells.push(Cell::from(format_thai_name(&name, 18)).style(Style::default().fg(theme.fg)));

    for (sc_offset, sc) in visible_sub.iter().enumerate() {
        let cell_val = record.get(sc).unwrap_or(&serde_json::Value::Null);
        let text = match cell_val {
            serde_json::Value::Null => "".to_string(),
            serde_json::Value::Number(n) => format!("{}", n.as_f64().unwrap_or(0.0)),
            serde_json::Value::String(s) => s.clone(),
            _ => cell_val.to_string(),
        };

        let abs_col = frozen_count + scroll_offset + sc_offset;
        let mut style = Style::default().fg(theme.fg);
        if abs_col == app.cursor_col {
            style = style.fg(theme.bg).bg(theme.active_tab).add_modifier(Modifier::BOLD);
        }
        cells.push(Cell::from(text).style(style));
    }

    if show_total {
        let total: f64 = sub_cols.iter()
            .filter_map(|sc| record.get(sc))
            .map(|v| score_value(v))
            .sum();
        cells.push(
            Cell::from(format!("{:.1}", total))
                .style(Style::default().fg(theme.success).add_modifier(Modifier::BOLD))
        );
    }

    let row = Row::new(cells).style(Style::default().bg(theme.highlight)).height(1);

    let mut widths = vec![Constraint::Length(12), Constraint::Length(28)];
    for _ in &visible_sub {
        widths.push(Constraint::Length(12));
    }
    if show_total {
        widths.push(Constraint::Length(8));
    }

    let table = Table::new(vec![row], widths)
        .header(header)
        .block(block)
        .column_spacing(1);

    f.render_widget(table, area);
}

fn draw_distribution_tab(f: &mut Frame, app: &App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border))
        .title(" 📊 Letter Grade Distributions ")
        .title_style(Style::default().fg(theme.info).bold());

    // Split area into metrics block and ASCII bar chart block
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(30), Constraint::Percentage(70)])
        .split(area);

    // Left Panel: Total Metrics
    let mut total_students = 0;
    let mut sum_scores = 0.0;
    let mut max_score = 0.0;

    for student in &data.student_grades {
        total_students += 1;
        if let Some(val) = student.get("Final Score") {
            let val_num = val.as_f64().unwrap_or(0.0);
            sum_scores += val_num;
            if val_num > max_score {
                max_score = val_num;
            }
        }
    }
    let avg_score = if total_students > 0 { sum_scores / total_students as f64 } else { 0.0 };

    let mut metrics_lines = vec![
        Line::from(""),
        Line::from(Span::styled("  ⚡ STATISTICAL METRICS", Style::default().fg(theme.title).bold())),
        Line::from(""),
        Line::from(vec![
            Span::raw("   Total Enrolled : "),
            Span::styled(format!("{} students", total_students), Style::default().fg(theme.info).bold()),
        ]),
        Line::from(vec![
            Span::raw("   Average Score  : "),
            Span::styled(format!("{:.2} pts", avg_score), Style::default().fg(theme.key_accent).bold()),
        ]),
        Line::from(vec![
            Span::raw("   Highest Score  : "),
            Span::styled(format!("{:.2} pts", max_score), Style::default().fg(theme.success).bold()),
        ]),
        Line::from(""),
        Line::from(Span::styled("  ⚡ BOUNDARIES LIST", Style::default().fg(theme.title).bold())),
        Line::from(""),
    ];

    for (g, val) in &data.grade_boundaries {
        let g_color = if g.starts_with("A") {
            theme.grade_a
        } else if g.starts_with("B") {
            theme.grade_b
        } else if g.starts_with("C") {
            theme.grade_c
        } else if g.starts_with("D") {
            theme.grade_d
        } else {
            theme.grade_f
        };
        metrics_lines.push(Line::from(vec![
            Span::raw("   Grade "),
            Span::styled(g.clone(), Style::default().fg(g_color).bold()),
            Span::raw(" : ≥ "),
            Span::styled(format!("{:.1}", val), Style::default().fg(theme.fg)),
        ]));
    }

    let metrics_block = Block::default()
        .borders(Borders::RIGHT)
        .border_style(Style::default().fg(theme.border));
    let metrics_p = Paragraph::new(metrics_lines)
        .block(metrics_block);
    f.render_widget(metrics_p, chunks[0]);

    // Right Panel: Unicode Bar Chart
    // Sort from F to A (F at top, A at bottom matches spec)
    let mut grade_keys: Vec<String> = data.grade_boundaries.keys().cloned().collect();
    grade_keys.push("F".to_string());
    
    // Sort keys: Let's reverse alphanumeric so F is first, then D, C, B, A
    grade_keys.sort();
    
    // Find maximum count for scaling bars
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

    for g in &grade_keys {
        let stats = data.grade_distribution.get(g);
        let count = stats.map(|s| s.count).unwrap_or(0);
        let pct = stats.map(|s| s.pct).unwrap_or(0.0);

        // Scale bar to 35 character length
        let max_bar_length = 35;
        let bar_len = if max_count > 0 {
            (count * max_bar_length) / max_count
        } else {
            0
        };

        let bar_filled = "█".repeat(bar_len);
        let bar_empty = "░".repeat(max_bar_length - bar_len);
        
        let g_color = if g.starts_with("A") {
            theme.grade_a
        } else if g.starts_with("B") {
            theme.grade_b
        } else if g.starts_with("C") {
            theme.grade_c
        } else if g.starts_with("D") {
            theme.grade_d
        } else {
            theme.grade_f
        };

        let bar_line = Line::from(vec![
            Span::raw("   "),
            Span::styled(format!("{:>2}", g), Style::default().fg(g_color).bold()),
            Span::styled(" │ ", Style::default().fg(theme.border)),
            Span::styled(bar_filled, Style::default().fg(g_color)),
            Span::styled(bar_empty, Style::default().fg(theme.border)),
            Span::raw("  "),
            Span::styled(format!("{:>2} students", count), Style::default().fg(theme.fg)),
            Span::styled(format!(" ({:>4.1}%)", pct), Style::default().fg(theme.info)),
        ]);
        lines.push(bar_line);
        lines.push(Line::from(vec![
            Span::raw("      "),
            Span::styled("│", Style::default().fg(theme.border)),
        ]));
    }

    let chart_p = Paragraph::new(lines)
        .block(block);
    f.render_widget(chart_p, chunks[1]);
}

fn draw_roundup_tab(f: &mut Frame, app: &mut App, area: Rect) {
    let theme = app.theme;
    let data = match &app.course_data {
        Some(d) => d,
        None => return,
    };

    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(35), Constraint::Percentage(65)])
        .split(area);

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
    f.render_widget(left_p, chunks[0]);

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
            let orig_g_color = if stud.original_grade.starts_with("A") {
                theme.grade_a
            } else if stud.original_grade.starts_with("B") {
                theme.grade_b
            } else if stud.original_grade.starts_with("C") {
                theme.grade_c
            } else if stud.original_grade.starts_with("D") {
                theme.grade_d
            } else {
                theme.grade_f
            };
            
            let new_g_color = if stud.grade.starts_with("A") {
                theme.grade_a
            } else if stud.grade.starts_with("B") {
                theme.grade_b
            } else if stud.grade.starts_with("C") {
                theme.grade_c
            } else if stud.grade.starts_with("D") {
                theme.grade_d
            } else {
                theme.grade_f
            };

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

    f.render_widget(table, chunks[1]);
}

fn draw_footer(f: &mut Frame, app: &App, area: Rect) {
    let theme = app.theme;
    
    // Bottom status line showing helpful messages or key legends
    let (status_line, is_special) = if let Some(ref info) = app.info_msg {
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
                if app.editing {
                    vec![
                        Span::raw(" Editing Score: "),
                        Span::styled(" [Type Value] ", Style::default().fg(theme.active_tab).bold()),
                        Span::raw("  "),
                        Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()),
                        Span::raw("Save  "),
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
                    let mut leg = vec![
                        Span::styled(" [Tab] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Next Tab  "),
                        Span::styled(" [Esc] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Courses Menu  "),
                        Span::styled(" [c] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Toggle Weighted  "),
                        Span::styled(" [e] ", Style::default().fg(theme.key_accent).bold()),
                        Span::raw("Export CSV  "),
                    ];
                    if app.active_tab == 1 {
                        if app.raw_selected_student.is_some() {
                            // L2: student popup
                            leg.push(Span::styled(" [◀/▶] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Move  "));
                            leg.push(Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Edit Score  "));
                            leg.push(Span::styled(" [Esc] ", Style::default().fg(theme.warning).bold()));
                            leg.push(Span::raw("Back  "));
                        } else if app.raw_right_focused {
                            // L1: right table focused
                            leg.push(Span::styled(" [▲/▼/◀/▶] ", Style::default().fg(theme.active_tab).bold()));
                            leg.push(Span::raw("Move  "));
                            leg.push(Span::styled(" [Enter] ", Style::default().fg(theme.success).bold()));
                            leg.push(Span::raw("Open Student  "));
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

    let style = match is_special {
        1 => Style::default().bg(theme.bg),
        2 => Style::default().bg(theme.bg),
        _ => Style::default().fg(theme.fg).bg(theme.panel_bg), // Monokai dark grey status bar (#1c1a1d)
    };
    
    let paragraph = Paragraph::new(status_line)
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
        "P" | "EA" => Some(1.0),
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
                    "P" | "EA" => 1.0,
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
                            "P" | "EA" => 1.0,
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

fn draw_edit_overlay(f: &mut Frame, app: &mut App) {
    let area = centered_rect(45, 35, f.area());
    f.render_widget(Clear, area);
    
    let theme = app.theme;

    // Split vertically: 3 lines for input, remaining for student info & grades
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(0),
        ])
        .split(area);

    if let Some(ref mut ta) = app.edit_textarea {
        // Set purple border (theme.purple) for the input box
        ta.set_block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(theme.purple))
                .title(format!(" Edit Score: {} ", app.editing_column))
                .title_style(Style::default().fg(theme.purple).bold())
        );
        f.render_widget(ta.widget(), chunks[0]);
    }

    // Retrieve typed value from textarea
    let mut new_value_str = String::new();
    if let Some(ref ta) = app.edit_textarea {
        if !ta.lines().is_empty() {
            new_value_str = ta.lines()[0].clone();
        }
    }

    // Retrieve selected student's Final Score and Grade dynamically
    let mut final_score = 0.0;
    let mut grade = String::from("F");
    let mut student_name = String::new();
    let mut warning_line = None;
    if let Some(ref data) = app.course_data {
        if let Some(student) = data.student_grades.iter().find(|s| {
            s.get("Student ID").and_then(|v| v.as_str()) == Some(&app.editing_student_id)
        }) {
            student_name = student.get("Name")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
                .unwrap_or_default();
        }

        let res = calculate_instant_score_and_grade(data, &app.editing_student_id, &app.editing_column, &new_value_str);
        final_score = res.0;
        grade = res.1;

        // Check if value exceeds max score
        if let Some(&max_score) = data.max_scores.get(&app.editing_column) {
            if let Some(val) = new_value_str.trim().parse::<f64>().ok() {
                if val > max_score {
                    warning_line = Some(Line::from(vec![
                        Span::styled(" ⚠️ Warning: Score exceeds max (", Style::default().fg(theme.warning).bold()),
                        Span::styled(format!("{:.1}", max_score), Style::default().fg(theme.warning).bold()),
                        Span::styled(" pts)!", Style::default().fg(theme.warning).bold()),
                    ]));
                }
            }
        }
    }

    // Semantic grade coloring (easily notified colors)
    let grade_color = match grade.trim().to_uppercase().as_str() {
        "A" | "A+" | "A-" | "PASSED" | "P" => theme.success, // Green
        "B" | "B+" | "B-" => theme.purple,                  // Purple
        "C" | "C+" | "C-" => theme.key_accent,              // Yellow
        "D" | "D+" | "D-" => theme.warning,                 // Orange
        _ => theme.border_focus,                            // Red/Pink
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.purple)) // Match purple border
        .style(Style::default().bg(theme.panel_bg))
        .title(format!(" Student: {} ({}) ", format_thai_name(&student_name, 22), app.editing_student_id))
        .title_style(Style::default().fg(theme.key_accent).bold());

    let mut info_text = vec![
        Line::from(vec![
            Span::raw(" Current Final Score: "),
            Span::styled(format!("{:.2}", final_score), Style::default().fg(theme.active_tab).bold()),
        ]),
        Line::from(vec![
            Span::raw(" Current Grade:       "),
            Span::styled(format!(" {} ", grade), Style::default().fg(theme.bg).bg(grade_color).bold()),
        ]),
    ];

    if let Some(w_line) = warning_line {
        info_text.push(Line::raw("")); // Spacer
        info_text.push(w_line);
    }

    let paragraph = Paragraph::new(info_text)
        .block(block)
        .alignment(Alignment::Left);

    f.render_widget(paragraph, chunks[1]);
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
        if first_width < target_first_name_width {
            let padding = " ".repeat(target_first_name_width - first_width);
            format!("{}{}{}", first_name, padding, surname)
        } else {
            format!("{} {}", first_name, surname)
        }
    } else {
        name.to_string()
    }
}
