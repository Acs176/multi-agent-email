package main

import (
	"context"
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type viewState int

const (
	stateLoading viewState = iota
	statePreviewEmail
	stateSummary
	stateReview
	stateEditingPayload
	statePromptGeneral
	stateSubmittingAction
	stateDone
	stateError
)

const (
	requestTimeout     = 30 * time.Second
	previewInstruction = "Press Enter to submit the email to the agents. Press 'q' to quit."
)

var (
	titleStyle      = lipgloss.NewStyle().Bold(true)
	labelStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("241")).Render
	successStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("42")).Render
	errorTextStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("9")).Render
	subtleTextStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("244")).Render
)

type newEmailMsg struct {
	email Email
	resp  *NewEmailResponse
	err   error
}

type actionUpdatedMsg struct {
	index  int
	action Action
	err    error
}

type appModel struct {
	client        *APIClient
	view          viewState
	spinner       spinner.Model
	email         Email
	emails        []Email
	currentEmail  int
	response      *NewEmailResponse
	currentAction int
	status        string
	editor        textarea.Model
	editorErr     string
	pending       map[string]interface{}
	err           error
	viewport      viewport.Model
}

func newAppModel(client *APIClient) *appModel {
	sp := spinner.New()
	sp.Spinner = spinner.Dot
	sp.Style = lipgloss.NewStyle().Foreground(lipgloss.Color("205"))

	editor := textarea.New()
	editor.Placeholder = "{ }"
	editor.ShowLineNumbers = true
	editor.CharLimit = 0
	editor.SetWidth(80)
	editor.SetHeight(12)

	vp := viewport.New(80, 20)
	vp.SetContent("")

	return &appModel{
		client:   client,
		view:     stateLoading,
		spinner:  sp,
		editor:   editor,
		viewport: vp,
	}
}

func (m *appModel) Init() tea.Cmd {
	emails := buildSampleEmails()
	if len(emails) == 0 {
		emails = []Email{buildSampleEmail()}
	}
	m.emails = emails
	return m.prepareEmail(0)
}

func renderEmailPreview(email Email) string {
	var b strings.Builder
	b.WriteString(titleStyle.Render("Email Ready to Submit"))
	b.WriteString("\n\n")
	b.WriteString(labelledLine("Mail ID:", email.MailID))

	if subject := strings.TrimSpace(email.Subject); subject != "" {
		b.WriteString("\n" + labelledLine("Subject:", subject))
	}

	b.WriteString("\n" + labelledLine("From:", formatSender(email)))

	if to := formatAddressList(email.To); to != "" {
		b.WriteString("\n" + labelledLine("To:", to))
	}
	if cc := formatAddressList(email.CC); cc != "" {
		b.WriteString("\n" + labelledLine("CC:", cc))
	}

	b.WriteString("\n\n" + labelStyle("Body:") + "\n")
	b.WriteString(indentMultiline(email.Body, "  "))

	return b.String()
}

func (m *appModel) renderPreviewEmailContent() string {
	content := renderEmailPreview(m.email)
	instruction := strings.TrimSpace(m.status)
	if instruction == "" {
		instruction = previewInstruction
	}
	return fmt.Sprintf("%s\n\n%s", content, subtleTextStyle(instruction))
}

func formatSender(email Email) string {
	if name := strings.TrimSpace(email.FromName); name != "" {
		return fmt.Sprintf("%s <%s>", name, email.FromEmail)
	}
	return email.FromEmail
}

func formatAddressList(addresses []string) string {
	if len(addresses) == 0 {
		return ""
	}
	return strings.Join(addresses, ", ")
}

func indentMultiline(text, indent string) string {
	if text == "" {
		return indent
	}
	clean := strings.ReplaceAll(text, "\r\n", "\n")
	lines := strings.Split(clean, "\n")
	for i, line := range lines {
		if line == "" {
			lines[i] = indent
			continue
		}
		lines[i] = indent + line
	}
	return strings.Join(lines, "\n")
}

func (m *appModel) prepareEmail(index int) tea.Cmd {
	if index < 0 || index >= len(m.emails) {
		return nil
	}
	m.currentEmail = index
	m.email = m.emails[index]
	m.response = nil
	m.pending = nil
	m.currentAction = 0
	m.editorErr = ""
	m.err = nil
	m.setView(statePreviewEmail, previewInstruction)
	return nil
}

func (m *appModel) prepareNextEmail() tea.Cmd {
	next := m.currentEmail + 1
	if next >= len(m.emails) {
		return nil
	}
	return m.prepareEmail(next)
}

