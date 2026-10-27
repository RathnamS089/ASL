package api

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"visualiser/backend-go/internal/config"
	"visualiser/backend-go/internal/inference"
)

var webm = append([]byte{0x1A, 0x45, 0xDF, 0xA3}, []byte("fake-webm-body")...)
var mp4 = append([]byte{0, 0, 0, 0x18}, []byte("ftypisomfake-mp4")...)

type fakeML struct {
	mu       sync.Mutex
	resp     *inference.Response
	err      error
	delay    time.Duration
	gotReq   inference.Request
	gotPath  string
	pathSeen bool
}

func (f *fakeML) Infer(ctx context.Context, req inference.Request, clipPath string) (*inference.Response, error) {
	f.mu.Lock()
	f.gotReq, f.gotPath = req, clipPath
	_, err := os.Stat(clipPath)
	f.pathSeen = err == nil
	f.mu.Unlock()
	if f.delay > 0 {
		select {
		case <-time.After(f.delay):
		case <-ctx.Done():
			return nil, &inference.Error{Code: "timeout"}
		}
	}
	return f.resp, f.err
}

func (f *fakeML) Ready(context.Context) (bool, bool, error) { return f.err == nil, false, nil }

func conf(t *testing.T) config.Config {
	t.Helper()
	return config.Config{
		MaxUploadBytes: 1 << 20, MaxMetadataBytes: 4096, InferenceConcurrency: 1, QueueDepth: 1,
		QueueWait: 200 * time.Millisecond, MLTimeout: time.Second, RatePerMinute: 100,
		SignLanguage: "ase", MinClipSeconds: 0.5, MaxClipSeconds: 10, MaxSigns: 8,
		WebDistDir: t.TempDir(), MockResponsePath: "../../../contracts/examples/translation-response.json",
		Version: "test",
	}
}

func ptr[T any](v T) *T { return &v }

func goodResponse() *inference.Response {
	return &inference.Response{
		RequestID: "x",
		Recognition: inference.Recognition{DurationSeconds: 3, Segments: []inference.Segment{
			{Label: "HELLO", StartSeconds: 0.2, EndSeconds: 1, Confidence: ptr(0.9)},
			{Label: "FRIEND", StartSeconds: 1.2, EndSeconds: 2, Confidence: ptr(0.4)},
		}},
		Generation: &inference.Generation{Text: "Hello, friend.", Source: "model", Constrained: true, Tokens: []inference.Token{
			{Text: "Hello,", SegmentIndex: ptr(0), Emphasis: "normal"},
			{Text: "friend.", SegmentIndex: ptr(1), Emphasis: "low_confidence"},
		}},
		Models: map[string]inference.ModelInfo{"recognizer": {Name: "islr", Version: "0.1.0"}},
	}
}

func newServer(t *testing.T, c config.Config, ml Inferer) http.Handler {
	t.Helper()
	s, err := New(c, ml, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatal(err)
	}
	return s.Handler()
}

type part struct {
	name, filename string
	body           []byte
}

func multipartReq(t *testing.T, path string, parts ...part) *http.Request {
	t.Helper()
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	for _, p := range parts {
		var w io.Writer
		var err error
		if p.filename != "" {
			w, err = mw.CreateFormFile(p.name, p.filename)
		} else {
			w, err = mw.CreateFormField(p.name)
		}
		if err != nil {
			t.Fatal(err)
		}
		w.Write(p.body)
	}
	mw.Close()
	r := httptest.NewRequest(http.MethodPost, path, &buf)
	r.Header.Set("Content-Type", mw.FormDataContentType())
	return r
}

func do(h http.Handler, r *http.Request) (*httptest.ResponseRecorder, map[string]any) {
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	var body map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	return w, body
}

func errCode(body map[string]any) string {
	e, _ := body["error"].(map[string]any)
	code, _ := e["code"].(string)
	return code
}

func TestHealthAndPrefix(t *testing.T) {
	h := newServer(t, conf(t), &fakeML{})
	for _, path := range []string{"/health", "/api/health"} {
		w, body := do(h, httptest.NewRequest(http.MethodGet, path, nil))
		if w.Code != 200 || body["status"] != "ok" {
			t.Fatalf("%s: %d %v", path, w.Code, body)
		}
		if w.Header().Get("X-Request-ID") == "" || w.Header().Get("Content-Security-Policy") == "" {
			t.Fatalf("%s: missing request id or CSP", path)
		}
	}
	w, body := do(h, httptest.NewRequest(http.MethodGet, "/api/v1/nope", nil))
	if w.Code != 404 || errCode(body) != "not_found" {
		t.Fatalf("unknown route: %d %v", w.Code, body)
	}
}

