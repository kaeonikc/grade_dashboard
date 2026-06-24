package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	runewidth "github.com/mattn/go-runewidth"
)

// States
type appState int

const (
	stateCourseSelect appState = iota
	stateDashboard
)

// Tab indices
const (
	tabSummary = iota
	tabRawDetails
	tabDistribution
	tabRoundup
)

// Go structs matching JSON from tui_api.py
type Course struct {
	Name string `json:"name"`
	Path string `json:"path"`
}

type CourseListResponse struct {
	Status  string   `json:"status"`
	Courses []Course `json:"courses"`
	Message string   `json:"message,omitempty"`
}

type GradeStats struct {
	Count int     `json:"count"`
	Pct   float64 `json:"pct"`
}

type RoundupDist struct {
	Grade    string `json:"grade"`
	Original int    `json:"original"`
	Rounded  int    `json:"rounded"`
	Change   int    `json:"change"`
}

type ImprovedStudent struct {
	StudentID          string  `json:"Student ID"`
	Name               string  `json:"Name"`
	OriginalFinalScore float64 `json:"Original Final Score"`
	FinalScore         float64 `json:"Final Score"`
	OriginalGrade      string  `json:"Original Grade"`
	Grade              string  `json:"Grade"`
}

type RoundupSummary struct {
	ImprovedCount    int               `json:"improved_count"`
	Distribution     []RoundupDist     `json:"distribution"`
	ImprovedStudents []ImprovedStudent `json:"improved_students"`
}

type CourseData struct {
	Status          string                   `json:"status"`
	Message         string                   `json:"message,omitempty"`
	CourseID        string                   `json:"course_id"`
	CourseName      string                   `json:"course_name"`
	Term            string                   `json:"term"`
	Weights         map[string]float64       `json:"weights"`
	GradeBoundaries map[string]float64       `json:"grade_boundaries"`
	DataMapping     map[string][]string      `json:"data_mapping"`
	Warnings        []string                 `json:"warnings"`
	MaxScores       map[string]float64       `json:"max_scores"`
	SummaryColumns  []string                 `json:"summary_columns"`
	StudentGrades   []map[string]interface{} `json:"student_grades"`
	RawColumns      []string                 `json:"raw_columns"`
	RawScores       []map[string]interface{} `json:"raw_scores"`
	GradeDist       map[string]GradeStats    `json:"grade_distribution"`
	RoundupSummary  RoundupSummary           `json:"roundup_summary"`
}

// bubbletea model
type model struct {
	state              appState
	courses            []Course
	courseIndex        int
	selectedCoursePath string
	courseData         *CourseData
	activeTab          int
	useWeighted        bool
	loading            bool
	loadingMsg         string
	err                error
	msg                string

	// Window dimensions
	width  int
	height int

	// Grid navigation state
	cursorRow       int
	cursorCol       int
	scrollRowOffset int
	scrollColOffset int

	// Editing state (scores)
	editing         bool
	editInput       textinput.Model
	editingStudent  string
	editingColumn   string
	editingOriginal string

	// Editing weights & boundaries
	editingWeights    bool
	editingBoundaries bool
	settingsKeys      []string
	settingsValues    []textinput.Model
	settingsIndex     int

	// Drill-down sub-scores state
	editingSubScores    bool
	subScoreStudentID   string
	subScoreStudentName string
	subScoreCategory    string
	subScoreColumns     []string
	subScoreIndex       int
	editingSubScoreCell bool

	// Raw category details tab state
	activeRawCatIndex int

	// Warnings modal
	showWarningsModal bool
}

// Styling definitions using LipGloss
var (
	accentColor = lipgloss.Color("99")  // Modern Purple
	cyanColor   = lipgloss.Color("45")  // Vibrant Cyan
	greenColor  = lipgloss.Color("78")  // Pastel Green
	yellowColor = lipgloss.Color("214") // Gold/Orange-Yellow
	redColor    = lipgloss.Color("197") // Crimson Red
	bgDarkColor = lipgloss.Color("233") // Rich dark charcoal

	titleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("255")).
			Background(accentColor).
			Padding(0, 2)

	headerStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(accentColor).
			Border(lipgloss.NormalBorder(), false, false, true, false).
			BorderForeground(accentColor).
			Padding(0, 1)

	subHeaderStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("244"))

	tabStyle = lipgloss.NewStyle().
			Padding(0, 2).
			Background(lipgloss.Color("235")).
			Foreground(lipgloss.Color("245")).
			Border(lipgloss.RoundedBorder(), true, true, false, true).
			BorderForeground(lipgloss.Color("238"))

	activeTabStyle = lipgloss.NewStyle().
			Bold(true).
			Padding(0, 2).
			Background(accentColor).
			Foreground(lipgloss.Color("255")).
			Border(lipgloss.RoundedBorder(), true, true, false, true).
			BorderForeground(accentColor)

	metricBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("240")).
			Padding(0, 2).
			Width(25).
			Align(lipgloss.Center)

	tableHeaderStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(lipgloss.Color("255")).
				Background(lipgloss.Color("57")) // Deep Blue/Indigo header

	selectedCellStyle = lipgloss.NewStyle().
				Background(lipgloss.Color("208")). // High contrast orange
				Foreground(lipgloss.Color("255")).
				Bold(true)

	editCellHighlightStyle = lipgloss.NewStyle().
				Background(lipgloss.Color("199")). // Vibrant pink for edit state
				Foreground(lipgloss.Color("255")).
				Bold(true)

	cellStyle = lipgloss.NewStyle().
			Padding(0, 1)

	footerStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("243")).
			Border(lipgloss.NormalBorder(), true, false, false, false).
			BorderForeground(lipgloss.Color("238"))

	modalStyle = lipgloss.NewStyle().
			Border(lipgloss.DoubleBorder()).
			BorderForeground(accentColor).
			Background(bgDarkColor).
			Padding(1, 2)
)

func initialModel() model {
	ti := textinput.New()
	ti.Focus()
	ti.CharLimit = 10
	ti.Width = 10

	return model{
		state:       stateCourseSelect,
		courseIndex: 0,
		activeTab:   tabSummary,
		useWeighted: true,
		editInput:   ti,
	}
}

func (m model) Init() tea.Cmd {
	return loadCoursesCmd()
}

// Helper to resolve the location of src/tui_api.py dynamically
func resolveTuiApiPath() string {
	// 1. Check if we can find it relative to current working directory (CWD)
	cwdPath := filepath.Join(".", "src", "tui_api.py")
	if _, err := os.Stat(cwdPath); err == nil {
		absPath, _ := filepath.Abs(cwdPath)
		return absPath
	}

	// 2. Check relative to binary directory
	execPath, err := os.Executable()
	if err == nil {
		resolvedPath, err := filepath.EvalSymlinks(execPath)
		if err == nil {
			execPath = resolvedPath
		}
		binaryDir := filepath.Dir(execPath)
		
		binPath := filepath.Join(binaryDir, "src", "tui_api.py")
		if _, err := os.Stat(binPath); err == nil {
			absPath, _ := filepath.Abs(binPath)
			return absPath
		}

		parentPath := filepath.Join(binaryDir, "..", "src", "tui_api.py")
		if _, err := os.Stat(parentPath); err == nil {
			absPath, _ := filepath.Abs(parentPath)
			return absPath
		}
	}

	// Fallback
	return "src/tui_api.py"
}

