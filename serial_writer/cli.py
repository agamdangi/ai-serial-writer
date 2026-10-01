"""CLI Agentic Serial Story Writer"""

import typer
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from serial_writer.config import load_settings
from serial_writer.drafter import Drafter
from serial_writer.extractor import Extractor
from serial_writer.judge import Judge
from serial_writer.llm import LLMClient
from serial_writer.store import Store

app = typer.Typer(name="serial-writer", help="CLI Agentic Serial Story Writer")
console = Console()


def _get_run_dir(run_name: str | None) -> Path:
    return Path("runs") / run_name if run_name else Path("runs/default")


@app.command()
def doctor(
    ping_all: bool = typer.Option(False, "--ping-all", help="Ping all resolved model endpoints"),
    run: str = typer.Option(None, "--run", help="Run folder name"),
):
    """Check API key, list models, resolve IDs, print role chains and limits."""
    from serial_writer.doctor import run_doctor
    run_doctor(ping_all=ping_all, run_name=run)


@app.command()
def init(
    premise_file: str = typer.Option("premise.txt", "--premise-file", help="Path to premise file"),
    run: str = typer.Option(None, "--run", help="Run folder name"),
):
    """Create a run folder and store the premise."""
    run_dir = _get_run_dir(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    p_path = Path(premise_file)
    if p_path.exists():
        content = p_path.read_text(encoding="utf-8")
        (run_dir / "premise.txt").write_text(content, encoding="utf-8")
        console.print(f"[bold green]Initialized run at {run_dir}[/bold green] with premise from {premise_file}.")
    else:
        console.print(f"[bold red]Premise file {premise_file} not found.[/bold red]")


@app.command()
def plan(
    premise: str = typer.Option(None, "--premise", help="Inline story premise"),
    run: str = typer.Option(None, "--run", help="Run folder name"),
):
    """Run the staged arc planner and write arc_plan.md."""
    console.print("[yellow]plan[/yellow] command: implemented in Part 2 context.")


@app.command(name="arc-review")
def arc_review(run: str = typer.Option(None, "--run", help="Run folder name")):
    """Approve, edit or give feedback on the arc."""
    console.print("[yellow]arc-review[/yellow] command: implemented in Part 2 context.")


@app.command()
def write(
    ep: int = typer.Option(None, "--ep", help="Episode number to write"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Interactive review mode"),
    autopilot: int = typer.Option(0, "--autopilot", help="Autopilot N episodes"),
    dry: bool = typer.Option(False, "--dry", help="Dry run without committing"),
    run: str = typer.Option(None, "--run", help="Run folder name"),
):
    """Produce episodes with human gate approval."""
    run_dir = _get_run_dir(run)
    settings = load_settings()
    store = Store(run_dir)
    client = LLMClient(settings, run_dir)

    drafter = Drafter(client, settings, run_dir)
    extractor = Extractor(client, settings, run_dir)
    judge = Judge(client, settings, run_dir)

    target_ep = ep if ep is not None else store.last_approved_ep() + 1
    beats = store.get_beats(target_ep, target_ep)
    if not beats:
        console.print(f"[bold red]No arc beat found for episode {target_ep}. Run 'plan' first.[/bold red]")
        return

    beat = beats[0]
    state = store.replay_state(target_ep - 1)
    directives = store.active_directives(target_ep)

    console.print(f"\n[bold cyan]=== Writing Episode {target_ep} ===[/bold cyan]")
    console.print(f"[bold]Beat:[/bold] {beat.beat_text}")

    draft_out, draft_res = drafter.draft_episode(
        beat=beat,
        state=state,
        context_summary=f"Episode {target_ep} in sequence.",
        directives=directives,
        episode=target_ep,
    )

    report, judge_res = judge.audit_draft(target_ep, draft_out.text, beat, state)

    console.print(Panel(draft_out.text, title=f"Episode {target_ep}: {draft_out.title} ({draft_out.word_count} words)"))
    
    table = Table(title="Judge Audit Report")
    table.add_column("Check", style="cyan")
    table.add_column("Result", style="magenta")
    table.add_row("Pass / Fail", "[green]PASS[/green]" if report.passed else "[red]FAIL[/red]")
    table.add_row("Hook Score", f"{report.hook_score}/5")
    table.add_row("Word Count Valid", str(report.word_count_valid))
    table.add_row("Contradictions", "\n".join(report.contradictions) or "None")
    table.add_row("Style Warnings", "\n".join(report.style_warnings) or "None")
    console.print(table)

    if dry:
        console.print("[yellow]Dry run specified. Episode not saved or approved.[/yellow]")
        return

    if interactive and not autopilot:
        action = Prompt.ask(
            "Select action",
            choices=["approve", "regenerate", "reject"],
            default="approve" if report.passed else "regenerate",
        )
        if action == "approve":
            delta, _ = extractor.extract_delta(target_ep, draft_out.text, beat.beat_text, state)
            store.save_draft(target_ep, draft_out.text, summary=delta.summary, cost=draft_res.notional_cost_usd)
            store.approve(target_ep, delta)
            console.print(f"[bold green]✓ Episode {target_ep} approved and committed to story store.[/bold green]")
        elif action == "reject":
            store.reject(target_ep)
            console.print(f"[yellow]Episode {target_ep} draft rejected.[/yellow]")
        else:
            console.print("[yellow]Re-running episode generation...[/yellow]")
            write(ep=target_ep, interactive=interactive, autopilot=autopilot, dry=dry, run=run)
    else:
        if report.passed:
            delta, _ = extractor.extract_delta(target_ep, draft_out.text, beat.beat_text, state)
            store.save_draft(target_ep, draft_out.text, summary=delta.summary, cost=draft_res.notional_cost_usd)
            store.approve(target_ep, delta)
            console.print(f"[bold green]✓ Episode {target_ep} auto-approved.[/bold green]")


@app.command()
def bakeoff(
    ep: int = typer.Option(1, "--ep", help="Episode number to run bakeoff on"),
    run: str = typer.Option(None, "--run", help="Run folder name"),
):
    """Draft episode on several candidate models for side-by-side comparison."""
    run_dir = _get_run_dir(run)
    settings = load_settings()
    store = Store(run_dir)
    client = LLMClient(settings, run_dir)
    drafter = Drafter(client, settings, run_dir)

    beats = store.get_beats(ep, ep)
    if not beats:
        console.print(f"[red]No beat found for episode {ep}.[/red]")
        return

    candidates = settings.roles.get("draft", [])
    console.print(f"[bold cyan]Running Model Bake-off for Episode {ep} across candidates:[/bold cyan] {candidates}")

    state = store.replay_state(ep - 1)
    directives = store.active_directives(ep)
    results = drafter.run_bakeoff(beats[0], state, "Bakeoff run context", directives, candidates)

    for model_name, output in results.items():
        console.print(Panel(output.text[:400] + "...", title=f"Model: {model_name} ({output.word_count} words)"))


@app.command()
def audit(
    from_ep: int = typer.Option(1, "--from", help="Start episode"),
    to_ep: int = typer.Option(200, "--to", help="End episode"),
    run: str = typer.Option(None, "--run", help="Run folder name"),
):
    """Re-check consistency over a past episode range."""
    run_dir = _get_run_dir(run)
    settings = load_settings()
    store = Store(run_dir)
    client = LLMClient(settings, run_dir)
    judge = Judge(client, settings, run_dir)

    console.print(f"[bold cyan]Auditing episodes {from_ep} to {to_ep}...[/bold cyan]")
    for ep_no in range(from_ep, to_ep + 1):
        record = store.get_episode(ep_no)
        if not record:
            continue
        beats = store.get_beats(ep_no, ep_no)
        if not beats:
            continue
        state = store.replay_state(ep_no - 1)
        report, _ = judge.audit_draft(ep_no, record.text, beats[0], state)
        status_str = "[green]PASS[/green]" if report.passed else "[red]FAIL[/red]"
        console.print(f"Episode {ep_no}: {status_str} (Hook Score: {report.hook_score}/5)")


if __name__ == "__main__":
    app()
