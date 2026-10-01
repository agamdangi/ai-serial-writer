"""Consistency and Quality Judge checking drafts against lore, beats, and style."""

from pathlib import Path
from typing import List
from pydantic import BaseModel, Field

from serial_writer.config import Settings
from serial_writer.llm import LLMClient, LLMResult
from serial_writer.models import ArcBeat, StoryState


class JudgeReport(BaseModel):
    passed: bool = Field(description="True if draft passes all critical checks without blocking errors")
    hook_score: int = Field(description="Rating of the ending hook from 1 (weak) to 5 (compelling)")
    word_count_valid: bool = Field(description="True if word count is within specified thresholds")
    contradictions: List[str] = Field(default_factory=list, description="Contradictions with prior state/facts")
    unfulfilled_beats: List[str] = Field(default_factory=list, description="Aspects of the assigned beat missing")
    style_warnings: List[str] = Field(default_factory=list, description="Prose style issues or repetitive language")
    feedback: str = Field(description="Constructive guidance for revision if required")


JUDGE_SYSTEM_PROMPT = """You are a rigorous literary editor auditing an episode draft.
Evaluate the episode text against the assigned beat, historical story state, and quality standards.

Criteria:
1. CONTRADICTIONS: Does anything conflict with character statuses, locations, or established facts?
2. BEAT DELIVERY: Is the assigned narrative beat properly accomplished?
3. HOOK QUALITY: Does the episode end on a punchy, engaging cliffhanger or narrative turn? Score 1 to 5.
4. PROSE / STYLE: Identify repetitive openers, tell-heavy exposition, or flat phrasing.

Respond in JSON strictly following the JudgeReport schema.
"""


class Judge:
    """Evaluates episode drafts for continuity and narrative punch."""

    def __init__(self, llm_client: LLMClient, settings: Settings, run_dir: Path):
        self.client = llm_client
        self.settings = settings
        self.run_dir = run_dir

    def audit_draft(
        self,
        ep_no: int,
        prose: str,
        beat: ArcBeat,
        state: StoryState,
    ) -> tuple[JudgeReport, LLMResult]:
        """Audit an episode draft and produce a JudgeReport."""
        word_count = len(prose.strip().split())
        wc_valid = self.settings.words_min <= word_count <= self.settings.words_max

        facts_str = "\n".join([f"- {f.subject}: {f.text}" for f in state.facts[-15:]]) or "None"
        char_str = "\n".join([f"- {c.name} ({c.status} at {c.location})" for c in state.characters.values()]) or "None"

        user_prompt = f"""
### EPISODE {ep_no} DRAFT ({word_count} words)
{prose}

### ASSIGNED BEAT
- Goal: {beat.beat_text}
- Required Hook Type: {beat.hook_type}

### KNOWN CHARACTERS & FACTS
Characters:
{char_str}

Recent Facts:
{facts_str}

Evaluate the episode and deliver your audit report.
"""
        report, res = self.client.complete_json(
            role="judge",
            system=JUDGE_SYSTEM_PROMPT,
            user=user_prompt,
            schema=JudgeReport,
            step="audit_episode_draft",
            episode=ep_no,
            max_tokens=2000,
            temperature=0.1,
        )
        report.word_count_valid = wc_valid
        if not wc_valid:
            report.style_warnings.append(
                f"Word count {word_count} is outside target range ({self.settings.words_min}-{self.settings.words_max})."
            )
        return report, res
