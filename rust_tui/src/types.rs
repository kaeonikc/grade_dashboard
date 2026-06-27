use serde::Deserialize;
use std::collections::{HashMap, BTreeMap};

#[derive(Debug, Clone, Deserialize)]
pub struct Course {
    pub name: String,
    pub path: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CourseListResponse {
    pub status: String,
    pub courses: Vec<Course>,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GradeStats {
    pub count: usize,
    pub pct: f64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RoundupDist {
    pub grade: String,
    pub original: usize,
    pub rounded: usize,
    pub change: isize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ImprovedStudent {
    #[serde(rename = "Student ID")]
    pub student_id: String,
    #[serde(rename = "Name")]
    pub name: String,
    #[serde(rename = "Original Final Score")]
    pub original_final_score: f64,
    #[serde(rename = "Final Score")]
    pub final_score: f64,
    #[serde(rename = "Original Grade")]
    pub original_grade: String,
    pub grade: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RoundupSummary {
    pub improved_count: usize,
    pub distribution: Vec<RoundupDist>,
    pub improved_students: Vec<ImprovedStudent>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CourseData {
    pub status: String,
    pub message: Option<String>,
    pub course_id: String,
    pub course_name: String,
    pub term: String,
    pub weights: HashMap<String, f64>,
    pub grade_boundaries: BTreeMap<String, f64>,
    pub data_mapping: HashMap<String, Vec<String>>,
    pub warnings: Vec<String>,
    pub max_scores: HashMap<String, f64>,
    pub summary_columns: Vec<String>,
    pub student_grades: Vec<HashMap<String, serde_json::Value>>,
    pub raw_columns: Vec<String>,
    pub raw_scores: Vec<HashMap<String, serde_json::Value>>,
    pub grade_distribution: HashMap<String, GradeStats>,
    pub roundup_summary: RoundupSummary,
    pub rules: Option<HashMap<String, serde_json::Value>>,
    pub attendance_labels: HashMap<String, String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GenericResponse {
    pub status: String,
    pub message: String,
}
