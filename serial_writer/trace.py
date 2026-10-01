from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List


class BudgetExceeded(Exception):
    pass


def append_event(run_dir: Path, **fields: Any) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "trace.jsonl"

    if "ts" not in fields:
        fields["ts"] = datetime.now(timezone.utc).isoformat()

    line = json.dumps(fields)
    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class BudgetGuard:
    def __init__(
        self,
        per_episode_cap: float,
        max_calls_per_episode: int,
        total_cap: float,
        run_dir: Path,
    ):
        self.per_episode_cap = per_episode_cap
        self.max_calls_per_episode = max_calls_per_episode
        self.total_cap = total_cap
        self.run_dir = Path(run_dir)

        self.total_cost: float = 0.0
        self.episode_costs: dict[int, float] = {}
        self.episode_calls: dict[int, int] = {}

        # Rebuild history from existing log files
        self._rebuild_from_logs()

    def _rebuild_from_logs(self) -> None:
        """Scan trace.jsonl in run_dir and restore accumulated cost and call metrics."""
        log_file = self.run_dir / "trace.jsonl"
        if not log_file.exists():
            return

        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cost = float(data.get("cost", 0.0))
                    ep = data.get("episode")

                    self.total_cost += cost
                    if ep is not None:
                        ep = int(ep)
                        self.episode_costs[ep] = self.episode_costs.get(ep, 0.0) + cost
                        self.episode_calls[ep] = self.episode_calls.get(ep, 0) + 1
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

    def check_before_call(self, episode: int, estimated_cost: float = 0.001) -> None:
        if self.total_cost + estimated_cost > self.total_cap:
            raise BudgetExceeded(
                f"Total budget cap exceeded: ${self.total_cost:.4f} + ${estimated_cost:.4f} > ${self.total_cap:.4f}"
            )

        current_ep_cost = self.episode_costs.get(episode, 0.0)
        if current_ep_cost + estimated_cost > self.per_episode_cap:
            raise BudgetExceeded(
                f"Episode {episode} cost cap exceeded: ${current_ep_cost:.4f} + ${estimated_cost:.4f} > ${self.per_episode_cap:.4f}"
            )

        current_ep_calls = self.episode_calls.get(episode, 0)
        if current_ep_calls + 1 > self.max_calls_per_episode:
            raise BudgetExceeded(
                f"Episode {episode} call limit reached: {current_ep_calls} calls >= max {self.max_calls_per_episode}"
            )

    def charge(self, episode: int, cost: float) -> None:
        self.total_cost += cost
        self.episode_costs[episode] = self.episode_costs.get(episode, 0.0) + cost
        self.episode_calls[episode] = self.episode_calls.get(episode, 0) + 1

        # Persist event to disk so rebuilding reads the recorded cost
        append_event(
            self.run_dir,
            event="charge",
            episode=episode,
            cost=cost,
        )


def summarize_trace(run_dir: Path) -> Dict[str, Any]:
    trace_path = run_dir / "trace.jsonl"
    events: List[Dict[str, Any]] = []
    if trace_path.exists():
        with open(trace_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    total_calls = len(events)
    total_cost = sum(float(e.get("notional_cost_usd", 0.0)) for e in events)
    total_in_tok = sum(int(e.get("in_tok", 0)) for e in events)
    total_out_tok = sum(int(e.get("out_tok", 0)) for e in events)

    return {
        "total_calls": total_calls,
        "total_cost_usd": total_cost,
        "total_input_tokens": total_in_tok,
        "total_output_tokens": total_out_tok,
        "events_count": len(events),
    }