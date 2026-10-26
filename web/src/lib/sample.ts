import type { Translation } from "./types";

// Same shape as contracts/examples/translation-response.json, labelled as a sample.
export const SAMPLE: Translation = {
  id: "sample",
  sentence: "Hello, my friend.",
  signs: [
    { label: "HELLO", start_seconds: 0.4, end_seconds: 1.3, confidence: 0.91 },
    { label: "MY", start_seconds: 1.45, end_seconds: 1.9, confidence: 0.62 },
    { label: "FRIEND", start_seconds: 2.05, end_seconds: 3.1, confidence: 0.84 },
  ],
  tokens: [
    { text: "Hello,", sign_index: 0, emphasis: "strong" },
    { text: "my", sign_index: 1, emphasis: "low_confidence" },
    { text: "friend.", sign_index: 2, emphasis: "normal" },
  ],
  low_confidence: false,
  generation: { source: "mock", constrained: true },
  is_mock: true,
};
