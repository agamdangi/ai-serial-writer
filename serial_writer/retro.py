"""Retroactive edits, delta diff analysis, and stale episode dependency tagging."""

from serial_writer.config import Settings
from serial_writer.domain.models import StateDelta
from serial_writer.extractor import Extractor
from serial_writer.llm import LLMClient
from serial_writer.replan import replan_window
from serial_writer.store import Store
from serial_writer.trace import append_event


def edit_past_episode(store: Store, llm: LLMClient, ep_no: int, new_text: str) -> list[int]:
    """Apply retroactive edit to ep_no, detect stale downstream episodes, and replan."""
    beats = store.get_beats(ep_no, ep_no)
    beat = beats[0] if beats else None
    prior_state = store.replay_state(ep_no - 1)

    if beat is not None and prior_state is not None:
        beat_text = (
            beat.get("beat_text", beat.get("summary", ""))
            if isinstance(beat, dict)
            else getattr(beat, "beat_text", "")
        )
        settings = getattr(llm, "settings", None) or Settings()
        new_delta, _ = Extractor(llm, settings, store.run_dir).extract_delta(
            ep_no, new_text, beat_text, prior_state
        )
    else:
        new_delta = StateDelta(ep_no=ep_no, summary=f"Edited Ep {ep_no}")

    store.save_draft(ep_no, new_text, new_delta.summary)
    store.approve(ep_no, new_delta)

    stale_eps = []
    latest_ep = store.last_approved_ep()

    for past_ep in range(ep_no + 1, latest_ep + 1):
        store.mark_stale(past_ep, past_ep, f"Upstream edit in EP {ep_no}")
        stale_eps.append(past_ep)

    replan_window(store, llm, ep_no + 1, window=15, reason=f"Retroactive edit on EP {ep_no}")
    append_event(
        store.run_dir,
        episode=ep_no,
        step="retroactive_edit",
        decision="edited_and_replanned",
        stale_episodes=stale_eps,
    )
    return stale_eps
