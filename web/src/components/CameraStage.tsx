import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { CameraState } from "../hooks/useCamera";
import { cameraCopy } from "../lib/messages";
import { ClipRecorder, MAX_CLIP_MS, MIN_CLIP_MS, type RecordedClip } from "../lib/recorder";
import type { Mode } from "../lib/types";
import { Button, Card, Icon } from "./ui";

interface Props {
  camera: CameraState;
  facing: "user" | "environment";
  canFlip: boolean;
  recording: boolean;
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  onFlip: () => void;
  onRetry: () => void;
  onStart: () => void;
  onRecorded: (clip: RecordedClip) => void;
  onTooShort: () => void;
}

export function CameraStage({ camera, facing, canFlip, recording, mode, onModeChange, onFlip, onRetry, onStart, onRecorded, onTooShort }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const recorderRef = useRef<ClipRecorder | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [countdown, setCountdown] = useState<number | null>(null);

  useEffect(() => {
    if (videoRef.current && camera.status === "live") videoRef.current.srcObject = camera.stream;
  }, [camera]);

  // Progress ring while recording.
  useEffect(() => {
    if (!recording) return;
    let raf = 0;
    const tick = () => {
      setElapsed(recorderRef.current?.elapsedMs() ?? 0);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [recording]);

  // 3-2-1 so the signer can get their hands up before recording starts.
  useEffect(() => {
    if (countdown === null) return;
    if (countdown === 0) {
      setCountdown(null);
      if (camera.status !== "live") return;
      recorderRef.current = new ClipRecorder(
        camera.stream,
        (clip) => (clip.durationMs < MIN_CLIP_MS || clip.blob.size === 0 ? (URL.revokeObjectURL(clip.url), onTooShort()) : onRecorded(clip)),
        () => onTooShort(),
      );
      recorderRef.current.start();
      onStart();
      return;
    }
    const t = setTimeout(() => setCountdown((c) => (c ?? 1) - 1), 700);
    return () => clearTimeout(t);
  }, [countdown, camera, onStart, onRecorded, onTooShort]);

  useEffect(() => () => recorderRef.current?.stop(), []);

  if (camera.status === "problem") {
    const copy = cameraCopy[camera.problem];
    return (
      <Card className="p-6 sm:p-8">
        <p className="eyebrow">Camera</p>
        <h2 className="mt-3 font-serif text-3xl">{copy.title}</h2>
        <p className="mt-3 text-muted">{copy.hint}</p>
        {camera.problem !== "insecure" && camera.problem !== "unsupported" && (
          <Button className="mt-6" onClick={onRetry}>
            Try again
          </Button>
        )}
      </Card>
    );
  }

  const progress = Math.min(1, elapsed / MAX_CLIP_MS);
  const ring = 2 * Math.PI * 34;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex justify-center">
        <div className="flex rounded-2xl bg-raised p-1 ring-1 ring-white/10" role="radiogroup" aria-label="What are you signing?">
          {(["signs", "letters"] as const).map((m) => (
            <button
              key={m}
              role="radio"
              aria-checked={mode === m}
              disabled={recording || countdown !== null}
              onClick={() => onModeChange(m)}
              className={`min-h-10 rounded-xl px-4 text-sm font-semibold transition ${mode === m ? "bg-lime text-ink" : "text-muted hover:text-paper"}`}
            >
              {m === "signs" ? "Signs" : "Letters A–Z"}
            </button>
          ))}
        </div>
      </div>
      <div className="relative overflow-hidden rounded-[2rem] bg-black ring-1 ring-white/10">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`aspect-[3/4] w-full object-cover sm:aspect-video ${facing === "user" ? "-scale-x-100" : ""}`}
          aria-label="Camera preview"
        />
        {camera.status !== "live" && <div className="absolute inset-0 grid place-items-center text-muted">Starting camera…</div>}

        {/* Framing guide: face and both hands need to be visible. */}
        <div className="pointer-events-none absolute inset-[9%] rounded-[1.6rem] border border-dashed border-white/20" />
        <div className="pointer-events-none absolute left-1/2 top-[14%] h-[22%] w-[22%] -translate-x-1/2 rounded-full border border-dashed border-violet/40" />
        <p className="pointer-events-none absolute inset-x-0 bottom-4 text-center font-mono text-[11px] uppercase tracking-widest text-white/60">
          {recording ? (mode === "letters" ? "Spelling…" : "Signing…") : mode === "letters" ? "Signing hand clearly in frame" : "Face and both hands in frame"}
        </p>

        {recording && (
          <div className="absolute left-4 top-4 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1.5 font-mono text-xs backdrop-blur">
            <span className="size-2 animate-pulse rounded-full bg-danger" />
            {(elapsed / 1000).toFixed(1)} / {MAX_CLIP_MS / 1000}s
          </div>
        )}
        {canFlip && !recording && (
          <button onClick={onFlip} className="absolute right-4 top-4 grid size-11 place-items-center rounded-full bg-black/50 backdrop-blur" aria-label="Switch camera">
            <Icon name="flip" />
          </button>
        )}
        {countdown !== null && countdown > 0 && (
          <motion.div key={countdown} initial={{ scale: 1.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="absolute inset-0 grid place-items-center font-serif text-8xl text-lime">
            {countdown}
          </motion.div>
        )}
      </div>

      <div className="flex items-center justify-center gap-6">
        <button
          onClick={() => (recording ? recorderRef.current?.stop() : setCountdown(3))}
          disabled={camera.status !== "live" || countdown !== null}
          className="relative grid size-20 place-items-center rounded-full disabled:opacity-40"
          aria-label={recording ? "Stop recording" : "Start recording"}
        >
          <svg viewBox="0 0 80 80" className="absolute inset-0 -rotate-90">
            <circle cx="40" cy="40" r="34" stroke="rgb(255 255 255 / 0.15)" strokeWidth="4" fill="none" />
            <circle cx="40" cy="40" r="34" stroke="var(--color-lime)" strokeWidth="4" fill="none" strokeDasharray={ring} strokeDashoffset={ring * (1 - progress)} strokeLinecap="round" />
          </svg>
          <motion.span layout className={recording ? "size-7 rounded-lg bg-danger" : "size-14 rounded-full bg-danger"} />
        </button>
      </div>
      <p className="text-center text-sm text-muted">
        {recording
          ? "Tap to stop. Recording ends automatically at 10 seconds."
          : mode === "letters"
            ? "Fingerspell a word: hold each letter for about half a second. For double letters (the LL in HELLO), drop your hand briefly between them."
            : "Tap to record after a 3-second countdown. Sign one short phrase."}
      </p>
    </div>
  );
}
