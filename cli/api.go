package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type APIClient struct {
	baseURL    string
	httpClient *http.Client
}

func NewAPIClient(baseURL string) *APIClient {
	trimmed := strings.TrimRight(baseURL, "/")
	return &APIClient{
		baseURL: trimmed,
		httpClient: &http.Client{
			Timeout: 60 * time.Second,
		},
	}
}

func (c *APIClient) PostNewEmail(ctx context.Context, email Email) (*NewEmailResponse, error) {
	var response NewEmailResponse
	if err := c.post(ctx, "/new_email", email, &response); err != nil {
		return nil, err
	}
	return &response, nil
}

func (c *APIClient) ApproveAction(ctx context.Context, actionID string) (Action, error) {
	request := map[string]string{"action_id": actionID}
	var response Action
	if err := c.post(ctx, "/action/approve", request, &response); err != nil {
		return Action{}, err
	}
	return response, nil
}

func (c *APIClient) RejectAction(ctx context.Context, actionID string) (Action, error) {
	request := map[string]string{"action_id": actionID}
	var response Action
	if err := c.post(ctx, "/action/reject", request, &response); err != nil {
		return Action{}, err
	}
	return response, nil
}

func (c *APIClient) ModifyAction(
	ctx context.Context,
	actionID string,
	payload map[string]interface{},
	applyToGeneral bool,
) (Action, error) {
	request := map[string]interface{}{
		"action_id":                    actionID,
		"payload":                      payload,
		"record_preferences":           true,
		"apply_to_general_preferences": applyToGeneral,
	}
	var response Action
	if err := c.post(ctx, "/action/modify", request, &response); err != nil {
		return Action{}, err
	}
	return response, nil
}

func (c *APIClient) post(ctx context.Context, path string, payload interface{}, target interface{}) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("post %s: %w", path, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		raw, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("post %s: status %d: %s", path, resp.StatusCode, strings.TrimSpace(string(raw)))
	}

	decoder := json.NewDecoder(resp.Body)
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}
