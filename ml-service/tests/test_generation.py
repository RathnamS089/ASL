import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from visualiser_ml.generation.constraints import align, gloss_surface_forms
from visualiser_ml.generation.openai_compat import (
    OpenAICompatConfig, OpenAICompatGenerator, parse_model_output,
)
from visualiser_ml.generation.template import TemplateGenerator, template_sentence
from visualiser_ml.schemas import Segment


def segs(*labels, conf=0.9):
    return [Segment(label, i, i + 0.5, conf) for i, label in enumerate(labels)]


# --- constraint ---------------------------------------------------------------

def test_accepts_function_words_and_inflection():
    tokens, reason = align("I will go to the stores tomorrow.", segs("IX-1", "GO", "STORE", "TOMORROW"), None)
    assert reason is None
    assert [t.segment_index for t in tokens] == [0, None, 1, None, None, 2, 3]


def test_accepts_reordered_wh_question():
    tokens, reason = align("What is your name?", segs("YOU", "NAME", "WHAT"), None)
    assert reason is None
    assert [t.segment_index for t in tokens] == [2, None, 0, 1]


def test_rejects_invented_content_word():
    _, reason = align("Hello, my dear friend.", segs("HELLO", "MY", "FRIEND"), None)
    assert reason and "dear" in reason


def test_rejects_dropped_sign():
    _, reason = align("Hello.", segs("HELLO", "FRIEND"), None)
    assert reason and "FRIEND" in reason


def test_low_confidence_and_strong_emphasis():
    segments = [Segment("HELLO", 0, 1, 0.9), Segment("FRIEND", 1, 2, 0.3)]
    tokens, _ = align("Hello friend.", segments, 0.5, emphasize=[0])
    assert [t.emphasis for t in tokens] == ["strong", "low_confidence"]


def test_gloss_forms():
    assert "went" in gloss_surface_forms("GO")
    assert {"thank", "you"} <= gloss_surface_forms("THANK-YOU")
    assert gloss_surface_forms("FS-JOHN") == {"john"}


# --- template -------------------------------------------------------------------

def test_template_is_deterministic_and_constrained():
    segments = segs("HELLO", "MY", "FRIEND")
    result = TemplateGenerator().generate(segments, sign_language="ase")
    assert result.text == "Hello my friend."
    assert result.source == "template"
    assert " ".join(t.text for t in result.tokens) == result.text


@pytest.mark.parametrize("labels", [("IX-1", "LOVE", "FS-ANA"), ("THANK-YOU",), ("ME", "GO")])
def test_template_never_violates_constraint(labels):
    assert TemplateGenerator().generate(segs(*labels), sign_language="ase").text
    assert template_sentence(segs(*labels))[0].isupper()


# --- model output parsing ---------------------------------------------------------

def test_parse_strips_reasoning_block():
    sentence, emph = parse_model_output('<think>glosses...</think>\n{"sentence": "Hi  there.", "emphasize": [0, 9]}', 2)
    assert sentence == "Hi there." and emph == [0]


@pytest.mark.parametrize("bad", ["", "no json", '{"sentence": ""}', '{"text": "x"}', "{broken"])
def test_parse_rejects_bad_output(bad):
    from visualiser_ml.generation.openai_compat import GenerationBackendError
    with pytest.raises(GenerationBackendError):
        parse_model_output(bad, 1)


# --- OpenAI-compatible backend against a fake server ------------------------------

class FakeServer:
    def __init__(self, content):
        self.content = content
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.requests.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                body = json.dumps({"choices": [{"message": {"content": outer.content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def fake():
    servers = []

    def make(content):
        servers.append(FakeServer(content))
        return servers[-1]
    yield make
    for s in servers:
        s.close()


def gen_for(url):
    return OpenAICompatGenerator(OpenAICompatConfig(base_url=url, model="test-model", timeout_s=2))


def test_model_output_accepted(fake):
    server = fake('{"sentence": "Hello, my friend.", "emphasize": [0]}')
    result = gen_for(server.url).generate(segs("HELLO", "MY", "FRIEND"), sign_language="ase")
    assert result.source == "model" and result.text == "Hello, my friend."
    path, body = server.requests[0]
    assert path == "/v1/chat/completions"
    assert body["model"] == "test-model" and body["temperature"] == 0
    assert body["response_format"]["type"] == "json_schema"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_hallucination_falls_back_to_template(fake):
    server = fake('{"sentence": "Hello, my best friend Sam."}')
    result = gen_for(server.url).generate(segs("HELLO", "MY", "FRIEND"), sign_language="ase")
    assert result.source == "template"
    assert result.text == "Hello my friend."
    assert result.rejected_reason.startswith("constraint:")


def test_unreachable_backend_falls_back_to_template():
    result = gen_for("http://127.0.0.1:9/v1").generate(segs("HELLO"), sign_language="ase")
    assert result.source == "template" and result.rejected_reason.startswith("backend:")


def test_benchmark_references_satisfy_constraint():
    """The constraint must accept fluent human references, or the model can never win."""
    from pathlib import Path
    lines = (Path(__file__).resolve().parents[1] / "benchmarks" / "glosses.jsonl").read_text().splitlines()
    for case in map(json.loads, filter(None, lines)):
        segments = [Segment(g, i, i + 0.5) for i, g in enumerate(case["glosses"])]
        _, reason = align(case["reference"], segments, None)
        assert reason is None, (case["reference"], reason)


def test_negation_needs_a_negation_sign():
    """Adding "not" flips the meaning, so it is never a free function word."""
    _, reason = align("I do not understand.", segs("IX-1", "UNDERSTAND"), None)
    assert reason and "not" in reason
    _, reason = align("I don't understand.", segs("IX-1", "UNDERSTAND"), None)
    assert reason and "don't" in reason
    tokens, reason = align("I don't understand.", segs("IX-1", "NOT", "UNDERSTAND"), None)
    assert reason is None and tokens[1].segment_index == 1


def test_non_negative_contractions_are_function_words():
    _, reason = align("Sorry, I'm late.", segs("SORRY", "IX-1", "LATE"), None)
    assert reason is None


def test_inflection_rules():
    assert {"studies", "studied"} <= gloss_surface_forms("STUDY")
    assert {"stopped", "stopping"} <= gloss_surface_forms("STOP")
    assert {"met", "bought", "well"} <= gloss_surface_forms("MEET") | gloss_surface_forms("BUY") | gloss_surface_forms("GOOD")
    assert "his" in gloss_surface_forms("IX-3")
    assert "let's" in gloss_surface_forms("LET'S")
    # Inflection never invents a different word.
    assert "meat" not in gloss_surface_forms("MEET")