// Commands to run Python backend bridge
func loadCoursesCmd() tea.Cmd {
	return func() tea.Msg {
		cmd := exec.Command("python3", resolveTuiApiPath(), "get-courses")
		var out bytes.Buffer
		cmd.Stdout = &out
		err := cmd.Run()
		if err != nil {
			return err
		}

		var resp CourseListResponse
		err = json.Unmarshal(out.Bytes(), &resp)
		if err != nil {
			return err
		}

		if resp.Status == "error" {
			return fmt.Errorf(resp.Message)
		}

		return resp
	}
}

func loadCourseDataCmd(path string, useWeighted bool) tea.Cmd {
	return func() tea.Msg {
		weightedStr := "true"
		if !useWeighted {
			weightedStr = "false"
		}
		cmd := exec.Command("python3", resolveTuiApiPath(), "get-course-data", path, weightedStr)
		var out bytes.Buffer
		cmd.Stdout = &out
		err := cmd.Run()
		if err != nil {
			return err
		}

		var data CourseData
		err = json.Unmarshal(out.Bytes(), &data)
		if err != nil {
			return err
		}

		if data.Status == "error" {
			return fmt.Errorf(data.Message)
		}

		return &data
	}
}

func updateScoreCmd(coursePath, studentID, colName, value string) tea.Cmd {
	return func() tea.Msg {
		cmd := exec.Command("python3", resolveTuiApiPath(), "update-score", coursePath, studentID, colName, value)
		var out bytes.Buffer
		cmd.Stdout = &out
		err := cmd.Run()
		if err != nil {
			return err
		}

		var res map[string]interface{}
		err = json.Unmarshal(out.Bytes(), &res)
		if err != nil {
			return err
		}

		if status, ok := res["status"].(string); ok && status == "error" {
			return fmt.Errorf(res["message"].(string))
		}

		return res["message"].(string)
	}
}

func updateConfigCmd(coursePath string, weights map[string]float64, boundaries map[string]float64) tea.Cmd {
	return func() tea.Msg {
		weightsJSON, _ := json.Marshal(weights)
		boundariesJSON, _ := json.Marshal(boundaries)

		cmd := exec.Command("python3", resolveTuiApiPath(), "update-config", coursePath, string(weightsJSON), string(boundariesJSON))
		var out bytes.Buffer
		cmd.Stdout = &out
		err := cmd.Run()
		if err != nil {
			return err
		}

		var res map[string]interface{}
		err = json.Unmarshal(out.Bytes(), &res)
		if err != nil {
			return err
		}

		if status, ok := res["status"].(string); ok && status == "error" {
			return fmt.Errorf(res["message"].(string))
		}

		return res["message"].(string)
	}
}

func exportReportsCmd(coursePath string, useWeighted bool) tea.Cmd {
	return func() tea.Msg {
		weightedStr := "true"
		if !useWeighted {
			weightedStr = "false"
		}
		cmd := exec.Command("python3", resolveTuiApiPath(), "export-reports", coursePath, weightedStr)
		var out bytes.Buffer
		cmd.Stdout = &out
		err := cmd.Run()
		if err != nil {
			return err
		}

		var res map[string]interface{}
		err = json.Unmarshal(out.Bytes(), &res)
		if err != nil {
			return err
		}

		if status, ok := res["status"].(string); ok && status == "error" {
			return fmt.Errorf(res["message"].(string))
		}

		return res["message"].(string)
	}
}