func TestRequestIDEcho(t *testing.T) {
	h := newServer(t, conf(t), &fakeML{})
	r := httptest.NewRequest(http.MethodGet, "/health", nil)
	r.Header.Set("X-Request-ID", "6f1c8a52-4f0e-4a4e-9a51-3e2b7d1c9a10")
	w, _ := do(h, r)
	if w.Header().Get("X-Request-ID") != "6f1c8a52-4f0e-4a4e-9a51-3e2b7d1c9a10" {
		t.Fatal("valid UUID not echoed")
	}
	r.Header.Set("X-Request-ID", "<script>")
	w, _ = do(h, r)
	if strings.Contains(w.Header().Get("X-Request-ID"), "script") {
		t.Fatal("invalid request id echoed")
	}
}

func TestTranslateSuccessMapsContractAndCleansUp(t *testing.T) {
	ml := &fakeML{resp: goodResponse()}
	h := newServer(t, conf(t), ml)
	meta := `{"client_request_id":"c1","sign_language":"ase","recording":{"duration_ms":4200}}`
	w, body := do(h, multipartReq(t, "/api/v1/translations", part{"metadata", "", []byte(meta)}, part{"clip", "c.webm", webm}))
	if w.Code != 200 {
		t.Fatalf("status %d: %v", w.Code, body)
	}
	if body["sentence"] != "Hello, friend." || body["is_mock"] != false || !strings.HasPrefix(body["id"].(string), "tr_") {
		t.Fatalf("body: %v", body)
	}
	tokens := body["tokens"].([]any)
	if tokens[1].(map[string]any)["sign_index"].(float64) != 1 || tokens[1].(map[string]any)["emphasis"] != "low_confidence" {
		t.Fatalf("tokens not mapped: %v", tokens)
	}
	if ml.gotReq.Clip.Container != "webm" || *ml.gotReq.Clip.ClientDurationMS != 4200 || !ml.gotReq.Options.Generate {
		t.Fatalf("ML request: %+v", ml.gotReq)
	}
	if !ml.pathSeen {
		t.Fatal("clip file did not exist during inference")
	}
	if _, err := os.Stat(ml.gotPath); !os.IsNotExist(err) {
		t.Fatal("temp clip not removed")
	}
}

func TestLettersModeIsPassedThrough(t *testing.T) {
	ml := &fakeML{resp: goodResponse()}
	h := newServer(t, conf(t), ml)
	w, body := do(h, multipartReq(t, "/v1/translations", part{"metadata", "", []byte(`{"mode":"letters"}`)}, part{"clip", "c", webm}))
	if w.Code != 200 || ml.gotReq.Options.Mode != "letters" || body["mode"] != "letters" {
		t.Fatalf("letters: %d %v %+v", w.Code, body, ml.gotReq.Options)
	}
	w, body = do(h, multipartReq(t, "/v1/translations", part{"metadata", "", []byte(`{"mode":"poems"}`)}, part{"clip", "c", webm}))
	if w.Code != 400 || errCode(body) != "invalid_request" {
		t.Fatalf("bad mode: %d %v", w.Code, body)
	}
	w, _ = do(h, multipartReq(t, "/v1/translations", part{"clip", "c", webm}))
	if ml.gotReq.Options.Mode != "signs" {
		t.Fatalf("default mode: %q", ml.gotReq.Options.Mode)
	}
}

func TestRawBodyCompatibility(t *testing.T) {
	ml := &fakeML{resp: goodResponse()}
	h := newServer(t, conf(t), ml)
	r := httptest.NewRequest(http.MethodPost, "/v1/translations", bytes.NewReader(mp4))
	r.Header.Set("Content-Type", "video/quicktime")
	w, body := do(h, r)
	if w.Code != 200 || ml.gotReq.Clip.Container != "mp4" {
		t.Fatalf("raw upload: %d %v", w.Code, body)
	}
}

