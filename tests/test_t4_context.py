from pathlib import Path
from serial_writer.config import load_settings
from serial_writer.context import ContextEngine
from serial_writer.store import StateStore


def test_context_engine_assembly(tmp_path: Path):
    settings = load_settings()
    store = StateStore(tmp_path)

    store.save_episode(1, {"content": "Episode 1 text", "summary": "Kaelen introduced."})
    store.save_summary(1, "Kaelen introduced.")
    store.save_episode(2, {"content": "Episode 2 text", "summary": "Kaelen meets Vane."})
    store.save_summary(2, "Kaelen meets Vane.")

    engine = ContextEngine(settings, store)
    compiled = engine.build_context_for_episode(episode=3, role="draft")

    assert compiled.estimated_tokens > 0
    assert len(compiled.sliding_window_episodes) == 2
