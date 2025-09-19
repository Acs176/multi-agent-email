package main

import "fmt"

type Email struct {
	MailID     string   `json:"mail_id"`
	ExternalID string   `json:"external_id,omitempty"`
	ThreadID   string   `json:"thread_id"`
	FromName   string   `json:"from_name,omitempty"`
	FromEmail  string   `json:"from_email"`
	To         []string `json:"to"`
	CC         []string `json:"cc"`
	Subject    string   `json:"subject,omitempty"`
	Body       string   `json:"body"`
}

func (e Email) String() string {
	return fmt.Sprintf(
		"From: %s <%s>\nTo: %v\nCC: %v\nSubject: %s\n\n%s",
		e.FromName,
		e.FromEmail,
		e.To,
		e.CC,
		e.Subject,
		e.Body,
	)
}

type SummaryPayload struct {
	Text string `json:"text"`
}

type ClassificationPayload struct {
	Probabilities map[string]float64 `json:"probabilities"`
	Decisions     map[string]bool    `json:"decisions"`
}

type Action struct {
	ActionID string                 `json:"action_id"`
	MailID   string                 `json:"mail_id,omitempty"`
	Type     string                 `json:"type"`
	Status   string                 `json:"status"`
	Payload  map[string]interface{} `json:"payload"`
	Result   map[string]interface{} `json:"result,omitempty"`
}

type NewEmailResponse struct {
	MailID          string                `json:"mail_id"`
	Summary         *SummaryPayload       `json:"summary"`
	ProposedActions []Action              `json:"proposed_actions"`
	Classification  ClassificationPayload `json:"classification"`
}
