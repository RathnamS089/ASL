import type { Emphasis, Translation } from "./types";

export interface Beat {
  text: string;
  emphasis: Emphasis;
  /** seconds from the start of playback when this word appears */
  at: number;
  /** the sign label behind the word, if any */
  sign?: string;
  confidence?: number | null;
}

const MIN_GAP = 0.18; // keep function words readable between timed words
const DEFAULT_GAP = 0.42;

/** Times each word to the sign it came from, so the text moves at the signer's pace.
 *  Words without a sign (function words the generator added) slot in between. */
export function beats(t: Translation, speed = 1): Beat[] {
  const tokens = t.tokens?.length
    ? t.tokens
    : t.sentence.split(/\s+/).filter(Boolean).map((text) => ({ text, sign_index: null, emphasis: "normal" as Emphasis }));
  const out: Beat[] = [];
  let clock = 0;
  for (const tok of tokens) {
    const sign = tok.sign_index != null ? t.signs[tok.sign_index] : undefined;
    let at = clock + (out.length ? DEFAULT_GAP : 0);
    if (sign) {
      // Appear as the sign starts, but never earlier than the previous word plus a gap.
      at = Math.max(out.length ? clock + MIN_GAP : 0, sign.start_seconds - (t.signs[0]?.start_seconds ?? 0));
    }
    out.push({ text: tok.text, emphasis: tok.emphasis, at, sign: sign?.label, confidence: sign?.confidence });
    clock = at;
  }
  return out.map((b) => ({ ...b, at: b.at / speed }));
}

export function totalDuration(bs: Beat[]): number {
  return bs.length ? bs[bs.length - 1].at + 0.8 : 0;
}
