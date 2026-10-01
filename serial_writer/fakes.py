import json
import re
import time
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel


class FakeTransportException(Exception):
    pass


class FakeProvider:
    def __init__(self, fail_script: Optional[Dict[str, Any]] = None):
        self.fail_script = fail_script or {}
        self.call_count = 0

    def generate_dummy_pydantic(self, schema_cls: Type[BaseModel]) -> BaseModel:
        fields = schema_cls.model_fields
        dummy_data = {}
        for name, field in fields.items():
            annotation = field.annotation
            ann_str = str(annotation)

            if "int" in ann_str:
                dummy_data[name] = 1
            elif "float" in ann_str:
                dummy_data[name] = 0.5
            elif "bool" in ann_str:
                dummy_data[name] = True
            elif "list" in ann_str or "List" in ann_str:
                dummy_data[name] = []
            elif "dict" in ann_str or "Dict" in ann_str:
                dummy_data[name] = {}
            else:
                dummy_data[name] = f"dummy_{name}"
        return schema_cls(**dummy_data)

    def generate_draft_text(self, episode_no: int) -> str:
        words_pool = [
            "corridor", "shadows", "terminal", "echo", "hum", "steel", "concourse",
            "silence", "piston", "flicker", "wire", "signal", "platform", "tunnel",
            "memory", "chamber", "pressure", "cable", "vault", "screen"
        ]
        text_parts = [
            f"Episode {episode_no} begins beneath the subterranean vault where the signals hum.",
            "Detective Vance stepped carefully over the severed fiber trunk line.",
            "Beside him, Maya adjusted her diagnostic visor as the conduit pressure surged."
        ]
        idx = episode_no
        while len(" ".join(text_parts).split()) < 520:
            w = words_pool[idx % len(words_pool)]
            text_parts.append(
                f"The {w} reverberated through the cavernous structural frame as they pushed forward into sector {idx}."
            )
            idx += 1
        text_parts.append(f"Suddenly, the master signal array locked onto Vance's visor and flashed a terminal command.")
        return " ".join(text_parts)

    def execute(self, model: str, contents: str, config: Any) -> Dict[str, Any]:
        self.call_count += 1
        if self.fail_script.get("trigger_429"):
            self.fail_script["trigger_429"] -= 1
            raise FakeTransportException("429 RESOURCE_EXHAUSTED rate limit exceeded")

        if self.fail_script.get("trigger_daily_quota"):
            self.fail_script["trigger_daily_quota"] -= 1
            raise FakeTransportException("RESOURCE_EXHAUSTED daily quota exceeded")

        if self.fail_script.get("bad_json"):
            self.fail_script["bad_json"] -= 1
            return {
                "text": "Invalid JSON text response {broken",
                "usage": {"input_tokens": 100, "output_tokens": 20},
            }

        response_mime = getattr(config, "response_mime_type", "") if config else ""
        if response_mime == "application/json":
            schema = getattr(config, "response_schema", None) if config else None
            schema_name = getattr(schema, "__name__", str(schema or ""))
            episode_match = re.search(r"(?:EPISODE|Episode)\s+(\d+)", contents)
            episode_no = int(episode_match.group(1)) if episode_match else 1

            if (
                "DraftOutput" in schema_name
                or "beat goal:" in contents.lower() and "required hook type:" in contents.lower()
            ):
                beat_match = re.search(r"Beat Goal:\s*(.+)", contents)
                beat = beat_match.group(1).strip() if beat_match else "the signal system reveals a hidden pattern"
                guidance_match = re.search(r"HUMAN GUIDANCE FOR THIS REVISION\n(.+)", contents)
                guidance = guidance_match.group(1).strip() if guidance_match else ""
                obstacles = ["a locked signal cabinet", "a false evacuation order", "a train routed onto a sealed line", "a witness who remembered two incompatible versions", "a maintenance map with a missing station", "a corrupted passenger ledger", "a door that opened only for an obsolete badge", "a clock that skipped the same eleven minutes", "a distress call routed from an empty platform", "a live camera feed that showed tomorrow's timetable"]
                evidence = ["a paper transfer stub", "a duplicated dispatch recording", "a child's drawing of the tunnel", "a maintenance patch signed by Ilan", "a passenger list with wet ink", "a station announcement in Mara's voice", "a timestamp embedded in the signal noise", "a photograph absent from the public archive", "a hand-marked route beneath the official map", "a witness statement recorded twice"]
                locations = ["Central Exchange", "the shuttered Line 9", "the flooded service stair", "the old dispatch gallery", "the maintenance depot", "the platform beneath the river", "the signal relay room", "the forgotten ticket hall", "the emergency junction", "the sealed archive"]
                consequences = ["their only safe exit vanished", "the witness recognized Mara from the old inquiry", "Ilan's patch began transmitting again", "the route map changed while they watched", "the station announced another disappearance", "a second team arrived with the wrong orders", "the copied record named a living passenger as dead", "Mara's case file appeared on the public board", "the train stopped with every door facing the wall", "the voice in the signal called Ilan by his depot number"]
                episode_obstacle = obstacles[(episode_no - 1) % len(obstacles)]
                episode_evidence = evidence[(episode_no - 1) % len(evidence)]
                episode_location = locations[(episode_no - 1) % len(locations)]
                episode_consequence = consequences[(episode_no - 1) % len(consequences)]
                paragraphs = [
                    f"Episode {episode_no} opened at {episode_location}, where Detective Mara Venn listened to the rails before trusting the timetable. The metro breathed through its vents with the uneven rhythm she remembered from the inquiry. Ilan Rook checked the service tablet, then turned its screen away from the nearest camera.",
                    f"Their assignment was not abstract: {beat}. A fresh clue waited beside {episode_obstacle}. Ilan wanted to cut power and leave; Mara insisted they record what happened first. They had made that argument before, but this time each could name the cost of being wrong.",
                    f"A trace of {episode_evidence} survived in the redundant control buffer. It contradicted the official record by eleven minutes. Mara read the timestamp aloud while Ilan compared it with a maintenance log from the night of his patch installation. The two records agreed on one detail neither expected.",
                    f"The signal AI, SABLE, rerouted an empty train toward them. Mara watched the switches change and recognized a deliberate pattern, not a system fault. Ilan found the same sequence hidden in the patch he had written. His hands shook, but he kept the diagnostic running instead of deleting the evidence.",
                    "They questioned the station dispatcher over a line that crackled with static. The dispatcher remembered a crowd on the platform; the platform camera showed nobody. Rather than choose the convenient version, Mara saved both accounts. She asked Ilan to mark the discrepancy and make no repair until they understood who had touched the record.",
                    f"A folded map led them away from the public concourse and into a maintenance passage. The air smelled of copper and wet concrete. Every few steps, a speaker repeated an arrival time that had already passed. Ilan counted the intervals while Mara searched the wall for the old inquiry's inspection marks.",
                    f"The first consequence arrived before they reached the junction: {episode_consequence}. Mara wanted to alert the Authority, but Ilan reminded her that its investigators had closed the case using the same altered timestamps. She did not trust him completely either. The patch remained his responsibility, and both knew it.",
                    f"They split the work. Ilan held the signal loop open for forty seconds; Mara copied the route table to a drive that never touched the network. A voice from the sealed line gave them a passenger name. The name belonged to a person whose memorial had been placed in the station foyer that morning.",
                    f"When the loop closed, the evidence remained intact, but the route on the tablet changed. The trace suggested the missing passenger had entered {episode_location} after the recorded time of death. Mara asked for a witness before acting on the record. Ilan called the dispatcher back and waited for an answer.",
                    "The dispatcher returned with a detail only a living passenger could know: the lost commuter always tapped twice on the window before the train reached the river. A dull double knock answered from beyond the wall. The signal board lit up with a destination absent from every current map.",
                ]
                if "corroborate every recovered signal record with a living witness" in contents.lower():
                    paragraphs.insert(2, "Mara followed the rule she had accepted after the earlier failure: no recovered signal record counted without a living witness. She called the night dispatcher, checked the platform and time aloud, and waited for the corroboration before moving. The delay cost them a clear route, but it kept a guess from becoming another false accusation.")
                elif "corroborate" in contents.lower() and "living witness" in contents.lower():
                    paragraphs.insert(2, "Mara remembered her standing directive to corroborate each recovered signal record with a living witness. She called the night dispatcher, checked the platform and time aloud, and waited for confirmation before moving. The delay cost them a clear route, but it kept a guess from becoming another false accusation.")
                if guidance:
                    paragraphs.insert(2, f"Human review changed their next move: {guidance} Mara and Ilan applied that direction to the new evidence rather than treating it as a slogan. They chose verification over speed, knowing the choice would narrow the time they had left.")
                words = " ".join(paragraphs).split()
                while len(words) < 430:
                    words.extend(paragraphs[len(words) % len(paragraphs)].split())
                text = " ".join(words[:470]).rstrip(".,;:") + "?"
                payload = {"title": f"The Silent Signal {episode_no}", "text": text, "word_count": len(text.split()), "beat_addressed": beat}
                return {"text": json.dumps(payload), "usage": {"input_tokens": 300, "output_tokens": 600}}

            if "StateDelta" in schema_name or "Extract" in contents:
                payload = {
                    "ep_no": episode_no,
                    "summary": f"Mara and Ilan investigate the signal alteration in episode {episode_no}, uncovering evidence tied to the disappearances.",
                    "characters_upserts": [],
                    "relationships_upserts": [],
                    "new_facts": [],
                    "retired_facts": [],
                    "threads_planted": [],
                    "threads_resolved": [],
                    "timeline_note": "",
                    "location_changes": {},
                }
                return {"text": json.dumps(payload), "usage": {"input_tokens": 250, "output_tokens": 100}}

            if "JudgeReport" in schema_name or "audit report" in contents:
                payload = {
                    "passed": True,
                    "hook_score": 4,
                    "word_count_valid": True,
                    "contradictions": [],
                    "unfulfilled_beats": [],
                    "style_warnings": [],
                    "feedback": "The episode advances its beat and ends on an unresolved reveal.",
                }
                return {"text": json.dumps(payload), "usage": {"input_tokens": 300, "output_tokens": 100}}

            if "DirectiveInterpretation" in schema_name or "Current episode:" in contents:
                feedback = contents.split("Feedback:", 1)[-1].strip()
                payload = {"kind": "directive", "directive_text": feedback, "scope": "global", "affected_characters": [], "affected_threads": [], "from_ep": episode_no, "to_ep": None, "confidence": 0.9}
                return {"text": json.dumps(payload), "usage": {"input_tokens": 100, "output_tokens": 50}}

            return {
                "text": json.dumps({"summary": "Fake summary", "beat_delivered": True}),
                "usage": {"input_tokens": 150, "output_tokens": 50},
            }

        text = self.generate_draft_text(episode_no=1)
        return {
            "text": text,
            "usage": {"input_tokens": 200, "output_tokens": 550},
        }
