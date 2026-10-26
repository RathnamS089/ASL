"""HTTP service implementing docs/ML_CONTRACT.md. Run with:

    uvicorn visualiser_ml.app:create_app --factory --host 127.0.0.1 --port 8001
"""
from __future__ import annotations

import asyncio
import copy
import hmac
import json
import platform
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from .config import Settings
from .generation import Generator
from .generation.openai_compat import OpenAICompatConfig, OpenAICompatGenerator
from .generation.template import TemplateGenerator
from .recognition import Recognizer
from .recognition.islr import ClipError
from .schemas import Limits, segment_from_dict

MOCK_FIXTURE = Path(__file__).resolve().parents[2] / "contracts" / "examples" / "ml-infer-response.json"
REQUEST_PARTS = {"request", "clip"}


def error(status: int, code: str, message: str, request_id: str | None = None,
          retryable: bool = False, details: dict | None = None) -> JSONResponse:
    body = {"code": code, "message": message, "request_id": request_id, "retryable": retryable}
    if details:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status)


def build_generator(s: Settings) -> Generator:
    if s.gen_backend == "template":
        return TemplateGenerator(s.low_confidence_threshold)
    if s.gen_backend == "openai_compat":
        if not s.gen_model:
            raise RuntimeError("GEN_MODEL must be set when GEN_BACKEND=openai_compat")
        return OpenAICompatGenerator(OpenAICompatConfig(
            base_url=s.gen_base_url, model=s.gen_model, api_key=s.gen_api_key,
            timeout_s=s.gen_timeout_s, max_tokens=s.gen_max_tokens,
            disable_thinking=s.gen_disable_thinking), s.low_confidence_threshold)
    raise RuntimeError(f"unknown GEN_BACKEND {s.gen_backend!r}")


def build_recognizer(s: Settings) -> Recognizer | None:
    """The ISLR recognizer if a trained model is on disk; None otherwise (health says why)."""
    d = s.recognizer_dir
    if s.mock or not ((d / "model.tflite").is_file() or (d / "weights.safetensors").is_file()):
        return None
    from .recognition.islr import IslrRecognizer, load_classifier
    from .recognition.landmarks import HolisticExtractor

    classifier = load_classifier(d)
    return IslrRecognizer(classifier, HolisticExtractor(s.mediapipe_model, target_fps=classifier.target_fps),
                          min_sign_confidence=s.min_sign_confidence,
                          low_confidence_threshold=s.low_confidence_threshold or 0.5)