// Update loop
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		return m, nil

	case error:
		m.err = msg
		m.loading = false
		return m, nil

	case CourseListResponse:
		m.courses = msg.Courses
		m.loading = false
		m.err = nil
		return m, nil

	case *CourseData:
		m.courseData = msg
		m.loading = false
		m.err = nil
		m.msg = "Course loaded successfully."
		
		// Keep current cursor position if valid, otherwise reset/adjust
		if m.cursorRow >= len(m.courseData.StudentGrades) {
			m.cursorRow = 0
			m.scrollRowOffset = 0
		}
		var maxCols int
		if m.activeTab == tabSummary {
			maxCols = len(m.courseData.SummaryColumns)
		}
		if m.cursorCol >= maxCols {
			m.cursorCol = 0
			m.scrollColOffset = 0
		}
		return m, nil

	case string: // Success messages from write operations
		m.msg = msg
		m.loading = false
		m.editing = false
		m.editingWeights = false
		m.editingBoundaries = false
		// Reload course data to refresh calculations
		m.loading = true
		m.loadingMsg = "Recalculating grades..."
		return m, loadCourseDataCmd(m.selectedCoursePath, m.useWeighted)

	case tea.KeyMsg:
		// Drill-down sub-scores modal keyboard controls
		if m.editingSubScores {
			if m.editingSubScoreCell {
				switch msg.String() {
				case "enter":
					val := m.editInput.Value()
					m.loading = true
					m.loadingMsg = "Saving sub-score..."
					m.editingSubScoreCell = false
					
					colName := m.subScoreColumns[m.subScoreIndex]
					return m, updateScoreCmd(m.selectedCoursePath, m.subScoreStudentID, colName, val)
				case "esc":
					m.editingSubScoreCell = false
					return m, nil
				}
				m.editInput, cmd = m.editInput.Update(msg)
				return m, cmd
			}

			switch msg.String() {
			case "up":
				if m.subScoreIndex > 0 {
					m.subScoreIndex--
				}
				return m, nil
			case "down":
				if m.subScoreIndex < len(m.subScoreColumns)-1 {
					m.subScoreIndex++
				}
				return m, nil
			case "enter": // Trigger sub-score cell editing input
				colName := m.subScoreColumns[m.subScoreIndex]
				var origVal string
				// Find raw score for the current student
				for _, rRow := range m.courseData.RawScores {
					if fmt.Sprintf("%v", rRow["Student ID"]) == m.subScoreStudentID {
						origVal = fmt.Sprintf("%v", rRow[colName])
						if origVal == "<nil>" || origVal == "nan" {
							origVal = ""
						}
						break
					}
				}
				m.editingOriginal = origVal
				m.editInput.SetValue(origVal)
				m.editingSubScoreCell = true
				m.editInput.Focus()
				return m, nil
			case "esc":
				m.editingSubScores = false
				return m, nil
			}
			return m, nil
		}

		// Editing state inputs bypass main controls
		if m.editing {
			switch msg.String() {
			case "enter":
				val := m.editInput.Value()
				m.loading = true
				m.loadingMsg = "Saving score..."
				m.editing = false
				return m, updateScoreCmd(m.selectedCoursePath, m.editingStudent, m.editingColumn, val)
			case "esc":
				m.editing = false
				return m, nil
			}
			m.editInput, cmd = m.editInput.Update(msg)
			return m, cmd
		}

		// Edit configuration modals
		if m.editingWeights || m.editingBoundaries {
			switch msg.String() {
			case "up":
				if m.settingsIndex > 0 {
					m.settingsIndex--
					m.settingsValues[m.settingsIndex].Focus()
					for i := range m.settingsValues {
						if i != m.settingsIndex {
							m.settingsValues[i].Blur()
						}
					}
				}
				return m, nil
			case "down":
				if m.settingsIndex < len(m.settingsKeys)-1 {
					m.settingsIndex++
					m.settingsValues[m.settingsIndex].Focus()
					for i := range m.settingsValues {
						if i != m.settingsIndex {
							m.settingsValues[i].Blur()
						}
					}
				}
				return m, nil
			case "enter":
				m.loading = true
				m.loadingMsg = "Saving settings..."
				
				if m.editingWeights {
					newWeights := make(map[string]float64)
					for i, key := range m.settingsKeys {
						val, _ := strconv.ParseFloat(m.settingsValues[i].Value(), 64)
						newWeights[key] = val
					}
					m.editingWeights = false
					return m, updateConfigCmd(m.selectedCoursePath, newWeights, nil)
				} else {
					newBounds := make(map[string]float64)
					for i, key := range m.settingsKeys {
						val, _ := strconv.ParseFloat(m.settingsValues[i].Value(), 64)
						newBounds[key] = val
					}
					m.editingBoundaries = false
					return m, updateConfigCmd(m.selectedCoursePath, nil, newBounds)
				}
			case "esc":
				m.editingWeights = false
				m.editingBoundaries = false
				return m, nil
			}

			// Pass keys to active text inputs
			for i := range m.settingsValues {
				if i == m.settingsIndex {
					m.settingsValues[i], cmd = m.settingsValues[i].Update(msg)
				}
			}
			return m, cmd
		}

		// Warnings modal key control
		if m.showWarningsModal {
			switch msg.String() {
			case "esc", "enter", "q":
				m.showWarningsModal = false
				return m, nil
			}
			return m, nil
		}

		// Global controls based on app state
		if m.state == stateCourseSelect {
			switch msg.String() {
			case "up":
				if m.courseIndex > 0 {
					m.courseIndex--
				}
				return m, nil
			case "down":
				if m.courseIndex < len(m.courses)-1 {
					m.courseIndex++
				}
				return m, nil
			case "enter":
				if len(m.courses) > 0 {
					m.selectedCoursePath = m.courses[m.courseIndex].Path
					m.state = stateDashboard
					m.loading = true
					m.loadingMsg = "Loading course data..."
					m.cursorRow = 0
					m.cursorCol = 0
					m.scrollRowOffset = 0
					m.scrollColOffset = 0
					return m, loadCourseDataCmd(m.selectedCoursePath, m.useWeighted)
				}
			case "q", "ctrl+c":
				return m, tea.Quit
			}
		} else if m.state == stateDashboard {
			switch msg.String() {
			case "esc":
				m.state = stateCourseSelect
				m.courseData = nil
				m.err = nil
				m.msg = ""
				return m, nil
			case "q", "ctrl+c":
				return m, tea.Quit
			case "tab":
				m.activeTab = (m.activeTab + 1) % 4
				m.cursorRow = 0
				m.cursorCol = 0
				m.scrollRowOffset = 0
				m.scrollColOffset = 0
				return m, nil
			case "shift+tab":
				m.activeTab = (m.activeTab - 1 + 4) % 4
				m.cursorRow = 0
				m.cursorCol = 0
				m.scrollRowOffset = 0
				m.scrollColOffset = 0
				return m, nil
			case "w":
				m.useWeighted = !m.useWeighted
				m.loading = true
				m.loadingMsg = "Updating weights..."
				return m, loadCourseDataCmd(m.selectedCoursePath, m.useWeighted)
			case "e":
				m.loading = true
				m.loadingMsg = "Exporting reports to CSV..."
				return m, exportReportsCmd(m.selectedCoursePath, m.useWeighted)
			case "l": // Log / warnings overlay
				if len(m.courseData.Warnings) > 0 {
					m.showWarningsModal = true
				}
				return m, nil
			case "W": // Capital W to Edit Weights
				m.openEditWeights()
				return m, nil
			case "G": // Capital G to Edit Grade Boundaries
				m.openEditBoundaries()
				return m, nil
			case "[":
				if m.activeTab == tabRawDetails {
					cats := m.getRawCategories()
					if len(cats) > 0 {
						m.activeRawCatIndex = (m.activeRawCatIndex - 1 + len(cats)) % len(cats)
						m.cursorCol = 0
						m.cursorRow = 0
						m.scrollColOffset = 0
						m.scrollRowOffset = 0
					}
				}
				return m, nil
			case "]":
				if m.activeTab == tabRawDetails {
					cats := m.getRawCategories()
					if len(cats) > 0 {
						m.activeRawCatIndex = (m.activeRawCatIndex + 1) % len(cats)
						m.cursorCol = 0
						m.cursorRow = 0
						m.scrollColOffset = 0
						m.scrollRowOffset = 0
					}
				}
				return m, nil
			case "up":
				if m.activeTab == tabSummary || m.activeTab == tabRawDetails {
					if m.cursorRow > 0 {
						m.cursorRow--
						m.scrollTableVertical()
					}
				}
				return m, nil
			case "down":
				if m.activeTab == tabSummary || m.activeTab == tabRawDetails {
					maxRows := 0
					if m.courseData != nil {
						if m.activeTab == tabSummary {
							maxRows = len(m.courseData.StudentGrades)
						} else {
							maxRows = len(m.courseData.RawScores)
						}
					}
					if m.cursorRow < maxRows-1 {
						m.cursorRow++
						m.scrollTableVertical()
					}
				}
				return m, nil
			case "left":
				if m.activeTab == tabSummary || m.activeTab == tabRawDetails {
					if m.cursorCol > 0 {
						m.cursorCol--
						m.scrollTableHorizontal()
					}
				}
				return m, nil
			case "right":
				if m.activeTab == tabSummary || m.activeTab == tabRawDetails {
					maxCols := 0
					if m.courseData != nil {
						if m.activeTab == tabSummary {
							maxCols = len(m.courseData.SummaryColumns)
						} else {
							cats := m.getRawCategories()
							if len(cats) > 0 {
								if m.activeRawCatIndex >= len(cats) {
									m.activeRawCatIndex = 0
								}
								activeCat := cats[m.activeRawCatIndex]
								subCols := m.courseData.DataMapping[activeCat]
								maxCols = 2 + len(subCols)
							}
						}
					}
					if m.cursorCol < maxCols-1 {
						m.cursorCol++
						m.scrollTableHorizontal()
					}
				}
				return m, nil
			case "enter": // Drill-down raw sub-scores for category OR edit raw score cell
				if m.activeTab == tabSummary && m.courseData != nil {
					colName := m.courseData.SummaryColumns[m.cursorCol]
					
					// If they select a category column that ends with _pct, open the drill-down modal!
					if strings.HasSuffix(colName, "_pct") {
						category := strings.TrimSuffix(colName, "_pct")
						subCols, ok := m.courseData.DataMapping[category]
						if ok && len(subCols) > 0 {
							studentRow := m.courseData.StudentGrades[m.cursorRow]
							m.subScoreStudentID = fmt.Sprintf("%v", studentRow["Student ID"])
							m.subScoreStudentName = fmt.Sprintf("%v", studentRow["Name"])
							m.subScoreCategory = category
							m.subScoreColumns = subCols
							m.subScoreIndex = 0
							m.editingSubScores = true
							m.editingSubScoreCell = false
							m.msg = ""
						} else {
							m.msg = fmt.Sprintf("No raw assignments mapped to category '%s'.", category)
						}
					} else {
						m.msg = "Calculated column. Highlight a category (like Homework) to edit sub-scores."
					}
				} else if m.activeTab == tabRawDetails && m.courseData != nil {
					cats := m.getRawCategories()
					if len(cats) > 0 {
						if m.activeRawCatIndex >= len(cats) {
							m.activeRawCatIndex = 0
						}
						activeCat := cats[m.activeRawCatIndex]
						subCols := m.courseData.DataMapping[activeCat]
						cols := make([]string, 0, 2+len(subCols))
						cols = append(cols, "Student ID", "Name")
						cols = append(cols, subCols...)
						
						colName := cols[m.cursorCol]
						if colName == "Student ID" || colName == "Name" {
							m.msg = "Cannot edit Student ID or Name."
						} else {
							// Open inline editing for this raw score cell!
							studentRow := m.courseData.RawScores[m.cursorRow]
							m.editingStudent = fmt.Sprintf("%v", studentRow["Student ID"])
							m.editingColumn = colName
							
							origVal := fmt.Sprintf("%v", studentRow[colName])
							if origVal == "<nil>" || origVal == "nan" {
								origVal = ""
							}
							m.editingOriginal = origVal
							m.editInput.SetValue(origVal)
							m.editing = true
							m.editInput.Focus()
							m.msg = ""
						}
					}
				}
				return m, nil
			}
		}
	}

	return m, nil
}

