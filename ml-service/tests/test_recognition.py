import json
import sys
from pathlib import Path

import numpy as np
import pytest

from visualiser_ml.recognition.features import FEATURE_DIM, T, featurize, select
from visualiser_ml.recognition.landmarks import LEFT_HAND, N_LANDMARKS, POSE, RIGHT_HAND, LandmarkTrack
from visualiser_ml.recognition.segmenter import segment
from visualiser_ml.schemas import Limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training" / "islr"))


def body(frames: int, hand: str = "right", path=None, shift=(0.0, 0.0), scale=1.0) -> np.ndarray:
    """A synthetic signer: shoulders, face, and one hand following `path(t)`."""
    xyz = np.full((frames, N_LANDMARKS, 3), np.nan, np.float32)
    cx, cy = 0.5 + shift[0], 0.6 + shift[1]
    xyz[:, POSE[0] + 11, :2] = (cx + 0.15 * scale, cy)  # person's left shoulder (image right)
    xyz[:, POSE[0] + 12, :2] = (cx - 0.15 * scale, cy)
    xyz[:, :468, 0] = cx + np.linspace(-0.05, 0.05, 468) * scale
    xyz[:, :468, 1] = cy - 0.25 * scale
    xyz[..., 2] = 0
    path = path or (lambda t: (0.1 * np.cos(6 * t), 0.1 * np.sin(6 * t)))
    span = RIGHT_HAND if hand == "right" else LEFT_HAND
    for f in range(frames):
        dx, dy = path(f / frames)
        if hand == "left":
            dx = -dx
        base = np.array([cx - 0.1 * scale if hand == "right" else cx + 0.1 * scale, cy - 0.1 * scale])
        offsets = np.stack([np.linspace(0, 0.04, 21), np.linspace(0, 0.06, 21)], axis=1) * scale
        if hand == "left":
            offsets[:, 0] *= -1
        xyz[f, span[0]:span[1], :2] = base + np.array([dx, dy]) * scale + offsets
    return xyz


def test_feature_shape_and_no_nans():
    f = featurize(body(40))
    assert f.shape == (T, FEATURE_DIM) and np.isfinite(f).all()
    assert featurize(np.full((0, N_LANDMARKS, 3), np.nan, np.float32)).shape == (T, FEATURE_DIM)


def test_features_ignore_position_and_distance():
    a = featurize(body(40))
    b = featurize(body(40, shift=(0.12, -0.05), scale=0.7))
    assert np.allclose(a, b, atol=1e-4)


def test_left_handed_signing_matches_right_handed():
    right, left = featurize(body(40, "right")), featurize(body(40, "left"))
    hands = slice(0, 42 * 2)  # dominant + other hand xy
    assert np.allclose(right[:, hands], left[:, hands], atol=1e-4)


def test_select_puts_dominant_hand_first():
    pts = select(body(10, "left"))
    assert np.isfinite(pts[:, :21]).all() and np.isnan(pts[:, 21:42]).all()


def track_with_gaps(spans, frames=150, fps=15.0):
    xyz = np.full((frames, N_LANDMARKS, 3), np.nan, np.float32)
    for s, e in spans:
        xyz[s:e] = body(e - s)
    return xyz, np.arange(frames, dtype=np.float32) / fps


def test_segmenter_splits_on_hands_down_and_bridges_dropouts():
    xyz, times = track_with_gaps([(5, 20), (21, 30), (60, 80)])  # 1-frame dropout at 20
    assert segment(xyz, times) == [(5, 30), (60, 80)]


def test_segmenter_drops_flicker_and_caps_signs():
    xyz, times = track_with_gaps([(5, 7), (40, 60)])
    assert segment(xyz, times) == [(40, 60)]
    xyz, times = track_with_gaps([(i * 15, i * 15 + 8) for i in range(9)])
    assert len(segment(xyz, times, max_signs=3)) == 3


def test_segmenter_splits_long_runs_at_pauses():
    xyz, times = track_with_gaps([(0, 75)])  # 5 s of continuous signing
    pieces = segment(xyz, times)
    assert len(pieces) >= 2
    assert pieces[0][0] == 0 and pieces[-1][1] == 75
    assert all(times[e - 1] - times[s] >= 0.5 for s, e in pieces)


# --- end to end on a synthetic ISLR-format dataset -------------------------------------

PATHS = {
    "circle": lambda t: (0.1 * np.cos(6.28 * t), 0.1 * np.sin(6.28 * t)),
    "swipe": lambda t: (0.25 * t - 0.12, 0.0),
    "nod": lambda t: (0.0, 0.2 * t - 0.1),
}


