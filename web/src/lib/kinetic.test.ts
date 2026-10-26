import { describe, expect, it } from "vitest";
import { beats, totalDuration } from "./kinetic";
import { SAMPLE } from "./sample";

describe("beats", () => {
  it("times words to their signs, relative to the first sign", () => {
    const b = beats(SAMPLE);
    expect(b.map((x) => x.text)).toEqual(["Hello,", "my", "friend."]);
    expect(b[0].at).toBe(0);
    expect(b[1].at).toBeCloseTo(1.05);
    expect(b[2].at).toBeCloseTo(1.65);
    expect(b[1].sign).toBe("MY");
  });

  it("keeps a minimum gap and spaces unsigned words", () => {
    const t = { ...SAMPLE, tokens: [{ text: "I", sign_index: 0, emphasis: "normal" as const }, { text: "am", sign_index: null, emphasis: "normal" as const }, { text: "here", sign_index: 0, emphasis: "normal" as const }] };
    const b = beats(t);
    expect(b[1].at).toBeGreaterThan(b[0].at);
    expect(b[2].at - b[1].at).toBeGreaterThanOrEqual(0.18 - 1e-9);
  });

  it("scales with speed and falls back to the sentence", () => {
    expect(beats(SAMPLE, 2)[2].at).toBeCloseTo(0.825);
    const plain = beats({ ...SAMPLE, tokens: undefined });
    expect(plain.map((x) => x.text).join(" ")).toBe(SAMPLE.sentence);
    expect(totalDuration(plain)).toBeGreaterThan(0);
  });
});