// Config editor helpers
func (m *model) openEditWeights() {
	if m.courseData == nil {
		return
	}
	m.editingWeights = true
	m.settingsKeys = []string{}
	m.settingsValues = []textinput.Model{}
	m.settingsIndex = 0

	// Gather keys sorted
	for k := range m.courseData.Weights {
		m.settingsKeys = append(m.settingsKeys, k)
	}

	for _, k := range m.settingsKeys {
		ti := textinput.New()
		ti.SetValue(fmt.Sprintf("%.2f", m.courseData.Weights[k]))
		ti.Width = 8
		ti.CharLimit = 5
		m.settingsValues = append(m.settingsValues, ti)
	}
	m.settingsValues[0].Focus()
}

func (m *model) openEditBoundaries() {
	if m.courseData == nil {
		return
	}
	m.editingBoundaries = true
	m.settingsKeys = []string{}
	m.settingsValues = []textinput.Model{}
	m.settingsIndex = 0

	// Ordered grade boundaries (e.g. A, B+, B, ...)
	order := []string{"A", "B+", "B", "C+", "C", "D+", "D"}
	for _, k := range order {
		if _, ok := m.courseData.GradeBoundaries[k]; ok {
			m.settingsKeys = append(m.settingsKeys, k)
		}
	}
	// Fallback to match unordered ones
	for k := range m.courseData.GradeBoundaries {
		found := false
		for _, o := range order {
			if o == k {
				found = true
				break
			}
		}
		if !found {
			m.settingsKeys = append(m.settingsKeys, k)
		}
	}

	for _, k := range m.settingsKeys {
		ti := textinput.New()
		ti.SetValue(fmt.Sprintf("%.1f", m.courseData.GradeBoundaries[k]))
		ti.Width = 8
		ti.CharLimit = 5
		m.settingsValues = append(m.settingsValues, ti)
	}
	m.settingsValues[0].Focus()
}

// Table viewport scrolling adjustments
func (m *model) scrollTableVertical() {
	tableHeight := m.height - 13 // Approximate space left for table rows
	if tableHeight < 5 {
		tableHeight = 5
	}

	if m.cursorRow < m.scrollRowOffset {
		m.scrollRowOffset = m.cursorRow
	} else if m.cursorRow >= m.scrollRowOffset+tableHeight {
		m.scrollRowOffset = m.cursorRow - tableHeight + 1
	}
}

func (m *model) scrollTableHorizontal() {
	if m.courseData == nil {
		return
	}

	var cols []string
	var rows []map[string]interface{}
	if m.activeTab == tabSummary {
		cols = m.courseData.SummaryColumns
		rows = m.courseData.StudentGrades
	} else if m.activeTab == tabRawDetails {
		cats := m.getRawCategories()
		if len(cats) == 0 {
			return
		}
		if m.activeRawCatIndex >= len(cats) {
			m.activeRawCatIndex = 0
		}
		activeCat := cats[m.activeRawCatIndex]
		subCols := m.courseData.DataMapping[activeCat]
		cols = make([]string, 0, 2+len(subCols))
		cols = append(cols, "Student ID", "Name")
		cols = append(cols, subCols...)
		rows = m.courseData.RawScores
	} else {
		return
	}

	if len(rows) == 0 || len(cols) == 0 {
		return
	}

	// Calculate column widths based on content
	colWidths := make(map[string]int)
	for _, col := range cols {
		width := thaiVisualWidth(col)
		if col == "Name" {
			width = 18
		} else if col == "Student ID" {
			width = 12
		} else {
			if width < 8 {
				width = 8
			}
		}
		for _, row := range rows {
			cellVal := fmt.Sprintf("%v", row[col])
			cellW := thaiVisualWidth(cellVal)
			if cellW > width {
				width = cellW
			}
		}
		colWidths[col] = width + 2
	}

	tableWidth := m.width - 4
	if tableWidth < 40 {
		tableWidth = 40
	}

	cursorColName := cols[m.cursorCol]
	isCursorFixed := (cursorColName == "Student ID" || cursorColName == "Name")

	if !isCursorFixed {
		if m.cursorCol < m.scrollColOffset {
			m.scrollColOffset = m.cursorCol
		} else {
			// Check if cursorCol is visible
			for {
				accum := 0
				// Fixed columns width
				for _, col := range cols {
					if col == "Student ID" || col == "Name" {
						accum += colWidths[col]
					}
				}
				
				cursorFits := false
				for i, col := range cols {
					if col == "Student ID" || col == "Name" {
						continue
					}
					if i >= m.scrollColOffset {
						colW := colWidths[col]
						if accum+colW < tableWidth {
							accum += colW
							if i == m.cursorCol {
								cursorFits = true
								break
							}
						} else {
							break
						}
					}
				}
				
				if cursorFits || m.scrollColOffset >= m.cursorCol {
					break
				}
				m.scrollColOffset++
			}
		}
	}
}

