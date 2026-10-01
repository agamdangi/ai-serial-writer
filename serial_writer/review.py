"""Interactive human-in-the-loop review interface for episode generation."""

import os
import subprocess
import tempfile

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from serial_writer.config import Settings
from serial_writer.directives import add_directive_from_interpretation, interpret_feedback
from serial_writer.domain.models import StateDelta
from serial_writer.extractor import Extractor
from serial_writer.judge import Judge
from serial_writer.llm import LLMClient
from serial_writer.pipeline import EpisodeResult, beat_from_record, produce_episode, story_state_before
from serial_writer.replan import replan_window
from serial_writer.store import Store
from serial_writer.trace import append_event


def _approval_block(text: str, settings: Settings) -> tuple[str, int] | None:
    """Return the blocking rule and word count when text is not approvable."""
    word_count = len(text.strip().split())
    if not settings.words_min <= word_count <= settings.words_max:
        return "word_count", word_count
    if not text.rstrip().endswith(("?", "!", "—", "…", "...")):
        return "missing_hook", word_count
    return None


def _approve_episode(store: Store, episode: int, delta: StateDelta) -> None:
    """Approve the persisted draft and apply its extracted state update."""
    store.approve(episode, delta)


def review_loop(
    store: Store,
    llm: LLMClient,
    settings: Settings,
    ep_no: int,
    autopilot_remaining: int = 0,
) -> tuple[str, int]:
    """Run interactive review for episode ep_no. Returns status string and autopilot count."""
    console = Console()
    human_feedback: str | None = None

    while True:
        res: EpisodeResult = produce_episode(
            store, llm, ep_no, settings, human_feedback=human_feedback
        )

        if res.status == "quota_pause":
            console.print("[bold red]Quota exhausted. Pausing pipeline.[/bold red]")
            return "quota_pause", autopilot_remaining

        if res.status == "budget_stop":
            console.print("[bold red]Budget limit reached.[/bold red]")
            return "budget_stop", autopilot_remaining

        table = Table(title=f"Episode {ep_no} Checks")
        table.add_column("Check")
        table.add_column("Passed")
        table.add_column("Instruction")
        for c in res.report.results:
            status_label = "[green]PASS[/green]" if c.passed else f"[red]{c.severity.upper()}[/red]"
            table.add_row(c.name, status_label, c.fix_instruction)

        preview = res.draft.text[:600] + "\n..."
        console.print(Panel(preview, title=f"Draft EP {ep_no} ({res.draft.word_count} words)"))
        console.print(table)

        if autopilot_remaining > 0 and res.report.passed:
            all_clean = all(c.severity != "warn" for c in res.report.results if not c.passed)
            if all_clean:
                _approve_episode(store, ep_no, res.delta)
                append_event(
                    store.run_dir,
                    episode=ep_no,
                    step="human_review",
                    decision="autopilot_approved",
                )
                console.print(f"[bold green]Autopilot approved Episode {ep_no}[/bold green]")
                return "approved", autopilot_remaining - 1

        console.print("\nOptions: [a]pprove | [e]dit | [r]eject | [f]eedback | [s]kip | [q]uit")
        choice = Prompt.ask("Choose action", choices=["a", "e", "r", "f", "s", "q"], default="a")

        if choice == "a":
            failure = _approval_block(res.draft.text, settings)
            if failure:
                reason, word_count = failure
                append_event(
                    store.run_dir,
                    episode=ep_no,
                    step="human_review",
                    decision="approval_blocked",
                    reason=reason,
                    word_count=word_count,
                )
                if reason == "word_count":
                    message = f"Cannot approve: {word_count} words is outside {settings.words_min}-{settings.words_max}."
                else:
                    message = "Cannot approve: revise the ending to land on a hook."
                console.print(f"[bold red]{message}[/bold red]")
                continue
            _approve_episode(store, ep_no, res.delta)
            append_event(store.run_dir, episode=ep_no, step="human_review", decision="approved")
            console.print(f"[bold green]Approved EP {ep_no}[/bold green]")
            return "approved", autopilot_remaining

        elif choice == "e":
            edited_text = _open_in_editor(res.draft.text)
            failure = _approval_block(edited_text, settings)
            if failure:
                reason, edited_count = failure
                append_event(
                    store.run_dir,
                    episode=ep_no,
                    step="human_review",
                    decision="edit_rejected",
                    reason=reason,
                    word_count=edited_count,
                )
                if reason == "word_count":
                    message = f"Edited text has {edited_count} words; it must be {settings.words_min}-{settings.words_max}."
                    human_feedback = "The human edit failed the word-count gate. Preserve its changes and bring the next version into the required word range."
                else:
                    message = "Edited text must end on a hook."
                    human_feedback = "The human edit must end on a clear unresolved hook. Preserve its changes and revise the ending."
                console.print(f"[bold red]{message} Draft not approved.[/bold red]")
                continue

            beats = store.get_beats(ep_no, ep_no)
            beat = beats[0] if beats else None
            prior_state = store.replay_state(ep_no - 1)
            if beat is not None and prior_state is not None:
                beat_text = (
                    beat.get("beat_text", beat.get("summary", ""))
                    if isinstance(beat, dict)
                    else getattr(beat, "beat_text", "")
                )
                new_delta, _ = Extractor(llm, settings, store.run_dir).extract_delta(
                    ep_no, edited_text, beat_text, prior_state
                )
            else:
                new_delta = res.delta
            normalized_beat = beat_from_record(beat, ep_no) if beat is not None else None
            if normalized_beat is not None and prior_state is not None:
                audit, _ = Judge(llm, settings, store.run_dir).audit_draft(
                    ep_no,
                    edited_text,
                    normalized_beat,
                    story_state_before(store, ep_no),
                )
                if (
                    not audit.passed
                    or not audit.word_count_valid
                    or audit.hook_score < 3
                    or audit.contradictions
                    or audit.unfulfilled_beats
                ):
                    append_event(
                        store.run_dir,
                        episode=ep_no,
                        step="human_review",
                        decision="edit_rejected_by_judge",
                        contradictions=audit.contradictions,
                        unfulfilled_beats=audit.unfulfilled_beats,
                        hook_score=audit.hook_score,
                    )
                    human_feedback = audit.feedback or (
                        "Revise the edited episode to resolve the judge's continuity and hook findings."
                    )
                    console.print(f"[bold red]Edited text needs revision: {audit.feedback}[/bold red]")
                    continue
            store.save_draft(ep_no, edited_text, new_delta.summary)
            _approve_episode(store, ep_no, new_delta)
            append_event(store.run_dir, episode=ep_no, step="human_review", decision="edited_and_approved")
            console.print(f"[bold green]Saved edited text and approved EP {ep_no}[/bold green]")
            return "approved", autopilot_remaining

        elif choice == "r":
            reason = Prompt.ask("Rejection reason")
            store.reject(ep_no)
            append_event(
                store.run_dir,
                episode=ep_no,
                step="human_review",
                decision="rejected",
                feedback=reason,
            )
            human_feedback = f"Previous draft rejected: {reason}"

        elif choice == "f":
            feedback_text = Prompt.ask("Enter feedback")
            interp = interpret_feedback(llm, feedback_text, ep_no)
            if interp.kind == "directive":
                d = add_directive_from_interpretation(store, interp, ep_no)
                append_event(
                    store.run_dir,
                    episode=ep_no,
                    step="human_feedback",
                    decision="directive_added",
                    directive_id=d.id,
                    directive=d.text,
                )
                console.print(f"[green]Added directive: {d.text}[/green]")
            elif interp.kind == "plan_change":
                revised = replan_window(store, llm, ep_no + 1, window=15, reason=feedback_text)
                append_event(
                    store.run_dir,
                    episode=ep_no,
                    step="human_feedback",
                    decision="arc_replanned",
                    feedback=feedback_text,
                    affected_episodes=[beat.ep_no for beat in revised],
                )
                console.print("[green]Re-planned upcoming window.[/green]")
            else:
                append_event(store.run_dir, episode=ep_no, step="human_feedback", decision="episode_guidance", feedback=feedback_text)
            human_feedback = feedback_text

        elif choice in ("s", "q"):
            return "stopped", autopilot_remaining


def _open_in_editor(initial_text: str) -> str:
    """Open initial_text in $EDITOR or notepad/nano fallback."""
    editor = os.getenv("EDITOR") or ("notepad" if os.name == "nt" else "nano")
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w+", delete=False, encoding="utf-8") as tf:
        tf.write(initial_text)
        temp_path = tf.name

    subprocess.call([editor, temp_path])
    with open(temp_path, "r", encoding="utf-8") as f:
        edited = f.read()
    if os.path.exists(temp_path):
        os.remove(temp_path)
    return edited
