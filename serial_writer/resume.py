"""Resume logic for detecting the next episode to process."""

from serial_writer.store import Store
from serial_writer.llm import LLMClient
from serial_writer.config import Settings


def resume_run(store: Store, llm: LLMClient, settings: Settings) -> int:
    """Determine the next episode number to generate or review."""
    plan = store.load_plan() if hasattr(store, "load_plan") else {}
    if isinstance(plan, dict) and "approved" in plan and not plan["approved"]:
        raise ValueError("The story arc is not approved. Review and approve the plan before resuming.")
    last_ep = store.last_approved_ep() if hasattr(store, "last_approved_ep") else 0
    return last_ep + 1
