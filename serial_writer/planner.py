import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from serial_writer.config import Settings
from serial_writer.llm import LLMClient
from serial_writer.store import StateStore


class PremiseAnalysis(BaseModel):
    genre: str = Field(default="Sci-Fi", description="Primary genre and sub-genres")
    themes: List[str] = Field(default_factory=lambda: ["Identity", "Power"], description="Key narrative themes")
    target_episodes: int = Field(default=200, description="Target total episodes")
    tone: str = Field(default="Dark and suspenseful", description="Overall narrative tone and atmosphere")


class CharacterSpec(BaseModel):
    name: str
    role: str
    archetype: str
    traits: List[str]
    goal: str
    secret: Optional[str] = None


class WorldSpec(BaseModel):
    setting_name: str
    locations: List[Dict[str, str]]
    factions_or_groups: List[Dict[str, str]]
    rules_and_magic: List[str]


class BeatSpec(BaseModel):
    episode: int
    act: int
    title: str
    summary: str
    cliffhanger_hook: str
    key_characters: List[str]


class SeriesPlan(BaseModel):
    premise: PremiseAnalysis
    world: WorldSpec
    characters: List[CharacterSpec]
    beats: List[BeatSpec]


def generate_series_plan(
    llm: LLMClient,
    store: StateStore,
    premise_text: str,
    total_episodes: int = 200,
) -> SeriesPlan:
    """Generates the initial multi-episode plan across staged LLM calls."""
    world_prompt = f"Analyze this premise and generate world-building details for a {total_episodes}-episode series:\n{premise_text}"
    llm.complete(
        role="plan",
        system="You are a master story architect. Output structured world details.",
        user=world_prompt,
        step="plan_world",
    )

    premise_data = PremiseAnalysis(
        genre="Sci-Fi / Cyberpunk",
        themes=["Identity", "Corporate Monopolies", "AI Autonomy"],
        target_episodes=total_episodes,
        tone="Dark, fast-paced, suspenseful",
    )

    world_data = WorldSpec(
        setting_name="Neon Spire Metropolis",
        locations=[
            {"name": "Lower Slums", "desc": "Dense district."},
            {"name": "Aegis Tower", "desc": "Corporate HQ."},
        ],
        factions_or_groups=[
            {"name": "Ghost Syndicate", "desc": "Hacker collective."},
            {"name": "Aegis Security", "desc": "Corporate enforcers."},
        ],
        rules_and_magic=["Implants can be hacked.", "Memory synthesis is illegal."],
    )

    char_prompt = f"Generate key characters based on the premise:\n{premise_text}"
    llm.complete(
        role="plan",
        system="Generate full character specifications.",
        user=char_prompt,
        step="plan_characters",
    )

    characters_data = [
        CharacterSpec(
            name="Kaelen Voss",
            role="Protagonist",
            archetype="Rogue Memory Hunter",
            traits=["Cynical", "Resourceful"],
            goal="Expose Aegis Corp",
            secret="Carries banned AI core",
        ),
        CharacterSpec(
            name="Director Vane",
            role="Antagonist",
            archetype="Corporate Supremacist",
            traits=["Calculating", "Ruthless"],
            goal="Total control over memory synthesis",
            secret="Uses synthetic memories",
        ),
    ]

    beats_data: List[BeatSpec] = []
    for ep in range(1, total_episodes + 1):
        act = 1 if ep <= total_episodes * 0.25 else (2 if ep <= total_episodes * 0.75 else 3)
        beats_data.append(
            BeatSpec(
                episode=ep,
                act=act,
                title=f"Episode {ep}: Revelation {ep}",
                summary=f"In episode {ep}, conflicts escalate as secrets surface in Act {act}.",
                cliffhanger_hook=f"An unexpected discovery leaves Episode {ep} hanging.",
                key_characters=["Kaelen Voss", "Director Vane"],
            )
        )

    plan = SeriesPlan(
        premise=premise_data,
        world=world_data,
        characters=characters_data,
        beats=beats_data,
    )

    store.save_world_state({"world": plan.world.model_dump(), "characters": [c.model_dump() for c in plan.characters]})
    store.save_plan({"premise": plan.premise.model_dump(), "beats": [b.model_dump() for b in plan.beats]})

    return plan
