import json
import pytest
from serial_writer.config import ModelSpec, Settings, load_settings
from serial_writer.fakes import FakeProvider
from serial_writer.llm import LLMClient, QuotaExhausted
from serial_writer.trace import BudgetGuard, BudgetExceeded


def test_rate_limiter_and_quota_exhaustion(tmp_path):
    settings = load_settings()
    settings.roles["draft"] = ["gemini-3.5-flash"]
    fake_transport = FakeProvider(fail_script={"trigger_daily_quota": 1})

    client = LLMClient(settings, run_dir=tmp_path, transport=fake_transport)

    with pytest.raises(QuotaExhausted):
        client.complete("draft", "sys", "user", step="test")


def test_budget_guard_limits_and_rebuild(tmp_path):
    guard = BudgetGuard(per_episode_cap=0.10, max_calls_per_episode=2, total_cap=1.0, run_dir=tmp_path)
    guard.charge(episode=1, cost=0.05)

    guard.check_before_call(episode=1, estimated_cost=0.01)

    with pytest.raises(BudgetExceeded):
        guard.check_before_call(episode=1, estimated_cost=0.06)

    guard.charge(episode=1, cost=0.04)

    with pytest.raises(BudgetExceeded):
        guard.check_before_call(episode=1, estimated_cost=0.01)

    rebuilt_guard = BudgetGuard(per_episode_cap=0.10, max_calls_per_episode=2, total_cap=1.0, run_dir=tmp_path)
    assert rebuilt_guard.total_cost == 0.09


def test_unavailable_service_error_retries_with_backoff(tmp_path, monkeypatch):
    class TemporarilyUnavailable:
        def __init__(self):
            self.calls = 0

        def execute(self, model, contents, config):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("503 UNAVAILABLE: model is experiencing high demand")
            return {"text": "Recovered", "usage": {"input_tokens": 1, "output_tokens": 1}}

    monkeypatch.setattr("serial_writer.llm.time.sleep", lambda _: None)
    settings = Settings(
        gemini_api_key="test-key",
        models={"test-model": ModelSpec(match=["test"], rpm=10, tpm=10000, rpd=50)},
        roles={"draft": ["test-model"]},
        max_retries=2,
    )
    transport = TemporarilyUnavailable()
    client = LLMClient(settings, tmp_path, transport=transport)

    result = client.complete("draft", "system", "prompt", step="test")

    assert result.text == "Recovered"
    assert transport.calls == 2
