package main

import (
	"flag"
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	host := flag.String("host", "localhost", "Backend host")
	port := flag.Int("port", 8000, "Backend port")
	scheme := flag.String("scheme", "http", "Backend scheme (http or https)")
	baseURL := flag.String("base-url", "", "Override full backend base URL (e.g. http://localhost:8000)")
	flag.Parse()

	url := *baseURL
	if url == "" {
		url = fmt.Sprintf("%s://%s:%d", *scheme, *host, *port)
	}

	client := NewAPIClient(url)
	model := newAppModel(client)
	program := tea.NewProgram(model, tea.WithAltScreen())

	if _, err := program.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}
