"""Typer command-line interface (inbound adapter)."""

import json
from pathlib import Path

import typer
from rich.console import Console

from serial_writer.application.services import SerialWriterService
from serial_writer.commands import estimate_run, finalize_run, lint_run, run_demo, write_report
from serial_writer.config import load_settings
from serial_writer.doctor import run_doctor
from serial_writer.infrastructure.runtime import build_runtime

app = typer.Typer(help="Agentic Serial Story Writer CLI")
console = Console()


def get_run_dir(run_name: str | None) -> Path:
    settings = load_settings()
    run_dir = settings.runs_dir / (run_name or "default")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _service(run_dir: Path, *, fake: bool = False) -> SerialWriterService:
    runtime = build_runtime(run_dir, settings=load_settings(), fake=fake)
    return SerialWriterService(runtime)


@app.command()
def doctor(ping_all: bool = False):
    """Run diagnostics on models and configuration."""
    run_doctor(ping_all=ping_all)


@app.command()
def init(premise_file: str = "premise.txt", run: str | None = None):
    """Initialize a run folder with premise."""
    run_dir = get_run_dir(run)
    premise_path = Path(premise_file)
    premise = premise_path.read_text(encoding="utf-8") if premise_path.exists() else "Default Premise"
    _service(run_dir).initialize(premise)
    console.print(f"[green]Initialized run in {run_dir}[/green]")


@app.command()
def plan(run: str | None = None):
    """Plan full story arc."""
    service = _service(get_run_dir(run))
    service.plan_from_saved_bible()
    console.print("[green]Arc planning complete.[/green]")


@app.command(name="arc-review")
def arc_review(run: str | None = None):
    """Review and approve arc plan."""
    run_dir = get_run_dir(run)
    _service(run_dir).review_arc(run_dir)


@app.command()
def write(
    ep: int | None = None,
    episodes: int = 1,
    interactive: bool = True,
    autopilot: int = 0,
    fake: bool = False,
    run: str | None = None,
):
    """Write episodes with human gate."""
    service = _service(get_run_dir(run), fake=fake)
    target_ep = ep or service.next_episode()
    if episodes < 1:
        raise typer.BadParameter("episodes must be at least 1")
    remaining_autopilot = autopilot
    for episode_no in range(target_ep, target_ep + episodes):
        status, remaining_autopilot = service.write_episode(
            episode_no,
            autopilot_remaining=remaining_autopilot,
        )
        console.print(f"Episode {episode_no} finished with status: [bold]{status}[/bold]")
        if status != "approved":
            break


@app.command()
def resume(run: str | None = None):
    """Resume workflow from last approved episode."""
    service = _service(get_run_dir(run))
    next_ep = service.resume()
    console.print(f"[green]Resuming workflow at Episode {next_ep}...[/green]")
    service.write_episode(next_ep)


@app.command()
def status(run: str | None = None):
    """Display story status."""
    service = _service(get_run_dir(run))
    console.print(f"[bold]Last Approved Episode:[/bold] {service.last_approved_episode()}")


@app.command(name="directive-list")
def directive_list(run: str | None = None):
    """List active directives."""
    service = _service(get_run_dir(run))
    for directive in service.list_active_directives():
        console.print(f"- [{directive.id}] {directive.text} (scope: {directive.scope})")


@app.command(name="edit")
def edit_ep(ep: int, run: str | None = None):
    """Retroactively edit an approved episode."""
    service = _service(get_run_dir(run))
    episode = service.get_episode(ep)
    if not episode:
        console.print(f"[red]Episode {ep} not found.[/red]")
        return
    stale = service.edit_episode(ep, episode["content"])
    console.print(f"[green]Episode {ep} updated. Stale downstream episodes: {stale}[/green]")


@app.command(name="demo")
def demo(fake: bool = True, run: str | None = None):
    """Run a small offline demo flow and produce a synthetic run."""
    run_dir = get_run_dir(run or "assignment_demo") if fake else get_run_dir(run)
    results = run_demo(run_dir, fake=fake)
    console.print(f"[green]Demo run created at {results['run_dir']}[/green]")
    console.print(f"Premise: {results['premise']}")
    console.print(f"Episodes generated: {results['episodes']}")


@app.command(name="report")
def report_cmd(run: str | None = None):
    """Write a Markdown report for the selected run."""
    path = write_report(get_run_dir(run))
    console.print(f"[green]Report saved to {path}[/green]")


@app.command(name="prose-lint")
def prose_lint(run: str | None = None):
    """Print simple prose-lint metrics for a run."""
    console.print(json.dumps(lint_run(get_run_dir(run)), indent=2))


@app.command(name="estimate")
def estimate(run: str | None = None, target_episodes: int = 200):
    """Estimate cost and quota needs from a run's trace log."""
    metrics = estimate_run(get_run_dir(run), target_episodes=target_episodes)
    console.print(json.dumps(metrics, indent=2))


@app.command(name="finalize")
def finalize(run: str | None = None):
    """Bundle documentation and the selected run's demo artifacts."""
    run_dir = get_run_dir(run)
    submission = finalize_run(run_dir.parent.parent, run_dir=run_dir)
    console.print(f"[green]Submission bundle created at {submission}[/green]")


if __name__ == "__main__":
    app()