// View loop
func (m model) View() string {
	if m.loading {
		return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center,
			lipgloss.NewStyle().Bold(true).Foreground(accentColor).Render(m.loadingMsg))
	}

	if m.err != nil {
		errBox := lipgloss.NewStyle().
			Border(lipgloss.DoubleBorder()).
			BorderForeground(redColor).
			Padding(1, 2).
			Render(fmt.Sprintf("❌ Error: %v\n\nPress Esc to retry or go back.", m.err))
		return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, errBox)
	}

	var content string

	switch m.state {
	case stateCourseSelect:
		content = m.viewCourseSelect()
	case stateDashboard:
		content = m.viewDashboard()
	}

	// Layout modals on top if active
	if m.editing {
		content = m.renderScoreEditModal(content)
	} else if m.editingWeights {
		content = m.renderConfigEditModal(content, "Weights Configuration")
	} else if m.editingBoundaries {
		content = m.renderConfigEditModal(content, "Grade Boundaries (Min scores)")
	} else if m.editingSubScores {
		content = m.renderSubScoresModal(content)
	} else if m.showWarningsModal {
		content = m.renderWarningsModal(content)
	}

	return content
}

func (m model) viewCourseSelect() string {
	var s strings.Builder

	s.WriteString(titleStyle.Render("🎓 GRADE DASHBOARD MANAGER (TUI)") + "\n\n")
	s.WriteString("Select a course directory to inspect:\n\n")

	if len(m.courses) == 0 {
		s.WriteString("  [No courses discovered. Drop course configurations in courses/ directory.]\n")
	} else {
		for i, c := range m.courses {
			cursor := " "
			if i == m.courseIndex {
				cursor = "▶"
				s.WriteString(lipgloss.NewStyle().Bold(true).Foreground(accentColor).Render(fmt.Sprintf("  %s %d. %s  (%s)", cursor, i+1, c.Name, filepath.Base(c.Path))) + "\n")
			} else {
				s.WriteString(fmt.Sprintf("    %d. %s  (%s)\n", i+1, c.Name, filepath.Base(c.Path)))
			}
		}
	}

	footer := footerStyle.Copy()
	if m.width > 0 {
		footer = footer.Width(m.width)
	}
	s.WriteString("\n\n" + footer.Render("Controls: ↑/↓ to navigate · Enter to select course · q to quit"))
	return s.String()
}

func (m model) viewDashboard() string {
	if m.courseData == nil {
		return "Loading..."
	}

	var s strings.Builder

	// 1. Header & Metadata
	warningIcon := ""
	if len(m.courseData.Warnings) > 0 {
		warningIcon = lipgloss.NewStyle().Foreground(yellowColor).Bold(true).Render(fmt.Sprintf(" ⚠️ %d Warning(s) [Press l]", len(m.courseData.Warnings)))
	}

	headerText := fmt.Sprintf("%s — %s  [Course ID: %s]%s", m.courseData.CourseName, m.courseData.Term, m.courseData.CourseID, warningIcon)
	header := headerStyle.Copy()
	if m.width > 0 {
		header = header.Width(m.width)
	}
	s.WriteString(header.Render(headerText) + "\n")

	// 2. Metrics bar
	s.WriteString(m.viewMetricsBar() + "\n\n")

	// 3. Tab Bar
	s.WriteString(m.viewTabBar() + "\n\n")

	// 4. Tab Content
	switch m.activeTab {
	case tabSummary:
		s.WriteString(m.viewTableTab())
	case tabRawDetails:
		s.WriteString(m.viewRawCategoryTab())
	case tabDistribution:
		s.WriteString(m.viewDistributionTab())
	case tabRoundup:
		s.WriteString(m.viewRoundupTab())
	}

	// 5. Message Line
	msgLine := ""
	if m.msg != "" {
		msgLine = lipgloss.NewStyle().Foreground(greenColor).Render(m.msg)
	}

	// 6. Footer Controls
	footerText := "Tab/Shift+Tab: switch tabs  ·  w: Toggle weighted  ·  e: Export CSV  ·  W: Edit Weights  ·  G: Edit Boundaries  ·  Esc: Back to courses  ·  q: Quit"
	if m.activeTab == tabSummary {
		footerText = "Arrow keys: Navigate table  ·  Enter: Drill-down & edit  ·  " + footerText
	} else if m.activeTab == tabRawDetails {
		footerText = "Arrow keys: Navigate table  ·  [/]: Switch category · Enter: Edit score  ·  " + footerText
	}

	footer := footerStyle.Copy()
	if m.width > 0 {
		footer = footer.Width(m.width)
	}
	s.WriteString("\n" + msgLine + "\n" + footer.Render(footerText))

	return s.String()
}

func (m model) viewMetricsBar() string {
	if m.courseData == nil || len(m.courseData.StudentGrades) == 0 {
		return ""
	}

	totalStudents := len(m.courseData.StudentGrades)
	
	// Average final score calculation
	var scoreSum float64
	var maxScore float64
	for _, st := range m.courseData.StudentGrades {
		if val, ok := st["Final Score"]; ok {
			var fVal float64
			switch v := val.(type) {
			case float64:
				fVal = v
			case float32:
				fVal = float64(v)
			case int:
				fVal = float64(v)
			case int64:
				fVal = float64(v)
			}
			scoreSum += fVal
			if fVal > maxScore {
				maxScore = fVal
			}
		}
	}
	avgScore := scoreSum / float64(totalStudents)

	weightedLabel := "Weighted"
	if !m.useWeighted {
		weightedLabel = "Raw Unweighted"
	}

	b1 := metricBoxStyle.Copy().BorderForeground(cyanColor).Render(
		fmt.Sprintf("👥 Students\n%s", lipgloss.NewStyle().Bold(true).Foreground(cyanColor).Render(strconv.Itoa(totalStudents))),
	)
	b2 := metricBoxStyle.Copy().BorderForeground(greenColor).Render(
		fmt.Sprintf("📈 Avg (%s)\n%s", weightedLabel, lipgloss.NewStyle().Bold(true).Foreground(greenColor).Render(fmt.Sprintf("%.2f%%", avgScore))),
	)
	b3 := metricBoxStyle.Copy().BorderForeground(yellowColor).Render(
		fmt.Sprintf("🏆 High Score\n%s", lipgloss.NewStyle().Bold(true).Foreground(yellowColor).Render(fmt.Sprintf("%.2f%%", maxScore))),
	)

	return lipgloss.JoinHorizontal(lipgloss.Top, b1, "  ", b2, "  ", b3)
}

func formatHeaderName(colName string) string {
	if colName == "Final Score" {
		return "Total"
	}
	if strings.HasSuffix(colName, "_pct") {
		cat := strings.TrimSuffix(colName, "_pct")
		return strings.Title(cat)
	}
	return colName
}

func (m model) viewTabBar() string {
	tabs := []string{"Summary Grades (calculated)", "Raw Category Details", "Grade Distribution", "Round-Up Audit"}
	var renderedTabs []string

	for i, name := range tabs {
		if i == m.activeTab {
			renderedTabs = append(renderedTabs, activeTabStyle.Render(name))
		} else {
			renderedTabs = append(renderedTabs, tabStyle.Render(name))
		}
	}

	return lipgloss.JoinHorizontal(lipgloss.Top, renderedTabs...)
}

