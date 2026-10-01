"""Forward window re-planning when directives or plot changes occur."""

from typing import List, Optional
from pydantic import BaseModel, Field
from serial_writer.llm import LLMClient
from serial_writer.domain.models import ArcBeat
from serial_writer.store import Store


def _dump(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    elif hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _get_valid_role(llm: LLMClient, preferred: str) -> str:
    """Pick a valid role configured in settings."""
    roles = getattr(getattr(llm, "settings", None), "roles", {})
    if preferred in roles and roles[preferred]:
        return preferred
    for fallback in ["writer", "drafter", "editor", "judge", "default"]:
        if fallback in roles and roles[fallback]:
            return fallback
    if isinstance(roles, dict) and roles:
        return list(roles.keys())[0]
    return preferred


class ReplanOutput(BaseModel):
    new_beats: List[ArcBeat] = Field(default_factory=list)


def replan_window(
    store: Store,
    llm: LLMClient,
    from_ep: int,
    window: int = 20,
    reason: str = "Directive updated",
) -> List[ArcBeat]:
    """Re-plan beats from from_ep to from_ep + window - 1."""
    to_ep = from_ep + window - 1
    
    existing_beats = []
    if hasattr(store, "get_beats"):
        try:
            existing_beats = store.get_beats(from_ep, to_ep)
        except Exception:
            pass
    if not existing_beats and hasattr(store, "get_arc"):
        try:
            all_arc = store.get_arc()
            existing_beats = [b for b in all_arc if from_ep <= getattr(b, "ep_no", 0) <= to_ep]
        except Exception:
            pass

    bible_obj = store.get_bible() if hasattr(store, "get_bible") else {}
    bible_title = getattr(bible_obj, "title", bible_obj.get("title", "Untitled") if isinstance(bible_obj, dict) else "Untitled")

    directives = store.active_directives(from_ep) if hasattr(store, "active_directives") else []
    state = store.replay_state(from_ep - 1) if hasattr(store, "replay_state") else None

    alive_chars = []
    if state and hasattr(state, "characters"):
        characters = state.characters.values() if isinstance(state.characters, dict) else state.characters
        alive_chars = [c.name for c in characters if getattr(c, "status", "") == "alive"]

    system = (
        "You are an expert story planner for serial audio drama. "
        "Re-plan a specific window of episode beats while respecting the story bible, "
        "active directives, current character states, and fixed future plot points."
    )

    user = (
        f"Re-plan reason: {reason}\n"
        f"Window: EP {from_ep} to EP {to_ep}\n"
        f"Bible Title: {bible_title}\n"
        f"Active Directives: {[d.text for d in directives]}\n"
        f"Current Alive Characters: {alive_chars}\n"
        f"Existing Beats in Window:\n"
        + "\n".join([f"EP {getattr(b, 'ep_no', i)}: {getattr(b, 'beat_text', str(b))}" for i, b in enumerate(existing_beats, start=from_ep)])
        + "\n\nProvide updated beats for this exact window preserving act numbers and ep_no sequence."
    )

    role = _get_valid_role(llm, "writer")
    out, _ = llm.complete_json(
        role=role,
        system=system,
        user=user,
        schema=ReplanOutput,
        step="replan_window",
        episode=from_ep,
    )

    beats_res = getattr(out, "new_beats", [])
    if not beats_res:
        beats_res = [
            ArcBeat(
                ep_no=ep,
                act=1,
                beat_text=f"Re-planned beat for Ep {ep} ({reason})",
                purpose="replan",
                hook_type="reveal",
                threads_to_touch=[],
                plan_version=2,
            )
            for ep in range(from_ep, to_ep + 1)
        ]

    new_version = store.arc_version() + 1 if hasattr(store, "arc_version") else 2
    for beat in beats_res:
        beat.plan_version = new_version
    
    dict_beats = [_dump(b) for b in beats_res]
    
    if hasattr(store, "update_beats"):
        store.update_beats(beats_res, new_version=new_version)
    elif hasattr(store, "save_beats"):
        try:
            store.save_beats(beats_res)
        except TypeError:
            store.save_beats(dict_beats)
    elif hasattr(store, "save_plan"):
        store.save_plan(dict_beats)

    return beats_res
