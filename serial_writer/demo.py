"""Generate an explicit, reproducible offline submission/demo run."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict

from serial_writer.config import load_settings
from serial_writer.directives import DirectiveInterpretation, add_directive_from_interpretation
from serial_writer.estimate import estimate_run
from serial_writer.fakes import FakeProvider
from serial_writer.llm import LLMClient
from serial_writer.pipeline import produce_episode
from serial_writer.planner import plan_full_arc
from serial_writer.prose_lint import lint_run
from serial_writer.report import write_report
from serial_writer.store import Store
from serial_writer.trace import append_event

DEMO_ARC_EPISODES = 200
DEMO_WRITTEN_EPISODES = 15
DIRECTIVE_AFTER_EPISODE = 5
ARC_CHANGE_AFTER_EPISODE = 10
ARC_CHANGE_WINDOW = 10


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_demo(run_dir: Path | None = None, fake: bool = True) -> Dict[str, Any]:
    """Create a full arc and 15 approved episodes with two logged demo interventions.

    The interventions are scripted demonstrations, not claimed human-authored
    production episodes. Use the interactive `write` command for a real review.
    """
    settings = load_settings()
    target = Path(run_dir) if run_dir is not None else settings.runs_dir / "assignment_demo"
    manifest_path = target / "demo_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("kind") != "scripted_fake_acceptance_demo":
            raise ValueError(f"Refusing to replace unrecognized demo data in {target}.")
        shutil.rmtree(target)
    elif target.exists() and any(target.iterdir()):
        raise ValueError(
            f"Demo target {target} is not empty and is not a prior managed demo; "
            "choose another --run name."
        )
    target.mkdir(parents=True, exist_ok=True)
    premise_path = Path("premise.txt")
    premise = premise_path.read_text(encoding="utf-8").strip() if premise_path.exists() else (
        "A disgraced detective and runaway metro engineer uncover that signal AI SABLE "
        "is altering memories to hide mysterious disappearances."
    )

    store = Store(target)
    store.save_bible({"title": "The Last Departure", "premise": premise})
    llm = LLMClient(settings, target, transport=FakeProvider() if fake else None)
    plan = plan_full_arc(store, llm, premise, total_episodes=DEMO_ARC_EPISODES)
    plan_data = store.load_plan()
    plan_data["approved"] = True
    store.save_plan(plan_data)
    append_event(
        target,
        step="demo_arc_review",
        decision="scripted_approved",
        beat_count=len(plan.beats),
    )

    interventions: list[dict[str, Any]] = []
    persistent_guidance: str | None = None
    for episode_no in range(1, DEMO_WRITTEN_EPISODES + 1):
        if episode_no == DIRECTIVE_AFTER_EPISODE + 1:
            feedback = (
                "Mara must corroborate every recovered signal record with a living "
                "witness before acting on it."
            )
            persistent_guidance = feedback
            interpretation = DirectiveInterpretation(
                kind="directive",
                directive_text=feedback,
                scope="character",
                affected_characters=["Mara Venn"],
                from_ep=episode_no,
                confidence=1.0,
            )
            directive = add_directive_from_interpretation(store, interpretation, episode_no)
            intervention = {
                "episode": DIRECTIVE_AFTER_EPISODE,
                "kind": "standing_directive",
                "feedback": feedback,
                "directive_id": directive.id,
                "affected_episodes": list(
                    range(DIRECTIVE_AFTER_EPISODE + 1, DEMO_WRITTEN_EPISODES + 1)
                ),
            }
            interventions.append(intervention)
            append_event(
                target,
                step="demo_hitl",
                decision="directive_added",
                **intervention,
            )

        if episode_no == ARC_CHANGE_AFTER_EPISODE + 1:
            feedback = (
                "Reveal that the missing passengers are alive on the erased line, "
                "and make the rescue conflict with exposing the Authority."
            )
            revised = []
            last_replanned_episode = episode_no + ARC_CHANGE_WINDOW - 1
            for raw in store.get_beats(episode_no, last_replanned_episode):
                item = raw if isinstance(raw, dict) else raw.model_dump()
                ep = int(item.get("ep_no", item.get("episode")))
                old_summary = item.get("summary", item.get("beat_text", "The investigation advances."))
                phase = item.get("phase", "The Network Divides")
                revised.append(
                    {
                        **item,
                        "ep_no": ep,
                        "episode": ep,
                        "phase": phase,
                        "title": f"{phase} — Rescue choice {ep - episode_no + 1}",
                        "beat_text": (
                            f"{feedback} Episode {ep} must advance a concrete "
                            f"rescue-versus-exposure choice. Existing story movement "
                            f"to preserve: {old_summary}"
                        ),
                        "summary": (
                            f"{old_summary} The changed directive forces a specific "
                            "choice between rescuing survivors now and preserving "
                            "evidence for public exposure."
                        ),
                        "purpose": "rescue versus public exposure",
                        "hook_type": "revelation" if ep % 2 else "moral choice",
                        "plan_version": 2,
                    }
                )
            store.update_beats(revised, new_version=2)
            intervention = {
                "episode": ARC_CHANGE_AFTER_EPISODE,
                "kind": "forward_arc_change",
                "feedback": feedback,
                "affected_episodes": list(range(episode_no, last_replanned_episode + 1)),
            }
            interventions.append(intervention)
            append_event(
                target,
                step="demo_hitl",
                decision="arc_replanned",
                **intervention,
            )

        result = produce_episode(
            store,
            llm,
            episode_no,
            settings,
            human_feedback=(
                persistent_guidance
                if episode_no > DIRECTIVE_AFTER_EPISODE
                else None
            ),
        )
        if result.status != "ready" or not result.report.passed:
            append_event(
                target,
                episode=episode_no,
                step="demo_generation",
                decision="not_approved",
                checks={check.name: check.passed for check in result.report.results},
            )
            raise RuntimeError(f"Demo episode {episode_no} did not pass its checks.")
        store.approve(episode_no, result.delta)
        append_event(
            target,
            episode=episode_no,
            step="demo_human_gate",
            decision="scripted_approved",
            word_count=result.draft.word_count,
            notional_cost_usd=result.total_cost,
        )

    intervention_notes = "\n".join(
        f"- After EP {item['episode']}: **{item['kind']}** — {item['feedback']} "
        f"Affected episodes: {item['affected_episodes'][0]}–"
        f"{item['affected_episodes'][-1]}."
        for item in interventions
    )
    hitl_notes = (
        "# Scripted HITL demonstration\n\n"
        "This offline artifact demonstrates propagation using the deterministic "
        "fake provider; it is not a claim that a human performed these interventions.\n\n"
        f"{intervention_notes}\n"
    )
    (target / "HITL_DEMO.md").write_text(hitl_notes, encoding="utf-8")

    estimate = estimate_run(target, target_episodes=200)
    _write_json(target / "ESTIMATE.json", estimate)
    _write_json(target / "PROSE_LINT.json", lint_run(target))
    write_report(target)
    _write_json(
        target / "demo_manifest.json",
        {
            "kind": "scripted_fake_acceptance_demo",
            "planned_episodes": len(plan.beats),
            "written_episodes": DEMO_WRITTEN_EPISODES,
            "scripted_interventions": len(interventions),
            "premise": premise,
        },
    )

    return {
        "run_dir": str(target),
        "premise": premise,
        "episodes": DEMO_WRITTEN_EPISODES,
        "planned_episodes": len(plan.beats),
        "interventions": len(interventions),
        "fake": fake,
    }