func (m *appModel) hasMoreEmails() bool {
	return m.currentEmail+1 < len(m.emails)
}

func (m *appModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.handleWindowSize(msg)
		return m, nil
	case tea.KeyMsg:
		return m.handleKeyMsg(msg)
	case newEmailMsg:
		if msg.err != nil {
			return m.fail(msg.err)
		}
		m.email = msg.email
		m.response = msg.resp
		if m.hasActions() {
			m.setView(stateSummary, "")
		} else {
			m.setView(stateDone, "No actions to review.")
		}
		return m, nil
	case actionUpdatedMsg:
		if msg.err != nil {
			return m.fail(msg.err)
		}
		if action := m.actionAt(msg.index); action != nil {
			*action = msg.action
		}
		if m.actionAt(msg.index+1) != nil {
			m.currentAction = msg.index + 1
			m.setView(stateReview, successStyle("Action updated successfully."))
		} else {
			m.setView(stateDone, successStyle("All actions reviewed."))
		}
		return m, m.spinner.Tick
	default:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}
}

func (m *appModel) handleWindowSize(msg tea.WindowSizeMsg) {
	if msg.Width <= 0 || msg.Height <= 0 {
		return
	}
	m.viewport.Width = msg.Width
	m.viewport.Height = maxInt(5, msg.Height-2)
	m.editor.SetWidth(maxInt(20, msg.Width-4))
	m.editor.SetHeight(maxInt(5, m.viewport.Height-2))
	m.refreshViewport(true)
}

func (m *appModel) handleKeyMsg(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	if msg.Type == tea.KeyCtrlC {
		return m, tea.Quit
	}
	if m.viewUsesViewport() && m.handleViewportScroll(msg) {
		return m, nil
	}
	switch m.view {
	case statePreviewEmail:
		return m.handlePreviewKey(msg)
	case stateSummary:
		if msg.Type == tea.KeyEnter {
			m.currentAction = 0
			m.setView(stateReview, "")
		}
		return m, nil
	case stateReview:
		return m.handleReviewKey(msg)
	case stateEditingPayload:
		return m.handlePayloadKey(msg)
	case statePromptGeneral:
		return m.handlePromptKey(msg)
	case stateDone:
		switch msg.Type {
		case tea.KeyEnter:
			if m.hasMoreEmails() {
				cmd := m.prepareNextEmail()
				return m, cmd
			}
			return m, tea.Quit
		case tea.KeyRunes:
			if strings.ToLower(string(msg.Runes)) == "q" {
				return m, tea.Quit
			}
		}
		return m, nil
	case stateError:
		if msg.Type == tea.KeyEnter {
			return m, tea.Quit
		}
		return m, nil
	default:
		return m, nil
	}
}
func (m *appModel) handlePreviewKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.Type {
	case tea.KeyEnter:
		return m.beginEmailSubmission()
	case tea.KeyRunes:
		runes := strings.ToLower(string(msg.Runes))
		if runes == "q" {
			return m, tea.Quit
		}
	}
	return m, nil
}

func (m *appModel) handleReviewKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	action := m.currentActionRef()
	if action == nil || msg.Type != tea.KeyRunes {
		return m, nil
	}
	id := action.ActionID
	switch strings.ToLower(string(msg.Runes)) {
	case "a":
		return m.beginActionUpdate("Approving action...", approveActionCmd(m.client, m.currentAction, id))
	case "r":
		return m.beginActionUpdate("Rejecting action...", rejectActionCmd(m.client, m.currentAction, id))
	case "m":
		return m.enterPayloadEditor()
	case "q":
		return m, tea.Quit
	default:
		return m, nil
	}
}

func (m *appModel) handlePayloadKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	m.editor, cmd = m.editor.Update(msg)
	switch msg.Type {
	case tea.KeyCtrlS:
		raw := strings.TrimSpace(m.editor.Value())
		if raw == "" {
			m.editorErr = "Payload cannot be empty."
			return m, cmd
		}
		var parsed map[string]interface{}
		if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
			m.editorErr = fmt.Sprintf("Invalid JSON: %v", err)
			return m, cmd
		}
		m.pending = parsed
		m.editorErr = ""
		m.setView(statePromptGeneral, "Apply extracted preferences to general profile? (y/N)")
		return m, cmd
	case tea.KeyEsc:
		m.setView(stateReview, subtleTextStyle("Modification cancelled."))
		return m, cmd
	default:
		return m, cmd
	}
}

func (m *appModel) handlePromptKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.Type {
	case tea.KeyRunes:
		choice := strings.ToLower(string(msg.Runes))
		if choice == "y" {
			return m.submitModifiedAction(true)
		}
		if choice == "n" {
			return m.submitModifiedAction(false)
		}
	case tea.KeyEnter:
		return m.submitModifiedAction(false)
	}
	return m, nil
}

