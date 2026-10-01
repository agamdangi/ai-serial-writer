import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import Field

from serial_writer.domain.models import (
    CharacterState,
    Fact,
    Relationship,
    StateDelta,
    StoryState,
    Thread,
)


class WorldState(StoryState):
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

    def save_bible(self, bible_data: Dict[str, Any]) -> None:
        path = self.run_dir / "bible.json"
        path.write_text(json.dumps(bible_data, indent=2), encoding="utf-8")

    def load_bible(self) -> Dict[str, Any]:
        path = self.run_dir / "bible.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def get_bible(self) -> Dict[str, Any]:
        return self.load_bible()

    def get_episode(self, ep_no: int) -> Optional[Dict[str, Any]]:
        return self.load_episode(ep_no)

    def get_beats(self, start_ep: int, end_ep: Optional[int] = None) -> List[Any]:
        plan_data = self.load_plan()
        raw_beats = []
        if isinstance(plan_data, dict):
            raw_beats = plan_data.get("beats", plan_data.get("arc", []))
        elif isinstance(plan_data, list):
            raw_beats = plan_data
        if not raw_beats:
            return []
        end_limit = end_ep if end_ep is not None else start_ep
        filtered = []
        for beat in raw_beats:
            ep_no = beat.get("ep_no", beat.get("episode")) if isinstance(beat, dict) else getattr(beat, "ep_no", getattr(beat, "episode", None))
            if ep_no is None:
                continue
            if start_ep <= ep_no <= end_limit:
                filtered.append(beat)
        return filtered

    def update_beats(self, beats: List[Any], new_version: int | None = None) -> None:
        """Replace only the requested episode beats, preserving the rest of the plan."""
        plan = self.load_plan()
        raw_beats = plan.get("beats", []) if isinstance(plan, dict) else plan
        replacements = {}
        for beat in beats:
            item = beat.model_dump() if hasattr(beat, "model_dump") else dict(beat)
            episode = item.get("ep_no", item.get("episode"))
            if episode is not None:
                item["ep_no"] = episode
                item["episode"] = episode
                if new_version is not None:
                    item["plan_version"] = new_version
                replacements[int(episode)] = item
        updated = []
        seen = set()
        for old in raw_beats:
            old_data = old.model_dump() if hasattr(old, "model_dump") else dict(old)
            episode = old_data.get("ep_no", old_data.get("episode"))
            if episode is not None and int(episode) in replacements:
                updated.append(replacements[int(episode)])
                seen.add(int(episode))
            else:
                updated.append(old_data)
        updated.extend(item for number, item in replacements.items() if number not in seen)
        if isinstance(plan, dict):
            plan["beats"] = updated
            if new_version is not None:
                plan["plan_version"] = new_version
        else:
            plan = {"beats": updated, "plan_version": new_version or 1}
        self.save_plan(plan)

    def last_approved_ep(self) -> int:
        last_ep = 0
        for path in self.episodes_dir.glob("episode_*.json"):
            try:
                ep_no = int(path.stem.split("_")[-1])
            except ValueError:
                continue
            last_ep = max(last_ep, ep_no)
        for path in (self.run_dir / "summaries").glob("summary_*.txt"):
            try:
                ep_no = int(path.stem.split("_")[-1])
            except ValueError:
                continue
            last_ep = max(last_ep, ep_no)
        for path in self.run_dir.glob("delta_ep_*.json"):
            try:
                ep_no = int(path.stem.split("_")[-1])
            except ValueError:
                continue
            last_ep = max(last_ep, ep_no)
        return last_ep

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

                for retired in data.get("retired_facts", []):
                    state.facts = [
                        fact for fact in state.facts
                        if retired not in {fact.text, fact.subject}
                    ]

                for relation in data.get("relationships_upserts", []):
                    relation_obj = Relationship(**relation) if isinstance(relation, dict) else relation
                    state.relationships = [
                        item for item in state.relationships
                        if not (item.a == relation_obj.a and item.b == relation_obj.b and item.kind == relation_obj.kind)
                    ]
                    state.relationships.append(relation_obj)

                for thread in data.get("threads_planted", []):
                    if isinstance(thread, dict) and thread.get("status") == "active":
                        thread = {**thread, "status": "open"}
                    t_obj = Thread(**thread) if isinstance(thread, dict) else thread
                    if t_obj.status == "active":
                        t_obj.status = "open"
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

    def active_directives(self, current_ep: int) -> List[Any]:
        from serial_writer.domain.models import Directive

        directives_data = self.get_active_directives()
        active = directives_data.get("active", []) or directives_data.get("standing", [])
        parsed = []
        for item in active:
            if not isinstance(item, dict) or not item.get("active", True):
                continue
            try:
                directive = Directive.model_validate(item)
            except Exception:
                continue
            if directive.from_ep <= current_ep and (directive.to_ep is None or directive.to_ep >= current_ep):
                parsed.append(directive)
        return parsed

    def add_directive(self, directive: Any) -> None:
        data = self.get_active_directives()
        item = directive.model_dump() if hasattr(directive, "model_dump") else dict(directive)
        for key in ("active", "standing"):
            entries = data.setdefault(key, [])
            if not any(existing.get("id") == item.get("id") for existing in entries if isinstance(existing, dict)):
                entries.append(item)
        self.save_directives(data)

    def deactivate_directive(self, directive_id: str) -> None:
        data = self.get_active_directives()
        for key in ("active", "standing"):
            for item in data.get(key, []):
                if isinstance(item, dict) and item.get("id") == directive_id:
                    item["active"] = False
        self.save_directives(data)

    def next_directive_id(self) -> int:
        existing = self.get_active_directives()
        count = 0
        for key in ("active", "standing"):
            for item in existing.get(key, []):
                if isinstance(item, dict):
                    count = max(count, int(item.get("id", "0").split("_")[-1]) if item.get("id", "0").split("_")[-1].isdigit() else 0)
        return count + 1

    def mark_stale(self, start_ep: int, end_ep: int, reason: str = "") -> None:
        stale_path = self.run_dir / "stale.json"
        data = json.loads(stale_path.read_text(encoding="utf-8")) if stale_path.exists() else {}
        key = f"{start_ep}:{end_ep}"
        data[key] = {"reason": reason, "start_ep": start_ep, "end_ep": end_ep}
        stale_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# Aliases
Store = StateStore
