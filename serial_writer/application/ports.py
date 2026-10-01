"""Structural runtime contract consumed by application use cases."""

from typing import Any, Protocol


class RuntimePorts(Protocol):
    """Dependencies an application service needs from its composition root."""

    settings: Any
    store: Any
    llm: Any
