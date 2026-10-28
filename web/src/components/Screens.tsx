import { motion } from "motion/react";
import { useEffect, useState } from "react";
import type { FriendlyError } from "../lib/messages";
import type { RecordedClip } from "../lib/recorder";
import type { Debug, Translation } from "../lib/types";
import { KineticSentence } from "./KineticSentence";
import { Badge, Button, Card, Icon } from "./ui";

export function Intro({ onStart, onSample }: { onStart: () => void; onSample: () => void }) {
  const [key, setKey] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setKey((k) => k + 1), 6000);
    return () => clearInterval(t);
  }, []);
  const demo: Translation = {
    id: "intro",
    sentence: "Every voice deserves to be seen.",
    signs: [],
    tokens: "Every voice deserves to be seen.".split(" ").map((text, i) => ({ text, sign_index: null, emphasis: i === 1 || i === 5 ? "strong" : "normal" })),
    is_mock: true,
  };
  return (
    <section className="flex flex-col gap-10 py-6 sm:py-14">
      <div className="flex flex-col gap-5">
        <p className="eyebrow">Sign language → words → motion</p>
        <h1 className="font-serif text-[clamp(3rem,11vw,7rem)] leading-[0.92] tracking-[-0.04em]">
          Turn signs
          <br />
          into <em className="text-violet">stories.</em>
        </h1>
        <p className="max-w-md text-lg text-muted">Sign to your phone's camera. VISUALISER recognises the signs and writes them out as moving type.</p>
      </div>
      <Card className="p-6 sm:p-8">
        <div className="mb-6 flex items-center justify-between">
          <span className="eyebrow">Language in motion</span>
          <Icon name="spark" className="size-4 text-violet" />
        </div>
        <KineticSentence translation={demo} playKey={key} size="lg" />
      </Card>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button onClick={onStart} className="sm:w-auto">
          <Icon name="camera" /> Start signing
        </Button>
        <Button variant="secondary" onClick={onSample}>
          See an example
        </Button>
      </div>
      <p className="text-sm text-muted">
        Clips are sent only to your own server, used once to translate, and deleted. Nothing is stored.
      </p>
    </section>
  );
}

export function Review({ clip, onSubmit, onReRecord }: { clip: RecordedClip; onSubmit: () => void; onReRecord: () => void }) {
  return (
    <section className="flex flex-col gap-5">
      <p className="eyebrow">Review</p>
      <video src={clip.url} controls playsInline loop autoPlay muted className="aspect-[3/4] w-full rounded-[2rem] bg-black object-cover ring-1 ring-white/10 sm:aspect-video" />
      <p className="text-sm text-muted">{(clip.durationMs / 1000).toFixed(1)} s · {clip.mimeType.split(";")[0]}</p>
      <div className="grid grid-cols-2 gap-3">
        <Button variant="secondary" onClick={onReRecord}>
          Re-record
        </Button>
        <Button onClick={onSubmit}>
          Translate <Icon name="arrow" />
        </Button>
      </div>
    </section>
  );
}

const STAGES = ["Reading the video", "Finding hands and face", "Recognising signs", "Writing the sentence"];

