import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { CameraStage } from "./components/CameraStage";
import { ErrorView, Intro, Processing, Result, Review } from "./components/Screens";
import { Badge } from "./components/ui";
import { useCamera } from "./hooks/useCamera";
import { checkReady, translateClip, type Readiness } from "./lib/api";
import { initialFlow, reduce, releasedClip, type Action, type Flow } from "./lib/flow";
import { friendlyApiError } from "./lib/messages";
import type { RecordedClip } from "./lib/recorder";
import { SAMPLE } from "./lib/sample";

function uuid(): string {
  return crypto.randomUUID?.() ?? "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) => (+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16));
}

function useFlow() {
  const [flow, dispatchRaw] = useReducer(reduce, initialFlow);
  const prev = useRef<Flow>(flow);
  useEffect(() => {
    const gone = releasedClip(prev.current, flow);
    if (gone) URL.revokeObjectURL(gone.url);
    prev.current = flow;
  }, [flow]);
  return [flow, dispatchRaw as (a: Action) => void] as const;
}

export default function App() {
  const [flow, dispatch] = useFlow();
  const cameraOn = flow.kind === "camera" || flow.kind === "recording";
  const { state: camera, facing, flip, canFlip, retry } = useCamera(cameraOn);
  const [ready, setReady] = useState<Readiness | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    checkReady().then(setReady);
  }, [flow.kind]);

  const submit = useCallback(
    async (clip: RecordedClip) => {
      const requestId = uuid();
      dispatch({ type: "submit", requestId });
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const translation = await translateClip(
          clip.blob,
          {
            client_request_id: requestId,
            recording: {
              started_at: clip.startedAt,
              duration_ms: Math.round(clip.durationMs),
              mime_type: clip.mimeType,
              width: clip.width,
              height: clip.height,
              frame_rate: clip.frameRate,
              facing_mode: facing,
            },
            client: { platform: "web", app_version: "0.1.0" },
          },
          { signal: ctrl.signal },
        );
        dispatch({ type: "translated", requestId, translation });
      } catch (e) {
        if ((e as { code?: string }).code === "aborted") return;
        dispatch({ type: "failed", requestId, error: friendlyApiError(e) });
      }
    },
    [dispatch, facing],
  );

  const status = ready === null ? null : !ready.ready ? <Badge tone="danger">Offline</Badge> : ready.mock ? <Badge tone="violet">Demo server</Badge> : <Badge tone="lime">Ready</Badge>;

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] sm:px-8">
      <header className="flex items-center justify-between py-4">
        <button onClick={() => dispatch({ type: "home" })} className="font-mono text-sm font-bold tracking-[0.3em]" aria-label="VISUALISER home">
          VISUALISER
        </button>
        {status}
      </header>

      <main className="flex-1">
        {notice && (
          <p role="status" className="mb-4 rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger ring-1 ring-danger/30">
            {notice}
          </p>
        )}
        <AnimatePresence mode="wait">
          <motion.div key={flow.kind === "recording" ? "camera" : flow.kind} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>
            {flow.kind === "intro" && <Intro onStart={() => dispatch({ type: "open_camera" })} onSample={() => dispatch({ type: "sample", translation: SAMPLE })} />}
            {(flow.kind === "camera" || flow.kind === "recording") && (
              <CameraStage
                camera={camera}
                facing={facing}
                canFlip={canFlip}
                recording={flow.kind === "recording"}
                onFlip={flip}
                onRetry={retry}
                onStart={() => (setNotice(null), dispatch({ type: "start_recording" }))}
                onRecorded={(clip) => dispatch({ type: "recorded", clip })}
                onTooShort={() => (setNotice("That clip was too short. Hold the sign for at least half a second."), dispatch({ type: "re_record" }))}
              />
            )}
            {flow.kind === "review" && <Review clip={flow.clip} onSubmit={() => submit(flow.clip)} onReRecord={() => dispatch({ type: "re_record" })} />}
            {flow.kind === "processing" && <Processing onCancel={() => (abortRef.current?.abort(), dispatch({ type: "cancel" }))} />}
            {flow.kind === "result" && <Result translation={flow.translation} onAgain={() => dispatch({ type: "open_camera" })} onHome={() => dispatch({ type: "home" })} />}
            {flow.kind === "error" && (
              <ErrorView error={flow.error} hasClip={!!flow.clip} onRetry={() => flow.clip && submit(flow.clip)} onReRecord={() => dispatch({ type: "re_record" })} onHome={() => dispatch({ type: "home" })} />
            )}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
