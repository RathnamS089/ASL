package inference

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func clipFile(t *testing.T) string {
	p := filepath.Join(t.TempDir(), "clip")
	os.WriteFile(p, []byte("\x1a\x45\xdf\xa3clip-bytes"), 0o600)
	return p
}

func TestInferSendsContractMultipart(t *testing.T) {
	example, err := os.ReadFile("../../../contracts/examples/ml-infer-response.json")
	if err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/infer" || r.Header.Get("X-Internal-Token") != "secret" {
			t.Errorf("path/token: %s %q", r.URL.Path, r.Header.Get("X-Internal-Token"))
		}
		mr, err := r.MultipartReader()
		if err != nil {
			t.Fatal(err)
		}
		seen := map[string]string{}
		for {
			p, err := mr.NextPart()
			if err == io.EOF {
				break
			}
			b, _ := io.ReadAll(p)
			seen[p.FormName()] = string(b)
		}
		var req Request
		if err := json.Unmarshal([]byte(seen["request"]), &req); err != nil || req.RequestID != "r1" || req.Limits.MaxSeconds != 10 {
			t.Errorf("request part: %v %+v", err, req)
		}
		if seen["clip"] != "\x1a\x45\xdf\xa3clip-bytes" {
			t.Errorf("clip part: %q", seen["clip"])
		}
		w.Write(example)
	}))
	defer srv.Close()
	c := NewClient(srv.URL, "secret")
	res, err := c.Infer(context.Background(), Request{RequestID: "r1", Limits: Limits{MaxSeconds: 10}}, clipFile(t))
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Recognition.Segments) != 3 || res.Generation.Text != "Hello, my friend." || *res.Generation.Tokens[2].SegmentIndex != 2 {
		t.Fatalf("decoded: %+v", res)
	}
}

func TestInferErrors(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.Copy(io.Discard, r.Body)
		switch r.URL.Query().Get("case") {
		default:
			w.WriteHeader(422)
			w.Write([]byte(`{"error":{"code":"undecodable_clip","message":"bad","request_id":"r","retryable":false}}`))
		}
	}))
	defer srv.Close()
	c := NewClient(srv.URL, "t")
	_, err := c.Infer(context.Background(), Request{RequestID: "r"}, clipFile(t))
	me, ok := err.(*Error)
	if !ok || me.Status != 422 || me.Code != "undecodable_clip" {
		t.Fatalf("got %v", err)
	}

	down := NewClient("http://127.0.0.1:1", "t")
	_, err = down.Infer(context.Background(), Request{RequestID: "r"}, clipFile(t))
	if me, ok := err.(*Error); !ok || me.Code != "unavailable" {
		t.Fatalf("down: %v", err)
	}

	slow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.Copy(io.Discard, r.Body)
		time.Sleep(500 * time.Millisecond)
	}))
	defer slow.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	_, err = NewClient(slow.URL, "t").Infer(ctx, Request{RequestID: "r"}, clipFile(t))
	if me, ok := err.(*Error); !ok || me.Code != "timeout" {
		t.Fatalf("slow: %v", err)
	}
}

func TestQueue(t *testing.T) {
	q := NewQueue(1, 1)
	rel, err := q.Acquire(context.Background(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	got := make(chan error, 1)
	go func() {
		r, err := q.Acquire(context.Background(), time.Second)
		if err == nil {
			r()
		}
		got <- err
	}()
	for q.Waiting() != 1 {
		time.Sleep(time.Millisecond)
	}
	if _, err := q.Acquire(context.Background(), time.Second); err != ErrBusy {
		t.Fatalf("over depth: %v", err)
	}
	rel()
	if err := <-got; err != nil {
		t.Fatalf("waiter: %v", err)
	}
	if !strings.Contains(ErrBusy.Error(), "busy") {
		t.Fatal("message")
	}
}