func (m model) viewTableTab() string {
	if m.courseData == nil {
		return ""
	}

	cols := m.courseData.SummaryColumns
	rows := m.courseData.StudentGrades

	if len(rows) == 0 {
		return "  No data found."
	}

	// Calculate visible table dimensions
	tableWidth := m.width - 4
	tableHeight := m.height - 13
	if tableHeight < 5 {
		tableHeight = 5
	}

	// Setup column widths
	colWidths := make(map[string]int)
	for _, col := range cols {
		// Minimum column sizes
		width := thaiVisualWidth(col)
		if col == "Name" {
			width = 18
		} else if col == "Student ID" {
			width = 12
		} else {
			if width < 8 {
				width = 8
			}
		}
		// Scale to fit content max length if larger
		for _, row := range rows {
			cellVal := fmt.Sprintf("%v", row[col])
			cellW := thaiVisualWidth(cellVal)
			if cellW > width {
				width = cellW
			}
		}
		colWidths[col] = width + 2 // include cell padding
	}

	// Figure out how many columns we can fit on screen
	var visibleCols []string
	accumWidth := 0
	
	// Always include Student ID and Name first if they are in the list
	for _, col := range cols {
		colW := colWidths[col]
		if col == "Student ID" || col == "Name" {
			visibleCols = append(visibleCols, col)
			accumWidth += colW
		}
	}

	// Now add scrolling columns
	for i, col := range cols {
		if col == "Student ID" || col == "Name" {
			continue
		}
		if i >= m.scrollColOffset {
			colW := colWidths[col]
			if accumWidth+colW < tableWidth {
				visibleCols = append(visibleCols, col)
				accumWidth += colW
			}
		}
	}

	var tableSB strings.Builder

	// Render table header
	var headerCells []string
	for _, col := range visibleCols {
		w := colWidths[col]
		headerCells = append(headerCells, tableHeaderStyle.Width(w).Render(padRight(formatHeaderName(col), w)))
	}
	tableSB.WriteString(lipgloss.JoinHorizontal(lipgloss.Top, headerCells...) + "\n")

	// Render table rows
	endRow := m.scrollRowOffset + tableHeight
	if endRow > len(rows) {
		endRow = len(rows)
	}

	for r := m.scrollRowOffset; r < endRow; r++ {
		var rowCells []string
		studentRow := rows[r]
		isSelectedRow := (r == m.cursorRow)

		for _, col := range visibleCols {
			w := colWidths[col]
			valStr := fmt.Sprintf("%v", studentRow[col])
			if valStr == "<nil>" || valStr == "nan" {
				valStr = ""
			}

			// Grade coloring
			cellStyleToUse := cellStyle.Copy()
			if col == "Grade" || col == "Original Grade" {
				if valStr == "A" {
					cellStyleToUse = cellStyleToUse.Foreground(greenColor).Bold(true)
				} else if valStr == "F" {
					cellStyleToUse = cellStyleToUse.Foreground(redColor).Bold(true)
				} else if strings.HasPrefix(valStr, "D") {
					cellStyleToUse = cellStyleToUse.Foreground(yellowColor)
				}
			}

			isSelectedCell := isSelectedRow && (col == cols[m.cursorCol])

			cellVal := padRight(valStr, w)
			if isSelectedCell {
				if m.editing {
					rowCells = append(rowCells, editCellHighlightStyle.Width(w).Render(cellVal))
				} else {
					rowCells = append(rowCells, selectedCellStyle.Width(w).Render(cellVal))
				}
			} else {
				var bg lipgloss.Color
				if isSelectedRow {
					bg = lipgloss.Color("238") // Highlighted row background
				} else if r%2 == 0 {
					bg = lipgloss.Color("234") // Darker zebra background
				} else {
					bg = lipgloss.Color("235") // Lighter zebra background
				}
				rowCells = append(rowCells, cellStyleToUse.Background(bg).Width(w).Render(cellVal))
			}
		}
		tableSB.WriteString(lipgloss.JoinHorizontal(lipgloss.Top, rowCells...) + "\n")
	}

	// If horizontal scrolling is active, show visual indicators
	if m.scrollColOffset > 0 || len(visibleCols) < len(cols) {
		indicators := fmt.Sprintf(" ← Horizontal scroll active: showing %d/%d columns. Use Left/Right keys. → ", len(visibleCols), len(cols))
		tableSB.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("240")).Render(indicators) + "\n")
	}

	return tableSB.String()
}

func (m model) viewDistributionTab() string {
	if m.courseData == nil || len(m.courseData.GradeDist) == 0 {
		return "  No grade distribution data."
	}

	var s strings.Builder
	s.WriteString("  " + lipgloss.NewStyle().Bold(true).Foreground(accentColor).Render("📊 Grade Distribution Chart:") + "\n\n")

	// Order F -> A (bottom to top, or A to F top to bottom)
	order := []string{"A", "B+", "B", "C+", "C", "D+", "D", "F"}
	
	// Max count to scale bar widths
	maxCount := 1
	for _, stats := range m.courseData.GradeDist {
		if stats.Count > maxCount {
			maxCount = stats.Count
		}
	}

	maxBarWidth := 40

	for _, grade := range order {
		stats, ok := m.courseData.GradeDist[grade]
		count := 0
		pct := 0.0
		if ok {
			count = stats.Count
			pct = stats.Pct
		}

		barFilled := 0
		if maxCount > 0 {
			barFilled = (count * maxBarWidth) / maxCount
		}

		filledChar := "█"
		emptyChar := "░"

		barStr := strings.Repeat(filledChar, barFilled) + strings.Repeat(emptyChar, maxBarWidth-barFilled)
		
		// Color the bar
		var barColor lipgloss.Color
		switch grade {
		case "A":
			barColor = greenColor
		case "B+", "B":
			barColor = cyanColor
		case "C+", "C":
			barColor = yellowColor
		case "D+", "D":
			barColor = lipgloss.Color("208") // Orange
		default:
			barColor = redColor
		}

		barRendered := lipgloss.NewStyle().Foreground(barColor).Render(barStr)
		gradeRendered := lipgloss.NewStyle().Bold(true).Foreground(barColor).Render(fmt.Sprintf("%-4s", grade))
		countRendered := lipgloss.NewStyle().Foreground(lipgloss.Color("253")).Render(fmt.Sprintf("%3d student(s)", count))
		pctRendered := lipgloss.NewStyle().Foreground(lipgloss.Color("244")).Render(fmt.Sprintf("(%5.1f%%)", pct))

		s.WriteString(fmt.Sprintf("    %s %s  %s %s\n", gradeRendered, barRendered, countRendered, pctRendered))
	}

	return s.String()
}

