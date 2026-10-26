import { describe, expect, it } from "vitest";
import { cameraConstraints, pickMimeType } from "./recorder";
import { cameraProblem, friendlyApiError } from "./messages";
import { ApiError } from "./api";

describe("recorder helpers", () => {
  it("prefers MP4 (Safari) then WebM (Chrome)", () => {
    expect(pickMimeType((t) => t.startsWith("video/mp4"))).toBe("video/mp4;codecs=avc1");
    expect(pickMimeType((t) => t === "video/webm;codecs=vp8")).toBe("video/webm;codecs=vp8");
    expect(pickMimeType(() => false)).toBeUndefined();
    expect(pickMimeType(() => { throw new Error("x"); })).toBeUndefined();
  });

  it("asks for a small video-only stream", () => {
    const c = cameraConstraints("environment");
    expect(c.audio).toBe(false);
    expect((c.video as MediaTrackConstraints).facingMode).toBe("environment");
  });

  it("maps camera and API errors to actionable copy", () => {
    expect(cameraProblem({ name: "NotAllowedError" })).toBe("denied");
    expect(cameraProblem({ name: "NotReadableError" })).toBe("busy");
    expect(friendlyApiError(new ApiError("no_signs_detected", "")).reRecord).toBe(true);
    expect(friendlyApiError(new ApiError("busy", "", 503, true)).canRetry).toBe(true);
    expect(friendlyApiError(new ApiError("rate_limited", "", 429, true, 7)).hint).toContain("7 seconds");
  });
});
