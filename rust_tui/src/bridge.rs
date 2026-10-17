use std::path::PathBuf;
use std::process::Stdio;
use tokio::process::Command;
use crate::types::*;

pub fn resolve_tui_api_path() -> PathBuf {
    // 1. Check relative to CWD
    if let Ok(cwd) = std::env::current_dir() {
        let path = cwd.join("src").join("tui_api.py");
        if path.exists() {
            return path;
        }
    }
    // 2. Check relative to executable directory. current_exe() does not reliably
    // resolve symlinks (e.g. a `grade-tui` shim on PATH pointing at this binary),
    // so canonicalize it ourselves to land on the binary's real location.
    if let Ok(exe_path) = std::env::current_exe() {
        let exe_path = exe_path.canonicalize().unwrap_or(exe_path);
        if let Some(exe_dir) = exe_path.parent() {
            let mut current = exe_dir.to_path_buf();
            for _ in 0..5 {
                let path = current.join("src").join("tui_api.py");
                if path.exists() {
                    return path;
                }
                if let Some(parent) = current.parent() {
                    current = parent.to_path_buf();
                } else {
                    break;
                }
            }
        }
    }
    // 3. Last-resort relative guess (only correct if CWD happens to be the project root;
    // the caller will get a clear "no such file" error from python3 otherwise).
    PathBuf::from("src/tui_api.py")
}

pub async fn get_courses() -> Result<CourseListResponse, String> {
    let api_path = resolve_tui_api_path();
    let output = Command::new("python3")
        .arg(&api_path)
        .arg("get-courses")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| format!("Failed to spawn python3: {}", e))?;

    if !output.status.success() {
        let err_str = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python bridge failed: {}", err_str));
    }

    let stdout_str = String::from_utf8_lossy(&output.stdout);
    let res: CourseListResponse = serde_json::from_str(&stdout_str)
        .map_err(|e| format!("JSON parse error: {}\nOutput was: {}", e, stdout_str))?;

    Ok(res)
}

pub async fn get_course_data(course_path: &str) -> Result<CourseData, String> {
    let api_path = resolve_tui_api_path();
    let output = Command::new("python3")
        .arg(&api_path)
        .arg("get-course-data")
        .arg(course_path)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| format!("Failed to spawn python3: {}", e))?;

    let stdout_str = String::from_utf8_lossy(&output.stdout);
    let res: CourseData = serde_json::from_str(&stdout_str)
        .map_err(|e| format!("JSON parse error: {}\nOutput was: {}", e, stdout_str))?;

    if res.status == "error" {
        return Err(res.message.unwrap_or_else(|| "Unknown error from Python bridge".to_string()));
    }

    Ok(res)
}

pub async fn apply_edits(course_path: &str, edits_json: String) -> Result<SaveReport, String> {
    use tokio::io::AsyncWriteExt;
    let api_path = resolve_tui_api_path();
    let mut child = Command::new("python3")
        .arg(&api_path)
        .arg("apply-edits")
        .arg(course_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn python3: {}", e))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(edits_json.as_bytes()).await.map_err(|e| format!("Failed to send edits: {}", e))?;
    }
    let output = child.wait_with_output().await.map_err(|e| format!("python3 failed: {}", e))?;

    let stdout_str = String::from_utf8_lossy(&output.stdout);
    let res: SaveReport = serde_json::from_str(&stdout_str)
        .map_err(|e| format!("JSON parse error: {}\nOutput was: {}", e, stdout_str))?;
    if res.status == "error" {
        return Err(res.message);
    }
    Ok(res)
}

pub async fn update_config(course_path: &str, weights: &str, boundaries: &str) -> Result<GenericResponse, String> {
    let api_path = resolve_tui_api_path();
    let output = Command::new("python3")
        .arg(&api_path)
        .arg("update-config")
        .arg(course_path)
        .arg(weights)
        .arg(boundaries)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| format!("Failed to spawn python3: {}", e))?;

    let stdout_str = String::from_utf8_lossy(&output.stdout);
    let res: GenericResponse = serde_json::from_str(&stdout_str)
        .map_err(|e| format!("JSON parse error: {}\nOutput was: {}", e, stdout_str))?;

    if res.status == "error" {
        return Err(res.message);
    }
    Ok(res)
}

pub async fn export_reports(course_path: &str) -> Result<GenericResponse, String> {
    let api_path = resolve_tui_api_path();
    let output = Command::new("python3")
        .arg(&api_path)
        .arg("export-reports")
        .arg(course_path)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| format!("Failed to spawn python3: {}", e))?;

    let stdout_str = String::from_utf8_lossy(&output.stdout);
    let res: GenericResponse = serde_json::from_str(&stdout_str)
        .map_err(|e| format!("JSON parse error: {}\nOutput was: {}", e, stdout_str))?;

    if res.status == "error" {
        return Err(res.message);
    }
    Ok(res)
}
