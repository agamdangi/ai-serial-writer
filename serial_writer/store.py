import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CharacterState(BaseModel):
    name: str
    status: str = "alive"
    location: str = ""


class Fact(BaseModel):
    text: str
    subject: str
    valid_from_ep: int
    source_ep: int


class Thread(BaseModel):
    id: str
    description: str
    planted_ep: int
    status: str = "active"


class StateDelta(BaseModel):
    ep_no: int
    summary: str
    characters_upserts: List[CharacterState] = Field(default_factory=list)
    new_facts: List[Fact] = Field(default_factory=list)
    threads_planted: List[Thread] = Field(default_factory=list)
    threads_resolved: List[str] = Field(default_factory=list)


class WorldState(BaseModel):
    characters: Dict[str, CharacterState] = Field(default_factory=dict)
    facts: List[Fact] = Field(default_factory=list)
    threads: Dict[str, Thread] = Field(default_factory=dict)
    summaries: Dict[int, str] = Field(default_factory=dict)


class StateStore:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_dir = self.run_dir / "drafts"
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.episodes_dir = self.run_dir / "episodes"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)

    def save_world_state(self, world_data: Dict[str, Any]) -> None:
        path = self.run_dir / "world_state.json"
        path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")

    def load_world_state(self) -> Dict[str, Any]:
        path = self.run_dir / "world_state.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def save_plan(self, plan_data: Dict[str, Any]) -> None:
        path = self.run_dir / "plan.json"
        path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")

    def load_plan(self) -> Dict[str, Any]:
        path = self.run_dir / "plan.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def save_draft(self, ep_no: int, text: str, summary: str) -> str:
        version = "v1"
        draft_path = self.drafts_dir / f"ep_{ep_no:03d}_{version}.json"
        data = {
            "ep_no": ep_no,
            "version": version,
            "text": text,
            "summary": summary,
            "status": "draft",
        }
        draft_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return version

    def approve(self, ep_no: int, delta: StateDelta, version: str = "v1") -> None:
        draft_path = self.drafts_dir / f"ep_{ep_no:03d}_{version}.json"
        if draft_path.exists():
            data = json.loads(draft_path.read_text(encoding="utf-8"))
            data["status"] = "approved"
            draft_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

            self.save_episode(ep_no, {"ep_no": ep_no, "content": data.get("text", ""), "summary": delta.summary})
            self.save_summary(ep_no, delta.summary)

        self.apply_delta(delta)

    def reject(self, ep_no: int, version: str = "v1") -> None:
        draft_path = self.drafts_dir / f"ep_{ep_no:03d}_{version}.json"
        if draft_path.exists():
            data = json.loads(draft_path.read_text(encoding="utf-8"))
            data["status"] = "rejected"
            draft_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def apply_delta(self, delta: StateDelta) -> None:
        delta_path = self.run_dir / f"delta_ep_{delta.ep_no:03d}.json"
        delta_path.write_text(json.dumps(delta.model_dump(), indent=2), encoding="utf-8")

    def replay_state(self, up_to_ep: int) -> WorldState:
        state = WorldState()
        for ep in range(1, up_to_ep + 1):
            delta_path = self.run_dir / f"delta_ep_{ep:03d}.json"
            if delta_path.exists():
                data = json.loads(delta_path.read_text(encoding="utf-8"))
                state.summaries[ep] = data.get("summary", "")

                for char in data.get("characters_upserts", []):
                    c_obj = CharacterState(**char) if isinstance(char, dict) else char
                    state.characters[c_obj.name] = c_obj

                for fact in data.get("new_facts", []):
                    f_obj = Fact(**fact) if isinstance(fact, dict) else fact
                    state.facts.append(f_obj)

                for thread in data.get("threads_planted", []):
                    t_obj = Thread(**thread) if isinstance(thread, dict) else thread
                    state.threads[t_obj.id] = t_obj

                for thread_id in data.get("threads_resolved", []):
                    if thread_id in state.threads:
                        state.threads[thread_id].status = "resolved"

        return state

    def get_state_at_ep(self, ep_no: int) -> WorldState:
        return self.replay_state(up_to_ep=ep_no)

    def save_episode(self, episode: int, ep_data: Dict[str, Any]) -> None:
        path = self.episodes_dir / f"episode_{episode:03d}.json"
        path.write_text(json.dumps(ep_data, indent=2), encoding="utf-8")

    def load_episode(self, episode: int) -> Optional[Dict[str, Any]]:
        path = self.episodes_dir / f"episode_{episode:03d}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def save_summary(self, episode: int, summary: str) -> None:
        sum_dir = self.run_dir / "summaries"
        sum_dir.mkdir(parents=True, exist_ok=True)
        path = sum_dir / f"summary_{episode:03d}.txt"
        path.write_text(summary, encoding="utf-8")

    def load_summary(self, episode: int) -> Optional[str]:
        path = self.run_dir / "summaries" / f"summary_{episode:03d}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def save_directives(self, directives: Dict[str, List[str]]) -> None:
        path = self.run_dir / "directives.json"
        path.write_text(json.dumps(directives, indent=2), encoding="utf-8")

    def get_active_directives(self) -> Dict[str, List[str]]:
        path = self.run_dir / "directives.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"standing": [], "active": []}


# Aliases
Store = StateStore
