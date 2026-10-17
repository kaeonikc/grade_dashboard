use std::path::PathBuf;
use std::process::Stdio;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU64, Ordering};
use serde::de::DeserializeOwned;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::Mutex;
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

// ---------------------------------------------------------------------------------------------
// The Python worker: `tui_api.py serve` stays running for the whole session, so pandas loads once
// (~1 s) instead of on every call. One JSON request line in, one JSON reply line out. If the
// worker dies it is restarted once; if that fails too, the call falls back to a one-shot
// `python3 tui_api.py <cmd>`. Calls are serialized by the mutex.

struct Worker {
    _child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

static WORKER: OnceLock<Mutex<Option<Worker>>> = OnceLock::new();

fn spawn_worker() -> Result<Worker, String> {
    let mut child = Command::new("python3")
        .arg(resolve_tui_api_path())
        .arg("serve")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null()) // stderr would draw over the TUI
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("Failed to spawn python3: {}", e))?;
    let stdin = child.stdin.take().ok_or("worker has no stdin")?;
    let stdout = BufReader::new(child.stdout.take().ok_or("worker has no stdout")?);
    Ok(Worker { _child: child, stdin, stdout })
}

static NEXT_ID: AtomicU64 = AtomicU64::new(1);

/// Sends one request and reads lines until the reply carrying its id (the worker writes `{"id": N, ...`
/// first). A reply to an abandoned earlier request is skipped instead of being taken for this one.
async fn ask_worker(w: &mut Worker, id: u64, request: &str) -> std::io::Result<String> {
    w.stdin.write_all(request.as_bytes()).await?;
    w.stdin.write_all(b"\n").await?;
    w.stdin.flush().await?;
    let tag = format!("{{\"id\": {},", id);
    loop {
        let mut reply = String::new();
        if w.stdout.read_line(&mut reply).await? == 0 {
            return Err(std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "worker exited"));
        }
        if reply.starts_with(&tag) {
            return Ok(reply);
        }
    }
}