def write_islr(root: Path, per_signer: int = 6, signers=(1, 2, 3, 4, 5, 6)):
    import pyarrow as pa
    import pyarrow.parquet as pq

    rng = np.random.default_rng(0)
    rows = []
    for pid in signers:
        for sign, path in PATHS.items():
            for k in range(per_signer):
                frames = int(rng.integers(20, 45))
                xyz = body(frames, "left" if k % 3 == 0 else "right", path,
                           shift=tuple(rng.normal(0, 0.03, 2)), scale=float(rng.uniform(0.8, 1.2)))
                xyz += rng.normal(0, 0.003, xyz.shape).astype(np.float32)
                seq = f"{pid}{sign}{k}"
                rel = f"train_landmark_files/{pid}/{seq}.parquet"
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                n = frames * N_LANDMARKS
                pq.write_table(pa.table({
                    "frame": np.repeat(np.arange(frames), N_LANDMARKS),
                    "row_id": [f"{f}-x" for f in range(n)],
                    "type": np.tile(["face"] * 468 + ["left_hand"] * 21 + ["pose"] * 33 + ["right_hand"] * 21, frames),
                    "landmark_index": np.tile(np.r_[0:468, 0:21, 0:33, 0:21], frames),
                    "x": xyz[..., 0].ravel(), "y": xyz[..., 1].ravel(), "z": xyz[..., 2].ravel(),
                }), root / rel)
                rows.append((rel, pid, seq, sign))
    with open(root / "train.csv", "w") as f:
        f.write("path,participant_id,sequence_id,sign\n")
        f.writelines(f"{r[0]},{r[1]},{r[2]},{r[3]}\n" for r in rows)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    import prepare
    import train

    tmp = tmp_path_factory.mktemp("islr")
    write_islr(tmp / "raw")
    prepare.main(["--data", str(tmp / "raw"), "--out", str(tmp / "feats"), "--workers", "2"])
    train.main(["--features", str(tmp / "feats"), "--out", str(tmp / "model"), "--epochs", "60", "--batch", "16",
                "--dim", "64", "--depth", "1", "--val-signers", "1", "--test-signers", "1", "--lr", "3e-3"])
    return tmp / "model"


def test_training_learns_held_out_signer(trained):
    metrics = json.loads((trained / "metrics.json").read_text())
    assert metrics["test_top1"] >= 0.8, metrics
    assert len(metrics["test_signers"]) == 1 and metrics["test_signers"][0] not in metrics["val_signers"]


class FakeExtractor:
    name = "fake"

    def __init__(self, track):
        self.track = track

    def extract(self, clip_path):
        return self.track


def test_recognizer_reads_two_signs_from_one_clip(trained, tmp_path):
    from visualiser_ml.recognition.islr import IslrRecognizer

    fps, frames = 15.0, 120
    xyz = np.full((frames, N_LANDMARKS, 3), np.nan, np.float32)
    xyz[10:40] = body(30, "right", PATHS["circle"])
    xyz[70:100] = body(30, "right", PATHS["swipe"])
    track = LandmarkTrack(xyz, np.arange(frames, dtype=np.float32) / fps, fps, frames, frames / fps)
    rec = IslrRecognizer(trained, FakeExtractor(track), min_sign_confidence=0.2)
    result = rec.recognize(tmp_path / "clip", sign_language="ase", limits=Limits())
    assert [s.label for s in result.segments] == ["CIRCLE", "SWIPE"]
    assert result.segments[0].end_seconds < result.segments[1].start_seconds
    assert all(0 <= s.confidence <= 1 for s in result.segments)


def test_recognizer_enforces_clip_limits(trained, tmp_path):
    from visualiser_ml.recognition.islr import ClipError, IslrRecognizer

    xyz = body(300)
    long_track = LandmarkTrack(xyz, np.arange(300, dtype=np.float32) / 15, 15.0, 300, 20.0)
    with pytest.raises(ClipError) as e:
        IslrRecognizer(trained, FakeExtractor(long_track)).recognize(tmp_path / "c", sign_language="ase", limits=Limits())
    assert e.value.code == "clip_too_long"


def test_recognizer_returns_no_segments_without_hands(trained, tmp_path):
    from visualiser_ml.recognition.islr import IslrRecognizer

    empty = LandmarkTrack(np.full((45, N_LANDMARKS, 3), np.nan, np.float32), np.arange(45, dtype=np.float32) / 15, 15.0, 45, 3.0)
    result = IslrRecognizer(trained, FakeExtractor(empty)).recognize(tmp_path / "c", sign_language="ase", limits=Limits())
    assert result.segments == [] and result.low_confidence


