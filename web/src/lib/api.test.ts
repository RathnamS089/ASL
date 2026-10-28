import { describe, expect, it, vi } from "vitest";
import example from "../../../contracts/examples/translation-response.json";
import errorExample from "../../../contracts/examples/error-response.json";
import { ApiError, checkReady, translateClip, validTranslation } from "./api";
import { friendlyApiError } from "./messages";
import type { RecordingMetadata } from "./types";

const meta: RecordingMetadata = {
  client_request_id: "6f1c8a52-4f0e-4a4e-9a51-3e2b7d1c9a10",
  recording: { started_at: "2026-10-26T00:00:00Z", duration_ms: 4200, mime_type: "video/webm" },
  client: { platform: "web", app_version: "0.1.0" },
};
const clip = new Blob(["\x1a\x45\xdf\xa3fake"], { type: "video/webm" });
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

describe("translateClip", () => {
  it("posts multipart metadata + clip and returns the shared example", async () => {
    const fetchImpl = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const form = init!.body as FormData;
      expect([...form.keys()]).toEqual(["metadata", "clip"]);
      expect(JSON.parse(await (form.get("metadata") as Blob).text())).toEqual(meta);
      expect((form.get("clip") as File).name).toBe("clip.webm");
      expect((init!.headers as Record<string, string>)["X-Request-ID"]).toBe(meta.client_request_id);
      return json(example);
    });
    const t = await translateClip(clip, meta, { fetchImpl: fetchImpl as typeof fetch });
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/v1/translations");
    expect(t.sentence).toBe("Hello, my friend.");
  });

  it("turns the error envelope into a typed error with Retry-After", async () => {
    const fetchImpl = async () => json({ error: { ...errorExample.error, code: "busy", retryable: true } }, 503, { "Retry-After": "5" });
    const err = await translateClip(clip, meta, { fetchImpl }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "busy", status: 503, retryable: true, retryAfterSeconds: 5 });
  });

  it("keeps no_signs_detected details for the debug panel", async () => {
    const details = { hands_seen: 0.8, candidates: [{ kind: "segment", start_seconds: 0.4, end_seconds: 1.2, kept: false, top: [{ label: "NO", confidence: 0.21 }] }] };
    const body = { error: { code: "no_signs_detected", message: "No signs.", details } };
    const err = await translateClip(clip, meta, { fetchImpl: (async () => json(body, 422)) as typeof fetch }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(friendlyApiError(err).debug?.candidates?.[0].top[0].label).toBe("NO");
  });

  it("rejects malformed success bodies", async () => {
    const fetchImpl = async () => json({ ...example, sentence: "  " });
    await expect(translateClip(clip, meta, { fetchImpl })).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("distinguishes network failure, timeout and user abort", async () => {
    await expect(translateClip(clip, meta, { fetchImpl: async () => { throw new TypeError("offline"); } })).rejects.toMatchObject({ code: "network" });
    const hang: typeof fetch = (_u, init) => new Promise((_, reject) => init!.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
    await expect(translateClip(clip, meta, { fetchImpl: hang, timeoutMs: 20 })).rejects.toMatchObject({ code: "timeout" });
    const user = new AbortController();
    const p = translateClip(clip, meta, { fetchImpl: hang, signal: user.signal });
    user.abort();
    await expect(p).rejects.toMatchObject({ code: "aborted" });
  });
});

describe("validTranslation", () => {
  it("accepts the contract example and rejects broken timings and indices", () => {
    expect(validTranslation(example)).toBe(true);
    expect(validTranslation({ ...example, signs: [{ label: "A", start_seconds: 2, end_seconds: 1 }] })).toBe(false);
    expect(validTranslation({ ...example, tokens: [{ text: "x", sign_index: 9, emphasis: "normal" }] })).toBe(false);
    expect(validTranslation({ ...example, signs: [{ label: "A", start_seconds: 0, end_seconds: 1, confidence: 3 }] })).toBe(false);
  });
});

describe("checkReady", () => {
  it("reports ready, mock and offline", async () => {
    expect(await checkReady(async () => json({ status: "ready", mock: true }))).toEqual({ ready: true, mock: true });
    expect(await checkReady(async () => json({ status: "not_ready" }, 503))).toEqual({ ready: false, mock: false });
    expect(await checkReady(async () => { throw new Error("x"); })).toEqual({ ready: false, mock: false });
  });
});

describe("letters mode", () => {
  it("sends mode in metadata and accepts a fingerspelling result", async () => {
    const fetchImpl = vi.fn(async (_u: RequestInfo | URL, init?: RequestInit) => {
      const sent = JSON.parse(await ((init!.body as FormData).get("metadata") as Blob).text());
      expect(sent.mode).toBe("letters");
      return json({ id: "tr_1", sentence: "HI", signs: [{ label: "H", start_seconds: 0, end_seconds: 0.5, confidence: 0.9 }, { label: "I", start_seconds: 0.6, end_seconds: 1, confidence: 0.8 }],
        tokens: [{ text: "HI", sign_index: null, emphasis: "strong" }], generation: { source: "fingerspelling", constrained: true }, is_mock: false, mode: "letters" });
    });
    const t = await translateClip(clip, { ...meta, mode: "letters" }, { fetchImpl: fetchImpl as typeof fetch });
    expect(t.sentence).toBe("HI");
    expect(t.generation?.source).toBe("fingerspelling");
  });
});
