import { describe, expect, it } from "vitest";
import { initialFlow, reduce, releasedClip, type Flow } from "./flow";
import { SAMPLE } from "./sample";
import type { RecordedClip } from "./recorder";

const clip = { url: "blob:1", durationMs: 2000 } as RecordedClip;
const err = { title: "x", hint: "y", canRetry: true, reRecord: true };

describe("flow", () => {
  it("walks the happy path", () => {
    let s: Flow = initialFlow;
    s = reduce(s, { type: "open_camera" });
    s = reduce(s, { type: "start_recording" });
    s = reduce(s, { type: "recorded", clip });
    expect(s).toEqual({ kind: "review", clip });
    s = reduce(s, { type: "submit", requestId: "a" });
    s = reduce(s, { type: "translated", requestId: "a", translation: SAMPLE });
    expect(s.kind).toBe("result");
  });

  it("ignores stale answers after cancel or a newer submit", () => {
    let s: Flow = { kind: "processing", clip, requestId: "old" };
    expect(reduce(s, { type: "translated", requestId: "other", translation: SAMPLE })).toBe(s);
    s = reduce(s, { type: "cancel" });
    expect(s).toEqual({ kind: "review", clip });
    expect(reduce(s, { type: "failed", requestId: "old", error: err })).toBe(s);
  });

  it("can retry from an error that kept its clip", () => {
    const s = reduce({ kind: "error", clip, error: err }, { type: "submit", requestId: "b" });
    expect(s).toEqual({ kind: "processing", clip, requestId: "b" });
    expect(reduce({ kind: "error", clip: null, error: err }, { type: "submit", requestId: "c" }).kind).toBe("error");
  });

  it("releases a clip's URL only when the clip is dropped", () => {
    expect(releasedClip({ kind: "review", clip }, { kind: "processing", clip, requestId: "a" })).toBeNull();
    expect(releasedClip({ kind: "review", clip }, { kind: "camera" })).toBe(clip);
  });
});