func (m model) viewRoundupTab() string {
	if m.courseData == nil {
		return ""
	}

	var s strings.Builder
	summary := m.courseData.RoundupSummary

	s.WriteString("  " + lipgloss.NewStyle().Bold(true).Foreground(accentColor).Render("Rounding Impact Summary:") + "\n")
	s.WriteString("  Grades improved by rounding: " + lipgloss.NewStyle().Bold(true).Foreground(greenColor).Render(strconv.Itoa(summary.ImprovedCount)) + " student(s)\n\n")

	// Render Grade Changes Table
	s.WriteString("  " + lipgloss.NewStyle().Bold(true).Foreground(cyanColor).Render("Distribution Changes:") + "\n")
	distTable := ""
	headers := []string{"Grade", "Original Count", "Rounded Count", "Change"}
	
	var headerCells []string
	widths := []int{8, 16, 16, 10}
	for i, h := range headers {
		headerCells = append(headerCells, tableHeaderStyle.Width(widths[i]).Render(padRight(h, widths[i])))
	}
	distTable += "    " + lipgloss.JoinHorizontal(lipgloss.Top, headerCells...) + "\n"

	for i, row := range summary.Distribution {
		changeStr := fmt.Sprintf("%+d", row.Change)
		if row.Change == 0 {
			changeStr = "0"
		}
		
		var changeColor lipgloss.Color
		if row.Change > 0 {
			changeColor = greenColor
		} else if row.Change < 0 {
			changeColor = redColor
		} else {
			changeColor = lipgloss.Color("244")
		}

		cells := []string{
			padRight(row.Grade, widths[0]),
			padRight(strconv.Itoa(row.Original), widths[1]),
			padRight(strconv.Itoa(row.Rounded), widths[2]),
			padRight(changeStr, widths[3]),
		}

		var rowBg lipgloss.Color
		if i%2 == 0 {
			rowBg = lipgloss.Color("234")
		} else {
			rowBg = lipgloss.Color("235")
		}

		renderedCells := []string{
			cellStyle.Copy().Background(rowBg).Render(cells[0]),
			cellStyle.Copy().Background(rowBg).Render(cells[1]),
			cellStyle.Copy().Background(rowBg).Render(cells[2]),
			lipgloss.NewStyle().Background(rowBg).Foreground(changeColor).Bold(true).Padding(0, 1).Render(cells[3]),
		}

		distTable += "    " + lipgloss.JoinHorizontal(lipgloss.Top, renderedCells...) + "\n"
	}
	s.WriteString(distTable + "\n")

	// Render improved students list
	s.WriteString("  " + lipgloss.NewStyle().Bold(true).Foreground(cyanColor).Render("Students with Improved Grades:") + "\n")
	if len(summary.ImprovedStudents) == 0 {
		s.WriteString("    " + lipgloss.NewStyle().Foreground(lipgloss.Color("243")).Render("No students improved by rounding boundaries.") + "\n")
	} else {
		impHeaders := []string{"Student ID", "Name", "Orig Score", "Rounded Score", "Orig Grade", "Final Grade"}
		impWidths := []int{12, 18, 12, 15, 12, 12}
		
		var impHeaderCells []string
		for i, h := range impHeaders {
			impHeaderCells = append(impHeaderCells, tableHeaderStyle.Width(impWidths[i]).Render(padRight(h, impWidths[i])))
		}
		s.WriteString("    " + lipgloss.JoinHorizontal(lipgloss.Top, impHeaderCells...) + "\n")

		for idx, row := range summary.ImprovedStudents {
			cells := []string{
				padRight(row.StudentID, impWidths[0]),
				padRight(row.Name, impWidths[1]),
				padRight(fmt.Sprintf("%.1f", row.OriginalFinalScore), impWidths[2]),
				padRight(fmt.Sprintf("%.0f", row.FinalScore), impWidths[3]),
				padRight(row.OriginalGrade, impWidths[4]),
				padRight(row.Grade, impWidths[5]),
			}

			var rowBg lipgloss.Color
			if idx%2 == 0 {
				rowBg = lipgloss.Color("234")
			} else {
				rowBg = lipgloss.Color("235")
			}

			renderedCells := []string{
				cellStyle.Copy().Background(rowBg).Render(cells[0]),
				cellStyle.Copy().Background(rowBg).Render(cells[1]),
				cellStyle.Copy().Background(rowBg).Render(cells[2]),
				cellStyle.Copy().Background(rowBg).Foreground(greenColor).Render(cells[3]),
				cellStyle.Copy().Background(rowBg).Render(cells[4]),
				lipgloss.NewStyle().Background(rowBg).Foreground(greenColor).Bold(true).Padding(0, 1).Render(cells[5]),
			}
			s.WriteString("    " + lipgloss.JoinHorizontal(lipgloss.Top, renderedCells...) + "\n")
		}
	}

	return s.String()
}

// Modals
func (m model) renderScoreEditModal(content string) string {
	title := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("255")).Render("📝 Edit Score for student " + m.editingStudent)
	body := fmt.Sprintf(
		"\nColumn: %s\nOriginal value: %s\n\nEnter new score:\n%s\n\n%s",
		m.editingColumn, m.editingOriginal, m.editInput.View(),
		lipgloss.NewStyle().Foreground(lipgloss.Color("243")).Render("Enter to Save · Esc to Cancel"),
	)
	
	modal := modalStyle.Render(title + "\n" + body)
	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, modal)
}

func (m model) renderConfigEditModal(content string, title string) string {
	var s strings.Builder
	s.WriteString(lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("255")).Render("⚙️  "+title) + "\n\n")

	for i, key := range m.settingsKeys {
		cursor := " "
		if i == m.settingsIndex {
			cursor = "▶"
		}
		s.WriteString(fmt.Sprintf("%s %-12s: %s\n", cursor, key, m.settingsValues[i].View()))
	}
	s.WriteString("\n" + lipgloss.NewStyle().Foreground(lipgloss.Color("243")).Render("↑/↓: Navigate  ·  Enter: Save  ·  Esc: Cancel"))

	modal := modalStyle.Render(s.String())
	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, modal)
}

func (m model) renderWarningsModal(content string) string {
	if m.courseData == nil {
		return content
	}

	var s strings.Builder
	title := lipgloss.NewStyle().Bold(true).Foreground(yellowColor).Render(fmt.Sprintf("⚠️  %d Score Validation Warning(s)", len(m.courseData.Warnings)))
	s.WriteString(title + "\n\n")
	
	// Max warnings to show scrollable or fitted
	maxViewable := 12
	for i, warning := range m.courseData.Warnings {
		if i >= maxViewable {
			s.WriteString(fmt.Sprintf("   ... and %d more warning(s)\n", len(m.courseData.Warnings)-maxViewable))
			break
		}
		s.WriteString(fmt.Sprintf(" • %s\n", warning))
	}
	
	s.WriteString("\n" + lipgloss.NewStyle().Foreground(lipgloss.Color("243")).Render("Press Esc/Enter to close warnings popup"))

	w := m.width - 10
	if w < 20 {
		w = 20
	}
	modal := modalStyle.Width(w).Border(lipgloss.DoubleBorder()).BorderForeground(yellowColor).Padding(1, 2).Render(s.String())
	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, modal)
}

