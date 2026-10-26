// Package config reads every setting from the environment (see backend-go/.env.example).
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	ListenAddr           string
	MLBaseURL            string
	MLToken              string
	MaxUploadBytes       int64
	MaxMetadataBytes     int64
	InferenceConcurrency int
	QueueDepth           int
	QueueWait            time.Duration
	MLTimeout            time.Duration
	RatePerMinute        int
	CORSAllowedOrigins   []string
	MockTranslation      bool
	MockResponsePath     string
	SignLanguage         string
	MinClipSeconds       float64
	MaxClipSeconds       float64
	MaxSigns             int
	WebDistDir           string
	// TrustForwardedFor makes the rate limiter key on X-Forwarded-For, but only for
	// requests arriving from loopback (Tailscale Serve or Vite proxying to us).
	TrustForwardedFor bool
	Version           string
}

func FromEnv() (Config, error) {
	c := Config{
		ListenAddr:           env("API_LISTEN_ADDR", "127.0.0.1:8080"),
		MLBaseURL:            strings.TrimRight(env("ML_BASE_URL", "http://127.0.0.1:8001"), "/"),
		MLToken:              os.Getenv("ML_INTERNAL_TOKEN"),
		MockResponsePath:     env("MOCK_RESPONSE_PATH", "../contracts/examples/translation-response.json"),
		SignLanguage:         env("SIGN_LANGUAGE", "ase"),
		WebDistDir:           env("WEB_DIST_DIR", "../web/dist"),
		MaxMetadataBytes:     4096,
		Version:              env("APP_VERSION", "0.1.0"),
		MockTranslation:      env("MOCK_TRANSLATION", "0") == "1",
		TrustForwardedFor:    env("TRUST_FORWARDED_FOR", "1") == "1",
		InferenceConcurrency: 1,
	}
	var err error
	if c.MaxUploadBytes, err = int64Env("MAX_UPLOAD_BYTES", 20<<20); err != nil {
		return c, err
	}
	if c.InferenceConcurrency, err = intEnv("INFERENCE_CONCURRENCY", 1); err != nil {
		return c, err
	}
	if c.QueueDepth, err = intEnv("INFERENCE_QUEUE_DEPTH", 4); err != nil {
		return c, err
	}
	if c.RatePerMinute, err = intEnv("RATE_LIMIT_PER_MINUTE", 10); err != nil {
		return c, err
	}
	if c.MaxSigns, err = intEnv("MAX_SIGNS", 8); err != nil {
		return c, err
	}
	if c.MinClipSeconds, err = floatEnv("MIN_CLIP_SECONDS", 0.5); err != nil {
		return c, err
	}
	if c.MaxClipSeconds, err = floatEnv("MAX_CLIP_SECONDS", 10); err != nil {
		return c, err
	}
	if c.QueueWait, err = durationEnv("QUEUE_WAIT", 20*time.Second); err != nil {
		return c, err
	}
	if c.MLTimeout, err = durationEnv("ML_TIMEOUT", 45*time.Second); err != nil {
		return c, err
	}
	for _, o := range strings.Split(os.Getenv("CORS_ALLOWED_ORIGINS"), ",") {
		if o = strings.TrimSpace(o); o != "" {
			c.CORSAllowedOrigins = append(c.CORSAllowedOrigins, o)
		}
	}
	if !c.MockTranslation && c.MLToken == "" {
		return c, fmt.Errorf("ML_INTERNAL_TOKEN must be set unless MOCK_TRANSLATION=1")
	}
	if c.InferenceConcurrency < 1 || c.QueueDepth < 0 || c.MaxUploadBytes < 1024 {
		return c, fmt.Errorf("invalid limits: concurrency=%d queue=%d upload=%d",
			c.InferenceConcurrency, c.QueueDepth, c.MaxUploadBytes)
	}
	return c, nil
}

func env(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && strings.TrimSpace(v) != "" {
		return strings.TrimSpace(v)
	}
	return def
}

func intEnv(key string, def int) (int, error) {
	v, err := strconv.Atoi(env(key, strconv.Itoa(def)))
	if err != nil {
		return 0, fmt.Errorf("%s: %w", key, err)
	}
	return v, nil
}

func int64Env(key string, def int64) (int64, error) {
	v, err := strconv.ParseInt(env(key, strconv.FormatInt(def, 10)), 10, 64)
	if err != nil {
		return 0, fmt.Errorf("%s: %w", key, err)
	}
	return v, nil
}

func floatEnv(key string, def float64) (float64, error) {
	v, err := strconv.ParseFloat(env(key, strconv.FormatFloat(def, 'f', -1, 64)), 64)
	if err != nil {
		return 0, fmt.Errorf("%s: %w", key, err)
	}
	return v, nil
}

func durationEnv(key string, def time.Duration) (time.Duration, error) {
	v, err := time.ParseDuration(env(key, def.String()))
	if err != nil {
		return 0, fmt.Errorf("%s: %w", key, err)
	}
	return v, nil
}
