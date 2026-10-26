package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"os"
	"strings"
)

// Metadata is the optional `metadata` part (docs/API_CONTRACT.md).
type Metadata struct {
	ClientRequestID string `json:"client_request_id"`
	SignLanguage    string `json:"sign_language"`
	Recording       *struct {
		StartedAt  string  `json:"started_at"`
		DurationMS *int    `json:"duration_ms"`
		MimeType   string  `json:"mime_type"`
		Width      int     `json:"width"`
		Height     int     `json:"height"`
		FrameRate  float64 `json:"frame_rate"`
		FacingMode string  `json:"facing_mode"`
	} `json:"recording"`
}

type upload struct {
	Path      string
	Container string // "webm" or "mp4"
	Size      int64
	Meta      Metadata
}

func (u *upload) remove() { _ = os.Remove(u.Path) }

// sniff identifies the container from its first bytes; Content-Type is never trusted.
func sniff(head []byte) string {
	switch {
	case len(head) >= 4 && bytes.Equal(head[:4], []byte{0x1A, 0x45, 0xDF, 0xA3}):
		return "webm"
	case len(head) >= 8 && string(head[4:8]) == "ftyp":
		return "mp4"
	}
	return ""
}

var rawTypes = map[string]bool{
	"video/mp4": true, "video/quicktime": true, "video/x-m4v": true, "video/webm": true,
	"application/octet-stream": true,
}

// readUpload accepts multipart (canonical) or a raw video body (iOS compatibility, D5).
// The caller must call remove() on success.
func readUpload(w http.ResponseWriter, r *http.Request, maxBytes, maxMeta int64) (*upload, *apiError) {
	r.Body = http.MaxBytesReader(w, r.Body, maxBytes)
	mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil {
		return nil, newErr(http.StatusUnsupportedMediaType, "unsupported_media_type", "Send multipart/form-data with a clip.")
	}
	if mediaType == "multipart/form-data" {
		return readMultipart(r, maxMeta)
	}
	if rawTypes[mediaType] {
		u, e := saveClip(r.Body)
		return u, e
	}
	return nil, newErr(http.StatusUnsupportedMediaType, "unsupported_media_type", "Send multipart/form-data with a clip.")
}

func readMultipart(r *http.Request, maxMeta int64) (*upload, *apiError) {
	mr, err := r.MultipartReader()
	if err != nil {
		return nil, newErr(http.StatusBadRequest, "invalid_request", "Malformed multipart body.")
	}
	var (
		u       *upload
		meta    Metadata
		hasMeta bool
	)
	fail := func(e *apiError) (*upload, *apiError) {
		if u != nil {
			u.remove()
		}
		return nil, e
	}
	for {
		part, err := mr.NextPart()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return fail(bodyError(err, "Malformed multipart body."))
		}
		switch part.FormName() {
		case "metadata":
			if hasMeta {
				return fail(newErr(http.StatusBadRequest, "invalid_request", "Only one metadata part is allowed."))
			}
			raw, err := io.ReadAll(io.LimitReader(part, maxMeta+1))
			if err != nil {
				return fail(bodyError(err, "Could not read metadata."))
			}
			if int64(len(raw)) > maxMeta {
				return fail(newErr(http.StatusBadRequest, "invalid_request", fmt.Sprintf("Metadata must be at most %d bytes.", maxMeta)))
			}
			if err := json.Unmarshal(raw, &meta); err != nil {
				return fail(newErr(http.StatusBadRequest, "invalid_request", "Metadata is not valid JSON."))
			}
			hasMeta = true
		case "clip":
			if u != nil {
				return fail(newErr(http.StatusBadRequest, "invalid_request", "Exactly one clip is allowed."))
			}
			var e *apiError
			if u, e = saveClip(part); e != nil {
				return nil, e
			}
		default:
			return fail(newErr(http.StatusBadRequest, "invalid_request", fmt.Sprintf("Unexpected part %q.", part.FormName())))
		}
	}
	if u == nil {
		return nil, newErr(http.StatusBadRequest, "invalid_request", "The clip part is required.")
	}
	u.Meta = meta
	return u, nil
}

// saveClip spools the clip to a temp file while checking its magic bytes.
func saveClip(src io.Reader) (*upload, *apiError) {
	head := make([]byte, 12)
	n, err := io.ReadFull(src, head)
	if err != nil && !errors.Is(err, io.ErrUnexpectedEOF) && !errors.Is(err, io.EOF) {
		return nil, bodyError(err, "Could not read the clip.")
	}
	container := sniff(head[:n])
	if container == "" {
		return nil, newErr(http.StatusUnsupportedMediaType, "unsupported_media_type", "The clip must be a WebM, MP4 or MOV video.")
	}
	f, err := os.CreateTemp("", "visualiser-clip-*")
	if err != nil {
		return nil, newErr(http.StatusInternalServerError, "internal", "Could not store the clip.")
	}
	u := &upload{Path: f.Name(), Container: container}
	written, err := io.Copy(f, io.MultiReader(bytes.NewReader(head[:n]), src))
	closeErr := f.Close()
	if err != nil || closeErr != nil {
		u.remove()
		return nil, bodyError(err, "Could not read the clip.")
	}
	u.Size = written
	return u, nil
}

func bodyError(err error, msg string) *apiError {
	var tooBig *http.MaxBytesError
	if errors.As(err, &tooBig) {
		return &apiError{Status: http.StatusRequestEntityTooLarge, Code: "payload_too_large",
			Message: fmt.Sprintf("The upload is over %.1f MB. Record a shorter clip.", float64(tooBig.Limit)/(1<<20)),
			Details: map[string]any{"max_bytes": tooBig.Limit}}
	}
	if err != nil && strings.Contains(err.Error(), "timeout") {
		return newErr(http.StatusRequestTimeout, "invalid_request", "The upload took too long.")
	}
	return newErr(http.StatusBadRequest, "invalid_request", msg)
}
