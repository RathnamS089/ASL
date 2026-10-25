import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from visualiser_ml.app import create_app
from visualiser_ml.config import Settings
from visualiser_ml.schemas import RecognitionResult, Segment

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"
TOKEN = "test-token"
AUTH = {"X-Internal-Token": TOKEN}
BASE = Settings(
    internal_token=TOKEN, mock=True, mock_delay_ms=0, model_dir=Path("models"),
    max_clip_bytes=1024, low_confidence_threshold=0.5, sign_language="ase",
    gen_backend="template", gen_base_url="", gen_model="", gen_api_key="",
    gen_timeout_s=1, gen_max_tokens=16, gen_disable_thinking=True,
)
REQUEST = json.loads((EXAMPLES / "ml-infer-request.json").read_text())


def parts(request=REQUEST, clip=b"\x1a\x45\xdf\xa3fake-webm"):
    return {"request": (None, json.dumps(request), "application/json"),
            "clip": ("clip.webm", clip, "video/webm")}


class FakeRecognizer:
    name, version = "fake", "0.0.1"

    def __init__(self, segments):
        self.segments = segments
        self.seen_paths = []

    def recognize(self, clip_path, *, sign_language, limits):
        assert clip_path.exists()
        self.seen_paths.append(clip_path)
        return RecognitionResult(3.0, 90, 45, 30.0, self.segments,
                                 0.8 if self.segments else None, not self.segments)


def client(settings=BASE, **kw):
    return TestClient(create_app(settings, **kw))


def test_health_needs_no_token_and_reports_runtime():
    body = client().get("/health").json()
    assert body["status"] == "ready" and body["mock"] is True
    assert body["runtime"]["execution_provider"] == "cpu"


def test_token_required():
    c = client()
    assert c.post("/v1/infer", files=parts()).status_code == 401
    assert c.post("/v1/infer", files=parts(), headers={"X-Internal-Token": "wrong"}).status_code == 401


def test_mock_returns_shared_example_labelled_as_mock():
    r = client().post("/v1/infer", files=parts(), headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    expected = json.loads((EXAMPLES / "ml-infer-response.json").read_text())
    assert body["request_id"] == REQUEST["request_id"]
    assert body["mock"] is True and body["generation"]["source"] == "mock"
    assert body["recognition"] == expected["recognition"]


@pytest.mark.parametrize("files, code", [
    ({"clip": ("c.webm", b"x", "video/webm")}, "invalid_request"),
    ({**parts(), "extra": (None, "x")}, "invalid_request"),
    ({"request": (None, "{not json"), "clip": ("c.webm", b"x", "video/webm")}, "invalid_request"),
])
def test_bad_requests(files, code):
    r = client().post("/v1/infer", files=files, headers=AUTH)
    assert r.status_code == 400 and r.json()["error"]["code"] == code


def test_clip_size_and_language_limits():
    c = client()
    r = c.post("/v1/infer", files=parts(clip=b"x" * 2048), headers=AUTH)
    assert r.json()["error"]["code"] == "clip_too_large"
    r = c.post("/v1/infer", files=parts({**REQUEST, "sign_language": "bfi"}), headers=AUTH)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_sign_language"


def test_real_mode_without_recognizer_is_not_ready():
    c = client(replace(BASE, mock=False))
    assert c.get("/health").json()["status"] == "not_ready"
    r = c.post("/v1/infer", files=parts(), headers=AUTH)
    assert r.status_code == 503 and r.json()["error"]["code"] == "models_not_loaded"


def test_real_pipeline_with_fake_recognizer_cleans_up_clip():
    rec = FakeRecognizer([Segment("HELLO", 0.4, 1.3, 0.91), Segment("FRIEND", 1.4, 2.0, 0.3)])
    r = client(replace(BASE, mock=False), recognizer=rec).post("/v1/infer", files=parts(), headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] is False
    assert body["generation"]["text"] == "Hello friend."
    assert [t["emphasis"] for t in body["generation"]["tokens"]] == ["normal", "low_confidence"]
    assert not rec.seen_paths[0].exists()


def test_no_signs_returns_200_with_null_generation():
    rec = FakeRecognizer([])
    body = client(replace(BASE, mock=False), recognizer=rec).post("/v1/infer", files=parts(), headers=AUTH).json()
    assert body["recognition"]["segments"] == [] and body["generation"] is None


def test_generate_endpoint():
    r = client().post("/v1/generate", headers=AUTH,
                      json={"segments": [{"label": "HELLO", "start_seconds": 0, "end_seconds": 1}]})
    assert r.status_code == 200 and r.json()["generation"]["text"] == "Hello."
    assert client().post("/v1/generate", headers=AUTH, json={"segments": []}).status_code == 400


def test_missing_token_config_refuses_to_start(monkeypatch):
    monkeypatch.delenv("ML_INTERNAL_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        Settings.from_env()
