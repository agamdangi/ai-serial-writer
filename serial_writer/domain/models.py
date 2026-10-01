"""Canonical domain models for serial story state and planning."""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ArcBeat(BaseModel):
    ep_no: int
    act: int
    beat_text: str
    purpose: str
    hook_type: str
    threads_to_touch: List[str] = Field(default_factory=list)
    plan_version: int = 1


class CharacterState(BaseModel):
    name: str
    status: Literal["alive", "dead", "missing", "unknown"] = "alive"
    location: str = "unknown"
    goals: List[str] = Field(default_factory=list)
    traits: List[str] = Field(default_factory=list)
    first_ep: int = 1
    last_seen_ep: int = 1
    notes: str = ""


class Relationship(BaseModel):
    a: str
    b: str
    kind: str
    intensity: int = Field(default=5, ge=0, le=10)
    since_ep: int = 1


class Fact(BaseModel):
    text: str
    subject: str
    valid_from_ep: int
    valid_to_ep: Optional[int] = None
    source_ep: int


class Thread(BaseModel):
    id: str
    description: str
    planted_ep: int
    due_by_ep: Optional[int] = None
    resolved_ep: Optional[int] = None
    status: Literal["open", "resolved", "dropped"] = "open"


class StateDelta(BaseModel):
    ep_no: int
    summary: str
    characters_upserts: List[CharacterState] = Field(default_factory=list)
    relationships_upserts: List[Relationship] = Field(default_factory=list)
    new_facts: List[Fact] = Field(default_factory=list)
    retired_facts: List[str] = Field(default_factory=list)
    threads_planted: List[Thread] = Field(default_factory=list)
    threads_resolved: List[str] = Field(default_factory=list)
    timeline_note: str = ""
    location_changes: Dict[str, str] = Field(default_factory=dict)


class Directive(BaseModel):
    id: str
    text: str
    scope: Literal["global", "character", "tone", "pacing"] = "global"
    from_ep: int
    to_ep: Optional[int] = None
    active: bool = True


class StoryState(BaseModel):
    characters: Dict[str, CharacterState] = Field(default_factory=dict)
    relationships: List[Relationship] = Field(default_factory=list)
    facts: List[Fact] = Field(default_factory=list)
    threads: Dict[str, Thread] = Field(default_factory=dict)
