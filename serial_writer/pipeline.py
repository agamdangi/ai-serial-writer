"""Episode production use case: context, draft, extract, judge, deterministic checks."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from serial_writer.checks import CheckReport, CheckResult
from serial_writer.config import Settings
from serial_writer.context import ContextEngine
from serial_writer.domain.models import ArcBeat, Directive, StateDelta, StoryState
from serial_writer.drafter import Drafter
from serial_writer.extractor import Extractor
from serial_writer.judge import Judge
from serial_writer.llm import LLMClient, LLMResult, QuotaExhausted
from serial_writer.store import Store
from serial_writer.trace import BudgetExceeded, append_event


class DraftOutput(BaseModel):
    text: str
    word_count: int
    llm_result: LLMResult


class EpisodeResult(BaseModel):
    draft: DraftOutput
    delta: StateDelta
    report: CheckReport
    attempts: int = 1
    total_cost: float = 0.0
    status: str = "ready"


def _word_count(text: str) -> int:
    return len(text.strip().split())


def beat_from_record(raw: Any, episode: int) -> ArcBeat | None:
    if raw is None:
        return None
    if isinstance(raw, ArcBeat):
        return raw
    data = raw if isinstance(raw, dict) else raw.model_dump()

    episode_number = data.get("ep_no", data.get("episode", episode))
    beat_text = data.get("beat_text") or data.get("summary") or data.get("title")
    purpose = data.get("purpose") or data.get("title") or "advance"
    hook_type = data.get("hook_type") or data.get("cliffhanger_hook") or "revelation"
    return ArcBeat(
        ep_no=int(episode_number),
        act=int(data.get("act", 1)),
        beat_text=beat_text or "Advance the central conflict.",
        purpose=purpose,
        hook_type=hook_type,
        threads_to_touch=data.get("threads_to_touch", []),
        plan_version=int(data.get("plan_version", 1)),
    )


def story_state_before(store: Store, episode: int) -> StoryState:
    """Replay all approved state before this episode for the drafting agents."""
    previous_state = store.replay_state(episode - 1)
    return StoryState(
        characters=previous_state.characters,
        relationships=previous_state.relationships,
        facts=previous_state.facts,
        threads=previous_state.threads,
    )


def _directives(store: Store, episode: int) -> list[Directive]:
    return store.active_directives(episode)


def _context_text(settings: Settings, store: Store, episode: int) -> str:
    context = ContextEngine(settings, store).build_context_for_episode(episode, role="draft")
    return context.model_dump_json(ensure_ascii=False)


def _result(
    text: str,
    delta: StateDelta,
    checks: list[CheckResult],
    llm_result: LLMResult,
    status: str = "ready",
) -> EpisodeResult:
    """Build the shared result structure used for success and pause outcomes."""
    report = CheckReport(
        passed=all(check.passed or check.severity == "warn" for check in checks),
        results=checks,
    )
    return EpisodeResult(
        draft=DraftOutput(text=text, word_count=_word_count(text), llm_result=llm_result),
        delta=delta,
        report=report,
        total_cost=llm_result.notional_cost_usd,
        status=status,
    )


def _combine_llm_results(*results: LLMResult, text: str) -> LLMResult:
    """Combine usage from drafting, extraction, and judging into episode totals."""
    return LLMResult(
        text=text,
        input_tokens=sum(result.input_tokens for result in results),
        output_tokens=sum(result.output_tokens for result in results),
        latency_s=sum(result.latency_s for result in results),
        model=results[0].model,
        wait_s=sum(result.wait_s for result in results),
        fallbacks=[model for result in results for model in result.fallbacks],
        notional_cost_usd=sum(result.notional_cost_usd for result in results),
    )


def _paused_result(episode: int, status: str) -> EpisodeResult:
    """Return an empty result for a run paused before producing a draft."""
    empty_usage = LLMResult(
        text="",
        input_tokens=0,
        output_tokens=0,
        latency_s=0.0,
        model="none",
    )
    empty_delta = StateDelta(ep_no=episode, summary="")
    return _result("", empty_delta, [], empty_usage, status=status)


def produce_episode(
    store: Store,
    llm: LLMClient,
    ep_no: int,
    settings: Settings,
    human_feedback: str | None = None,
) -> EpisodeResult:
    """Generate and audit an episode, preserving a draft until a human decision."""
    plan = store.load_plan()
    if isinstance(plan, dict) and not plan.get("approved", False):
        raise ValueError("The story arc must be approved before episode writing can begin.")
    beats = store.get_beats(ep_no, ep_no)
    beat = beat_from_record(beats[0], ep_no) if beats else None
    if beat is None:
        append_event(
            store.run_dir,
            episode=ep_no,
            step="episode_generation",
            decision="blocked",
            reason="missing_arc_beat",
        )
        raise ValueError(f"No planned beat exists for episode {ep_no}; plan the arc before writing.")

    state = story_state_before(store, ep_no)
    directives = _directives(store, ep_no)
    context = _context_text(settings, store, ep_no)
    context += "\n\nACTIVE STANDING DIRECTIVES:\n" + "\n".join(
        f"- [{item.scope}] {item.text}" for item in directives
    )
    drafter = Drafter(llm, settings, store.run_dir)
    extractor = Extractor(llm, settings, store.run_dir)
    judge = Judge(llm, settings, store.run_dir)

    try:
        draft, draft_result = drafter.draft_episode(
            beat,
            state,
            context,
            directives,
            episode=ep_no,
            additional_guidance=human_feedback or "",
        )
        delta, extract_result = extractor.extract_delta(ep_no, draft.text, beat.beat_text, state)
        delta.ep_no = ep_no
        judge_report, judge_result = judge.audit_draft(ep_no, draft.text, beat, state)
    except QuotaExhausted as error:
        append_event(
            store.run_dir,
            episode=ep_no,
            step="episode_generation",
            decision="quota_pause",
            reset_at=error.reset_at,
        )
        return _paused_result(ep_no, "quota_pause")
    except BudgetExceeded as error:
        append_event(
            store.run_dir,
            episode=ep_no,
            step="episode_generation",
            decision="budget_stop",
            error=str(error),
        )
        return _paused_result(ep_no, "budget_stop")

    count = _word_count(draft.text)
    checks = [
        CheckResult(
            name="word_count",
            passed=settings.words_min <= count <= settings.words_max,
            severity="block",
            detail=f"Draft has {count} words; expected {settings.words_min}-{settings.words_max}.",
            fix_instruction=f"Revise to {settings.words_min}-{settings.words_max} words.",
        ),
        CheckResult(
            name="hook",
            passed=bool(draft.text.rstrip().endswith(("?", "!", "—", "…", "..."))),
            severity="block",
            detail=f"Ending should land as a hook ({beat.hook_type}).",
            fix_instruction=f"End on a clear {beat.hook_type} hook, not a summary sentence.",
        ),
        CheckResult(
            name="judge",
            passed=(
                judge_report.passed
                and judge_report.word_count_valid
                and judge_report.hook_score >= 3
                and not judge_report.contradictions
                and not judge_report.unfulfilled_beats
            ),
            severity="block",
            detail=(
                f"Hook score {judge_report.hook_score}/5; "
                f"contradictions={len(judge_report.contradictions)}, "
                f"unfulfilled beats={len(judge_report.unfulfilled_beats)}. {judge_report.feedback}"
            ),
            fix_instruction=judge_report.feedback or "Resolve judge findings before approval.",
        ),
    ]
    combined = _combine_llm_results(draft_result, extract_result, judge_result, text=draft.text)
    store.save_draft(ep_no, draft.text, delta.summary)
    append_event(
        store.run_dir,
        episode=ep_no,
        step="episode_review_ready",
        decision="draft_ready",
        word_count=count,
        checks={item.name: item.passed for item in checks},
        notional_cost_usd=combined.notional_cost_usd,
    )
    return _result(draft.text, delta, checks, combined)
