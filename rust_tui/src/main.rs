mod types;
mod bridge;
mod style;
mod app;
mod ui;

use app::{App, AppEvent};
use std::io;
use std::time::Duration;
use crossterm::{
    event::{self, Event, KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    cursor::{Hide, Show},
};
use ratatui::{backend::CrosstermBackend, Terminal};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Setup panic hook to clean up terminal on crash
    let original_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |panic_info| {
        let _ = disable_raw_mode();
        let _ = execute!(io::stdout(), LeaveAlternateScreen, Show);
        original_hook(panic_info);
    }));

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, Hide)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Setup communication channel
    let (tx, mut rx) = tokio::sync::mpsc::channel(100);

    // Spawn Input Polling Task
    let tx_keys = tx.clone();
    tokio::spawn(async move {
        loop {
            if event::poll(Duration::from_millis(50)).unwrap_or(false) {
                if let Ok(ev) = event::read() {
                    match ev {
                        Event::Key(key) => {
                            let _ = tx_keys.send(AppEvent::Key(key)).await;
                        }
                        Event::Resize(w, h) => {
                            let _ = tx_keys.send(AppEvent::Resize(w, h)).await;
                        }
                        _ => {}
                    }
                }
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    });

    // Spawn Tick Task (for animations/loading spinners/status message timeouts)
    let tx_tick = tx.clone();
    tokio::spawn(async move {
        loop {
            let _ = tx_tick.send(AppEvent::Tick).await;
            tokio::time::sleep(Duration::from_millis(200)).await;
        }
    });

    // Initialize App
    let mut app = App::new(tx);
    
    // Initial size query
    if let Ok((w, h)) = crossterm::terminal::size() {
        app.width = w;
        app.height = h;
    }

    // Trigger initial load
    app.load_courses();

    // Main Draw-Event Loop
    loop {
        // Draw TUI
        terminal.draw(|f| ui::draw(f, &mut app))?;

        // Wait for event from tokio channel
        if let Some(event) = rx.recv().await {
            // Check for exit
            if let AppEvent::Key(key) = event {
                // If 'q' is pressed and we aren't editing a cell, weight, or boundary: exit!
                if key.code == KeyCode::Char('q') && !app.editing && !app.editing_weights && !app.editing_boundaries {
                    break;
                }
                
                // Allow Ctrl+C to exit globally
                if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
                    break;
                }

                // Process standard key events inside app update
                app.update(AppEvent::Key(key));
            } else {
                // Forward resize, tick, and async results to app updater
                app.update(event);
            }
        }
    }

    // Restore terminal state
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, Show)?;
    terminal.show_cursor()?;

    Ok(())
}