func TestUploadValidation(t *testing.T) {
	c := conf(t)
	c.MaxUploadBytes = 8192
	h := newServer(t, c, &fakeML{resp: goodResponse()})
	big := append(append([]byte{}, webm...), bytes.Repeat([]byte("x"), 16384)...)
	cases := []struct {
		name   string
		req    *http.Request
		status int
		code   string
	}{
		{"missing clip", multipartReq(t, "/v1/translations", part{"metadata", "", []byte(`{}`)}), 400, "invalid_request"},
		{"extra part", multipartReq(t, "/v1/translations", part{"clip", "c", webm}, part{"evil", "", []byte("x")}), 400, "invalid_request"},
		{"two clips", multipartReq(t, "/v1/translations", part{"clip", "a", webm}, part{"clip", "b", webm}), 400, "invalid_request"},
		{"bad metadata", multipartReq(t, "/v1/translations", part{"metadata", "", []byte(`{nope`)}, part{"clip", "c", webm}), 400, "invalid_request"},
		{"huge metadata", multipartReq(t, "/v1/translations", part{"metadata", "", bytes.Repeat([]byte("a"), 5000)}, part{"clip", "c", webm}), 400, "invalid_request"},
		{"not a video", multipartReq(t, "/v1/translations", part{"clip", "c.webm", []byte("<html>hello</html>")}), 415, "unsupported_media_type"},
		{"too large", multipartReq(t, "/v1/translations", part{"clip", "c.webm", big}), 413, "payload_too_large"},
		{"wrong language", multipartReq(t, "/v1/translations", part{"metadata", "", []byte(`{"sign_language":"bfi"}`)}, part{"clip", "c", webm}), 422, "unsupported_sign_language"},
		{"too long", multipartReq(t, "/v1/translations", part{"metadata", "", []byte(`{"recording":{"duration_ms":15000}}`)}, part{"clip", "c", webm}), 422, "clip_too_long"},
		{"too short", multipartReq(t, "/v1/translations", part{"metadata", "", []byte(`{"recording":{"duration_ms":100}}`)}, part{"clip", "c", webm}), 422, "clip_too_short"},
	}
	plain := httptest.NewRequest(http.MethodPost, "/v1/translations", strings.NewReader("hi"))
	plain.Header.Set("Content-Type", "text/plain")
	cases = append(cases, struct {
		name   string
		req    *http.Request
		status int
		code   string
	}{"text body", plain, 415, "unsupported_media_type"})
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			w, body := do(h, tc.req)
			if w.Code != tc.status || errCode(body) != tc.code {
				t.Fatalf("got %d %q, want %d %q (%v)", w.Code, errCode(body), tc.status, tc.code, body)
			}
			e := body["error"].(map[string]any)
			if e["request_id"] == "" || e["message"] == "" {
				t.Fatalf("envelope incomplete: %v", e)
			}
		})
	}
}

func TestNoSignsAndMLErrors(t *testing.T) {
	empty := goodResponse()
	empty.Recognition.Segments = nil
	empty.Generation = nil
	cases := []struct {
		name   string
		ml     *fakeML
		status int
		code   string
	}{
		{"no signs", &fakeML{resp: empty}, 422, "no_signs_detected"},
		{"timeout", &fakeML{err: &inference.Error{Code: "timeout"}}, 504, "inference_timeout"},
		{"down", &fakeML{err: &inference.Error{Code: "unavailable"}}, 503, "inference_unavailable"},
		{"not loaded", &fakeML{err: &inference.Error{Status: 503, Code: "models_not_loaded"}}, 503, "inference_unavailable"},
		{"undecodable", &fakeML{err: &inference.Error{Status: 422, Code: "undecodable_clip", Message: "bad video"}}, 422, "undecodable_clip"},
		{"ml bug", &fakeML{err: &inference.Error{Status: 500, Code: "internal"}}, 502, "inference_failed"},
		{"token wrong", &fakeML{err: &inference.Error{Status: 401, Code: "unauthorized"}}, 500, "internal"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := newServer(t, conf(t), tc.ml)
			w, body := do(h, multipartReq(t, "/v1/translations", part{"clip", "c", webm}))
			if w.Code != tc.status || errCode(body) != tc.code {
				t.Fatalf("got %d %q, want %d %q", w.Code, errCode(body), tc.status, tc.code)
			}
		})
	}
}

func TestMLDeadlineBecomes504(t *testing.T) {
	c := conf(t)
	c.MLTimeout = 50 * time.Millisecond
	h := newServer(t, c, &fakeML{resp: goodResponse(), delay: time.Second})
	w, body := do(h, multipartReq(t, "/v1/translations", part{"clip", "c", webm}))
	if w.Code != 504 || errCode(body) != "inference_timeout" {
		t.Fatalf("got %d %v", w.Code, body)
	}
}

