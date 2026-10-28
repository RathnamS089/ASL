// Mirrors docs/API_CONTRACT.md (v1). Unknown fields are ignored on purpose.

export type Emphasis = "normal" | "strong" | "low_confidence";

export interface Sign {
  label: string;
  start_seconds: number;
  end_seconds: number;
  confidence?: number | null;
}

export interface Token {
  text: string;
  sign_index: number | null;
  emphasis: Emphasis;
}

export interface Translation {
  id: string;
  created_at?: string;
  sentence: string;
  signs: Sign[];
  tokens?: Token[];
  sign_language?: string;
  low_confidence?: boolean;
  generation?: { source: "model" | "template" | "mock" | "fingerspelling"; constrained: boolean };
  mode?: Mode;
  is_mock: boolean;
  models?: Record<string, string>;
  timings_ms?: Record<string, number>;
  debug?: Debug;
}

/** What the recognizer saw, including guesses below its confidence floor. */
export interface Debug {
  hands_seen?: number | null;
  candidates?: Candidate[];
}

export interface Candidate {
  kind: "segment" | "whole_clip";
  start_seconds: number;
  end_seconds: number;
  kept: boolean;
  top: { label: string; confidence: number }[];
}

export type Mode = "signs" | "letters";

export interface RecordingMetadata {
  client_request_id: string;
  sign_language?: string;
  mode?: Mode;
  recording: {
    started_at: string;
    duration_ms: number;
    mime_type: string;
    width?: number;
    height?: number;
    frame_rate?: number;
    facing_mode?: "user" | "environment";
  };
  client: { platform: "web"; app_version: string; user_agent_family?: string };
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id?: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}
