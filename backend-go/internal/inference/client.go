// Package inference is the Go side of docs/ML_CONTRACT.md: a client for the Python
// service and a bounded queue in front of it.
package inference

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"os"
	"time"
)

type Limits struct {
	MinSeconds float64 `json:"min_seconds"`
	MaxSeconds float64 `json:"max_seconds"`
	MaxSigns   int     `json:"max_signs"`
}

type Request struct {
	RequestID    string  `json:"request_id"`
	SignLanguage string  `json:"sign_language"`
	Clip         ClipRef `json:"clip"`
	Limits       Limits  `json:"limits"`
	Options      Options `json:"options"`
}

type ClipRef struct {
	Container        string `json:"container"`
	SizeBytes        int64  `json:"size_bytes"`
	ClientDurationMS *int   `json:"client_duration_ms,omitempty"`
}

type Options struct {
	Generate            bool `json:"generate"`
	IncludeAlternatives bool `json:"include_alternatives"`
}

type Segment struct {
	Label        string   `json:"label"`
	StartSeconds float64  `json:"start_seconds"`
	EndSeconds   float64  `json:"end_seconds"`
	Confidence   *float64 `json:"confidence"`
}

type Token struct {
	Text         string `json:"text"`
	SegmentIndex *int   `json:"segment_index"`
	Emphasis     string `json:"emphasis"`
}

type Recognition struct {
	DurationSeconds   float64   `json:"duration_seconds"`
	Segments          []Segment `json:"segments"`
	OverallConfidence *float64  `json:"overall_confidence"`
	LowConfidence     bool      `json:"low_confidence"`
}

type Generation struct {
	Text           string  `json:"text"`
	Tokens         []Token `json:"tokens"`
	Source         string  `json:"source"`
	Constrained    bool    `json:"constrained"`
	RejectedReason *string `json:"rejected_reason"`
}

type ModelInfo struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

type Response struct {
	RequestID   string               `json:"request_id"`
	Mock        bool                 `json:"mock"`
	Recognition Recognition          `json:"recognition"`
	Generation  *Generation          `json:"generation"`
	Models      map[string]ModelInfo `json:"models"`
	TimingsMS   map[string]int       `json:"timings_ms"`
}

// Error is a typed failure from the ML service or the connection to it.
type Error struct {
	Status  int    // HTTP status from the ML service; 0 for transport failures
	Code    string // contract error code, or "unavailable" / "timeout"
	Message string
	Details map[string]any
}

func (e *Error) Error() string { return fmt.Sprintf("ml %d %s: %s", e.Status, e.Code, e.Message) }

type Client struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

func NewClient(baseURL, token string) *Client {
	return &Client{BaseURL: baseURL, Token: token, HTTP: &http.Client{}}
}

// Infer streams the clip to POST /v1/infer. The caller's context carries the deadline.
func (c *Client) Infer(ctx context.Context, req Request, clipPath string) (*Response, error) {
	meta, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	pr, pw := io.Pipe()
	mw := multipart.NewWriter(pw)
	go func() {
		pw.CloseWithError(writeInferBody(mw, meta, clipPath))
	}()
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/v1/infer", pr)
	if err != nil {
		pr.Close()
		return nil, err
	}
	httpReq.Header.Set("Content-Type", mw.FormDataContentType())
	httpReq.Header.Set("X-Internal-Token", c.Token)
	httpReq.Header.Set("X-Request-ID", req.RequestID)
	resp, err := c.HTTP.Do(httpReq)
	if err != nil {
		pr.Close()
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return nil, &Error{Code: "timeout", Message: "inference timed out"}
		}
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, &Error{Code: "unavailable", Message: err.Error()}
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return nil, &Error{Code: "timeout", Message: "inference timed out"}
		}
		return nil, &Error{Code: "unavailable", Message: err.Error()}
	}
	if resp.StatusCode != http.StatusOK {
		var env struct {
			Error struct {
				Code    string         `json:"code"`
				Message string         `json:"message"`
				Details map[string]any `json:"details"`
			} `json:"error"`
		}
		if json.Unmarshal(body, &env) != nil || env.Error.Code == "" {
			return nil, &Error{Status: resp.StatusCode, Code: "internal", Message: "unparseable ML error"}
		}
		return nil, &Error{Status: resp.StatusCode, Code: env.Error.Code, Message: env.Error.Message, Details: env.Error.Details}
	}
	var out Response
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, &Error{Status: resp.StatusCode, Code: "internal", Message: "invalid ML response JSON"}
	}
	return &out, nil
}

func writeInferBody(mw *multipart.Writer, meta []byte, clipPath string) error {
	h := textproto.MIMEHeader{}
	h.Set("Content-Disposition", `form-data; name="request"`)
	h.Set("Content-Type", "application/json")
	part, err := mw.CreatePart(h)
	if err != nil {
		return err
	}
	if _, err := part.Write(meta); err != nil {
		return err
	}
	f, err := os.Open(clipPath)
	if err != nil {
		return err
	}
	defer f.Close()
	clip, err := mw.CreateFormFile("clip", "clip")
	if err != nil {
		return err
	}
	if _, err := io.Copy(clip, f); err != nil {
		return err
	}
	return mw.Close()
}

// Ready reports whether the ML service says it can serve inferences.
func (c *Client) Ready(ctx context.Context) (bool, bool, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/health", nil)
	if err != nil {
		return false, false, err
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return false, false, err
	}
	defer resp.Body.Close()
	var h struct {
		Status string `json:"status"`
		Mock   bool   `json:"mock"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<16)).Decode(&h); err != nil {
		return false, false, err
	}
	return h.Status == "ready", h.Mock, nil
}
