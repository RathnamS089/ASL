import type { ApiErrorBody, RecordingMetadata, Translation } from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");
export const REQUEST_TIMEOUT_MS = 110_000; // longer than every server-side timeout

/** A typed failure. `code` is a contract error code, or a client-side one:
 *  network, timeout, aborted, invalid_response. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 0,
    readonly retryable = false,
    readonly retryAfterSeconds?: number,
    readonly requestId?: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function validTranslation(t: unknown): t is Translation {
  if (!t || typeof t !== "object") return false;
  const r = t as Translation;
  if (typeof r.id !== "string" || typeof r.sentence !== "string" || !r.sentence.trim()) return false;
  if (!Array.isArray(r.signs) || typeof r.is_mock !== "boolean") return false;
  let prevEnd = 0;
  for (const s of r.signs) {
    if (typeof s.label !== "string" || !s.label.trim()) return false;
    if (!(s.start_seconds >= 0 && s.end_seconds >= s.start_seconds && s.start_seconds >= prevEnd - 1e-6)) return false;
    if (s.confidence != null && !(s.confidence >= 0 && s.confidence <= 1)) return false;
    prevEnd = s.end_seconds;
  }
  for (const tok of r.tokens ?? []) {
    if (typeof tok.text !== "string") return false;
    if (tok.sign_index != null && (tok.sign_index < 0 || tok.sign_index >= r.signs.length)) return false;
  }
  return true;
}

async function parseError(res: Response): Promise<ApiError> {
  const retryAfter = Number(res.headers.get("Retry-After")) || undefined;
  try {
    const body = (await res.json()) as { error?: ApiErrorBody };
    if (body.error?.code) {
      return new ApiError(body.error.code, body.error.message, res.status, !!body.error.retryable, retryAfter, body.error.request_id, body.error.details);
    }
  } catch {
    /* not JSON */
  }
  return new ApiError("http_" + res.status, `The server returned HTTP ${res.status}.`, res.status, res.status >= 500, retryAfter);
}

export interface TranslateOptions {
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

export async function translateClip(clip: Blob, metadata: RecordingMetadata, opts: TranslateOptions = {}): Promise<Translation> {
  const form = new FormData();
  form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));
  const ext = clip.type.includes("mp4") ? "mp4" : "webm";
  form.append("clip", clip, `clip.${ext}`);

  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), opts.timeoutMs ?? REQUEST_TIMEOUT_MS);
  const signal = opts.signal ? AbortSignal.any([opts.signal, timeout.signal]) : timeout.signal;
  let res: Response;
  try {
    res = await (opts.fetchImpl ?? fetch)(`${BASE}/v1/translations`, {
      method: "POST",
      body: form,
      headers: { Accept: "application/json", "X-Request-ID": metadata.client_request_id },
      signal,
    });
  } catch (e) {
    if (opts.signal?.aborted) throw new ApiError("aborted", "Cancelled.");
    if (timeout.signal.aborted) throw new ApiError("timeout", "The server took too long to answer.", 0, true);
    throw new ApiError("network", "Couldn't reach the server. Check your connection.", 0, true);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) throw await parseError(res);
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new ApiError("invalid_response", "The server sent an unreadable answer.", res.status);
  }
  if (!validTranslation(body)) throw new ApiError("invalid_response", "The server sent an unexpected answer.", res.status);
  return body;
}

export interface Readiness {
  ready: boolean;
  mock: boolean;
}

export async function checkReady(fetchImpl: typeof fetch = fetch): Promise<Readiness> {
  try {
    const res = await fetchImpl(`${BASE}/health/ready`, { headers: { Accept: "application/json" } });
    const body = (await res.json()) as { status?: string; mock?: boolean };
    return { ready: res.ok && body.status === "ready", mock: !!body.mock };
  } catch {
    return { ready: false, mock: false };
  }
}

export { validTranslation };
