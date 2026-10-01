"""Directive interpretation and storage for standing human feedback."""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from serial_writer.llm import LLMClient
from serial_writer.domain.models import Directive
from serial_writer.store import Store


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


class DirectiveInterpretation(BaseModel):
    """Interpretation of human feedback by LLM."""

    kind: Literal["episode_only", "directive", "plan_change"] = Field(
        default="directive",
        description="Category of the feedback."
    )
    directive_text: str = Field(
        default="",
        description="Imperative rule for writer if kind is directive."
    )
    scope: Literal["global", "character", "tone", "pacing"] = "global"
    affected_characters: list[str] = Field(default_factory=list)
    affected_threads: list[str] = Field(default_factory=list)
    from_ep: int = 1
    to_ep: Optional[int] = None
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


def interpret_feedback(
    llm: LLMClient,
    feedback_text: str,
    current_ep: int,
    current_state_summary: str = "",
) -> DirectiveInterpretation:
    """Interpret natural language feedback into structured intent."""
    system = (
        "You are an assistant for a serialized fiction writer. Classify user feedback into:\n"
        "- episode_only: A fix meant only for the current episode draft.\n"
        "- directive: A standing rule for all future episodes (e.g. style, character behavior, pacing).\n"
        "- plan_change: A request to alter major future plot events or character deaths/fates.\n"
        "If it is a directive, rewrite the directive_text as an imperative, clear rule."
    )
    user = (
        f"Current episode: {current_ep}\n"
        f"State summary: {current_state_summary}\n"
        f"Feedback: {feedback_text}"
    )

    role = _get_valid_role(llm, "writer")
    interp, _ = llm.complete_json(
        role=role,
        system=system,
        user=user,
        schema=DirectiveInterpretation,
        step="interpret_feedback",
        episode=current_ep,
    )
    if not interp.directive_text:
        interp.directive_text = feedback_text
    return interp


def add_directive_from_interpretation(
    store: Store,
    interp: DirectiveInterpretation,
    current_ep: int,
) -> Directive:
    """Save a directive and handle conflicting active directives."""
    active = store.active_directives(current_ep) if hasattr(store, "active_directives") else []
    for d in active:
        if d.text.strip().lower() == interp.directive_text.strip().lower():
            if hasattr(store, "deactivate_directive"):
                store.deactivate_directive(d.id)

    next_id = store.next_directive_id() if hasattr(store, "next_directive_id") else 1
    directive = Directive(
        id=f"dir_{current_ep}_{next_id}",
        text=interp.directive_text,
        scope=interp.scope,
        from_ep=current_ep,
        to_ep=interp.to_ep,
        active=True,
    )
    if hasattr(store, "add_directive"):
        store.add_directive(directive)
    return directive
