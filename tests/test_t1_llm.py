import json
import pytest
from serial_writer.config import load_settings
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
