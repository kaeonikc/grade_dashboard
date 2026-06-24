# Workspace Rules: Grade Dashboard TUI

## TUI Focus Constraint
For all tasks in this repository, focus exclusively on the development, styling, debugging, and optimization of the Go-based Text User Interface (TUI) components (`tui/main.go`, `grade-tui` binary) and the JSON API bridge (`src/tui_api.py`).

## Core Ingestion Preservation
- **Do not modify** the stable Python calculation engine (`src/calculators.py`) or the ingestion modules (`src/data_loader.py`) unless explicitly requested by the user, or if a bug in TUI display data is traced directly to missing metadata exposure in these files.
- Re-use the existing calculations and pandas workflows via the JSON IPC bridge commands rather than attempting to rewrite parsing in Go.
- Make sure any script adjustments maintain CWD-agnostic absolute path resolution so that the global binary remains executable from any directory.
