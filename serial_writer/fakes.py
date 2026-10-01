import json
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
            return {
                "text": json.dumps({"summary": "Fake summary", "beat_delivered": True}),
                "usage": {"input_tokens": 150, "output_tokens": 50},
            }

        text = self.generate_draft_text(episode_no=1)
        return {
            "text": text,
            "usage": {"input_tokens": 200, "output_tokens": 550},
        }