export function Processing({ onCancel }: { onCancel: () => void }) {
  return (
    <section className="flex flex-col gap-8 py-8">
      <p className="eyebrow">Translating</p>
      <h2 className="font-serif text-5xl leading-tight">
        A little room
        <br />
        for <em className="text-violet">expression.</em>
      </h2>
      <div className="flex gap-2" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <motion.span key={i} className="h-10 w-2 rounded-full bg-lime" animate={{ scaleY: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.1, delay: i * 0.12 }} />
        ))}
      </div>
      <ol className="flex flex-col gap-3 text-muted" aria-label="What the server does">
        {STAGES.map((s, i) => (
          <li key={s} className="flex gap-4">
            <span className="font-mono text-xs text-violet">0{i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      <p className="sr-only" role="status">
        Translating your clip.
      </p>
      <Button variant="secondary" onClick={onCancel}>
        Cancel
      </Button>
    </section>
  );
}

export function Result({ translation, onAgain, onHome }: { translation: Translation; onAgain: () => void; onHome: () => void }) {
  const [key, setKey] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(translation.sentence);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <section className="flex flex-col gap-8 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="eyebrow mr-auto">Translation</p>
        {translation.is_mock && <Badge tone="violet">Sample</Badge>}
        {translation.generation?.source === "template" && <Badge>Literal</Badge>}
        {translation.generation?.source === "fingerspelling" && <Badge tone="lime">Fingerspelling</Badge>}
        {translation.low_confidence && <Badge tone="danger">Low confidence</Badge>}
      </div>

      <Card className="min-h-56 p-6 sm:p-10">
        <KineticSentence translation={translation} playKey={key} speed={speed} />
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => setKey((k) => k + 1)}>
          <Icon name="replay" /> Replay
        </Button>
        <div className="flex rounded-2xl bg-raised p-1 ring-1 ring-white/10" role="group" aria-label="Playback speed">
          {[0.5, 1, 2].map((s) => (
            <button key={s} onClick={() => (setSpeed(s), setKey((k) => k + 1))} aria-pressed={speed === s} className={`min-h-10 rounded-xl px-3 font-mono text-sm ${speed === s ? "bg-white/10 text-paper" : "text-muted"}`}>
              {s}×
            </button>
          ))}
        </div>
        <Button variant="ghost" onClick={copy} aria-live="polite">
          <Icon name={copied ? "check" : "copy"} /> {copied ? "Copied" : "Copy"}
        </Button>
      </div>

      {translation.low_confidence && <p className="text-sm text-danger">The recogniser wasn't sure about some signs. Faded words are guesses; re-recording with more light usually helps.</p>}

      {translation.signs.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="eyebrow">{translation.generation?.source === "fingerspelling" ? "Letters recognised" : "Signs recognised"}</p>
          <ul className="flex flex-wrap gap-2">
            {translation.signs.map((s, i) => (
              <li key={i} className="rounded-2xl bg-surface px-3 py-2 ring-1 ring-white/10">
                <span className="font-mono text-sm">{s.label}</span>
                {s.confidence != null && (
                  <span className="mt-1.5 block h-1 w-full overflow-hidden rounded-full bg-white/10" title={`${Math.round(s.confidence * 100)}%`}>
                    <span className={`block h-full ${s.confidence < 0.5 ? "bg-danger" : "bg-lime"}`} style={{ width: `${Math.round(s.confidence * 100)}%` }} />
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {translation.debug && <WhatModelSaw debug={translation.debug} />}

      <div className="grid grid-cols-2 gap-3">
        <Button variant="secondary" onClick={onHome}>
          Home
        </Button>
        <Button onClick={onAgain}>
          <Icon name="camera" /> Sign again
        </Button>
      </div>
      {translation.timings_ms?.total != null && <p className="font-mono text-xs text-muted">server {translation.timings_ms.total} ms</p>}
    </section>
  );
}

export function ErrorView({ error, hasClip, onRetry, onReRecord, onHome }: { error: FriendlyError; hasClip: boolean; onRetry: () => void; onReRecord: () => void; onHome: () => void }) {
  return (
    <Card className="flex flex-col gap-4 p-6 sm:p-8" >
      <p className="eyebrow text-danger">Didn't work</p>
      <h2 className="font-serif text-3xl" role="alert">
        {error.title}
      </h2>
      <p className="text-muted">{error.hint}</p>
      <div className="mt-2 flex flex-wrap gap-3">
        {error.canRetry && hasClip && <Button onClick={onRetry}>Try again</Button>}
        {error.reRecord && (
          <Button variant={error.canRetry ? "secondary" : "primary"} onClick={onReRecord}>
            Record again
          </Button>
        )}
        <Button variant="ghost" onClick={onHome}>
          Home
        </Button>
      </div>
      {error.debug && <WhatModelSaw debug={error.debug} />}
    </Card>
  );
}

/** Debug panel: every piece of the clip the recognizer classified, with its top guesses,
 *  including ones dropped for low confidence. */
export function WhatModelSaw({ debug }: { debug: Debug }) {
  const candidates = debug.candidates ?? [];
  const hands = debug.hands_seen;
  return (
    <details className="rounded-2xl bg-surface p-4 text-sm ring-1 ring-white/10">
      <summary className="cursor-pointer select-none font-medium">What the model saw</summary>
      <div className="mt-3 flex flex-col gap-4">
        {hands != null && (
          <p className={hands < 0.5 ? "text-danger" : "text-muted"}>
            Hands tracked in {Math.round(hands * 100)}% of frames.
            {hands < 0.5 && " Move back so both hands stay in view."}
          </p>
        )}
        {candidates.length === 0 && <p className="text-muted">No sign-like movement was found, so nothing was classified.</p>}
        {candidates.map((c, i) => (
          <div key={i} className="flex flex-col gap-2">
            <p className="flex flex-wrap items-center gap-2 font-mono text-xs text-muted">
              {c.kind === "whole_clip" ? "Whole clip as one sign" : `Piece ${i + 1}`} · {c.start_seconds.toFixed(1)}–{c.end_seconds.toFixed(1)} s
              {c.kind === "segment" && (c.kept ? <Badge tone="lime">Used</Badge> : <Badge tone="danger">Too unsure, dropped</Badge>)}
            </p>
            <ul className="flex flex-col gap-1">
              {c.top.map((g) => (
                <li key={g.label} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-2">
                  <span className="truncate font-mono">{g.label}</span>
                  <span className="h-1.5 overflow-hidden rounded-full bg-white/10">
                    <span className="block h-full bg-violet" style={{ width: `${Math.round(g.confidence * 100)}%` }} />
                  </span>
                  <span className="text-right font-mono text-xs text-muted">{Math.round(g.confidence * 100)}%</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {candidates.length > 0 && <p className="text-xs text-muted">Guesses under 35% are dropped. A sign that shows up here but below 35% was close.</p>}
      </div>
    </details>
  );
}