func (m *appModel) handleViewportScroll(msg tea.KeyMsg) bool {
	switch msg.Type {
	case tea.KeyUp:
		m.viewport.LineUp(1)
	case tea.KeyDown:
		m.viewport.LineDown(1)
	case tea.KeyPgUp:
		m.viewport.ViewUp()
	case tea.KeyPgDown:
		m.viewport.ViewDown()
	case tea.KeyHome:
		m.viewport.GotoTop()
	case tea.KeyEnd:
		m.viewport.GotoBottom()
	default:
		return false
	}
	return true
}

func (m *appModel) enterPayloadEditor() (tea.Model, tea.Cmd) {
	action := m.currentActionRef()
	if action == nil {
		return m, nil
	}
	pretty, err := toPrettyJSON(action.Payload)
	if err != nil {
		return m.fail(fmt.Errorf("format payload: %w", err))
	}
	m.editor.SetValue(pretty)
	m.editor.CursorEnd()
	m.editor.Focus()
	m.editorErr = ""
	m.view = stateEditingPayload
	return m, nil
}

func (m *appModel) beginEmailSubmission() (tea.Model, tea.Cmd) {
	m.setView(stateLoading, "Submitting email to the agents...")
	return m, tea.Batch(m.spinner.Tick, loadSampleEmailCmd(m.client, m.email))
}

func (m *appModel) beginActionUpdate(message string, cmd tea.Cmd) (tea.Model, tea.Cmd) {
	m.setView(stateSubmittingAction, message)
	return m, tea.Batch(m.spinner.Tick, cmd)
}

func (m *appModel) submitModifiedAction(apply bool) (tea.Model, tea.Cmd) {
	cmd := modifyActionCmd(m.client, m.currentAction, m.currentActionID(), m.pending, apply)
	return m.beginActionUpdate("Submitting modified action...", cmd)
}

func (m *appModel) setView(view viewState, status string) {
	m.view = view
	m.status = status
	m.refreshViewport(true)
}

func (m *appModel) fail(err error) (tea.Model, tea.Cmd) {
	m.err = err
	m.setView(stateError, "")
	return m, nil
}

func (m *appModel) refreshViewport(reset bool) {
	if !m.viewUsesViewport() {
		return
	}
	m.viewport.SetContent(m.currentViewContent())
	if reset {
		m.viewport.GotoTop()
	}
}

func (m *appModel) viewUsesViewport() bool {
	switch m.view {
	case statePreviewEmail, stateSummary, stateReview, statePromptGeneral, stateDone, stateError:
		return true
	default:
		return false
	}
}

func (m *appModel) currentViewContent() string {
	switch m.view {
	case statePreviewEmail:
		return m.renderPreviewEmailContent()
	case stateSummary:
		return m.renderSummaryContent()
	case stateReview:
		return m.renderCurrentActionContent()
	case statePromptGeneral:
		return m.renderPromptGeneralContent()
	case stateDone:
		return m.renderFinalStatusContent()
	case stateError:
		return m.renderErrorContent()
	default:
		return ""
	}
}

func (m *appModel) View() string {
	switch m.view {
	case stateLoading, stateSubmittingAction:
		return fmt.Sprintf("%s %s\n", m.spinner.View(), m.status)
	case stateEditingPayload:
		return m.renderPayloadEditor()
	default:
		return m.viewport.View()
	}
}

func (m *appModel) renderSummaryContent() string {
	if m.response == nil {
		return ""
	}
	from := m.email.FromEmail
	if name := strings.TrimSpace(m.email.FromName); name != "" {
		from = fmt.Sprintf("%s <%s>", name, m.email.FromEmail)
	}
	summary := ""
	if s := m.response.Summary; s != nil && strings.TrimSpace(s.Text) != "" {
		summary = fmt.Sprintf("\n%s\n%s", labelStyle("Summary:"), s.Text)
	}
	return fmt.Sprintf(`%s

%s
%s
%s
%s%s

%s
%s
%s`,
		titleStyle.Render("Email Summary"),
		labelledLine("Mail ID:", m.response.MailID),
		labelledLine("Subject:", m.email.Subject),
		labelledLine("From:", from),
		labelledLine("To:", strings.Join(m.email.To, ", ")),
		summary,
		labelStyle("Classification:"),
		renderClassification(m.response.Classification),
		subtleTextStyle("Press Enter to review proposed actions. Use arrow keys to scroll."),
	)
}

