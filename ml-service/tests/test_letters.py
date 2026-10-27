from pathlib import Path

import numpy as np
import pytest

from visualiser_ml.recognition.landmarks import LEFT_HAND, N_LANDMARKS, RIGHT_HAND
from visualiser_ml.recognition.letters import LETTERS, LetterReader, hand_features, spelled_generation, track_hands
from visualiser_ml.schemas import Segment

ROOT = Path(__file__).resolve().parents[1]


def hand(shift=(0.4, 0.5), scale=0.2, seed=0):
    rng = np.random.default_rng(seed)
    pts = np.zeros((21, 3), np.float32)
    pts[:, :2] = rng.uniform(-1, 1, (21, 2)) * scale + shift
    pts[9, :2] = pts[0, :2] + (0, -scale)  # middle knuckle straight above the wrist
    return pts


def test_hand_features_ignore_position_and_size():
    a = hand_features(hand(), False)
    b = hand_features(hand(shift=(0.7, 0.2), scale=0.2) * 1, False)
    big = hand(scale=0.4)
    assert np.allclose(a, b, atol=1e-5)
    assert a.shape == (63,) and np.isfinite(a).all() and np.isfinite(hand_features(big, False)).all()


def test_left_hand_is_mirrored_to_right():
    p = hand()
    mirrored = p.copy()
    mirrored[:, 0] = 1 - mirrored[:, 0]
    assert np.allclose(hand_features(p, False), hand_features(mirrored, True), atol=1e-5)


def test_track_hands_prefers_the_hand_seen_most():
    xyz = np.full((10, N_LANDMARKS, 3), np.nan, np.float32)
    xyz[:, LEFT_HAND[0]:LEFT_HAND[1]] = hand()
    xyz[:3, RIGHT_HAND[0]:RIGHT_HAND[1]] = hand(seed=1)
    feats, present = track_hands(xyz)
    assert present.all() and np.allclose(feats[0], hand_features(hand(), True))


class StubReader(LetterReader):
    """LetterReader with a scripted per-frame prediction instead of the MLP."""

    def __init__(self, script):
        self.script, self.min_hold, self.min_confidence, self.merge_gap = script, 0.5, 0.6, 1.0

    def frame_probabilities(self, feats):
        out = np.full((len(feats), 26), 0.01, np.float32)
        for i, ch in enumerate(self.script[: len(feats)]):
            out[i, LETTERS.index(ch)] = 0.9
        return out


def frames(n):
    xyz = np.full((n, N_LANDMARKS, 3), np.nan, np.float32)
    xyz[:, RIGHT_HAND[0]:RIGHT_HAND[1]] = hand()
    return xyz, np.arange(n, dtype=np.float32) / 30


def test_reader_spells_held_letters_and_drops_flicker():
    script = "H" * 20 + "E" * 3 + "I" * 20  # the 0.1 s E is a transition, not a letter
    letters = StubReader(script).read(*frames(len(script)))
    assert "".join(l.char for l in letters) == "HI"
    assert letters[0].start_seconds == 0 and 0 < letters[0].confidence <= 1


def test_double_letters_need_the_hand_to_drop():
    script = "L" * 20 + "L" * 20
    xyz, t = frames(60)
    assert "".join(l.char for l in StubReader(script + "L" * 20).read(xyz, t)) == "L"
    xyz[20:26] = np.nan  # hand drops out between the two Ls
    assert "".join(l.char for l in StubReader(script + "L" * 20).read(xyz, t)) == "LL"


def test_spelled_generation():
    g = spelled_generation([Segment(c, i, i + 0.5, 0.9) for i, c in enumerate("HELLO")])
    assert g.text == "HELLO" and g.source == "fingerspelling" and [t.text for t in g.tokens] == ["HELLO"]


@pytest.mark.skipif(not (ROOT / "models/letters/asl-mlp/weights.safetensors").exists(), reason="letter model not trained")
def test_trained_letter_model_loads_and_scores():
    reader = LetterReader(ROOT / "models/letters/asl-mlp")
    probs = reader.frame_probabilities(np.stack([hand_features(hand(seed=s), False) for s in range(3)]))
    assert probs.shape == (3, 26) and np.allclose(probs.sum(1), 1, atol=1e-5)


@pytest.mark.skipif(not (ROOT / "models/letters/asl-mlp/weights.safetensors").exists(), reason="letter model not trained")
def test_numpy_inference_matches_mlx_and_works_in_threads():
    import threading

    import mlx.core as mx

    from visualiser_ml.recognition.letters import LetterModelConfig, build_mlp

    reader = LetterReader(ROOT / "models/letters/asl-mlp")
    feats = np.stack([hand_features(hand(seed=s), False) for s in range(5)])
    mlp = build_mlp(LetterModelConfig())
    mlp.load_weights(str(ROOT / "models/letters/asl-mlp/weights.safetensors"))
    mlp.eval()
    expected = np.array(mx.softmax(mlp(mx.array(feats)), axis=-1))
    assert np.allclose(reader.frame_probabilities(feats), expected, atol=1e-4)
    got = {}
    t = threading.Thread(target=lambda: got.setdefault("p", reader.frame_probabilities(feats)))
    t.start()
    t.join()
    assert np.allclose(got["p"], expected, atol=1e-4)
