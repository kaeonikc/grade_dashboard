//! Unsaved score edits (SPEC_batch_editing.md): typed cells and fills collect here and are
//! written together on Ctrl+S. Pure bookkeeping — no I/O, no UI.

use std::collections::HashMap;

use crate::types::SaveReport;

/// "ขส": absent (src/cells.py ABSENT).
pub const ABSENT: &str = "ขส";

/// (student id, column)
pub type CellKey = (String, String);

#[derive(Debug, Clone, PartialEq)]
pub struct PendingCell {
    /// What will be written.
    pub value: String,
    /// What the file held when the edit started; the save skips the cell if the file changed since.
    pub original: String,
}

#[derive(Debug, Default)]
pub struct Edits {
    cells: HashMap<CellKey, PendingCell>,
    /// One step per typed cell or per fill: each key with the pending state it had before.
    undo: Vec<Vec<(CellKey, Option<PendingCell>)>>,
}

impl Edits {
    pub fn len(&self) -> usize {
        self.cells.len()
    }

    pub fn is_empty(&self) -> bool {
        self.cells.is_empty()
    }

    pub fn get(&self, student_id: &str, column: &str) -> Option<&PendingCell> {
        self.cells.get(&(student_id.to_string(), column.to_string()))
    }

    /// Sets cells as one undo step. Each item is (student id, column, new value, value as loaded).
    /// Setting a cell back to what the file holds drops it from the unsaved list.
    /// Returns how many cells actually changed.
    pub fn set(&mut self, items: Vec<(String, String, String, String)>) -> usize {
        let mut step = Vec::new();
        for (sid, col, value, loaded) in items {
            let key = (sid, col);
            let prev = self.cells.get(&key).cloned();
            let original = prev.as_ref().map(|p| p.original.clone()).unwrap_or(loaded);
            let next = if same_value(&value, &original) {
                None
            } else {
                Some(PendingCell { value, original })
            };
            if next == prev {
                continue;
            }
            match next {
                Some(cell) => self.cells.insert(key.clone(), cell),
                None => self.cells.remove(&key),
            };
            step.push((key, prev));
        }
        let n = step.len();
        if n > 0 {
            self.undo.push(step);
        }
        n
    }

    /// Reverses the last typed cell or fill. False when there is nothing to undo.
    pub fn undo(&mut self) -> bool {
        let Some(step) = self.undo.pop() else { return false };
        for (key, prev) in step.into_iter().rev() {
            match prev {
                Some(cell) => self.cells.insert(key, cell),
                None => self.cells.remove(&key),
            };
        }
        true
    }

    pub fn clear(&mut self) {
        self.cells.clear();
        self.undo.clear();
    }

    /// The cells to send, sorted so saves are deterministic.
    pub fn snapshot(&self) -> Vec<(CellKey, PendingCell)> {
        let mut v: Vec<_> = self.cells.iter().map(|(k, c)| (k.clone(), c.clone())).collect();
        v.sort_by(|a, b| a.0.cmp(&b.0));
        v
    }

    /// `{"edits": [...]}` for `tui_api.py apply-edits`.
    pub fn to_json(sent: &[(CellKey, PendingCell)]) -> String {
        let edits: Vec<_> = sent
            .iter()
            .map(|((sid, col), c)| {
                serde_json::json!({"student_id": sid, "column": col, "value": c.value, "original": c.original})
            })
            .collect();
        serde_json::json!({ "edits": edits }).to_string()
    }

    /// After a save: cells that were sent and not reported are written, so they leave the list.
    /// A cell that changed on disk stays, now based on the disk value, so the next save writes it
    /// on purpose. Undo history ends at a save.
    pub fn settle(&mut self, sent: &[(CellKey, PendingCell)], report: &SaveReport) {
        let conflicts: HashMap<CellKey, &crate::types::Conflict> = report
            .conflicts
            .iter()
            .map(|c| ((c.student_id.clone(), c.column.clone()), c))
            .collect();
        for (key, cell) in sent {
            if self.cells.get(key) != Some(cell) {
                continue; // changed again while saving: keep the newer edit
            }
            match conflicts.get(key) {
                None => {
                    self.cells.remove(key);
                }
                Some(c) if c.reason == "changed" => {
                    let disk = c.disk_value.clone().unwrap_or_default();
                    if same_value(&cell.value, &disk) {
                        self.cells.remove(key);
                    } else if let Some(p) = self.cells.get_mut(key) {
                        p.original = disk;
                    }
                }
                Some(_) => {}
            }
        }
        self.undo.clear();
    }