func renderClassification(c ClassificationPayload) string {
	if c.Probabilities == nil || len(c.Probabilities) == 0 {
		return "No classification data."
	}
	keys := mapsKeys(c.Probabilities)
	slices.Sort(keys)
	lines := make([]string, 0, len(keys))
	for _, key := range keys {
		percent := fmt.Sprintf("%.1f%%", c.Probabilities[key]*100)
		mark := ""
		if c.Decisions != nil && c.Decisions[key] {
			mark = " (selected)"
		}
		lines = append(lines, fmt.Sprintf("- %s: %s%s", key, percent, mark))
	}
	return strings.Join(lines, "\n")
}

func (m *appModel) renderCurrentActionContent() string {
	action := m.currentActionRef()
	if action == nil {
		return ""
	}
	result := ""
	if action.Result != nil {
		result = jsonBlock("Result", action.Result)
	}
	status := ""
	if m.status != "" {
		status = fmt.Sprintf("\n\n%s", subtleTextStyle(m.status))
	}
	return fmt.Sprintf(`%s (%d/%d)

%s
%s
%s%s%s%s

%s
%s`,
		titleStyle.Render("Proposed Action"),
		m.currentAction+1,
		len(m.response.ProposedActions),
		labelledLine("Action ID:", action.ActionID),
		labelledLine("Type:", action.Type),
		labelledLine("Status:", action.Status),
		jsonBlock("Payload", action.Payload),
		result,
		status,
		"Choose: [a]pprove  [m]odify  [r]eject  [q]uit",
		"Use arrow keys or PgUp/PgDn to scroll.",
	)
}

func (m *appModel) renderPromptGeneralContent() string {
	return fmt.Sprintf(`%s

%s

Press 'y' to apply to general preferences, 'n' for per-recipient, or Enter for the default (No).`,
		titleStyle.Render("Preference Update"),
		m.status,
	)
}

func (m *appModel) renderPayloadEditor() string {
	errorLine := ""
	if m.editorErr != "" {
		errorLine = "\n" + errorTextStyle(m.editorErr)
	}
	return fmt.Sprintf(`%s

%s%s
%s`,
		titleStyle.Render("Modify Payload"),
		m.editor.View(),
		errorLine,
		subtleTextStyle("Press Ctrl+S to submit changes, Esc to cancel."),
	)
}

func (m *appModel) renderFinalStatusContent() string {
	var b strings.Builder
	b.WriteString(titleStyle.Render("Review Complete"))
	b.WriteString("\n\n")
	if m.response != nil {
		for _, action := range m.response.ProposedActions {
			fmt.Fprintf(&b, "- %s: %s\n", action.ActionID, action.Status)
		}
		if len(m.response.ProposedActions) > 0 {
			b.WriteByte('\n')
		}
	}
	if m.status != "" {
		b.WriteString(m.status)
		b.WriteByte('\n')
	}
	instruction := "Press Enter or 'q' to exit. Use arrow keys to review the list."
	if m.hasMoreEmails() {
		instruction = "Press Enter to load the next email, or 'q' to exit. Use arrow keys to review the list."
	}
	b.WriteString(subtleTextStyle(instruction))
	return strings.TrimSuffix(b.String(), "\n")
}

func (m *appModel) renderErrorContent() string {
	message := ""
	if m.err != nil {
		message = errorTextStyle(m.err.Error()) + "\n\n"
	}
	return fmt.Sprintf(`%s

%s%s`,
		titleStyle.Render("Error"),
		message,
		subtleTextStyle("Press Enter to exit."),
	)
}

func labelledLine(label, value string) string {
	return fmt.Sprintf("%s %s", labelStyle(label), value)
}

func jsonBlock(title string, value interface{}) string {
	text, err := toPrettyJSON(value)
	if err != nil {
		text = fmt.Sprintf("<unable to render %s: %v>", strings.ToLower(title), err)
	}
	return fmt.Sprintf("\n%s\n%s", labelStyle(title+":"), text)
}

func toPrettyJSON(value interface{}) (string, error) {
	raw, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return "", err
	}
	return string(raw), nil
}

func loadSampleEmailCmd(client *APIClient, email Email) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), requestTimeout)
		defer cancel()
		resp, err := client.PostNewEmail(ctx, email)
		return newEmailMsg{email: email, resp: resp, err: err}
	}
}

func approveActionCmd(client *APIClient, index int, actionID string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), requestTimeout)
		defer cancel()
		action, err := client.ApproveAction(ctx, actionID)
		return actionUpdatedMsg{index: index, action: action, err: err}
	}
}

