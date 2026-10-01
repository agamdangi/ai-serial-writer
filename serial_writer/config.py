import os
from pathlib import Path
from importlib.resources import files
from typing import Dict, List
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

load_dotenv()


class ModelSpec(BaseModel):
    match: List[str]
    exclude: List[str] = Field(default_factory=list)
    rpm: int
    tpm: int
    rpd: int
    json_mode: bool = True
    system_prompt: bool = True
    max_prompt_tokens: int = 200000
    price_in: float = 0.0
    price_out: float = 0.0


class Settings(BaseModel):
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    models: Dict[str, ModelSpec] = Field(default_factory=dict)
    roles: Dict[str, List[str]] = Field(default_factory=dict)
    context_budget_tokens: Dict[str, int] = Field(
        default_factory=lambda: {"plan": 12000, "draft": 10000, "extract": 6000, "judge": 6000}
    )
    thinking: Dict[str, str | bool] = Field(
        default_factory=lambda: {"plan": "default", "draft": "low", "extract": "off", "judge": "off"}
    )
    day_boundary_tz: str = "America/Los_Angeles"
    per_episode_cost_cap_usd: float = Field(
        default_factory=lambda: float(os.getenv("PER_EPISODE_COST_CAP_USD", "0.40"))
    )
    max_calls_per_episode: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CALLS_PER_EPISODE", "9"))
    )
    total_budget_cap_usd: float = Field(
        default_factory=lambda: float(os.getenv("TOTAL_BUDGET_CAP_USD", "15.0"))
    )
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "2")))
    words_min: int = Field(default_factory=lambda: int(os.getenv("WORDS_MIN", "400")))
    words_max: int = Field(default_factory=lambda: int(os.getenv("WORDS_MAX", "700")))
    repetition_block_threshold: float = Field(
        default_factory=lambda: float(os.getenv("REPETITION_BLOCK_THRESHOLD", "0.88"))
    )
    repetition_warn_threshold: float = Field(
        default_factory=lambda: float(os.getenv("REPETITION_WARN_THRESHOLD", "0.80"))
    )
    hook_streak_limit: int = Field(
        default_factory=lambda: int(os.getenv("HOOK_STREAK_LIMIT", "3"))
    )
    runs_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("RUNS_DIR", "runs"))
    )

    @model_validator(mode="after")
    def _ensure_default_roles(self):
        if not self.models:
            self.models = {
                "fake-model": ModelSpec(
                    match=[],
                    exclude=[],
                    rpm=999999,
                    tpm=999999999,
                    rpd=999999,
                    json_mode=True,
                    system_prompt=True,
                    max_prompt_tokens=200000,
                    price_in=0.0,
                    price_out=0.0,
                )
            }

        model_names = list(self.models.keys())
        if self.roles is None:
            self.roles = {}

        if model_names and not any(chain for chain in self.roles.values()):
            self.roles = {name: list(model_names) for name in ["plan", "draft", "extract", "judge", "writer", "default", "drafter", "editor"]}
            return self

        aliases = [
            ("writer", ["draft", "plan", "judge", "extract", "default"]),
            ("drafter", ["draft", "writer", "plan", "default"]),
            ("editor", ["judge", "draft", "writer", "default"]),
            ("default", ["plan", "draft", "extract", "judge", "writer"]),
        ]
        for alias_name, fallback_names in aliases:
            chain = self.roles.get(alias_name)
            if not chain:
                for fallback_name in fallback_names:
                    candidate = self.roles.get(fallback_name)
                    if candidate:
                        self.roles[alias_name] = list(candidate)
                        break
                else:
                    if model_names:
                        self.roles[alias_name] = list(model_names)

        for role in ["plan", "draft", "extract", "judge"]:
            if not self.roles.get(role) and model_names:
                self.roles[role] = list(model_names)

        if not self.roles.get('writer'):
            self.roles['writer'] = list(model_names)
        if not self.roles.get('default'):
            self.roles['default'] = list(model_names)

        return self


def load_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        configured_path = os.getenv("SERIAL_WRITER_CONFIG")
        if configured_path:
            config_path = Path(configured_path)
        else:
            project_config = Path(__file__).parent.parent / "config" / "models.yaml"
            packaged_config = Path(str(files("serial_writer.resources").joinpath("models.yaml")))
            config_path = project_config if project_config.exists() else packaged_config

    models_data = {}
    roles_data = {}
    day_boundary = "America/Los_Angeles"
    context_budget = {"plan": 12000, "draft": 10000, "extract": 6000, "judge": 6000}
    thinking_data = {"plan": "default", "draft": "low", "extract": "off", "judge": "off"}

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            day_boundary = raw.get("day_boundary_tz", day_boundary)
            context_budget = raw.get("context_budget_tokens", context_budget)
            thinking_data = raw.get("thinking", thinking_data)
            roles_data = raw.get("roles", roles_data)

            for name, spec in raw.get("models", {}).items():
                models_data[name] = ModelSpec(**spec)

    return Settings(
        models=models_data,
        roles=roles_data,
        day_boundary_tz=day_boundary,
        context_budget_tokens=context_budget,
        thinking=thinking_data,
    )
