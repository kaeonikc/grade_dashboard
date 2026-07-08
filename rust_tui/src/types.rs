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
    #[serde(rename = "Grade")]
    pub grade: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RoundupSummary {
    pub improved_count: usize,
    pub distribution: Vec<RoundupDist>,
    pub improved_students: Vec<ImprovedStudent>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct OverviewStats {
    pub mean: f64,
    pub median: f64,
    pub std_dev: f64,
    pub pass_rate: f64,
    pub passing_count: usize,
    pub total_count: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct HistogramBin {
    pub label: String,
    pub count: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct BoxPlotOutlier {
    pub student_id: String,
    pub name: String,
    pub final_score: f64,
    pub raw_index: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct BoxPlotStats {
    pub min: f64,
    pub q1: f64,
    pub median: f64,
    pub q3: f64,
    pub max: f64,
    pub mean: f64,
    pub whisker_low: f64,
    pub whisker_high: f64,
    pub skew_label: String,
    pub outliers: Vec<BoxPlotOutlier>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProgressItem {
    pub label: String,
    pub avg_pct: f64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProgressSeries {
    pub category: String,
    pub items: Vec<ProgressItem>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ItemStat {
    pub category: String,
    pub item: String,
    pub max_score: f64,
    pub difficulty: f64,
    pub difficulty_label: String,
    pub discrimination: f64,
    pub n: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CorrelationMatrix {
    pub categories: Vec<String>,
    pub matrix: Vec<Vec<f64>>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AtRiskStudent {
    pub raw_index: usize,
    pub student_id: String,
    pub name: String,
    pub final_score: f64,
    pub grade: String,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AnalyticsData {
    pub overview: OverviewStats,
    pub histogram: Vec<HistogramBin>,
    pub box_plot: BoxPlotStats,
    pub progress: Vec<ProgressSeries>,
    pub item_analysis: Vec<ItemStat>,
    pub correlation: CorrelationMatrix,
    pub at_risk: Vec<AtRiskStudent>,
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
    pub analytics: AnalyticsData,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GenericResponse {
    pub status: String,
    pub message: String,
}
