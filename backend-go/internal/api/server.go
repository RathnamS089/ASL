// Package api implements the browser-facing API in docs/API_CONTRACT.md and serves the
// built web app, so one port (and one Tailscale Serve URL) carries everything.
package api

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"visualiser/backend-go/internal/config"
	"visualiser/backend-go/internal/inference"
)

// Inferer is the ML client; an interface so tests can fake it.
type Inferer interface {
	Infer(ctx context.Context, req inference.Request, clipPath string) (*inference.Response, error)
	Ready(ctx context.Context) (ready bool, mock bool, err error)
}

type Server struct {
	cfg   config.Config
	ml    Inferer
	queue *inference.Queue
	rate  *rateLimiter
	log   *slog.Logger
	mock  json.RawMessage
	now   func() time.Time
}

func New(cfg config.Config, ml Inferer, log *slog.Logger) (*Server, error) {
	s := &Server{
		cfg:   cfg,
		ml:    ml,
		queue: inference.NewQueue(cfg.InferenceConcurrency, cfg.QueueDepth),
		rate:  newRateLimiter(cfg.RatePerMinute),
		log:   log,
		now:   time.Now,
	}
	if cfg.MockTranslation {
		raw, err := os.ReadFile(cfg.MockResponsePath)
		if err != nil {
			return nil, fmt.Errorf("MOCK_TRANSLATION=1 but %s: %w", cfg.MockResponsePath, err)
		}
		if !json.Valid(raw) {
			return nil, fmt.Errorf("%s is not valid JSON", cfg.MockResponsePath)
		}
		s.mock = raw
	}
	return s, nil
}

// Handler routes the API at / and at /api (the web app's base), plus the web app.
func (s *Server) Handler() http.Handler {
	api := http.NewServeMux()
	api.HandleFunc("GET /health", s.health)
	api.HandleFunc("GET /health/ready", s.ready)
	api.HandleFunc("POST /v1/translations", s.translate)
	api.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, r, newErr(http.StatusNotFound, "not_found", "Unknown API route."))
	})

	root := http.NewServeMux()
	root.Handle("/api/", http.StripPrefix("/api", api))
	root.Handle("/health", api)
	root.Handle("/health/", api)
	root.Handle("/v1/", api)
	root.Handle("/", s.webApp())

	var h http.Handler = root
	h = withCORS(s.cfg.CORSAllowedOrigins, h)
	h = withSecurityHeaders(h)
	h = withRecover(s.log, h)
	h = withLogging(s.log, h)
	return withRequestID(h)
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "version": s.cfg.Version})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	if s.cfg.MockTranslation {
		writeJSON(w, http.StatusOK, map[string]any{"status": "ready", "inference": "mock", "mock": true})
		return
	}
	ok, mock, err := s.ml.Ready(r.Context())
	if err != nil || !ok {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"status": "not_ready", "inference": "unavailable", "mock": mock})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ready", "inference": "ok", "mock": mock})
}

