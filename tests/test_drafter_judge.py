"""Unit tests for drafting, extracting, and judging with fully compliant mocked schemas."""

from pathlib import Path
from unittest.mock import MagicMock
from serial_writer.config import Settings, ModelSpec
from serial_writer.drafter import Drafter, DraftOutput
from serial_writer.extractor import Extractor
from serial_writer.judge import Judge, JudgeReport
from serial_writer.llm import LLMClient, LLMResult
from serial_writer.models import ArcBeat, StateDelta, StoryState


def test_drafter_and_judge_flow(tmp_path: Path):
    settings = Settings(
        models={"mock-model": ModelSpec(match=["mock"], exclude=[], rpm=10, tpm=250000, rpd=50)},
        roles={
            "draft": ["mock-model"],
            "extract": ["mock-model"],
            "judge": ["mock-model"],
        },
        words_min=100,
        words_max=1000,
    )
    
    mock_res = LLMResult(
        text="{}",
        model="mock-model",
        input_tokens=100,
        output_tokens=100,
        latency_s=0.5,
        notional_cost_usd=0.001,
    )

    client = LLMClient(settings=settings, run_dir=tmp_path)

    drafter = Drafter(client, settings, tmp_path)
    extractor = Extractor(client, settings, tmp_path)
    judge = Judge(client, settings, tmp_path)

    beat = ArcBeat(
        ep_no=1,
        act=1,
        beat_text="Discover the altered map in the archives.",
        purpose="Setup mystery",
        hook_type="Discovery",
    )
    state = StoryState()

    dummy_draft = DraftOutput(
        title="The Whispering Archive",
        text=" ".join(["Word"] * 150),
        word_count=150,
        beat_addressed="Discovered map.",
    )
    dummy_delta = StateDelta(
        ep_no=1,
        summary="Found a map in the archives.",
    )
    dummy_report = JudgeReport(
        passed=True,
        hook_score=4,
        word_count_valid=True,
        feedback="Solid episode draft.",
    )

    client.complete_json = MagicMock(side_effect=[
        (dummy_draft, mock_res),
        (dummy_delta, mock_res),
        (dummy_report, mock_res),
    ])

    # 1. Test Drafter Engine
    draft_out, draft_llm_res = drafter.draft_episode(beat, state, "Context summary", [], episode=1)
    assert draft_out.word_count == 150
    assert "Word" in draft_out.text
    assert draft_llm_res.model == "mock-model"

    # 2. Test Extractor Engine
    delta, extract_llm_res = extractor.extract_delta(1, draft_out.text, beat.beat_text, state)
    assert delta.ep_no == 1
    assert delta.summary == "Found a map in the archives."
    assert extract_llm_res.notional_cost_usd == 0.001

    # 3. Test Judge Engine
    report, judge_llm_res = judge.audit_draft(1, draft_out.text, beat, state)
    assert report.hook_score == 4
    assert report.passed is True
    assert report.word_count_valid is True
    assert judge_llm_res.latency_s == 0.5
