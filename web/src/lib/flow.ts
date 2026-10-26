import type { RecordedClip } from "./recorder";
import type { Translation } from "./types";
import type { FriendlyError } from "./messages";

/** The whole app is one small state machine:
 *  intro → camera → recording → review → processing → result, with error branches. */
export type Flow =
  | { kind: "intro" }
  | { kind: "camera" }
  | { kind: "recording" }
  | { kind: "review"; clip: RecordedClip }
  | { kind: "processing"; clip: RecordedClip; requestId: string }
  | { kind: "result"; clip: RecordedClip | null; translation: Translation }
  | { kind: "error"; clip: RecordedClip | null; error: FriendlyError };

export type Action =
  | { type: "open_camera" }
  | { type: "start_recording" }
  | { type: "recorded"; clip: RecordedClip }
  | { type: "submit"; requestId: string }
  | { type: "translated"; requestId: string; translation: Translation }
  | { type: "failed"; requestId: string; error: FriendlyError }
  | { type: "sample"; translation: Translation }
  | { type: "re_record" }
  | { type: "cancel" }
  | { type: "home" };

export const initialFlow: Flow = { kind: "intro" };

export function reduce(state: Flow, action: Action): Flow {
  switch (action.type) {
    case "open_camera":
      return { kind: "camera" };
    case "start_recording":
      return state.kind === "camera" ? { kind: "recording" } : state;
    case "recorded":
      return state.kind === "recording" ? { kind: "review", clip: action.clip } : state;
    case "submit":
      if (state.kind === "review" || (state.kind === "error" && state.clip)) {
        return { kind: "processing", clip: state.clip!, requestId: action.requestId };
      }
      return state;
    // A late answer for a request the user already left is ignored.
    case "translated":
      return state.kind === "processing" && state.requestId === action.requestId
        ? { kind: "result", clip: state.clip, translation: action.translation }
        : state;
    case "failed":
      return state.kind === "processing" && state.requestId === action.requestId
        ? { kind: "error", clip: state.clip, error: action.error }
        : state;
    case "sample":
      return { kind: "result", clip: null, translation: action.translation };
    case "re_record":
      return { kind: "camera" };
    case "cancel":
      return state.kind === "processing" ? { kind: "review", clip: state.clip } : state;
    case "home":
      return initialFlow;
  }
}

/** Clips whose object URL should be released when leaving `prev` for `next`. */
export function releasedClip(prev: Flow, next: Flow): RecordedClip | null {
  const clipOf = (f: Flow) => ("clip" in f ? f.clip : null);
  const a = clipOf(prev);
  return a && a !== clipOf(next) ? a : null;
}
