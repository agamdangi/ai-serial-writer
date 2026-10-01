"""Composition root for concrete runtime dependencies."""

from dataclasses import dataclass
from pathlib import Path

from serial_writer.config import Settings, load_settings
from serial_writer.fakes import FakeProvider
from serial_writer.llm import LLMClient
from serial_writer.store import Store


@dataclass(frozen=True)
class Runtime:
    """Concrete adapters needed by application use cases."""

    settings: Settings
    store: Store
    llm: LLMClient


def build_runtime(
    run_dir: Path,
    *,
    settings: Settings | None = None,
    fake: bool = False,
) -> Runtime:
    """Construct settings, persistence, and model-client dependencies."""
    run_dir = Path(run_dir)
    resolved_settings = settings or load_settings()
    transport = FakeProvider() if fake else None
    return Runtime(
        settings=resolved_settings,
        store=Store(run_dir),
        llm=LLMClient(resolved_settings, run_dir, transport=transport),
    )