def test_extractor_decodes_real_video_files(tmp_path):
    """Needs ffmpeg and the MediaPipe model; skipped otherwise."""
    import shutil
    import subprocess

    model = ROOT / "models" / "mediapipe" / "holistic_landmarker.task"
    if not model.exists() or not shutil.which("ffmpeg"):
        pytest.skip("MediaPipe model or ffmpeg not available")
    from visualiser_ml.recognition.landmarks import HolisticExtractor, UndecodableClip

    clip = tmp_path / "c.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30", "-t", "2",
                    "-c:v", "libvpx", str(clip)], check=True)
    track = HolisticExtractor(model).extract(clip)
    assert 28 <= track.frames_used <= 32 and abs(track.duration_seconds - 2) < 0.1
    bad = tmp_path / "bad.webm"
    bad.write_bytes(b"\x1a\x45\xdf\xa3not really a video")
    with pytest.raises(UndecodableClip):
        HolisticExtractor(model).extract(bad)


PRETRAINED = ROOT / "models" / "recognizer" / "islr-1st-place"


@pytest.mark.skipif(not (PRETRAINED / "model.tflite").exists(), reason="pretrained ISLR model not downloaded")
def test_pretrained_tflite_classifier():
    from visualiser_ml.recognition.islr import IslrRecognizer, TFLiteClassifier, load_classifier

    clf = load_classifier(PRETRAINED)
    assert isinstance(clf, TFLiteClassifier) and len(clf.labels) == 250 and clf.labels[0] == "TV"
    probs = clf.probabilities([body(20), body(45, "left")])
    assert probs.shape == (2, 250) and np.allclose(probs.sum(axis=1), 1, atol=1e-5)

    frames = 90
    xyz = np.full((frames, N_LANDMARKS, 3), np.nan, np.float32)
    xyz[10:40] = body(30)
    track = LandmarkTrack(xyz, np.arange(frames, dtype=np.float32) / 30, 30.0, frames, 3.0)
    result = IslrRecognizer(clf, FakeExtractor(track), min_sign_confidence=0.0).recognize(
        Path("unused"), sign_language="ase", limits=Limits())
    assert len(result.segments) == 1
    seg = result.segments[0]
    assert seg.label == seg.label.upper() and 0 <= seg.confidence <= 1
    assert 0.2 < seg.start_seconds < seg.end_seconds < 1.5


def test_islr_compound_labels_become_real_words():
    from visualiser_ml.generation.constraints import align
    from visualiser_ml.recognition.islr import gloss
    from visualiser_ml.schemas import Segment

    assert [gloss(l) for l in ("thankyou", "minemy", "weus", "dog", "TV")] == ["THANK-YOU", "MY", "WE", "DOG", "TV"]
    segs = [Segment(gloss(l), i, i + 0.5) for i, l in enumerate(["thankyou", "minemy", "mom"])]
    _, reason = align("Thank you, my mom.", segs, None)
    assert reason is None


def test_mlx_classifier_works_from_a_worker_thread(trained):
    import threading

    from visualiser_ml.recognition.islr import MlxClassifier

    clf = MlxClassifier(trained)
    got = {}
    t = threading.Thread(target=lambda: got.setdefault("p", clf.probabilities([body(30)])))
    t.start()
    t.join()
    assert got["p"].shape == (1, 3)


def test_recognizer_reports_guesses_it_dropped(trained, tmp_path):
    """The debug candidates keep every piece's top guesses, even below the confidence floor."""
    from visualiser_ml.recognition.islr import IslrRecognizer

    fps, frames = 15.0, 120
    xyz = np.full((frames, N_LANDMARKS, 3), np.nan, np.float32)
    xyz[10:40] = body(30, "right", PATHS["circle"])
    xyz[70:100] = body(30, "right", PATHS["swipe"])
    track = LandmarkTrack(xyz, np.arange(frames, dtype=np.float32) / fps, fps, frames, frames / fps)
    result = IslrRecognizer(trained, FakeExtractor(track), min_sign_confidence=1.01).recognize(
        tmp_path / "clip", sign_language="ase", limits=Limits())
    assert result.segments == []
    kinds = [c["kind"] for c in result.candidates]
    assert kinds == ["segment", "segment", "whole_clip"]
    assert not any(c["kept"] for c in result.candidates)
    assert [c["top"][0]["label"] for c in result.candidates[:2]] == ["CIRCLE", "SWIPE"]
    assert all(1 <= len(c["top"]) <= 5 for c in result.candidates)
    assert result.hands_seen == pytest.approx(60 / 120)
