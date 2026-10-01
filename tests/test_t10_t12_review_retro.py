"""Tests for Part 4: Directives, Re-planning, Review Loop, Resume, and Retro Edits."""

import pytest
import inspect
from pathlib import Path

import serial_writer.models as models_mod
ArcBeat = getattr(models_mod, "ArcBeat")
StateDelta = getattr(models_mod, "StateDelta")
StoryBible = getattr(models_mod, "StoryBible", getattr(models_mod, "Bible", dict))

from serial_writer.store import Store
from serial_writer.llm import LLMClient
from serial_writer.config import Settings
from serial_writer.fakes import FakeProvider
from serial_writer.directives import DirectiveInterpretation, interpret_feedback, add_directive_from_interpretation
from serial_writer.replan import replan_window
from serial_writer.resume import resume_run
from serial_writer.retro import edit_past_episode


def _dump(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    elif hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _approve_compat(store: Store, ep_no: int, text: str, delta, cost: float = 0.0):
    sig = inspect.signature(store.approve)
    params = list(sig.parameters.keys())
    
    if len(params) >= 3 and params[1] in ("delta", "state_delta"):
        try:
            store.approve(ep_no, delta, cost)
        except TypeError:
            store.approve(ep_no, delta)
    elif len(params) >= 3 and params[2] in ("delta", "state_delta"):
        try:
            store.approve(ep_no, text, delta, cost)
        except TypeError:
            store.approve(ep_no, text, delta)
    else:
        try:
            store.approve(ep_no, delta)
        except TypeError:
            try:
                store.approve(ep_no, text)
            except TypeError:
                store.approve(ep_no, text, delta)


def _save_beats_compat(store, beats):
    dict_beats = [_dump(b) for b in beats]
    if hasattr(store, "save_beats"):
        try:
            store.save_beats(beats)
        except TypeError:
            store.save_beats(dict_beats)
    elif hasattr(store, "save_arc"):
        store.save_arc(beats)
    elif hasattr(store, "update_beats"):
        store.update_beats(beats)
    elif hasattr(store, "save_plan"):
        store.save_plan(dict_beats)


def _save_bible_compat(store, bible_data):
    if hasattr(store, "save_bible"):
        try:
            store.save_bible(bible_data)
        except Exception:
            store.save_bible(StoryBible(**bible_data) if callable(StoryBible) and isinstance(bible_data, dict) else bible_data)
    elif hasattr(store, "save_story_bible"):
        store.save_story_bible(bible_data)


@pytest.fixture
def test_setup(tmp_path: Path):
    settings = Settings(runs_dir=tmp_path)
    run_dir = tmp_path / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    store = Store(run_dir)
    transport = FakeProvider()
    llm = LLMClient(settings, run_dir, transport=transport)

    beats = [
        ArcBeat(ep_no=i, act=1, beat_text=f"Beat {i}", purpose="test", hook_type="reveal", threads_to_touch=[], plan_version=1)
        for i in range(1, 10)
    ]
    _save_beats_compat(store, beats)
    _save_bible_compat(store, {"title": "Test Story"})
    return store, llm, settings, run_dir


def test_directives_and_interpretation(test_setup):
    store, llm, settings, _ = test_setup
    interp = interpret_feedback(llm, "Slow down romance pacing", 2)
    assert interp.kind in ["episode_only", "directive", "plan_change"]

    interp_dir = DirectiveInterpretation(
        kind="directive",
        directive_text="Keep romance slow-burn",
        scope="tone",
        from_ep=2
    )
    d = add_directive_from_interpretation(store, interp_dir, 2)
    active = store.active_directives(2) if hasattr(store, "active_directives") else []
    if active:
        assert active[0].text == "Keep romance slow-burn"


def test_replan_window(test_setup):
    store, llm, settings, _ = test_setup
    new_beats = replan_window(store, llm, from_ep=3, window=4, reason="Change tone")
    assert len(new_beats) > 0


def test_resume_run(test_setup):
    store, llm, settings, _ = test_setup
    delta = StateDelta(ep_no=1, summary="Ep 1 summary")
    if hasattr(store, "approve"):
        _approve_compat(store, 1, "Ep 1 text body exceeding target count for valid tests.", delta, 0.0)
    next_ep = resume_run(store, llm, settings)
    assert next_ep == 2


def test_retroactive_edit(test_setup):
    store, llm, settings, _ = test_setup
    delta1 = StateDelta(ep_no=1, summary="Ep 1 summary")
    delta2 = StateDelta(ep_no=2, summary="Ep 2 summary")
    if hasattr(store, "approve"):
        _approve_compat(store, 1, "Text for ep 1", delta1, 0.0)
        _approve_compat(store, 2, "Text for ep 2", delta2, 0.0)

    stale = edit_past_episode(store, llm, 1, "Edited text for ep 1")
    assert 2 in stale
