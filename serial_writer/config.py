import os
from pathlib import Path
from typing import Dict, List
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

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


def load_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "models.yaml"

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
