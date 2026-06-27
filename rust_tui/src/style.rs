use ratatui::style::Color;
use std::path::PathBuf;

#[derive(Clone, Copy)]
pub struct Theme {
    pub bg: Color,
    pub fg: Color,
    pub panel_bg: Color,                  // Monokai Pro Dark Panel/Overlay (Index 233)
    pub border: Color,
    pub border_focus: Color,
    pub active_tab: Color,
    pub inactive_tab: Color,
    pub warning: Color,
    pub success: Color,
    pub info: Color,
    pub highlight: Color,
    pub key_accent: Color,
    pub purple: Color,                    // Monokai Pro signature Purple (Index 141)
    pub alt_row: Color,
    pub title: Color,
    // Per-grade colors: A, B+, B, C+, C, D+, D, F
    pub grade_a: Color,
    pub grade_bplus: Color,
    pub grade_b: Color,
    pub grade_cplus: Color,
    pub grade_c: Color,
    pub grade_dplus: Color,
    pub grade_d: Color,
    pub grade_f: Color,
}

pub const MONOKAI_PRO: Theme = Theme {
    bg: Color::Indexed(235),              // Monokai Pro charcoal grey (#262626)
    fg: Color::Indexed(252),              // Monokai Pro soft white foreground (#d0d0d0)
    panel_bg: Color::Indexed(233),         // Monokai Pro Dark Panel/Overlay (#121212)
    border: Color::Indexed(243),          // Monokai Pro comment gray (#767676)
    border_focus: Color::Indexed(197),    // Monokai Pro Red/Pink (#ff005f)
    active_tab: Color::Indexed(81),       // Monokai Pro Cyan (#5fd7ff)
    inactive_tab: Color::Indexed(243),     // Monokai Pro comment gray
    warning: Color::Indexed(208),         // Monokai Pro Orange (#ff8700)
    success: Color::Indexed(114),         // Monokai Pro Green (#87d787)
    info: Color::Indexed(81),             // Monokai Pro Cyan
    highlight: Color::Indexed(237),        // Selection row focus (slightly lighter grey #3a3a3a)
    key_accent: Color::Indexed(221),      // Monokai Pro Yellow (#ffd75f)
    purple: Color::Indexed(141),          // Monokai Pro Purple (#af87ff)
    alt_row: Color::Indexed(234),         // Alternating zebra row (#1c1c1c)
    title: Color::Indexed(197),           // Monokai Pro Red/Pink

    // Per-grade heat-map palette (Blue → Red)
    grade_a:     Color::Indexed(33),      // Blue          (#0087ff)
    grade_bplus: Color::Indexed(37),      // Blue-Green    (#00afaf)
    grade_b:     Color::Indexed(82),      // Green         (#5fd700)
    grade_cplus: Color::Indexed(154),     // Green-Yellow  (#afd700)
    grade_c:     Color::Indexed(226),     // Yellow        (#ffff00)
    grade_dplus: Color::Indexed(214),     // Yellow-Orange (#ffaf00)
    grade_d:     Color::Indexed(208),     // Orange        (#ff8700)
    grade_f:     Color::Indexed(160),     // Darker-Red    (#d70000)
};

fn parse_json_color(val: &serde_json::Value) -> Option<Color> {
    match val {
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_u64() {
                if i <= 255 {
                    return Some(Color::Indexed(i as u8));
                }
            }
            None
        }
        serde_json::Value::String(s) => {
            if s.starts_with('#') && s.len() == 7 {
                let r = u8::from_str_radix(&s[1..3], 16).ok()?;
                let g = u8::from_str_radix(&s[3..5], 16).ok()?;
                let b = u8::from_str_radix(&s[5..7], 16).ok()?;
                return Some(Color::Rgb(r, g, b));
            }
            None
        }
        serde_json::Value::Array(arr) => {
            if arr.len() == 3 {
                let r = arr[0].as_u64()? as u8;
                let g = arr[1].as_u64()? as u8;
                let b = arr[2].as_u64()? as u8;
                return Some(Color::Rgb(r, g, b));
            }
            None
        }
        _ => None
    }
}

pub fn load_theme() -> Theme {
    let mut theme = MONOKAI_PRO;

    // Search locations:
    // 1. Same directory as the executable
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()));

    let mut paths = vec![];
    if let Some(d) = exe_dir {
        paths.push(d.join("theme.json"));
    }

    // 2. ~/.config/grade_dashboard/theme.json
    if let Ok(home) = std::env::var("HOME") {
        paths.push(PathBuf::from(home).join(".config").join("grade_dashboard").join("theme.json"));
    }

    for path in paths {
        if path.exists() {
            if let Ok(content) = std::fs::read_to_string(&path) {
                if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let Some(obj) = json_val.as_object() {
                        if let Some(val) = obj.get("bg").and_then(parse_json_color) { theme.bg = val; }
                        if let Some(val) = obj.get("fg").and_then(parse_json_color) { theme.fg = val; }
                        if let Some(val) = obj.get("panel_bg").and_then(parse_json_color) { theme.panel_bg = val; }
                        if let Some(val) = obj.get("border").and_then(parse_json_color) { theme.border = val; }
                        if let Some(val) = obj.get("border_focus").and_then(parse_json_color) { theme.border_focus = val; }
                        if let Some(val) = obj.get("active_tab").and_then(parse_json_color) { theme.active_tab = val; }
                        if let Some(val) = obj.get("inactive_tab").and_then(parse_json_color) { theme.inactive_tab = val; }
                        if let Some(val) = obj.get("warning").and_then(parse_json_color) { theme.warning = val; }
                        if let Some(val) = obj.get("success").and_then(parse_json_color) { theme.success = val; }
                        if let Some(val) = obj.get("info").and_then(parse_json_color) { theme.info = val; }
                        if let Some(val) = obj.get("highlight").and_then(parse_json_color) { theme.highlight = val; }
                        if let Some(val) = obj.get("key_accent").and_then(parse_json_color) { theme.key_accent = val; }
                        if let Some(val) = obj.get("purple").and_then(parse_json_color) { theme.purple = val; }
                        if let Some(val) = obj.get("alt_row").and_then(parse_json_color) { theme.alt_row = val; }
                        if let Some(val) = obj.get("title").and_then(parse_json_color) { theme.title = val; }

                        if let Some(val) = obj.get("grade_a").and_then(parse_json_color)     { theme.grade_a = val; }
                        if let Some(val) = obj.get("grade_bplus").and_then(parse_json_color) { theme.grade_bplus = val; }
                        if let Some(val) = obj.get("grade_b").and_then(parse_json_color)     { theme.grade_b = val; }
                        if let Some(val) = obj.get("grade_cplus").and_then(parse_json_color) { theme.grade_cplus = val; }
                        if let Some(val) = obj.get("grade_c").and_then(parse_json_color)     { theme.grade_c = val; }
                        if let Some(val) = obj.get("grade_dplus").and_then(parse_json_color) { theme.grade_dplus = val; }
                        if let Some(val) = obj.get("grade_d").and_then(parse_json_color)     { theme.grade_d = val; }
                        if let Some(val) = obj.get("grade_f").and_then(parse_json_color)     { theme.grade_f = val; }

                        break;
                    }
                }
            }
        }
    }

    theme
}