async fn one_shot(cmd: &str, args: &[&str], stdin: Option<&str>) -> Result<String, String> {
    let mut child = Command::new("python3")
        .arg(resolve_tui_api_path())
        .arg(cmd)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn python3: {}", e))?;
    if let Some(mut pipe) = child.stdin.take() {
        if let Some(text) = stdin {
            pipe.write_all(text.as_bytes()).await.map_err(|e| format!("Failed to send input: {}", e))?;
        }
    }
    let output = child.wait_with_output().await.map_err(|e| format!("python3 failed: {}", e))?;
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

/// Runs one tui_api.py command and returns its JSON reply text.
async fn call(cmd: &str, args: &[&str], stdin: Option<&str>) -> Result<String, String> {
    call_with(WORKER.get_or_init(|| Mutex::new(None)), cmd, args, stdin).await
}

async fn call_with(slot: &Mutex<Option<Worker>>, cmd: &str, args: &[&str], stdin: Option<&str>) -> Result<String, String> {
    {
        let mut guard = slot.lock().await;
        for _ in 0..2 {
            let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
            let request = serde_json::json!({ "id": id, "cmd": cmd, "args": args, "stdin": stdin }).to_string();
            if guard.is_none() {
                match spawn_worker() {
                    Ok(w) => *guard = Some(w),
                    Err(_) => break,
                }
            }
            match ask_worker(guard.as_mut().unwrap(), id, &request).await {
                Ok(reply) => return Ok(reply),
                Err(_) => *guard = None, // dropped = killed; the next round starts a fresh one
            }
        }
    }
    one_shot(cmd, args, stdin).await
}

async fn call_json<T: DeserializeOwned>(cmd: &str, args: &[&str], stdin: Option<&str>) -> Result<T, String> {
    let reply = call(cmd, args, stdin).await?;
    serde_json::from_str(&reply).map_err(|e| format!("JSON parse error: {}\nOutput was: {}", e, reply))
}


pub async fn get_courses() -> Result<CourseListResponse, String> {
    call_json("get-courses", &[], None).await
}

pub async fn get_course_data(course_path: &str) -> Result<CourseData, String> {
    let res: CourseData = call_json("get-course-data", &[course_path], None).await?;
    if res.status == "error" {
        return Err(res.message.unwrap_or_else(|| "Unknown error from Python bridge".to_string()));
    }
    Ok(res)
}

/// Saves a batch of edits in one call (the edits JSON travels as the command's stdin).
pub async fn apply_edits(course_path: &str, edits_json: String) -> Result<SaveReport, String> {
    let res: SaveReport = call_json("apply-edits", &[course_path], Some(&edits_json)).await?;
    if res.status == "error" {
        return Err(res.message);
    }
    Ok(res)
}

pub async fn update_config(course_path: &str, weights: &str, boundaries: &str) -> Result<GenericResponse, String> {
    let res: GenericResponse = call_json("update-config", &[course_path, weights, boundaries], None).await?;
    if res.status == "error" {
        return Err(res.message);
    }
    Ok(res)
}

pub async fn export_reports(course_path: &str) -> Result<GenericResponse, String> {
    let res: GenericResponse = call_json("export-reports", &[course_path], None).await?;
    if res.status == "error" {
        return Err(res.message);
    }
    Ok(res)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    /// A small course in the real on-disk format (as tests/conftest.py builds it).
    fn temp_course() -> PathBuf {
        let p = "2026_S1_Test_SEC_51";
        let dir = std::env::temp_dir().join(format!("gt-bridge-{}-{}", std::process::id(), NEXT_ID.fetch_add(1, Ordering::Relaxed)));
        let c = dir.join(format!("{p}_grading"));
        let write = |rel: String, text: &str| {
            let f = c.join(rel);
            std::fs::create_dir_all(f.parent().unwrap()).unwrap();
            std::fs::write(f, text).unwrap();
        };
        write(format!("course_info/{p}_config.yaml"), "course_id: PHYS1120\ncourse_name: Test\nterm: 2026_S1\nsec_num: '51'\n\
weights:\n  homework: 0.5\n  final: 0.5\ndata_mapping:\n  homework:\n  - hw1\n  final:\n  - final_exam\n\
grade_boundaries:\n  A: 80\n  B: 70\n  C: 60\n  D: 50\n");
        write(format!("course_info/{p}_student_info.csv"), "Student ID,Name,Class Group\n69000001,A One,G1\n69000002,B Two,G2\n");
        write(format!("data/{p}_homework.csv"), "Student ID,Name,hw1 (30pts),total (30pts)\n69000001,A One,30,30\n69000002,B Two,15,15\n");
        write(format!("data/{p}_final.csv"), "Student ID,Name,final_exam (40pts),total (40pts)\n69000001,A One,40,40\n69000002,B Two,20,20\n");
        c
    }

    fn pid(slot: &Mutex<Option<Worker>>) -> Option<u32> {
        slot.try_lock().ok().and_then(|g| g.as_ref().and_then(|w| w._child.id()))
    }

    async fn course_data(slot: &Mutex<Option<Worker>>, path: &str) -> CourseData {
        let reply = call_with(slot, "get-course-data", &[path], None).await.unwrap();
        let data: CourseData = serde_json::from_str(&reply).unwrap();
        assert_eq!(data.status, "success", "{:?}", data.message);
        data
    }

    #[tokio::test]
    async fn worker_is_reused_restarted_and_skips_stale_replies() {
        let slot = Mutex::new(None);
        let course = temp_course();
        let path = course.to_str().unwrap();

        course_data(&slot, path).await; // starts the worker (pays the pandas import once)
        let first = pid(&slot).expect("worker running");
        let t = Instant::now();
        course_data(&slot, path).await;
        assert!(t.elapsed() < Duration::from_millis(900), "warm call took {:?}", t.elapsed());
        assert_eq!(pid(&slot), Some(first), "same process");

        // A save through the worker, edits on stdin, reloaded course in the reply
        let edits = r#"{"edits": [{"student_id": "69000002", "column": "hw1", "value": "21", "original": "15"}]}"#;
        let reply = call_with(&slot, "apply-edits", &[path], Some(edits)).await.unwrap();
        let report: SaveReport = serde_json::from_str(&reply).unwrap();
        assert_eq!(report.saved, 1, "{}", report.message);
        assert!(report.course_data.is_some());

        // An abandoned request leaves its reply in the pipe; the next call must not take it
        {
            let mut g = slot.lock().await;
            let w = g.as_mut().unwrap();
            w.stdin.write_all(b"{\"id\": 1, \"cmd\": \"get-courses\", \"args\": []}\n").await.unwrap();
        }
        let data = course_data(&slot, path).await;
        assert_eq!(data.raw_scores.len(), 2);

        // Killed worker: the next call starts a new one and still answers
        std::process::Command::new("kill").arg("-9").arg(first.to_string()).status().unwrap();
        tokio::time::sleep(Duration::from_millis(100)).await;
        course_data(&slot, path).await;
        assert_ne!(pid(&slot), Some(first));

        let _ = std::fs::remove_dir_all(course.parent().unwrap());
    }
}