func (s *Server) translate(w http.ResponseWriter, r *http.Request) {
	started := s.now()
	if wait := s.rate.allow(clientKey(r, s.cfg.TrustForwardedFor)); wait > 0 {
		writeError(w, r, &apiError{Status: http.StatusTooManyRequests, Code: "rate_limited",
			Message: "Too many translations. Wait a moment and try again.", Retryable: true, RetryAfter: wait})
		return
	}
	up, e := readUpload(w, r, s.cfg.MaxUploadBytes, s.cfg.MaxMetadataBytes)
	if e != nil {
		writeError(w, r, e)
		return
	}
	defer up.remove()

	mode := up.Meta.Mode
	if mode == "" {
		mode = "signs"
	}
	if mode != "signs" && mode != "letters" {
		writeError(w, r, newErr(http.StatusBadRequest, "invalid_request", `metadata.mode must be "signs" or "letters".`))
		return
	}
	lang := s.cfg.SignLanguage
	if up.Meta.SignLanguage != "" && up.Meta.SignLanguage != lang {
		writeError(w, r, &apiError{Status: 422, Code: "unsupported_sign_language",
			Message: fmt.Sprintf("This server translates %q only.", lang)})
		return
	}
	var clientMS *int
	if rec := up.Meta.Recording; rec != nil && rec.DurationMS != nil {
		clientMS = rec.DurationMS
		secs := float64(*rec.DurationMS) / 1000
		if secs > s.cfg.MaxClipSeconds+0.5 { // small allowance for client clock jitter
			writeError(w, r, &apiError{Status: 422, Code: "clip_too_long",
				Message: fmt.Sprintf("The clip is %.1f s long. Record %.0f seconds or less.", secs, s.cfg.MaxClipSeconds),
				Details: map[string]any{"max_seconds": s.cfg.MaxClipSeconds, "actual_seconds": secs}})
			return
		}
		if secs < s.cfg.MinClipSeconds {
			writeError(w, r, &apiError{Status: 422, Code: "clip_too_short",
				Message: "The clip is too short. Record at least half a second.",
				Details: map[string]any{"min_seconds": s.cfg.MinClipSeconds, "actual_seconds": secs}})
			return
		}
	}

	release, err := s.queue.Acquire(r.Context(), s.cfg.QueueWait)
	if err != nil {
		if errors.Is(err, inference.ErrBusy) {
			writeError(w, r, &apiError{Status: 503, Code: "busy",
				Message: "The translator is busy. Try again in a few seconds.", Retryable: true, RetryAfter: 5})
		}
		return // client went away
	}
	queued := s.now().Sub(started)
	defer release()

	if s.cfg.MockTranslation {
		s.writeMock(w, r, queued, started)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), s.cfg.MLTimeout)
	defer cancel()
	inferStart := s.now()
	res, err := s.ml.Infer(ctx, inference.Request{
		RequestID:    requestID(r.Context()),
		SignLanguage: lang,
		Clip:         inference.ClipRef{Container: up.Container, SizeBytes: up.Size, ClientDurationMS: clientMS},
		Limits:       inference.Limits{MinSeconds: s.cfg.MinClipSeconds, MaxSeconds: s.cfg.MaxClipSeconds, MaxSigns: s.cfg.MaxSigns},
		Options:      inference.Options{Generate: true, Mode: mode},
	}, up.Path)
	if err != nil {
		if r.Context().Err() != nil {
			return // client cancelled; nothing to send
		}
		writeError(w, r, mapMLError(err))
		return
	}
	if len(res.Recognition.Segments) == 0 || res.Generation == nil || strings.TrimSpace(res.Generation.Text) == "" {
		msg := "No signs were recognised. Keep your hands and face in frame, with good light, and try again."
		if mode == "letters" {
			msg = "No letters were recognised. Hold each letter still for about half a second, with your hand clearly in view."
		}
		writeError(w, r, &apiError{Status: 422, Code: "no_signs_detected", Message: msg, Details: debugInfo(res)})
		return
	}
	writeJSON(w, http.StatusOK, s.publicResponse(res, mode, queued, s.now().Sub(inferStart), s.now().Sub(started)))
}

func (s *Server) writeMock(w http.ResponseWriter, r *http.Request, queued time.Duration, started time.Time) {
	var body map[string]any
	_ = json.Unmarshal(s.mock, &body)
	body["id"] = newTranslationID()
	body["created_at"] = s.now().UTC().Format(time.RFC3339)
	body["is_mock"] = true
	body["generation"] = map[string]any{"source": "mock", "constrained": true}
	body["timings_ms"] = map[string]any{"queue": queued.Milliseconds(), "inference": 0, "total": s.now().Sub(started).Milliseconds()}
	writeJSON(w, http.StatusOK, body)
}

type publicSign struct {
	Label        string   `json:"label"`
	StartSeconds float64  `json:"start_seconds"`
	EndSeconds   float64  `json:"end_seconds"`
	Confidence   *float64 `json:"confidence"`
}

type publicToken struct {
	Text      string `json:"text"`
	SignIndex *int   `json:"sign_index"`
	Emphasis  string `json:"emphasis"`
}

