import { ApiError } from "./api";

export interface FriendlyError {
  title: string;
  hint: string;
  canRetry: boolean;
  reRecord: boolean;
}

/** Turns API and camera errors into copy a person can act on. */
export function friendlyApiError(e: unknown): FriendlyError {
  const err = e instanceof ApiError ? e : new ApiError("network", String(e));
  switch (err.code) {
    case "no_signs_detected":
      return { title: "No signs recognised", hint: "Keep both hands and your face in frame, with light in front of you, and sign a little slower.", canRetry: false, reRecord: true };
    case "clip_too_long":
    case "clip_too_short":
    case "payload_too_large":
      return { title: "That clip didn't fit", hint: err.message, canRetry: false, reRecord: true };
    case "undecodable_clip":
    case "unsupported_media_type":
      return { title: "The video couldn't be read", hint: "Try recording again. If it keeps happening, try another browser.", canRetry: false, reRecord: true };
    case "rate_limited":
      return { title: "Slow down a little", hint: `Too many translations in a row. Try again in ${err.retryAfterSeconds ?? 10} seconds.`, canRetry: true, reRecord: false };
    case "busy":
      return { title: "The translator is busy", hint: "Someone else is translating. Try again in a few seconds.", canRetry: true, reRecord: false };
    case "inference_unavailable":
      return { title: "The translator is offline", hint: "The model server on the Mac isn't running. Ask whoever runs it to start it.", canRetry: true, reRecord: false };
    case "inference_timeout":
    case "timeout":
      return { title: "That took too long", hint: "Try a shorter clip.", canRetry: true, reRecord: true };
    case "network":
      return { title: "Can't reach the server", hint: "Check that this device is online (and connected to Tailscale).", canRetry: true, reRecord: false };
    case "unsupported_sign_language":
      return { title: "Language not supported", hint: err.message, canRetry: false, reRecord: false };
    default:
      return { title: "Something went wrong", hint: err.message || "Please try again.", canRetry: err.retryable, reRecord: true };
  }
}

export type CameraProblem = "insecure" | "unsupported" | "denied" | "not_found" | "busy" | "unknown";

export function cameraProblem(e: unknown): CameraProblem {
  const name = (e as { name?: string })?.name;
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "denied";
    case "NotFoundError":
    case "OverconstrainedError":
      return "not_found";
    case "NotReadableError":
    case "AbortError":
      return "busy";
  }
  return "unknown";
}

export const cameraCopy: Record<CameraProblem, { title: string; hint: string }> = {
  insecure: {
    title: "Open this page over HTTPS",
    hint: "Browsers only allow the camera on secure pages. Use the https://…ts.net address from Tailscale, not a plain http:// address.",
  },
  unsupported: { title: "This browser can't record video", hint: "Use a current Safari, Chrome or Firefox." },
  denied: {
    title: "Camera access is blocked",
    hint: "Allow the camera for this site. iPhone: tap “aA” in the address bar → Website Settings → Camera. Android Chrome: tap the lock icon → Permissions.",
  },
  not_found: { title: "No camera found", hint: "This device has no usable camera. Open this page on your phone instead." },
  busy: { title: "The camera is in use", hint: "Close other apps or tabs using the camera, then try again." },
  unknown: { title: "The camera didn't start", hint: "Reload the page and try again." },
};
