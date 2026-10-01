import json
from pathlib import Path

import pytest

from serial_writer.config import ModelSpec, Settings
from serial_writer.demo import run_demo
from serial_writer.estimate import estimate_run
from serial_writer.fakes import FakeProvider
from serial_writer.llm import LLMClient
from serial_writer.trace import BudgetExceeded


def test_real_pipeline_enforces_episode_word_range_and_traces_calls(tmp_path: Path):
    settings = Settings(
        models={
            "fake-model": ModelSpec(
                match=["fake"], exclude=[], rpm=100, tpm=1_000_000, rpd=1_000,
                price_in=0.0, price_out=0.0,
            )
        },
        roles={"plan": ["fake-model"], "draft": ["fake-model"], "extract": ["fake-model"], "judge": ["fake-model"]},
        runs_dir=tmp_path,
    )
    client = LLMClient(settings, tmp_path, transport=FakeProvider())
    result = client.complete("draft", "system", "user", episode=1, step="budget-test")
    assert result.text
    events = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(event.get("event") == "llm_call" and event.get("step") == "budget-test" for event in events)


def test_llm_budget_guard_blocks_before_provider_call(tmp_path: Path):
    settings = Settings(
        models={
            "fake-model": ModelSpec(
                match=["fake"], exclude=[], rpm=100, tpm=1_000_000, rpd=1_000,
                price_in=10.0, price_out=10.0,
            )
        },
        roles={"draft": ["fake-model"]},
        per_episode_cost_cap_usd=0.00001,
        total_budget_cap_usd=1.0,
    )
    provider = FakeProvider()
    client = LLMClient(settings, tmp_path, transport=provider)
    with pytest.raises(BudgetExceeded):
        client.complete("draft", "system", "a large prompt " * 100, episode=1)
    assert provider.call_count == 0


def test_demo_contains_full_arc_15_checked_episodes_and_two_interventions(tmp_path: Path):
    results = run_demo(tmp_path / "assignment-demo", fake=True)
    run_dir = Path(results["run_dir"])
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert len(plan["beats"]) == 200
    assert [beat["episode"] for beat in plan["beats"]] == list(range(1, 201))
    assert plan["approved"] is True
    assert len(plan["phases"]) == 10
    assert len(plan["character_arcs"]) >= 3

    episodes = sorted((run_dir / "episodes").glob("episode_*.json"))
    assert len(episodes) == 15
    texts = []
    for path in episodes:
        episode = json.loads(path.read_text(encoding="utf-8"))
        word_count = len(episode["content"].split())
        assert 400 <= word_count <= 700
        texts.append(episode["content"])
    assert len(set(texts)) == 15
    assert "corroborate" in texts[5].lower()
    assert "rescue" in texts[10].lower()

    interventions = [
        json.loads(line)
        for line in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("step") == "demo_hitl"
    ]
    assert len(interventions) == 2
    assert (run_dir / "HITL_DEMO.md").exists()
    assert (run_dir / "REPORT.md").exists()
    assert (run_dir / "ESTIMATE.json").exists()
    assert (run_dir / "PROSE_LINT.json").exists()
    lint = json.loads((run_dir / "PROSE_LINT.json").read_text(encoding="utf-8"))
    assert sum(lint["hook_distribution"].values()) == 15
    assert lint["synthetic_trace"] is True
    assert lint["models_used"] == ["FakeProvider (simulated; no live model call)"]
    report = (run_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "EP 200" in report
    estimate = estimate_run(run_dir, target_episodes=200)
    assert estimate["synthetic_trace"] is True
    assert estimate["estimated_cost_200"] is None