func rejectActionCmd(client *APIClient, index int, actionID string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), requestTimeout)
		defer cancel()
		action, err := client.RejectAction(ctx, actionID)
		return actionUpdatedMsg{index: index, action: action, err: err}
	}
}

func modifyActionCmd(
	client *APIClient,
	index int,
	actionID string,
	payload map[string]interface{},
	applyToGeneral bool,
) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), requestTimeout)
		defer cancel()
		action, err := client.ModifyAction(ctx, actionID, payload, applyToGeneral)
		return actionUpdatedMsg{index: index, action: action, err: err}
	}
}

func buildSampleEmails() []Email {

	return []Email{
		{
			MailID:    "mail-1",
			ThreadID:  "thread-team-lunch",
			FromName:  "Jamie Lee",
			FromEmail: "jamie.lee@example.com",
			To: []string{
				"user@example.com",
			},
			CC:      []string{},
			Subject: "Team Lunch Catch-Up?",
			Body: strings.Join([]string{
				"Hi Adrian,\n\nIt's been a while since the Mobile team grabbed lunch together. Are you free next week for a quick catch-up?",
				"I was thinking something casual near the office. Let me know what days work and I'll loop in Taylor to help lock it down.\n\nThanks!\nJamie",
			}, " "),
		},
		{
			MailID:    "mail-2",
			ThreadID:  "thread-team-lunch",
			FromName:  "Taylor Brooks",
			FromEmail: "taylor.brooks@example.com",
			To: []string{
				"user@example.com",
				"jamie.lee@example.com",
			},
			CC:      []string{},
			Subject: "Re: Team Lunch Catch-Up?",
			Body: strings.Join([]string{
				"Hi both,\n\nGreat! I can hold a 45-minute slot on either Tuesday at 12:00 PM or Thursday at 12:30 PM.",
				"Let me know which one you prefer and I'll send the calendar invite.\n\nThanks,\nTaylor",
			}, " "),
		},
		{
			MailID:    "mail-3",
			ThreadID:  "thread-team-lunch",
			FromName:  "Jamie Lee",
			FromEmail: "jamie.lee@example.com",
			To: []string{
				"taylor.brooks@example.com",
			},
			CC: []string{
				"user@example.com",
			},
			Subject: "Re: Team Lunch Catch-Up?",
			Body: strings.Join([]string{
				"Taylor,\n\nLet's go with Tuesday at 12:00 PM. Adrian and I will meet you in the lobby and walk over to Bella's Deli.",
				"Please send the invite when you have a minute.\n\nThanks!\nJamie",
			}, " "),
		},
		{
			MailID:    "mail-4",
			ThreadID:  "thread-team-lunch",
			FromName:  "Taylor Brooks",
			FromEmail: "taylor.brooks@example.com",
			To: []string{
				"user@example.com",
				"jamie.lee@example.com",
			},
			CC:      []string{},
			Subject: "Calendar Invite: Tuesday Lunch at Bella's Deli",
			Body: strings.Join([]string{
				"Calendar invite sent for Tuesday at 12:00 PM at Bella's Deli.",
				"See you both then!\n\nTaylor",
			}, " "),
		},
	}
}

func buildSampleEmail() Email {
	return Email{
		MailID:    fmt.Sprintf("mail-%d", time.Now().UnixNano()),
		ThreadID:  "thread-project-launch",
		FromName:  "Priya Singh",
		FromEmail: "pm@example.com",
		To: []string{
			"alice.johnson@example.com",
			"diego.martinez@example.com",
		},
		CC: []string{
			"finance@example.com",
			"product@example.com",
		},
		Subject: "Re: Project Launch - Kickoff Prep",
		Body: strings.Join([]string{
			"Looks solid now! Finance confirmed the numbers on slide 6.",
			"I suggest we trim slide 9 a bit -- too much detail for kickoff.",
			"Otherwise, I think we're ready to present tomorrow.",
			"Please let me know if you're available. Please respond.\n\n- Priya",
		}, " "),
	}
}

func mapsKeys(m map[string]float64) []string {
	keys := make([]string, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	return keys
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func (m *appModel) hasActions() bool {
	return m.response != nil && len(m.response.ProposedActions) > 0
}

func (m *appModel) actionAt(index int) *Action {
	if m.response == nil || index < 0 || index >= len(m.response.ProposedActions) {
		return nil
	}
	return &m.response.ProposedActions[index]
}

func (m *appModel) currentActionRef() *Action {
	return m.actionAt(m.currentAction)
}

func (m *appModel) currentActionID() string {
	if action := m.currentActionRef(); action != nil {
		return action.ActionID
	}
	return ""
}
