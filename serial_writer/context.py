import json
from typing import Any, Dict, List
from pydantic import BaseModel

from serial_writer.config import Settings
from serial_writer.store import StateStore


class CompiledContext(BaseModel):
    system_directives: List[Any]
    world_and_entities: Dict[str, Any]
    compressed_summaries: List[str]
    sliding_window_episodes: List[Dict[str, Any]]
    active_directives: List[Any]
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
        if hasattr(self.store, "replay_state"):
            replayed = self.store.replay_state(episode - 1)
            world_state = {
                "world": world_state.get("world", world_state),
                "characters": {
                    name: character.model_dump()
                    for name, character in replayed.characters.items()
                },
                "relationships": [item.model_dump() for item in replayed.relationships],
                "facts": [item.model_dump() for item in replayed.facts],
                "threads": {
                    name: thread.model_dump()
                    for name, thread in replayed.threads.items()
                },
            }

        all_summaries: List[tuple[int, str]] = []
        summary_cutoff = max(1, episode - window_size)
        for ep in range(1, summary_cutoff):
            summary = self.store.load_summary(ep)
            if summary:
                all_summaries.append((ep, f"Ep {ep}: {summary}"))

        # Preserve chronological coverage without stuffing every historical summary
        # into the prompt. Replay state carries durable facts/characters/threads.
        if len(all_summaries) > 18:
            stride = max(1, len(all_summaries) // 12)
            sampled = all_summaries[::stride]
            recent_cutoff = max(0, len(all_summaries) - 6)
            summaries = [text for _, text in sampled if _ < all_summaries[recent_cutoff][0]]
            summaries.extend(text for _, text in all_summaries[recent_cutoff:])
        else:
            summaries = [text for _, text in all_summaries]

        window_episodes: List[Dict[str, Any]] = []
        for ep in range(max(1, episode - window_size), episode):
            ep_data = self.store.load_episode(ep)
            if ep_data:
                window_episodes.append(ep_data)

        def estimate_tokens() -> int:
            raw = (
                json.dumps(directives, ensure_ascii=False, default=str)
                + json.dumps(world_state, ensure_ascii=False, default=str)
                + "".join(summaries)
                + json.dumps(window_episodes, ensure_ascii=False, default=str)
            )
            return max(1, int(len(raw) / 4))

        while estimate_tokens() > budget and len(summaries) > 1:
            summaries.pop(0)
        while estimate_tokens() > budget and len(window_episodes) > 1:
            window_episodes.pop(0)
        estimated_tokens = estimate_tokens()

        return CompiledContext(
            system_directives=directives.get("standing", []),
            world_and_entities=world_state,
            compressed_summaries=summaries,
            sliding_window_episodes=window_episodes,
            active_directives=directives.get("active", []),
            estimated_tokens=min(estimated_tokens, budget),
        )
