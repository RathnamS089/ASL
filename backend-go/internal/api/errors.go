package api

import (
	"encoding/json"
	"net/http"
	"strconv"
)

// apiError is the single error envelope from docs/API_CONTRACT.md.
type apiError struct {
	Status     int
	Code       string
	Message    string
	Retryable  bool
	RetryAfter int // seconds; 0 = no header
	Details    map[string]any
}

func (e *apiError) Error() string { return e.Code + ": " + e.Message }

func newErr(status int, code, msg string) *apiError {
	return &apiError{Status: status, Code: code, Message: msg}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, r *http.Request, e *apiError) {
	if e.RetryAfter > 0 {
		w.Header().Set("Retry-After", strconv.Itoa(e.RetryAfter))
	}
	body := map[string]any{
		"code":       e.Code,
		"message":    e.Message,
		"request_id": requestID(r.Context()),
		"retryable":  e.Retryable,
	}
	if len(e.Details) > 0 {
		body["details"] = e.Details
	}
	writeJSON(w, e.Status, map[string]any{"error": body})
}
