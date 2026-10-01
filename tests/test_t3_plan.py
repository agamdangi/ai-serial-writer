from pathlib import Path
from unittest.mock import MagicMock
from serial_writer.config import load_settings
from serial_writer.llm import LLMClient
from serial_writer.planner import generate_series_plan
from serial_writer.store import StateStore


def test_staged_plan_generation(tmp_path: Path):
    settings = load_settings()
    llm = LLMClient(settings, run_dir=tmp_path)
    
    # Mock LLM complete method
    llm.complete = MagicMock(return_value="Mocked LLM generation")
    
    store = StateStore(tmp_path)
    plan = generate_series_plan(llm, store, premise_text="A memory hunter uncovers a corporate conspiracy.", total_episodes=10)

    assert len(plan.beats) == 10
    assert plan.premise.target_episodes == 10
    assert len(plan.characters) > 0
    assert store.load_plan() is not None
