"""StateDelta extractor engine updating world memory after episode approval."""

from pathlib import Path
from pydantic import BaseModel, Field

from serial_writer.config import Settings
from serial_writer.llm import LLMClient, LLMResult
from serial_writer.models import StateDelta, StoryState


EXTRACTOR_SYSTEM_PROMPT = """You are a meticulous continuity editor and lore keeper for a fiction series.
Given an episode's prose and the prior story state, analyze the episode and extract a precise StateDelta update in JSON.

Guidelines:
1. SUMMARY: Provide a concise 2-3 sentence summary of main events.
2. CHARACTERS: Upsert any character status or location changes.
3. FACTS: Record newly introduced permanent facts or retire invalidated ones.
4. THREADS: Record any new plot threads opened or existing threads resolved in this episode.
5. BEAT CHECK: Confirm if the intended narrative beat was delivered.
"""


class Extractor:
    """Extracts structured StateDelta objects from episode prose."""

    def __init__(self, llm_client: LLMClient, settings: Settings, run_dir: Path):
        self.client = llm_client
        self.settings = settings
        self.run_dir = run_dir

    def extract_delta(
        self,
        ep_no: int,
        prose: str,
        assigned_beat: str,
        current_state: StoryState,
    ) -> tuple[StateDelta, LLMResult]:
        """Extract state changes from episode text into a StateDelta."""
        user_prompt = f"""
### EPISODE {ep_no} TEXT
{prose}

### ASSIGNED BEAT
{assigned_beat}

### PRIOR STORY STATE SUMMARY
- Known Characters: {list(current_state.characters.keys())}
- Active Threads: {[t.id for t in current_state.threads.values() if t.status == 'open']}
- Total Facts Tracked: {len(current_state.facts)}

Extract the StateDelta for Episode {ep_no}.
"""
        delta, res = self.client.complete_json(
            role="extract",
            system=EXTRACTOR_SYSTEM_PROMPT,
            user=user_prompt,
            schema=StateDelta,
            step="extract_state_delta",
            episode=ep_no,
            max_tokens=2500,
            temperature=0.2,
        )
        delta.ep_no = ep_no
        return delta, res
