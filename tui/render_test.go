package main

import (
	"strings"
	"testing"
)

func TestViewRawCategoryTabAttendance(t *testing.T) {
	// Initialize a mock model
	m := initialModel()
	m.state = stateDashboard
	m.activeTab = tabRawDetails
	m.width = 100
	m.height = 30
	m.cursorRow = 0
	m.cursorCol = 2 // Navigated on the first attendance column (since 0 is Student ID, 1 is Name)

	// Mock course data
	m.courseData = &CourseData{
		Status:     "success",
		CourseID:   "PHYS1120",
		CourseName: "Physics",
		Term:       "2026_S1",
		DataMapping: map[string][]string{
			"attendance": {"22 Jun 2026", "29 Jun 2026", "6 Jul 2026"},
			"homework":   {"hw1", "hw2"},
		},
		RawScores: []map[string]interface{}{
			{
				"Student ID":  "69143302",
				"Name":        "Alice Smith",
				"22 Jun 2026": "P",
				"29 Jun 2026": "A",
				"6 Jul 2026":  "P",
			},
		},
	}

	// Make sure activeRawCatIndex points to "attendance"
	cats := m.getRawCategories()
	attendanceIdx := -1
	for i, cat := range cats {
		if cat == "attendance" {
			attendanceIdx = i
			break
		}
	}
	if attendanceIdx == -1 {
		t.Fatalf("attendance category not found in mock categories")
	}
	m.activeRawCatIndex = attendanceIdx

	// ── Test 1: Left panel focused (default) ───────────────────────────────────
	m.rawRightFocused = false
	rendered := m.viewRawCategoryTab()

	// The categories list should appear in the left panel
	if !strings.Contains(rendered, "Attendance") {
		t.Errorf("expected left panel to list 'Attendance' category")
	}
	if !strings.Contains(rendered, "Homework") {
		t.Errorf("expected left panel to list 'Homework' category")
	}

	// Table headers with compact aliases should be present
	if !strings.Contains(rendered, "a1") {
		t.Errorf("expected table header to contain compact header 'a1'")
	}
	if !strings.Contains(rendered, "a2") {
		t.Errorf("expected table header to contain compact header 'a2'")
	}

	// ── Test 2: Right panel focused — status bar shows student/col info ────────
	m.rawRightFocused = true
	rendered = m.viewRawCategoryTab()

	// Student ID should appear in the bottom status bar
	if !strings.Contains(rendered, "69143302") {
		t.Errorf("expected rendered output to contain student ID '69143302' when right panel focused")
	}

	// Compact alias should appear in status bar
	if !strings.Contains(rendered, "a1") {
		t.Errorf("expected rendered output to contain column alias 'a1' when right panel focused")
	}

	// Attendance info sub-panel: date and code
	if !strings.Contains(rendered, "22 Jun 2026") {
		t.Errorf("expected attendance info panel to show date '22 Jun 2026'")
	}
	// Code value "P" should appear in the att. cell sub-panel
	if !strings.Contains(rendered, "P") {
		t.Errorf("expected attendance info panel to contain code value 'P'")
	}
}