func (s *Server) publicResponse(res *inference.Response, mode string, queued, inferDur, total time.Duration) map[string]any {
	signs := make([]publicSign, len(res.Recognition.Segments))
	for i, seg := range res.Recognition.Segments {
		signs[i] = publicSign{seg.Label, seg.StartSeconds, seg.EndSeconds, seg.Confidence}
	}
	tokens := make([]publicToken, len(res.Generation.Tokens))
	for i, t := range res.Generation.Tokens {
		emphasis := t.Emphasis
		if emphasis == "" {
			emphasis = "normal"
		}
		tokens[i] = publicToken{t.Text, t.SegmentIndex, emphasis}
	}
	models := map[string]string{}
	for k, m := range res.Models {
		models[k] = m.Name + "@" + m.Version
	}
	return map[string]any{
		"id":             newTranslationID(),
		"created_at":     s.now().UTC().Format(time.RFC3339),
		"sentence":       res.Generation.Text,
		"signs":          signs,
		"tokens":         tokens,
		"sign_language":  s.cfg.SignLanguage,
		"mode":           mode,
		"low_confidence": res.Recognition.LowConfidence,
		"generation":     map[string]any{"source": res.Generation.Source, "constrained": res.Generation.Constrained},
		"is_mock":        res.Mock,
		"models":         models,
		"debug":          debugInfo(res),
		"timings_ms": map[string]any{"queue": queued.Milliseconds(), "inference": inferDur.Milliseconds(),
			"total": total.Milliseconds()},
	}
}

// debugInfo is what the recognizer saw, including guesses below the confidence floor, so a
// missed sign can be told apart from a sign that was never in frame.
func debugInfo(res *inference.Response) map[string]any {
	d := map[string]any{"hands_seen": res.Recognition.HandsSeen}
	if len(res.Recognition.Candidates) > 0 {
		d["candidates"] = res.Recognition.Candidates
	} else {
		d["candidates"] = []any{}
	}
	return d
}

// mapMLError follows the table in docs/ML_CONTRACT.md.
func mapMLError(err error) *apiError {
	var me *inference.Error
	if !errors.As(err, &me) {
		return &apiError{Status: 500, Code: "internal", Message: "Unexpected server error.", Retryable: true}
	}
	switch me.Code {
	case "timeout":
		return &apiError{Status: 504, Code: "inference_timeout", Message: "Translation took too long. Try a shorter clip.", Retryable: true}
	case "unavailable", "models_not_loaded":
		return &apiError{Status: 503, Code: "inference_unavailable", Message: "The translator is not running right now.", Retryable: true, RetryAfter: 10}
	case "busy":
		return &apiError{Status: 503, Code: "busy", Message: "The translator is busy. Try again in a few seconds.", Retryable: true, RetryAfter: 5}
	case "undecodable_clip", "clip_too_short", "clip_too_long", "unsupported_sign_language":
		msg := me.Message
		if msg == "" {
			msg = "The clip could not be used."
		}
		return &apiError{Status: 422, Code: me.Code, Message: msg, Details: me.Details}
	case "clip_too_large":
		return &apiError{Status: 413, Code: "payload_too_large", Message: "The clip is too large."}
	case "invalid_request", "unauthorized":
		return &apiError{Status: 500, Code: "internal", Message: "Server misconfiguration.", Retryable: false}
	}
	return &apiError{Status: 502, Code: "inference_failed", Message: "The translator failed. Try again.", Retryable: true}
}

func newTranslationID() string {
	var b [10]byte
	_, _ = rand.Read(b[:])
	return "tr_" + hex.EncodeToString(b[:])
}

// webApp serves web/dist with an SPA fallback to index.html. Missing dist is not an error:
// the API still works and "/" explains how to build the app.
func (s *Server) webApp() http.Handler {
	dir := s.cfg.WebDistDir
	files := http.FileServer(http.Dir(dir))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			writeError(w, r, newErr(http.StatusMethodNotAllowed, "invalid_request", "Method not allowed."))
			return
		}
		clean := filepath.Clean("/" + r.URL.Path)
		if info, err := os.Stat(filepath.Join(dir, clean)); err == nil && !info.IsDir() {
			if strings.HasPrefix(clean, "/assets/") { // content-hashed by Vite
				w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
			}
			files.ServeHTTP(w, r)
			return
		}
		index := filepath.Join(dir, "index.html")
		if _, err := os.Stat(index); err != nil {
			w.Header().Set("Content-Type", "text/plain; charset=utf-8")
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte("Web app not built. Run `npm run build` in web/.\n"))
			return
		}
		w.Header().Set("Cache-Control", "no-cache")
		http.ServeFile(w, r, index)
	})
}
