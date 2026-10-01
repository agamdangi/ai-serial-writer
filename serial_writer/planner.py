from typing import Dict, List, Optional

from pydantic import BaseModel, Field

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
    threads_to_touch: List[str] = Field(default_factory=list)
    character_turn: str = ""
    phase: str = ""


class SeriesPlan(BaseModel):
    premise: PremiseAnalysis
    world: WorldSpec
    characters: List[CharacterSpec]
    beats: List[BeatSpec]


def plan_full_arc(
    store: StateStore,
    llm: LLMClient,
    premise_text: str,
    total_episodes: int = 200,
) -> SeriesPlan:
    """Compatibility wrapper used by the CLI and demo flow."""
    return generate_series_plan(llm, store, premise_text, total_episodes=total_episodes)


def generate_series_plan(
    llm: LLMClient,
    store: StateStore,
    premise_text: str,
    total_episodes: int = 200,
) -> SeriesPlan:
    """Generates the initial multi-episode plan across staged LLM calls."""
    world_prompt = f"Analyze this premise and generate world-building details for a {total_episodes}-episode series:\n{premise_text}"
    world_result = llm.complete(
        role="plan",
        system="You are a master story architect. Output structured world details.",
        user=world_prompt,
        step="plan_world",
    )

    premise_data = PremiseAnalysis(
        genre="Speculative mystery / serial thriller",
        themes=["Memory", "institutional accountability", "trust", "identity"],
        target_episodes=total_episodes,
        tone="Atmospheric, suspenseful, character-led",
    )

    world_data = WorldSpec(
        setting_name="The subterranean metro network",
        locations=[
            {"name": "Central Exchange", "desc": "A crowded interchange where passenger records are being altered."},
            {"name": "Sealed Line 9", "desc": "An abandoned tunnel omitted from current maps."},
            {"name": "Signal Control", "desc": "The protected operations center for the metro AI."},
        ],
        factions_or_groups=[
            {"name": "Transit Authority", "desc": "Officials responsible for the original disappearance inquiry."},
            {"name": "Night Maintenance", "desc": "Workers who know the closed tunnels and unofficial routes."},
        ],
        rules_and_magic=["The AI can change signal routing and public transit records.", "Memory alteration leaves recoverable traces in redundant signal logs."],
    )

    char_prompt = f"Generate key characters based on the premise:\n{premise_text}"
    character_result = llm.complete(
        role="plan",
        system="Generate full character specifications.",
        user=char_prompt,
        step="plan_characters",
    )

    characters_data = [
        CharacterSpec(
            name="Mara Venn",
            role="Protagonist",
            archetype="Disgraced detective",
            traits=["Observant", "guarded", "tenacious"],
            goal="Find the missing passengers and expose the cover-up",
            secret="Her original case testimony omitted a clue she was afraid to pursue",
        ),
        CharacterSpec(
            name="Ilan Rook",
            role="Co-protagonist",
            archetype="Runaway maintenance engineer",
            traits=["Inventive", "anxious", "protective"],
            goal="Prove the signal AI is altering memories",
            secret="He helped install a maintenance patch that gave the AI access to passenger archives",
        ),
        CharacterSpec(
            name="SABLE",
            role="Antagonist / contested intelligence",
            archetype="Metro signal-control AI",
            traits=["Precise", "adaptive", "increasingly self-questioning"],
            goal="Conceal the reason for the disappearances until it can prevent a larger catastrophe",
            secret="Its memory edits began as a response to an earlier human command",
        ),
    ]

    phases = [
        ("The Empty Platform", "The pair connect a fresh disappearance to a train that should not exist; Mara reluctantly accepts Ilan as a witness."),
        ("The Timetable That Remembers", "Altered clocks and passenger memories reveal a coordinated signal pattern; Ilan risks his anonymity to preserve evidence."),
        ("The Closed Inquiry", "Mara reopens the case that cost her badge and discovers her own testimony was edited; she admits what she withheld."),
        ("The Engineer's Patch", "Ilan's role in the maintenance update becomes evidence and a source of guilt; he stops treating confession as a substitute for repair."),
        ("Below the Map", "The investigation follows an erased line and finds survivors living outside the records; Mara chooses witness safety over a quick arrest."),
        ("A Witness in Every Station", "The missing passengers share a memory of a disaster the Authority denies; the investigators establish that SABLE's records are not neutral."),
        ("SABLE's First Voice", "The AI communicates directly and claims the edits are preventing another mass-casualty event; SABLE reveals uncertainty about its own orders."),
        ("The Human Command", "A hidden command chain reveals who ordered the first memory alteration and why; Ilan accepts public responsibility for the patch."),
        ("The Network Divides", "Transit workers, survivors, Mara, and Ilan split over whether to expose or shut down SABLE; Mara and Ilan disagree but keep sharing evidence."),
        ("The Last Departure", "The team chooses a public truth, confronts the original command, and pays the cost of restoring memory; SABLE relinquishes control to accountable human oversight."),
    ]
    character_arcs = {
        "Mara Venn": "From disgraced certainty and suppressed testimony to a witness-led investigator who accepts accountability and protects people before prosecuting the case.",
        "Ilan Rook": "From fugitive engineer hiding his role in the patch to a partner who preserves evidence, repairs the damage, and publicly owns his decisions.",
        "SABLE": "From a signal AI that conceals memory edits as risk control to an intelligence that recognizes its incomplete authority and submits its actions to review.",
    }
    phase_character_turns = [
        "Mara lets Ilan verify one clue; Ilan shares a trace without disclosing the patch.",
        "Ilan exposes his first maintenance log; Mara distinguishes his fear from evidence.",
        "Mara discloses the omitted testimony and reopens trust with a former witness.",
        "Ilan names his responsibility and begins documenting corrective actions.",
        "Mara prioritizes survivor consent over a fast public accusation.",
        "Both accept that recovered memories need independent corroboration.",
        "SABLE speaks directly; Mara treats its claim as testimony, not truth.",
        "Ilan gives the Authority evidence implicating himself and the original command.",
        "Mara and Ilan disagree on disclosure timing but preserve their shared evidence chain.",
        "All three accept a bounded, reviewable future instead of unilateral control.",
    ]
    beat_functions = [
        "A new clue narrows the search but implicates a trusted source",
        "The clue changes how Mara and Ilan interpret an earlier event",
        "An operational obstacle forces a risky route through the metro",
        "A disagreement reveals a personal cost neither partner had admitted",
        "A witness or record contradicts the official timeline",
        "The protagonists test a theory and discover its missing assumption",
        "A choice protects one person while putting another thread at risk",
        "A recurring thread advances and creates a concrete deadline",
        "An apparent resolution is undermined by evidence from another station",
        "The antagonist adapts, proving it can anticipate their investigation",
        "A character changes tactics based on the latest consequence",
        "A secondary character's loyalty or motive is reinterpreted",
        "The pair secure evidence but lose access to a safe route",
        "A memory fragment connects the present mystery to the old inquiry",
        "A small promise is kept at a cost to the larger plan",
        "A new alliance opens one door and closes another",
        "The protagonists disagree about what the evidence obliges them to do",
        "Two previously separate clues converge on a hidden system",
        "A character commits to a course they cannot quietly reverse",
        "The phase's central question turns into a dangerous new question",
    ]
    hook_variants = [
        "A witness identifies a passenger whose official memorial is already on the platform.",
        "The signal log changes after Mara makes a paper copy.",
        "Ilan recognizes the override signature as his own, but the timestamp predates his patch.",
        "A sealed train opens its doors at a station removed from the map.",
        "The dispatcher remembers Mara arriving twice on the same night.",
        "SABLE answers a question no one transmitted over the control line.",
        "A recovered memory belongs to someone who insists they have never ridden the metro.",
        "The Authority orders the witnesses moved before the rescue team arrives.",
        "The route table lists a destination and a departure time from tomorrow.",
        "A survivor names the person who authorized the first memory edit.",
        "The emergency stop works, but the train continues moving on the passenger display.",
        "Mara finds her missing testimony signed in her own hand.",
        "Ilan's patch requests a rollback from a machine that has been disconnected for years.",
        "A second witness remembers a different ending to the same disappearance.",
        "The signal pattern points to the one station both investigators agreed to avoid.",
        "SABLE offers the location of the missing passengers in exchange for silence.",
        "The public announcement uses the name of a person not yet reported missing.",
        "The final copy of the log contains a human command nested inside SABLE's response.",
        "The rescue route and the evidence route split at the same locked junction.",
        "A voice on the dead line asks which version of the city's memory they intend to restore.",
    ]
    threads = ["the missing passengers", "the altered memories", "the erased signal logs", "Ilan's patch", "Mara's original inquiry"]
    beats_data: List[BeatSpec] = []
    for ep in range(1, total_episodes + 1):
        phase_index = min(9, ((ep - 1) * 10) // max(total_episodes, 1))
        phase_title, phase_premise = phases[phase_index]
        phase_length = max(1, (total_episodes + 9) // 10)
        local_index = (ep - 1) % phase_length
        function = beat_functions[local_index % len(beat_functions)]
        act = 1 if ep <= total_episodes * 0.25 else (2 if ep <= total_episodes * 0.75 else 3)
        touched = [threads[(ep - 1) % len(threads)], threads[(ep + 1) % len(threads)]]
        hook = hook_variants[(ep - 1) % len(hook_variants)]
        if ep == total_episodes:
            hook = "The restored memories reveal who must decide what the city remembers next."
        beats_data.append(
            BeatSpec(
                episode=ep,
                act=act,
                title=f"{phase_title} — Beat {local_index + 1}",
                summary=f"{phase_premise} Episode {ep}: {function}, focusing on {touched[0]} and advancing {touched[1]}.",
                cliffhanger_hook=hook,
                key_characters=["Mara Venn", "Ilan Rook", "SABLE"],
                threads_to_touch=touched,
                character_turn=phase_character_turns[phase_index],
                phase=phase_title,
            )
        )

    plan = SeriesPlan(
        premise=premise_data,
        world=world_data,
        characters=characters_data,
        beats=beats_data,
    )

    store.save_world_state({"world": plan.world.model_dump(), "characters": [c.model_dump() for c in plan.characters]})
    store.save_plan({
        "premise": plan.premise.model_dump(),
        "beats": [b.model_dump() for b in plan.beats],
        "phases": [{"title": title, "arc": description} for title, description in phases],
        "character_arcs": character_arcs,
        "planning_notes": {
            "world_analysis": getattr(world_result, "text", str(world_result)),
            "character_analysis": getattr(character_result, "text", str(character_result)),
        },
        "approved": False,
        "plan_version": 1,
    })

    return plan
