import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "finetune"))

import build_dataset  # noqa: E402
from visualiser_ml.generation.openai_compat import build_messages, parse_model_output  # noqa: E402


def test_every_pair_is_valid_and_not_in_the_benchmark():
    pairs = build_dataset.load_pairs()
    assert len(pairs) >= 200
    assert build_dataset.problems(pairs) == []


def test_example_matches_serving_prompt_exactly():
    ex = build_dataset.example(["WHERE", "HOSPITAL"], "Where is the hospital?")
    assert ex["messages"][:-1] == build_messages(["WHERE", "HOSPITAL"])
    answer = ex["messages"][-1]
    assert answer["role"] == "assistant"
    assert parse_model_output(answer["content"], 2) == ("Where is the hospital?", [0])


def test_split_is_deterministic_and_disjoint(tmp_path):
    for out in (tmp_path / "a", tmp_path / "b"):
        assert build_dataset.main(["--out", str(out)]) == 0
    for name in ("train", "valid", "test"):
        assert (tmp_path / "a" / f"{name}.jsonl").read_text() == (tmp_path / "b" / f"{name}.jsonl").read_text()
    keys = {name: {tuple(json.loads(l)["glosses"]) for l in (tmp_path / "a" / f"{name}_glosses.jsonl").read_text().splitlines()}
            for name in ("train", "valid", "test")}
    assert not keys["train"] & keys["test"] and not keys["train"] & keys["valid"]


def test_adding_pairs_never_moves_existing_ones():
    pairs = build_dataset.load_pairs()
    before = {tuple(g): build_dataset.split_of(g, 10, 10) for g, _ in pairs}
    extra = [(["NEW", "SIGN", str(i)], "x") for i in range(50)]
    after = {tuple(g): build_dataset.split_of(g, 10, 10) for g, _ in pairs + extra}
    assert all(after[k] == v for k, v in before.items())
