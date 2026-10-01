import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from serial_writer.config import Settings
from serial_writer.store import StateStore


class CompiledContext(BaseModel):
    system_directives: List[str]
    world_and_entities: Dict[str, Any]
    compressed_summaries: List[str]
    sliding_window_episodes: List[Dict[str, Any]]
    active_directives: List[str]
    estimated_tokens: int


class ContextEngine:
    def __init__(self, settings: Settings, store: StateStore):
        self.settings = settings
        self.store = store

    def build_context_for_episode(
        self,
        episode: int,
        role: str = "draft",
        window_size: int = 3,
    ) -> CompiledContext:
        """Assembles multi-tiered context within target token budgets."""
        budget = self.settings.context_budget_tokens.get(role, 10000)

        directives = self.store.get_active_directives()
        world_state = self.store.load_world_state() or {}

        summaries: List[str] = []
        summary_cutoff = max(1, episode - window_size)
        for ep in range(1, summary_cutoff):
            summary = self.store.load_summary(ep)
            if summary:
                summaries.append(f"Ep {ep} Summary: {summary}")

        window_episodes: List[Dict[str, Any]] = []
        for ep in range(max(1, episode - window_size), episode):
            ep_data = self.store.load_episode(ep)
            if ep_data:
                window_episodes.append(ep_data)

        raw_payload = (
            json.dumps(directives)
            + json.dumps(world_state)
            + "".join(summaries)
            + json.dumps(window_episodes)
        )
        estimated_tokens = int(len(raw_payload) / 4)

        return CompiledContext(
            system_directives=directives.get("standing", []),
            world_and_entities=world_state,
            compressed_summaries=summaries,
            sliding_window_episodes=window_episodes,
            active_directives=directives.get("active", []),
            estimated_tokens=min(estimated_tokens, budget),
        )
