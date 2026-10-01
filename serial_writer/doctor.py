import json
import sys
from pathlib import Path
from typing import Dict, List
from rich.console import Console
from rich.table import Table

from serial_writer.config import load_settings, Settings
from serial_writer.llm import LLMClient, QuotaExhausted

console = Console()


def resolve_models_from_list(configured_models: dict, available_model_ids: List[str]) -> Dict[str, str]:
    resolved = {}
    clean_available = []
    for m_id in available_model_ids:
        clean_id = m_id.replace("models/", "") if m_id.startswith("models/") else m_id
        clean_available.append(clean_id)

    for name, spec in configured_models.items():
        candidates = []
        for real_id in clean_available:
            real_id_lower = real_id.lower()
            match_ok = all(tok.lower() in real_id_lower for tok in spec.match)
            exclude_ok = not any(tok.lower() in real_id_lower for tok in spec.exclude)
            if match_ok and exclude_ok:
                candidates.append(real_id)

        if not candidates:
            continue

        def score_candidate(cid: str) -> tuple:
            cid_lower = cid.lower()
            is_preview = 1 if ("preview" in cid_lower or "exp" in cid_lower) else 0
            has_date = 1 if any(char.isdigit() for char in cid.split("-")[-1]) and len(cid.split("-")[-1]) == 8 else 0
            return (is_preview, has_date, len(cid), cid)

        candidates.sort(key=score_candidate)
        resolved[name] = candidates[0]

    return resolved


def resolve_models(client: LLMClient, settings: Settings, run_dir: Path | None = None) -> Dict[str, str]:
    cache_path = (run_dir if run_dir else settings.runs_dir / "_global") / "models_resolved.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        available_ids = client.list_available_models()
    except Exception as err:
        error_text = str(err).upper()
        if "501" in error_text and "UNIMPLEMENTED" in error_text:
            console.print(
                "[yellow]Gemini model listing is unsupported (501); "
                "checking configured model IDs directly instead.[/yellow]"
            )
            # The current config uses API model IDs as its keys. Do not cache
            # this assumption; the subsequent generation ping validates it.
            return {name: name for name in settings.models}

        console.print(f"[bold red]Failed to fetch model list from Gemini API:[/] {err}")
        if cache_path.exists():
            console.print("[yellow]Using cached model resolutions.[/yellow]")
            return json.loads(cache_path.read_text(encoding="utf-8"))
        raise err

    resolved = resolve_models_from_list(settings.models, available_ids)
    cache_path.write_text(json.dumps(resolved, indent=2), encoding="utf-8")
    return resolved


def run_doctor(ping_all: bool = False):
    settings = load_settings()
    if not settings.gemini_api_key:
        console.print("[bold red]GEMINI_API_KEY is not set in environment or .env file.[/bold red]")
        sys.exit(1)

    console.print(f"[bold green]GEMINI_API_KEY detected.[/bold green]")
    client = LLMClient(settings, run_dir=settings.runs_dir / "_global")

    try:
        resolved = resolve_models(client, settings)
    except Exception as err:
        console.print(f"[bold red]Doctor failed to resolve models:[/] {err}")
        sys.exit(1)

    table = Table(title="Role Chains and Model Resolutions")
    table.add_column("Role", style="cyan")
    table.add_column("Configured Name", style="magenta")
    table.add_column("Resolved Model ID", style="green")
    table.add_column("Limits (RPM/TPM/RPD)", style="yellow")

    role_status = {}
    for role, chain in settings.roles.items():
        resolved_chain = []
        for cfg_name in chain:
            real_id = resolved.get(cfg_name)
            if real_id:
                resolved_chain.append(real_id)
                spec = settings.models[cfg_name]
                limits = f"{spec.rpm}/{spec.tpm}/{spec.rpd}"
                table.add_row(role, cfg_name, real_id, limits)
            else:
                table.add_row(role, cfg_name, "[red]NOT FOUND[/red]", "N/A")
        role_status[role] = len(resolved_chain) > 0

    console.print(table)

    empty_roles = [r for r, ok in role_status.items() if not ok]
    if empty_roles:
        console.print(f"[bold red]Error: The following roles have no valid resolved models:[/] {', '.join(empty_roles)}")
        sys.exit(1)

    extract_chain = settings.roles.get("extract", [])
    first_extract_name = extract_chain[0] if extract_chain else None
    if first_extract_name and first_extract_name in resolved:
        console.print(f"\n[bold blue]Pinging first extract model ({resolved[first_extract_name]})...[/bold blue]")
        try:
            res = client.complete("extract", "You are a health-check assistant.", "Respond with 'OK'.", step="doctor_ping")
            console.print(f"[bold green]Ping test successful:[/] {res.text.strip()}")
        except Exception as ping_err:
            console.print(f"[bold red]Ping test failed:[/] {ping_err}")
            sys.exit(1)

    if ping_all:
        console.print("\n[bold yellow]Pinging all resolved models (--ping-all)...[/bold yellow]")
        for cfg_name, real_id in resolved.items():
            console.print(f"Pinging {cfg_name} ({real_id})...")
            try:
                res = client.complete_with_model(real_id, "You are a check assistant.", "Ping", step="doctor_ping_all")
                console.print(f"  [green]Success:[/] {res.text.strip()[:40]}")
            except Exception as p_err:
                console.print(f"  [red]Failed:[/] {p_err}")

    console.print("\n[bold cyan]Reminder:[/] Verify rate limits with your AI Studio dashboard dashboard.")
