"""Video → per-frame landmarks in the Google ISLR layout.

ISLR (Kaggle "asl-signs") stores 543 landmarks per frame, extracted with MediaPipe
Holistic, in this order: face 0-467, left hand 468-488, pose 489-521, right hand
522-542. We extract the same layout from uploaded clips with MediaPipe's
HolisticLandmarker, so the model sees the same kind of input at training and serving
time. Missing parts (a hand out of frame) are NaN, exactly as in ISLR.

Landmarks describe body and face *geometry* for sign recognition only; nothing here
identifies who the signer is, and nothing is stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

FACE, LEFT_HAND, POSE, RIGHT_HAND = (0, 468), (468, 489), (489, 522), (522, 543)
N_LANDMARKS = 543


class UndecodableClip(Exception):
    pass


@dataclass
class LandmarkTrack:
    xyz: np.ndarray          # [frames, 543, 3] float32, NaN where not detected
    times: np.ndarray        # [frames] seconds from the first decoded frame
    fps: float
    frames_decoded: int
    duration_seconds: float

    @property
    def frames_used(self) -> int:
        return len(self.times)


def _fill(out: np.ndarray, span: tuple[int, int], landmarks) -> None:
    if not landmarks:
        return
    pts = np.array([(p.x, p.y, p.z) for p in landmarks], dtype=np.float32)
    n = min(len(pts), span[1] - span[0])  # the face may include iris points beyond 468
    out[span[0]:span[0] + n] = pts[:n]


class HolisticExtractor:
    """Decodes a clip with OpenCV and runs MediaPipe HolisticLandmarker on sampled frames."""

    name = "mediapipe-holistic"

    def __init__(self, model_path: Path, target_fps: float = 15.0, max_seconds: float = 12.0):
        from mediapipe.tasks.python import BaseOptions, vision  # imported lazily: heavy

        if not Path(model_path).is_file():
            raise FileNotFoundError(model_path)
        self._vision = vision
        self._options = vision.HolisticLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
        )
        self.target_fps = target_fps
        self.max_seconds = max_seconds

    def extract(self, clip_path: Path) -> LandmarkTrack:
        import cv2
        import mediapipe as mp

        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            raise UndecodableClip("the video could not be opened")
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        if not (0 < fps < 240):
            fps = 30.0  # MediaRecorder WebM often reports no frame rate
        rows, times, decoded = [], [], 0
        next_sample = 0.0
        # A fresh landmarker per clip: VIDEO mode needs increasing timestamps.
        with self._vision.HolisticLandmarker.create_from_options(self._options) as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                t = pos_ms / 1000 if pos_ms and pos_ms > 0 else decoded / fps
                decoded += 1
                if t > self.max_seconds:
                    break
                if t + 0.5 / fps < next_sample:  # tolerate millisecond-rounded timestamps
                    continue
                next_sample = t + 1 / self.target_fps
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = int(round(t * 1000))
                if times and ts <= int(round(times[-1] * 1000)):
                    ts = int(round(times[-1] * 1000)) + 1
                res = landmarker.detect_for_video(image, ts)
                out = np.full((N_LANDMARKS, 3), np.nan, dtype=np.float32)
                _fill(out, FACE, res.face_landmarks)
                _fill(out, LEFT_HAND, res.left_hand_landmarks)
                _fill(out, POSE, res.pose_landmarks)
                _fill(out, RIGHT_HAND, res.right_hand_landmarks)
                rows.append(out)
                times.append(ts / 1000)
        cap.release()
        if decoded == 0:
            raise UndecodableClip("no video frames could be decoded")
        duration = max(times[-1] if times else 0.0, decoded / fps)
        return LandmarkTrack(np.stack(rows) if rows else np.zeros((0, N_LANDMARKS, 3), np.float32),
                             np.asarray(times, dtype=np.float32), fps, decoded, float(duration))