def create_app(settings: Settings | None = None, recognizer: Recognizer | None = None,
               generator: Generator | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    gen = generator or build_generator(s)
    recognizer = recognizer or (build_recognizer(s) if settings is None else None)
    busy = threading.Lock()
    app = FastAPI(title="VISUALISER ML", version="0.1.0", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if request.url.path != "/health":
            supplied = request.headers.get("x-internal-token", "")
            if not hmac.compare_digest(supplied.encode(), s.internal_token.encode()):
                return error(401, "unauthorized", "Missing or invalid internal token.")
        return await call_next(request)

    @app.get("/health")
    async def health():
        ready = s.mock or recognizer is not None
        body = {
            "status": "ready" if ready else "not_ready",
            "mock": s.mock,
            "models": {
                "recognizer": ({"name": recognizer.name, "version": recognizer.version, "loaded": True}
                               if recognizer else {"name": None, "version": None, "loaded": False}),
                "generator": {"name": gen.name, "version": gen.version,
                              "loaded": gen.name == "template", "remote": gen.name == "openai_compat"},
            },
            "runtime": {"python": platform.python_version(), "machine": platform.machine(),
                        "execution_provider": "cpu"},
        }
        if not ready:
            body["reason"] = "no recognizer loaded (Recognition workstream, milestone 5); set ML_MOCK=1 to use the mock"
        return body

    @app.post("/v1/infer")
    async def infer(request: Request):
        try:
            form = await request.form()
        except Exception:
            return error(400, "invalid_request", "Body must be multipart/form-data.")
        if set(form.keys()) != REQUEST_PARTS:
            return error(400, "invalid_request", "Expected exactly the parts 'request' and 'clip'.")
        try:
            meta = json.loads(form["request"])
            request_id = str(meta["request_id"])
            limits = Limits(**meta.get("limits", {}))
            sign_language = meta.get("sign_language", s.sign_language)
            generate = bool(meta.get("options", {}).get("generate", True))
        except (ValueError, KeyError, TypeError):
            return error(400, "invalid_request", "The 'request' part is not valid JSON for this contract.")
        clip = form["clip"]
        if not isinstance(clip, UploadFile):
            return error(400, "invalid_request", "'clip' must be a file part.", request_id)
        if clip.size is not None and clip.size > s.max_clip_bytes:
            return error(422, "clip_too_large", "Clip exceeds the service limit.", request_id)
        if sign_language != s.sign_language:
            return error(422, "unsupported_sign_language",
                         f"This service is configured for '{s.sign_language}'.", request_id)
        if not s.mock and recognizer is None:
            return error(503, "models_not_loaded", "No recognizer is loaded.", request_id, retryable=True)
        if not busy.acquire(blocking=False):
            return error(503, "busy", "Another inference is running.", request_id, retryable=True)
        try:
            if s.mock:
                await asyncio.sleep(s.mock_delay_ms / 1000)
                body = copy.deepcopy(_mock_body())
                body["request_id"] = request_id
                body["mock"] = True
                if body.get("generation"):
                    body["generation"]["source"] = "mock"
                return body
            return await run_in_threadpool(_run, clip, request_id, sign_language, limits, generate)
        except ClipError as e:
            return error(422, e.code, e.message, request_id, details=e.details)
        finally:
            busy.release()

    def _run(clip: UploadFile, request_id: str, sign_language: str, limits: Limits, generate: bool):
        started = time.perf_counter()
        # delete=False + explicit unlink: the decoder reopens the file by name, which an open
        # NamedTemporaryFile does not allow on every platform.
        with tempfile.NamedTemporaryFile(suffix=".clip", delete=False) as tmp:
            clip.file.seek(0)
            while chunk := clip.file.read(1 << 20):
                tmp.write(chunk)
        clip_path = Path(tmp.name)
        try:
            recognition = recognizer.recognize(clip_path, sign_language=sign_language, limits=limits)
        finally:
            clip_path.unlink(missing_ok=True)
        recognized_ms = round((time.perf_counter() - started) * 1000)
        generation = None
        if generate and recognition.segments:
            generation = gen.generate(recognition.segments, sign_language=sign_language).to_dict()
        total_ms = round((time.perf_counter() - started) * 1000)
        return {
            "request_id": request_id,
            "mock": False,
            "recognition": recognition.to_dict(),
            "generation": generation,
            "models": {"recognizer": {"name": recognizer.name, "version": recognizer.version},
                       "generator": {"name": gen.name, "version": gen.version}},
            "timings_ms": {"recognition": recognized_ms, "generation": total_ms - recognized_ms,
                           "total": total_ms},
        }

    @app.post("/v1/generate")
    async def generate_only(request: Request):
        """Internal: glosses → text, for generator benchmarks without a recognizer."""
        try:
            body = await request.json()
            segments = [segment_from_dict(d) for d in body["segments"]]
        except (ValueError, KeyError, TypeError):
            return error(400, "invalid_request", "Expected {\"segments\": [...]}.")
        if not segments:
            return error(400, "invalid_request", "At least one segment is required.")
        started = time.perf_counter()
        result = await run_in_threadpool(gen.generate, segments,
                                         sign_language=body.get("sign_language", s.sign_language))
        return {"generation": result.to_dict(),
                "timings_ms": {"generation": round((time.perf_counter() - started) * 1000)}}

    return app


_mock_cache: dict | None = None


def _mock_body() -> dict:
    global _mock_cache
    if _mock_cache is None:
        _mock_cache = json.loads(MOCK_FIXTURE.read_text(encoding="utf-8"))
    return _mock_cache
