"""Application use cases coordinating domain workflows and adapters."""

from pathlib import Path
from typing import Any

from serial_writer.arc_review import run_arc_review
from serial_writer.directives import add_directive_from_interpretation
from serial_writer.application.ports import RuntimePorts
from serial_writer.planner import plan_full_arc
from serial_writer.retro import edit_past_episode
from serial_writer.resume import resume_run
from serial_writer.review import review_loop


class SerialWriterService:
    """Orchestrate story-writing use cases without CLI concerns."""

    def __init__(self, runtime: RuntimePorts):
        self.runtime = runtime

    def initialize(self, premise: str, title: str = "Serial Story") -> None:
        self.runtime.store.save_bible({"premise": premise, "title": title})

    def plan(self, premise: str) -> Any:
        return plan_full_arc(self.runtime.store, self.runtime.llm, premise)

    def plan_from_saved_bible(self) -> Any:
        premise = self.runtime.store.get_bible().get("premise", "Default Premise")
        return self.plan(premise)

    def review_arc(self, run_dir: Path) -> bool:
        return run_arc_review(self.runtime.store, self.runtime.llm, run_dir)

    def write_episode(self, episode: int, autopilot_remaining: int = 0) -> tuple[str, int]:
        return review_loop(
            self.runtime.store,
            self.runtime.llm,
            self.runtime.settings,
            episode,
            autopilot_remaining=autopilot_remaining,
        )

    def resume(self) -> int:
        return resume_run(self.runtime.store, self.runtime.llm, self.runtime.settings)

    def next_episode(self) -> int:
        return self.runtime.store.last_approved_ep() + 1

    def last_approved_episode(self) -> int:
        return self.runtime.store.last_approved_ep()

    def list_active_directives(self, limit: int = 1000) -> list[Any]:
        return self.runtime.store.active_directives(limit)

    def get_episode(self, episode: int) -> Any:
        return self.runtime.store.get_episode(episode)

    def edit_episode(self, episode: int, content: str) -> list[int]:
        return edit_past_episode(self.runtime.store, self.runtime.llm, episode, content)

    def add_directive(self, interpretation: Any, from_episode: int) -> Any:
        return add_directive_from_interpretation(
            self.runtime.store, interpretation, from_episode
        )

