"""Lightweight arc review flow for approving the planned story arc."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console
from rich.prompt import Confirm
from serial_writer.trace import append_event


console = Console()


def _read_plan(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"beats": [], "approved": False}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"beats": [], "approved": False}


def render_arc_markdown(plan: Dict[str, Any]) -> str:
    beats = plan.get("beats", [])
    lines: List[str] = ["# Story Arc", ""]
    if plan.get("phases"):
        lines.extend(["## Major phases", ""])
        for phase in plan["phases"]:
            lines.append(f"- **{phase.get('title', 'Phase')}**: {phase.get('arc', '')}")
        lines.append("")
    if plan.get("character_arcs"):
        lines.extend(["## Character arcs", ""])
        for name, arc in plan["character_arcs"].items():
            lines.append(f"- **{name}**: {arc}")
        lines.append("")
    for beat in beats:
        ep = beat.get("ep_no", beat.get("episode", "?"))
        phase = beat.get("phase", "")
        purpose = beat.get("purpose", beat.get("title", ""))
        hook = beat.get("hook_type", beat.get("cliffhanger_hook", ""))
        text = beat.get("beat_text", beat.get("summary", ""))
        lines.append(f"- EP {ep} | {phase} | {purpose} | Hook: {hook} | {text}")
    return "\n".join(lines) + "\n"


def run_arc_review(store: Any, llm: Any, run_dir: Path) -> bool:
    """Render the plan, present a review gate, and record approval."""
    plan = _read_plan(Path(run_dir) / "plan.json")
    if not plan.get("beats"):
        console.print("[red]No arc plan found. Run `plan` before reviewing it.[/red]")
        return False

    path = Path(run_dir) / "arc_plan.md"
    path.write_text(render_arc_markdown(plan), encoding="utf-8")
    console.print(f"[green]Arc plan saved to {path}[/green]")

    if not Confirm.ask("Approve this arc and allow episode writing?", default=False):
        plan["approved"] = False
        (Path(run_dir) / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        append_event(Path(run_dir), step="arc_review", decision="rejected")
        console.print("[yellow]Arc left unapproved.[/yellow]")
        return False

    plan["approved"] = True
    plan["plan_version"] = plan.get("plan_version", 1)
    (Path(run_dir) / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    append_event(Path(run_dir), step="arc_review", decision="approved", beat_count=len(plan["beats"]))
    console.print("[green]Arc approved.[/green]")
    return True
