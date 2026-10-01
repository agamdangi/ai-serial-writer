"""Episode drafter engine enforcing word budgets, style directives, and beats."""

from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from serial_writer.config import Settings
from serial_writer.llm import LLMClient, LLMResult
from serial_writer.models import ArcBeat, Directive, StoryState


class DraftOutput(BaseModel):
    title: str = Field(description="Episode title")
    text: str = Field(description="Full prose text of the episode")
    word_count: int = Field(description="Exact word count of the text")
    beat_addressed: str = Field(description="Brief note on how the assigned beat was executed")


DRAFT_SYSTEM_PROMPT = """You are an expert fiction author writing an episodic serial novel.
Your task is to write a single compelling episode (400 to 700 words) based on the assigned beat, state summary, and style directives.

Rules:
1. WORD COUNT: Strict 400 - 700 words.
2. SHOW, DON'T TELL: Maintain strong sensory detail and grounded prose.
3. BEAT ADHERENCE: Fully execute the assigned arc beat and end on the required hook type.
4. CONTINUITY: Respect character statuses, current locations, active relationships, and known facts.
5. NO REPETITION: Avoid repeating recent sentence openings or dialogue tags.
6. OUTPUT FORMAT: Respond in JSON strictly matching the output schema.
"""


class Drafter:
    """Handles generating episode prose and running model bake-offs."""

    def __init__(self, llm_client: LLMClient, settings: Settings, run_dir: Path):
        self.client = llm_client
        self.settings = settings
        self.run_dir = run_dir

    def build_prompt(
        self,
        beat: ArcBeat,
        state: StoryState,
        context_summary: str,
        directives: List[Directive],
    ) -> str:
        active_dirs_str = "\n".join([f"- [{d.scope.upper()}] {d.text}" for d in directives]) or "None"
        char_str = "\n".join([
            f"- {c.name}: {c.status}, at {c.location}. Traits: {', '.join(c.traits)}"
            for c in state.characters.values()
        ]) or "None specified yet."

        prompt = f"""
### EPISODE {beat.ep_no} ASSIGNMENT
- Act: {beat.act}
- Beat Goal: {beat.beat_text}
- Target Purpose: {beat.purpose}
- Required Hook Type: {beat.hook_type}
- Active Threads to Touch: {', '.join(beat.threads_to_touch) if beat.threads_to_touch else 'None'}

### ACTIVE DIRECTIVES
{active_dirs_str}

### STORY CONTEXT & MEMORY
{context_summary}

### KNOWN CHARACTERS
{char_str}

Write Episode {beat.ep_no} following all guidelines.
"""
        return prompt.strip()

    def draft_episode(
        self,
        beat: ArcBeat,
        state: StoryState,
        context_summary: str,
        directives: List[Directive],
        *,
        episode: int,
        forced_model: str | None = None,
    ) -> tuple[DraftOutput, LLMResult]:
        """Draft a single episode using the `draft` LLM role."""
        prompt = self.build_prompt(beat, state, context_summary, directives)
        
        role = "draft"
        if forced_model:
            orig_chain = self.settings.roles.get(role, [])
            self.settings.roles[role] = [forced_model]
            try:
                parsed, res = self.client.complete_json(
                    role=role,
                    system=DRAFT_SYSTEM_PROMPT,
                    user=prompt,
                    schema=DraftOutput,
                    step="draft_episode",
                    episode=episode,
                    max_tokens=3000,
                    temperature=0.75,
                )
            finally:
                self.settings.roles[role] = orig_chain
        else:
            parsed, res = self.client.complete_json(
                role=role,
                system=DRAFT_SYSTEM_PROMPT,
                user=prompt,
                schema=DraftOutput,
                step="draft_episode",
                episode=episode,
                max_tokens=3000,
                temperature=0.75,
            )

        parsed.word_count = len(parsed.text.strip().split())
        return parsed, res

    def run_bakeoff(
        self,
        beat: ArcBeat,
        state: StoryState,
        context_summary: str,
        directives: List[Directive],
        candidate_models: List[str],
    ) -> Dict[str, DraftOutput]:
        """Draft the same episode across multiple model candidates for human comparison."""
        results = {}
        for model_name in candidate_models:
            try:
                draft_out, _ = self.draft_episode(
                    beat=beat,
                    state=state,
                    context_summary=context_summary,
                    directives=directives,
                    episode=beat.ep_no,
                    forced_model=model_name,
                )
                results[model_name] = draft_out
            except Exception as e:
                results[model_name] = DraftOutput(
                    title=f"FAILED ({model_name})",
                    text=f"Error generating with {model_name}: {e}",
                    word_count=0,
                    beat_addressed="Error",
                )
        return results
