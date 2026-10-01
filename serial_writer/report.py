"""Generate a concise Markdown report for a run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from serial_writer.store import Store


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def generate_report(run_dir: Path) -> str:
    """Build a simple project report from the run directory."""
    store = Store(Path(run_dir))
    plan = _safe_read_json(Path(run_dir) / "plan.json")
    directives = _safe_read_json(Path(run_dir) / "directives.json")
    episodes: List[Dict[str, Any]] = []
    for ep_file in sorted((Path(run_dir) / "episodes").glob("episode_*.json")):
        episodes.append(_safe_read_json(ep_file))

    trace_entries: List[Dict[str, Any]] = []
    trace_path = Path(run_dir) / "trace.jsonl"
    if trace_path.exists():
        with open(trace_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    trace_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    llm_calls = [item for item in trace_entries if item.get("event") == "llm_call"]
    is_synthetic = any(item.get("synthetic", False) for item in llm_calls)
    total_cost = sum(float(item.get("notional_cost_usd", 0.0)) for item in llm_calls)
    totals = {
        "episodes": len(episodes),
        "notional_cost_usd": None if is_synthetic else round(total_cost, 4),
        "calls": len(llm_calls),
        "last_approved_ep": store.last_approved_ep(),
        "planned_beats": len(plan.get("beats", [])),
    }

    lines: List[str] = []
    lines.append("# Run Report")
    lines.append("")
    lines.append(f"- Run directory: `{run_dir}`")
    lines.append(f"- Approved episodes: {totals['episodes']}")
    lines.append(f"- Last approved episode: {totals['last_approved_ep']}")
    if is_synthetic:
        lines.append("- Provider cost: unavailable (synthetic fake-provider run)")
    else:
        lines.append(f"- Total notional cost: ${totals['notional_cost_usd']:.4f}")
    lines.append(f"- Trace entries: {totals['calls']}")
    lines.append(f"- Planned episode beats: {totals['planned_beats']}")
    lines.append("")

    bible = store.load_bible() if hasattr(store, "load_bible") else {}
    if isinstance(bible, dict) and bible:
        lines.append("## Premise")
        lines.append(bible.get("premise", bible.get("title", "No premise recorded.")))
        lines.append("")

    if plan.get("phases"):
        lines.append("## Major arc phases")
        for phase in plan["phases"]:
            lines.append(f"- **{phase.get('title', 'Phase')}**: {phase.get('arc', '')}")
        lines.append("")

    if plan.get("character_arcs"):
        lines.append("## Character arcs")
        for name, arc in plan["character_arcs"].items():
            lines.append(f"- **{name}**: {arc}")
        lines.append("")

    if plan.get("beats"):
        lines.append(f"## Full arc plan ({len(plan['beats'])} beats)")
        for beat in plan["beats"]:
            ep = beat.get("ep_no", beat.get("episode", "?"))
            summary = beat.get("beat_text", beat.get("summary", ""))
            phase = beat.get("phase", "")
            purpose = beat.get("purpose", beat.get("title", ""))
            hook = beat.get("hook_type", beat.get("cliffhanger_hook", ""))
            lines.append(f"- EP {ep} [{phase}] ({purpose}): {summary} Hook: {hook}")
        lines.append("")

    if episodes:
        lines.append("## Episodes")
        for ep in episodes:
            lines.append(f"- EP {ep.get('ep_no', '?')}: {ep.get('summary', '')}")
        lines.append("")

    active = directives.get("active", directives.get("standing", []))
    if active:
        lines.append("## Active directives")
        for directive in active:
            lines.append(f"- {directive.get('text', '')}")
        lines.append("")

    return "\n".join(lines) + "\n"


def write_report(run_dir: Path) -> Path:
    report_path = Path(run_dir) / "REPORT.md"
    report_path.write_text(generate_report(run_dir), encoding="utf-8")
    return report_path
