"""Check report models and lightweight validation helpers."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    name: str
    passed: bool
    severity: Literal["block", "warn"] = "warn"
    detail: str = ""
    fix_instruction: str = ""


class CheckReport(BaseModel):
    passed: bool = True
    results: List[CheckResult] = Field(default_factory=list)
