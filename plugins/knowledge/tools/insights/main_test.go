package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func fixture(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	dir := filepath.Join(root, "entries", "example")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	a := Analysis{Title: "Visual experiments", Summary: "Example", Coverage: json.RawMessage(`{"limitations":["Untested transfer"]}`), Insights: []Insight{
		{Claim: "Checkpoint restores scene state", Status: "source-claim", Caveats: "Demo only", Evidence: json.RawMessage(`[{"start":10,"end":20,"kind":"transcript"}]`)},
		{Claim: "Use explicit coordinates", Status: "inference", Caveats: "Not tested", Evidence: json.RawMessage(`[]`)},
	}}
	data, err := json.Marshal(a)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "analysis.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), []byte(`{"source":"https://example.com","analyzed_at":"2026-10-03"}`), 0600); err != nil {
		t.Fatal(err)
	}
	return root
}
func TestSearchJSONPreservesEvidenceAndCaveats(t *testing.T) {
	library := fixture(t)
	var out, diagnostics bytes.Buffer
	if err := run([]string{"search", "checkpoint", "--json", "--library", library}, &out, &diagnostics); err != nil {
		t.Fatal(err)
	}
	var matches []Match
	if err := json.Unmarshal(out.Bytes(), &matches); err != nil {
		t.Fatal(err)
	}
	if len(matches) != 1 || matches[0].Number != 1 || matches[0].Caveats != "Demo only" || !strings.Contains(string(matches[0].Evidence), "transcript") {
		t.Fatalf("unexpected matches: %+v", matches)
	}
}
func TestViewAndMarkdown(t *testing.T) {
	var out, errout bytes.Buffer
	if err := run([]string{"view", "example", "2", "--library", fixture(t), "--markdown"}, &out, &errout); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "Status: inference") || strings.Contains(out.String(), "Checkpoint restores") || strings.Contains(out.String(), "\x1b") {
		t.Fatal(out.String())
	}
}
func TestNoMatchesIsEmptyJSON(t *testing.T) {
	var out, errout bytes.Buffer
	if err := run([]string{"--library", fixture(t), "search", "absent", "--json"}, &out, &errout); err != nil {
		t.Fatal(err)
	}
	if strings.TrimSpace(out.String()) != "[]" {
		t.Fatal(out.String())
	}
}
func TestInvalidIDsAndNumbers(t *testing.T) {
	library := fixture(t)
	for _, args := range [][]string{{"view", "../example"}, {"view", "example", "1oops"}, {"view", "example", "0"}, {"search"}, {"search", "scene", "--limit", "0"}} {
		var out, errout bytes.Buffer
		if err := run(append([]string{"--library", library}, args...), &out, &errout); err == nil {
			t.Fatalf("accepted invalid args %v", args)
		}
	}
}
func TestBrokenEntryIsVisible(t *testing.T) {
	library := fixture(t)
	if err := os.Remove(filepath.Join(library, "entries", "example", "manifest.json")); err != nil {
		t.Fatal(err)
	}
	var out, errout bytes.Buffer
	if err := run([]string{"--library", library, "list"}, &out, &errout); err == nil {
		t.Fatal("missing manifest accepted")
	}
}
func TestTerminalControlSanitization(t *testing.T) {
	if got := clean("safe\x1b[31m\x00\r\ntext"); strings.ContainsAny(got, "\x1b\x00\r") {
		t.Fatal(got)
	}
}