func (m model) renderSubScoresModal(content string) string {
	if m.courseData == nil {
		return content
	}

	// Find the raw scores row for this student
	var studentRawRow map[string]interface{}
	for _, rRow := range m.courseData.RawScores {
		if fmt.Sprintf("%v", rRow["Student ID"]) == m.subScoreStudentID {
			studentRawRow = rRow
			break
		}
	}

	var s strings.Builder
	title := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("255")).Render(
		fmt.Sprintf("📝 Edit %s Scores for %s (%s)", strings.Title(m.subScoreCategory), m.subScoreStudentName, m.subScoreStudentID),
	)
	s.WriteString(title + "\n\n")

	for i, col := range m.subScoreColumns {
		cursor := "  "
		valStr := ""
		if studentRawRow != nil {
			if val, ok := studentRawRow[col]; ok {
				valStr = fmt.Sprintf("%v", val)
				if valStr == "<nil>" || valStr == "nan" {
					valStr = ""
				}
			}
		}

		if i == m.subScoreIndex {
			cursor = "▶ "
			if m.editingSubScoreCell {
				s.WriteString(fmt.Sprintf("%s%s: %s\n", cursor, col, m.editInput.View()))
			} else {
				valDisplay := valStr
				if valDisplay == "" {
					valDisplay = "(empty)"
				}
				s.WriteString(lipgloss.NewStyle().Bold(true).Foreground(accentColor).Render(fmt.Sprintf("%s%s: %s", cursor, col, valDisplay)) + "\n")
			}
		} else {
			valDisplay := valStr
			if valDisplay == "" {
				valDisplay = "-"
			}
			s.WriteString(fmt.Sprintf("%s%s: %s\n", cursor, col, valDisplay))
		}
	}

	s.WriteString("\n" + lipgloss.NewStyle().Foreground(lipgloss.Color("243")).Render("↑/↓: Navigate  ·  Enter: Edit/Save  ·  Esc: Close/Cancel"))

	modal := modalStyle.Render(s.String())
	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, modal)
}

// Formatting helpers
func thaiVisualWidth(s string) int {
	return runewidth.StringWidth(s)
}

func padRight(s string, w int) string {
	visW := thaiVisualWidth(s)
	if visW >= w {
		return s
	}
	return s + strings.Repeat(" ", w-visW)
}

func main() {
	p := tea.NewProgram(initialModel(), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Printf("Error starting TUI: %v", err)
		os.Exit(1)
	}
}

func (m model) getRawCategories() []string {
	if m.courseData == nil {
		return []string{}
	}
	var cats []string
	for cat := range m.courseData.DataMapping {
		if len(m.courseData.DataMapping[cat]) > 0 {
			cats = append(cats, cat)
		}
	}
	sort.Strings(cats)
	return cats
}

func (m model) viewRawCategoryTab() string {
	if m.courseData == nil {
		return ""
	}

	cats := m.getRawCategories()
	if len(cats) == 0 {
		return "  No raw category mappings found."
	}
	if m.activeRawCatIndex >= len(cats) {
		return "  Invalid category selection."
	}
	activeCat := cats[m.activeRawCatIndex]
	subCols := m.courseData.DataMapping[activeCat]

	cols := make([]string, 0, 2+len(subCols))
	cols = append(cols, "Student ID", "Name")
	cols = append(cols, subCols...)

	rows := m.courseData.RawScores
	if len(rows) == 0 {
		return "  No raw score data found."
	}

	var sb strings.Builder

	// Render Category Sub-Menu Selector
	sb.WriteString("  " + lipgloss.NewStyle().Bold(true).Foreground(accentColor).Render("Category:") + " ")
	for i, cat := range cats {
		catLabel := strings.Title(cat)
		if i == m.activeRawCatIndex {
			sb.WriteString(lipgloss.NewStyle().Bold(true).Underline(true).Foreground(cyanColor).Render("["+catLabel+"]") + "  ")
		} else {
			sb.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("244")).Render(catLabel) + "  ")
		}
	}
	sb.WriteString("\n\n")

	// Calculate visible table dimensions
	tableWidth := m.width - 4
	tableHeight := m.height - 15 // Leave slightly more space for the sub-menu selector
	if tableHeight < 5 {
		tableHeight = 5
	}

	// Setup column widths
	colWidths := make(map[string]int)
	for _, col := range cols {
		width := thaiVisualWidth(col)
		if col == "Name" {
			width = 18
		} else if col == "Student ID" {
			width = 12
		} else {
			if width < 8 {
				width = 8
			}
		}
		for _, row := range rows {
			cellVal := fmt.Sprintf("%v", row[col])
			cellW := thaiVisualWidth(cellVal)
			if cellW > width {
				width = cellW
			}
		}
		colWidths[col] = width + 2 // include cell padding
	}

	// Figure out visible columns
	var visibleCols []string
	accumWidth := 0

	// Fixed columns: ID and Name
	for _, col := range cols {
		colW := colWidths[col]
		if col == "Student ID" || col == "Name" {
			visibleCols = append(visibleCols, col)
			accumWidth += colW
		}
	}

	// Dynamic columns
	for i, col := range cols {
		if col == "Student ID" || col == "Name" {
			continue
		}
		if i >= m.scrollColOffset {
			colW := colWidths[col]
			if accumWidth+colW < tableWidth {
				visibleCols = append(visibleCols, col)
				accumWidth += colW
			}
		}
	}

	// Render table header
	var headerCells []string
	for _, col := range visibleCols {
		w := colWidths[col]
		headerCells = append(headerCells, tableHeaderStyle.Width(w).Render(padRight(formatHeaderName(col), w)))
	}
	sb.WriteString(lipgloss.JoinHorizontal(lipgloss.Top, headerCells...) + "\n")

	// Render table rows
	endRow := m.scrollRowOffset + tableHeight
	if endRow > len(rows) {
		endRow = len(rows)
	}

	for r := m.scrollRowOffset; r < endRow; r++ {
		var rowCells []string
		studentRow := rows[r]
		isSelectedRow := (r == m.cursorRow)

		for _, col := range visibleCols {
			w := colWidths[col]
			valStr := fmt.Sprintf("%v", studentRow[col])
			if valStr == "<nil>" || valStr == "nan" {
				valStr = ""
			}

			cellStyleToUse := cellStyle.Copy()
			isSelectedCell := isSelectedRow && (col == cols[m.cursorCol])

			cellVal := padRight(valStr, w)
			if isSelectedCell {
				if m.editing {
					rowCells = append(rowCells, editCellHighlightStyle.Width(w).Render(cellVal))
				} else {
					rowCells = append(rowCells, selectedCellStyle.Width(w).Render(cellVal))
				}
			} else {
				var bg lipgloss.Color
				if isSelectedRow {
					bg = lipgloss.Color("238")
				} else if r%2 == 0 {
					bg = lipgloss.Color("234")
				} else {
					bg = lipgloss.Color("235")
				}
				rowCells = append(rowCells, cellStyleToUse.Background(bg).Width(w).Render(cellVal))
			}
		}
		sb.WriteString(lipgloss.JoinHorizontal(lipgloss.Top, rowCells...) + "\n")
	}

	if m.scrollColOffset > 0 || len(visibleCols) < len(cols) {
		indicators := fmt.Sprintf(" ← Horizontal scroll active: showing %d/%d columns. Use Left/Right keys. → ", len(visibleCols), len(cols))
		sb.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("240")).Render(indicators) + "\n")
	}

	return sb.String()
}
