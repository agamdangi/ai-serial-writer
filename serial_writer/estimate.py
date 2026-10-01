"""Simple cost and quota estimate generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from serial_writer.config import load_settings


def _read_trace(run_dir: Path) -> List[Dict[str, Any]]:
    trace_path = Path(run_dir) / "trace.jsonl"
    if not trace_path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with open(trace_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def estimate_run(run_dir: Path, target_episodes: int = 200) -> Dict[str, Any]:
    events = _read_trace(Path(run_dir))
    calls = [event for event in events if event.get("event") == "llm_call"]
    is_synthetic = any(event.get("step") == "demo_arc_review" for event in events)
    episode_calls = [
        event for event in calls
        if event.get("episode") is not None and int(event.get("episode", 0)) > 0
    ]
    planning_calls = [event for event in calls if event not in episode_calls]
    total_calls = len(calls)
    total_cost = sum(float(event.get("notional_cost_usd", 0.0)) for event in calls)
    episode_cost = sum(float(event.get("notional_cost_usd", 0.0)) for event in episode_calls)
    total_latency = sum(float(event.get("latency_s", 0.0)) for event in episode_calls)
    total_wait = sum(float(event.get("wait_s", 0.0)) for event in episode_calls)

    by_episode = {}
    for event in episode_calls:
        ep = event.get("episode")
        if ep is None:
            continue
        ep_key = int(ep)
        by_episode.setdefault(ep_key, {"calls": 0, "cost": 0.0})
        by_episode[ep_key]["calls"] += 1
        by_episode[ep_key]["cost"] += float(event.get("notional_cost_usd", 0.0))

    if by_episode:
        avg_calls = len(episode_calls) / len(by_episode)
        avg_cost = episode_cost / len(by_episode)
    else:
        avg_calls = 0.0
        avg_cost = 0.0

    projected_episode_cost = round(avg_cost * target_episodes * 1.15, 4)
    planning_cost = sum(float(event.get("notional_cost_usd", 0.0)) for event in planning_calls)
    projected_cost = round(planning_cost + projected_episode_cost, 4)
    projected_latency = round(total_latency / max(len(by_episode), 1) * target_episodes * 1.15, 2)
    # Trace latency includes in-call work; use 15% schedule headroom and retain measured wait separately.
    projected_wait = round(total_wait / max(len(by_episode), 1) * target_episodes * 1.15, 2)
    estimate = {
        "target_episodes": target_episodes,
        "observed_calls": total_calls,
        "observed_planning_calls": len(planning_calls),
        "observed_planning_cost": None if is_synthetic else round(planning_cost, 4),
        "projected_episode_generation_cost": None if is_synthetic else projected_episode_cost,
        "observed_cost": None if is_synthetic else round(total_cost, 4),
        "average_calls_per_episode": round(avg_calls, 2),
        "average_cost_per_episode": None if is_synthetic else round(avg_cost, 4),
        "estimated_cost_200": None if is_synthetic else projected_cost,
        "estimated_calls_200": round(avg_calls * target_episodes * 1.15, 2),
        "estimated_latency_seconds": None if is_synthetic else projected_latency,
        "estimated_wait_seconds": None if is_synthetic else projected_wait,
        "estimated_total_seconds": None if is_synthetic else round(projected_latency + projected_wait, 2),
        "synthetic_trace": is_synthetic,
        "projection_method": "Observed successful LLM calls per approved episode, plus a 15% revision/retry reserve.",
        "cost_reduction_options": [
            "Use the lower-cost configured model for extraction and routine audits.",
            "Cache stable world/character context and batch arc planning by act.",
            "Skip a second judge call when deterministic checks pass and retain human approval.",
            "Use short structured summaries for old episodes and reserve full context for the recent window.",
        ],
    }
    if is_synthetic:
        settings = load_settings()
        assumptions = {
            "draft": {"input_tokens": 5000, "output_tokens": 1200},
            "extract": {"input_tokens": 1500, "output_tokens": 350},
            "judge": {"input_tokens": 2500, "output_tokens": 250},
        }
        per_episode_cost = 0.0
        role_schedule_minutes = []
        estimated_role_calls = estimate["estimated_calls_200"] / 3
        scenario_roles = {}
        for role, usage in assumptions.items():
            chain = settings.roles.get(role, [])
            spec = settings.models.get(chain[0]) if chain else None
            if spec is None:
                continue
            role_cost = (
                usage["input_tokens"] * spec.price_in
                + usage["output_tokens"] * spec.price_out
            ) / 1_000_000
            per_episode_cost += role_cost
            role_calls = estimated_role_calls
            role_schedule_minutes.append(role_calls / max(spec.rpm, 1))
            scenario_roles[role] = {
                "preferred_model": chain[0],
                "assumed_input_tokens": usage["input_tokens"],
                "assumed_output_tokens": usage["output_tokens"],
                "configured_input_price_per_million": spec.price_in,
                "configured_output_price_per_million": spec.price_out,
                "configured_rpm": spec.rpm,
            }
        plan_chain = settings.roles.get("plan", [])
        plan_spec = settings.models.get(plan_chain[0]) if plan_chain else None
        planning_cost = 0.0
        planning_rate_minutes = 0.0
        if plan_spec:
            planning_cost = 2 * (6000 * plan_spec.price_in + 1000 * plan_spec.price_out) / 1_000_000
            planning_rate_minutes = 2 / max(plan_spec.rpm, 1)
        planned_episode_cost = per_episode_cost * estimated_role_calls * 3
        estimated_scenario_cost = planned_episode_cost + planning_cost
        rate_limit_floor = max(role_schedule_minutes, default=0.0) + planning_rate_minutes
        estimated_provider_minutes = rate_limit_floor + (estimate["estimated_calls_200"] + 2) * 2 / 60
        estimate["scenario_estimate"] = {
            "kind": "assumption_based_not_live_measurement",
            "assumptions": {
                "episodes": target_episodes,
                "calls_per_episode": "one draft, one extraction, one judge; 15% reserve",
                "planning_calls": 2,
                "planning_input_tokens_per_call": 6000,
                "planning_output_tokens_per_call": 1000,
                "estimated_network_latency_seconds_per_call": 2,
                "human_review_time_included": False,
            },
            "roles": scenario_roles,
            "estimated_cost_usd": round(estimated_scenario_cost, 2),
            "estimated_rate_limit_floor_minutes": round(rate_limit_floor, 1),
            "estimated_provider_time_minutes": round(estimated_provider_minutes, 1),
            "caveat": "Uses configured preferred-model prices and quotas plus assumed token use; actual fallback model, retries, provider pricing, and quota waits will change this estimate.",
        }
        estimate["summary"] = (
            f"Synthetic run: live trace cost/time unavailable. Assumption-based scenario for "
            f"{target_episodes} episodes is about ${estimated_scenario_cost:.2f} and "
            f"{estimated_provider_minutes / 60:.1f} provider hours, excluding human review."
        )
    else:
        estimate["summary"] = (
            f"Projected to {estimate['target_episodes']} episodes: "
            f"about ${estimate['estimated_cost_200']:.4f} notional spend, "
            f"{estimate['estimated_calls_200']:.0f} calls, and "
            f"{estimate['estimated_total_seconds']:.0f} seconds provider time."
        )
    return estimate