func TestQueueFullReturnsBusy(t *testing.T) {
	c := conf(t)
	c.QueueDepth = 0
	ml := &fakeML{resp: goodResponse(), delay: 300 * time.Millisecond}
	h := newServer(t, c, ml)
	done := make(chan int)
	go func() {
		w, _ := do(h, multipartReq(t, "/v1/translations", part{"clip", "c", webm}))
		done <- w.Code
	}()
	time.Sleep(50 * time.Millisecond)
	w, body := do(h, multipartReq(t, "/v1/translations", part{"clip", "c", webm}))
	if w.Code != 503 || errCode(body) != "busy" || w.Header().Get("Retry-After") == "" {
		t.Fatalf("second request: %d %v", w.Code, body)
	}
	if first := <-done; first != 200 {
		t.Fatalf("first request: %d", first)
	}
}

func TestRateLimit(t *testing.T) {
	c := conf(t)
	c.RatePerMinute = 2
	h := newServer(t, c, &fakeML{resp: goodResponse()})
	var last *httptest.ResponseRecorder
	var body map[string]any
	for i := 0; i < 3; i++ {
		last, body = do(h, multipartReq(t, "/v1/translations", part{"clip", "c", webm}))
	}
	if last.Code != 429 || errCode(body) != "rate_limited" || last.Header().Get("Retry-After") == "" {
		t.Fatalf("third request: %d %v", last.Code, body)
	}
}

func TestClientKeyTrustsProxyOnlyFromLoopback(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/", nil)
	r.RemoteAddr = "127.0.0.1:5555"
	r.Header.Set("Tailscale-User-Login", "me@example.com")
	if clientKey(r, true) != "ts:me@example.com" {
		t.Fatal("tailscale identity ignored")
	}
	r.RemoteAddr = "192.168.1.9:5555"
	if clientKey(r, true) != "192.168.1.9" {
		t.Fatal("forwarded headers trusted from a non-loopback peer")
	}
}

func TestMockMode(t *testing.T) {
	c := conf(t)
	c.MockTranslation = true
	h := newServer(t, c, nil)
	w, body := do(h, multipartReq(t, "/api/v1/translations", part{"clip", "c", webm}))
	if w.Code != 200 || body["is_mock"] != true || body["sentence"] == "" {
		t.Fatalf("mock: %d %v", w.Code, body)
	}
	w, body = do(h, httptest.NewRequest(http.MethodGet, "/api/health/ready", nil))
	if w.Code != 200 || body["mock"] != true {
		t.Fatalf("ready: %v", body)
	}
}

func TestCORS(t *testing.T) {
	c := conf(t)
	c.CORSAllowedOrigins = []string{"https://ok.example"}
	h := newServer(t, c, &fakeML{})
	r := httptest.NewRequest(http.MethodOptions, "/v1/translations", nil)
	r.Header.Set("Origin", "https://ok.example")
	w, _ := do(h, r)
	if w.Code != 204 || w.Header().Get("Access-Control-Allow-Origin") != "https://ok.example" {
		t.Fatalf("allowed origin: %d %v", w.Code, w.Header())
	}
	r.Header.Set("Origin", "https://evil.example")
	w, _ = do(h, r)
	if w.Header().Get("Access-Control-Allow-Origin") != "" {
		t.Fatal("disallowed origin got CORS headers")
	}
}

func TestWebAppAndSPAFallback(t *testing.T) {
	c := conf(t)
	os.MkdirAll(filepath.Join(c.WebDistDir, "assets"), 0o755)
	os.WriteFile(filepath.Join(c.WebDistDir, "index.html"), []byte("<!doctype html><title>app</title>"), 0o644)
	os.WriteFile(filepath.Join(c.WebDistDir, "assets", "app-123.js"), []byte("console.log(1)"), 0o644)
	h := newServer(t, c, &fakeML{})
	w, _ := do(h, httptest.NewRequest(http.MethodGet, "/", nil))
	if w.Code != 200 || !strings.Contains(w.Body.String(), "<title>app") {
		t.Fatalf("index: %d %s", w.Code, w.Body.String())
	}
	w, _ = do(h, httptest.NewRequest(http.MethodGet, "/record", nil))
	if !strings.Contains(w.Body.String(), "<title>app") {
		t.Fatal("SPA fallback missing")
	}
	w, _ = do(h, httptest.NewRequest(http.MethodGet, "/assets/app-123.js", nil))
	if !strings.Contains(w.Header().Get("Cache-Control"), "immutable") {
		t.Fatal("hashed asset not cached")
	}
	w, _ = do(h, httptest.NewRequest(http.MethodGet, "/../../etc/passwd", nil))
	if strings.Contains(w.Body.String(), "root:") {
		t.Fatal("path traversal")
	}
}
