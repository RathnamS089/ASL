export const MAX_CLIP_MS = 10_000;
export const MIN_CLIP_MS = 500;

// Safari records MP4; Chrome/Firefox record WebM. Prefer what the browser does natively.
const CANDIDATES = [
  "video/mp4;codecs=avc1",
  "video/mp4",
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
];

export function pickMimeType(isSupported: (t: string) => boolean = (t) => MediaRecorder.isTypeSupported(t)): string | undefined {
  return CANDIDATES.find((t) => {
    try {
      return isSupported(t);
    } catch {
      return false;
    }
  });
}

export function canRecord(): boolean {
  return typeof window !== "undefined" && "MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia;
}

/** The camera constraints the API contract recommends: small, steady, no audio. */
export function cameraConstraints(facingMode: "user" | "environment"): MediaStreamConstraints {
  return {
    audio: false,
    video: { facingMode, width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30, max: 30 } },
  };
}

export interface RecordedClip {
  blob: Blob;
  url: string;
  mimeType: string;
  durationMs: number;
  startedAt: string;
  width?: number;
  height?: number;
  frameRate?: number;
}

/** Records one clip from a live stream, stopping itself at MAX_CLIP_MS. */
export class ClipRecorder {
  private recorder?: MediaRecorder;
  private chunks: Blob[] = [];
  private started = 0;
  private startedAt = "";
  private timer?: ReturnType<typeof setTimeout>;

  constructor(private stream: MediaStream, private onDone: (clip: RecordedClip) => void, private onError: (e: unknown) => void) {}

  start() {
    const mimeType = pickMimeType();
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType, videoBitsPerSecond: 1_500_000 } : undefined);
    this.recorder.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.recorder.onerror = (e) => this.onError(e);
    this.recorder.onstop = () => {
      clearTimeout(this.timer);
      const type = this.recorder?.mimeType || mimeType || "video/webm";
      const blob = new Blob(this.chunks, { type: type.split(";")[0] });
      const settings = this.stream.getVideoTracks()[0]?.getSettings() ?? {};
      this.onDone({
        blob,
        url: URL.createObjectURL(blob),
        mimeType: type,
        durationMs: Math.min(MAX_CLIP_MS, performance.now() - this.started),
        startedAt: this.startedAt,
        width: settings.width,
        height: settings.height,
        frameRate: settings.frameRate,
      });
    };
    this.started = performance.now();
    this.startedAt = new Date().toISOString();
    this.recorder.start(250);
    this.timer = setTimeout(() => this.stop(), MAX_CLIP_MS);
  }

  stop() {
    if (this.recorder?.state === "recording") this.recorder.stop();
  }

  elapsedMs() {
    return this.recorder?.state === "recording" ? performance.now() - this.started : 0;
  }
}
