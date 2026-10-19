//! Grade letter order and the boundaries check, shared rule with the web app's `grades.js` / `save.js`
//! (`../SPEC_grade_order.md`). Pure, unit-tested.

use std::collections::BTreeMap;

/// The letter scale, highest first. `F` is never a boundary key.
pub const GRADE_SCALE: [&str; 7] = ["A", "B+", "B", "C+", "C", "D+", "D"];

/// The letters of `saved` in scale order. A letter outside the scale goes before the first letter with a lower
/// saved threshold (ties among those by key text), so the order never depends on map order.
pub fn grade_order(saved: &BTreeMap<String, f64>) -> Vec<String> {
    let mut order: Vec<String> = GRADE_SCALE
        .iter()
        .filter(|g| saved.contains_key(**g))
        .map(|g| g.to_string())
        .collect();
    let mut unknown: Vec<(&String, f64)> = saved
        .iter()
        .filter(|(k, _)| !GRADE_SCALE.contains(&k.as_str()))
        .map(|(k, v)| (k, *v))
        .collect();
    // BTreeMap iterates by key text, so a stable sort by value keeps ties in text order.
    unknown.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    for (k, v) in unknown {
        let at = order.iter().position(|g| saved[g] < v).unwrap_or(order.len());
        order.insert(at, k.clone());
    }
    order
}

/// The first letter, along `order`, that isn't strictly lower than the letter above it:
/// `B 70 must be lower than B+ 69` (the web app's wording).
pub fn boundary_problem(order: &[String], values: &BTreeMap<String, f64>) -> Option<String> {
    order.windows(2).find_map(|w| {
        let (upper, lower) = (values[&w[0]], values[&w[1]]);
        (lower >= upper).then(|| format!("{} {} must be lower than {} {}", w[1], fmt(lower), w[0], fmt(upper)))
    })
}

/// 70.0 → "70", 74.5 → "74.5".
fn fmt(x: f64) -> String {
    format!("{}", x)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn map(pairs: &[(&str, f64)]) -> BTreeMap<String, f64> {
        pairs.iter().map(|(k, v)| (k.to_string(), *v)).collect()
    }

    fn defaults() -> BTreeMap<String, f64> {
        map(&[("A", 80.0), ("B+", 75.0), ("B", 70.0), ("C+", 65.0), ("C", 60.0), ("D+", 55.0), ("D", 50.0)])
    }

    #[test]
    fn scale_order_not_map_order() {
        assert_eq!(grade_order(&defaults()), GRADE_SCALE.to_vec());
        assert_eq!(grade_order(&map(&[("A", 80.0)])), vec!["A"]);
        assert!(grade_order(&BTreeMap::new()).is_empty());
    }

    #[test]
    fn unknown_letters_by_saved_value() {
        let mut b = defaults();
        b.insert("A+".into(), 85.0);
        b.insert("E".into(), 0.0);
        let mut want = vec!["A+"];
        want.extend(GRADE_SCALE);
        want.push("E");
        assert_eq!(grade_order(&b), want);
        assert_eq!(grade_order(&map(&[("D", 50.0), ("X", 72.0), ("A", 80.0), ("B", 70.0)])), vec!["A", "X", "B", "D"]);
        assert_eq!(grade_order(&map(&[("Z", 60.0), ("Y", 60.0), ("A", 80.0)])), vec!["A", "Y", "Z"]);
    }

    #[test]
    fn descending_check() {
        let b = defaults();
        assert_eq!(boundary_problem(&grade_order(&b), &b), None);
        let mut low = b.clone();
        low.insert("B+".into(), 69.0);
        assert_eq!(boundary_problem(&grade_order(&low), &low).as_deref(), Some("B 70 must be lower than B+ 69"));
        let mut eq = b.clone();
        eq.insert("C".into(), 65.0);
        assert_eq!(boundary_problem(&grade_order(&eq), &eq).as_deref(), Some("C 65 must be lower than C+ 65"));
        let mut half = b;
        half.insert("B+".into(), 74.5);
        assert_eq!(boundary_problem(&grade_order(&half), &half), None);
    }
}
