import { useCallback, useEffect, useRef, useState } from "react";
import { cameraConstraints, canRecord } from "../lib/recorder";
import { cameraProblem, type CameraProblem } from "../lib/messages";

export type CameraState =
  | { status: "idle" }
  | { status: "starting" }
  | { status: "live"; stream: MediaStream }
  | { status: "problem"; problem: CameraProblem };

/** Owns the camera stream: starts on request, stops when hidden or unmounted. */
export function useCamera(active: boolean) {
  const [state, setState] = useState<CameraState>({ status: "idle" });
  const [facing, setFacing] = useState<"user" | "environment">("user");
  const streamRef = useRef<MediaStream | null>(null);
  const [canFlip, setCanFlip] = useState(false);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(
    async (mode: "user" | "environment") => {
      if (!window.isSecureContext) return setState({ status: "problem", problem: "insecure" });
      if (!canRecord()) return setState({ status: "problem", problem: "unsupported" });
      stop();
      setState({ status: "starting" });
      try {
        let stream: MediaStream;
        try {
          stream = await navigator.mediaDevices.getUserMedia(cameraConstraints(mode));
        } catch (e) {
          if ((e as Error).name !== "OverconstrainedError") throw e;
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        }
        streamRef.current = stream;
        setState({ status: "live", stream });
        const devices = await navigator.mediaDevices.enumerateDevices();
        setCanFlip(devices.filter((d) => d.kind === "videoinput").length > 1);
      } catch (e) {
        setState({ status: "problem", problem: cameraProblem(e) });
      }
    },
    [stop],
  );

  useEffect(() => {
    if (!active) {
      stop();
      setState({ status: "idle" });
      return;
    }
    start(facing);
    const onHide = () => {
      if (document.hidden) {
        stop();
        setState({ status: "idle" });
      } else {
        start(facing);
      }
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      stop();
    };
  }, [active, facing, start, stop]);

  const flip = useCallback(() => setFacing((f) => (f === "user" ? "environment" : "user")), []);
  const retry = useCallback(() => start(facing), [start, facing]);

  return { state, facing, flip, canFlip, retry };
}