    /// How many unsaved values are above their column's maximum.
    pub fn over_max(&self, max_of: impl Fn(&str) -> Option<f64>) -> usize {
        self.cells
            .iter()
            .filter(|((_, col), c)| is_over_max(&c.value, max_of(col)))
            .count()
    }
}

/// Whether two cell texts mean the same: "8" == "8.0", " ขส " == "ขส".
pub fn same_value(a: &str, b: &str) -> bool {
    let (a, b) = (a.trim(), b.trim());
    match (a.parse::<f64>(), b.parse::<f64>()) {
        (Ok(x), Ok(y)) => x == y,
        _ => a == b,
    }
}

/// How a raw-score JSON value is shown and edited: 8.0 -> "8", 8.5 -> "8.5", null -> "".
pub fn cell_text(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::Null => String::new(),
        serde_json::Value::Number(n) => n.as_f64().map(|f| format!("{}", f)).unwrap_or_default(),
        serde_json::Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

pub fn is_over_max(value: &str, max: Option<f64>) -> bool {
    match (value.trim().parse::<f64>(), max) {
        (Ok(v), Some(m)) => v > m,
        _ => false,
    }
}

/// Checks a typed score: blank, ขส, or a number ≥ 0. Ok(true) means accepted but above the max.
pub fn validate_score(text: &str, max: Option<f64>) -> Result<bool, String> {
    let t = text.trim();
    if t.is_empty() || t == ABSENT {
        return Ok(false);
    }
    match t.parse::<f64>() {
        Ok(v) if v.is_finite() && v >= 0.0 => Ok(is_over_max(t, max)),
        Ok(_) => Err(format!("'{}' is negative; scores start at 0", t)),
        Err(_) => Err(format!("'{}' is not a score (use a number, - for {}, or blank)", t, ABSENT)),
    }
}

/// Parses "1-10, 15, 20-25" (the 1-based # column) into sorted 0-based row indices.
pub fn parse_row_ranges(text: &str, n_rows: usize) -> Result<Vec<usize>, String> {
    let mut rows = std::collections::BTreeSet::new();
    let compact: String = text.chars().filter(|c| !c.is_whitespace()).collect();
    if compact.is_empty() {
        return Err("type row numbers, e.g. 1-10, 15".to_string());
    }
    for part in compact.split(',').filter(|p| !p.is_empty()) {
        let (a, b) = match part.split_once('-') {
            Some((a, b)) => (a, b),
            None => (part, part),
        };
        let parse = |s: &str| s.parse::<usize>().map_err(|_| format!("'{}' is not a row number", part));
        let (a, b) = (parse(a)?, parse(b)?);
        if a == 0 || b == 0 || a > n_rows || b > n_rows {
            return Err(format!("rows go from 1 to {}", n_rows));
        }
        if a > b {
            return Err(format!("'{}' runs backwards", part));
        }
        rows.extend(a - 1..b);
    }
    Ok(rows.into_iter().collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Conflict;

    fn item(sid: &str, col: &str, value: &str, loaded: &str) -> (String, String, String, String) {
        (sid.into(), col.into(), value.into(), loaded.into())
    }

    #[test]
    fn typed_cell_is_pending_and_typing_the_original_back_drops_it() {
        let mut e = Edits::default();
        assert_eq!(e.set(vec![item("1", "hw1", "8.5", "7")]), 1);
        assert_eq!(e.get("1", "hw1").unwrap().value, "8.5");
        assert_eq!(e.set(vec![item("1", "hw1", "7.0", "8.5")]), 1);
        assert!(e.is_empty());
    }

    #[test]
    fn re_editing_keeps_the_first_original() {
        let mut e = Edits::default();
        e.set(vec![item("1", "hw1", "8", "7")]);
        e.set(vec![item("1", "hw1", "9", "8")]);
        assert_eq!(e.get("1", "hw1").unwrap(), &PendingCell { value: "9".into(), original: "7".into() });
    }

    #[test]
    fn undo_reverses_one_cell_or_one_whole_fill() {
        let mut e = Edits::default();
        e.set(vec![item("1", "hw1", "8", "")]);
        e.set(vec![item("1", "hw1", "0", ""), item("2", "hw1", "0", ""), item("3", "hw1", "0", "")]);
        assert_eq!(e.len(), 3);
        assert!(e.undo());
        assert_eq!(e.len(), 1);
        assert_eq!(e.get("1", "hw1").unwrap().value, "8");
        assert!(e.undo());
        assert!(e.is_empty());
        assert!(!e.undo());
    }

    #[test]
    fn settle_drops_saved_cells_and_rebases_conflicts() {
        let mut e = Edits::default();
        e.set(vec![item("1", "hw1", "8", "7"), item("2", "hw1", "9", "6"), item("3", "x", "1", "")]);
        let sent = e.snapshot();
        let report = SaveReport {
            status: "success".into(),
            saved: 1,
            files: vec![],
            conflicts: vec![
                Conflict { student_id: "2".into(), column: "hw1".into(), reason: "changed".into(), disk_value: Some("5".into()) },
                Conflict { student_id: "3".into(), column: "x".into(), reason: "not found".into(), disk_value: None },
            ],
            message: String::new(),
        };
        e.settle(&sent, &report);
        assert!(e.get("1", "hw1").is_none());
        assert_eq!(e.get("2", "hw1").unwrap().original, "5");
        assert!(e.get("3", "x").is_some());
        assert!(!e.undo(), "undo history ends at a save");
    }

    #[test]
    fn json_payload_carries_value_and_original() {
        let mut e = Edits::default();
        e.set(vec![item("69000001", "hw1", "ขส", "30")]);
        let v: serde_json::Value = serde_json::from_str(&Edits::to_json(&e.snapshot())).unwrap();
        assert_eq!(v["edits"][0]["value"], "ขส");
        assert_eq!(v["edits"][0]["original"], "30");
    }

    #[test]
    fn validation_refuses_text_and_negatives_and_flags_over_max() {
        assert_eq!(validate_score("8.5", Some(10.0)), Ok(false));
        assert_eq!(validate_score("12", Some(10.0)), Ok(true));
        assert_eq!(validate_score("", Some(10.0)), Ok(false));
        assert_eq!(validate_score("ขส", Some(10.0)), Ok(false));
        assert!(validate_score("abc", Some(10.0)).is_err());
        assert!(validate_score("-3", Some(10.0)).is_err());
        assert!(validate_score("1..5", None).is_err());
    }

    #[test]
    fn row_ranges() {
        assert_eq!(parse_row_ranges("1-3, 5", 10), Ok(vec![0, 1, 2, 4]));
        assert_eq!(parse_row_ranges(" 2 ,2-3", 10), Ok(vec![1, 2]));
        assert!(parse_row_ranges("", 10).is_err());
        assert!(parse_row_ranges("0-2", 10).is_err());
        assert!(parse_row_ranges("5-11", 10).is_err());
        assert!(parse_row_ranges("4-2", 10).is_err());
        assert!(parse_row_ranges("a", 10).is_err());
    }

    #[test]
    fn values_compare_by_meaning() {
        assert!(same_value("8", "8.0"));
        assert!(same_value(" ขส", "ขส"));
        assert!(!same_value("", "0"));
        assert_eq!(cell_text(&serde_json::json!(8.0)), "8");
        assert_eq!(cell_text(&serde_json::json!(8.5)), "8.5");
        assert_eq!(cell_text(&serde_json::Value::Null), "");
    }
}
