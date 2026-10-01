# Agentic Serial Story Writer

A resumable, CLI-first serial-fiction workflow with a 200-beat arc, layered continuity memory, LLM drafting/extraction/judging, deterministic checks, human approval, and persisted run traces.

## Setup (under five minutes)

Requires Python 3.11+ and a Gemini API key for live generation. From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Add `GEMINI_API_KEY=...` to `.env`. The included `config/models.yaml` supplies model role chains and is also packaged for installed deployments. Set `SERIAL_WRITER_CONFIG` to use a different YAML file. Embedding support is optional (`python -m pip install -e ".[embeddings]"`). For offline verification no key is needed:

```powershell
python -m pytest -q
python -m serial_writer demo --fake --run assignment_demo
```

The offline demo writes a 200-beat plan, 15 checked 400–700-word episodes, two **scripted** feedback interventions, a trace, report, lint metrics, and estimate under `runs/assignment_demo/`. Fake output validates control flow, not live-model writing quality and not real provider cost.

Review the generated arc/episodes in `submission/demo_run/`, the intervention explanation in `submission/demo_run/HITL_DEMO.md`, and the complete arc/report in `submission/demo_run/REPORT.md`. The video deliverable is not fabricated: record the live interaction using the script in `docs/SCREEN_RECORDING_SCRIPT.md` and add the resulting video separately.

## Live CLI flow

```powershell
python -m serial_writer doctor
python -m serial_writer init --premise-file premise.txt --run live-demo
python -m serial_writer plan --run live-demo
python -m serial_writer arc-review --run live-demo
python -m serial_writer write --episodes 15 --run live-demo
```

`write` presents an approve/edit/reject/feedback/quit gate per episode. Continue later with `python -m serial_writer resume --run live-demo`. Feedback may apply to the current episode, become a standing directive, or replan the next 15 beats. Editing a past episode replaces its delta and marks downstream episodes stale. Review and approve revised beats before continuing.

Other commands: `status`, `edit`, `directive-list`, `report`, `prose-lint`, `estimate`, and `finalize`. `finalize --run assignment_demo` bundles docs and the selected run under `submission/`.

## Design

- `serial_writer/domain/`: canonical story state entities.
- `serial_writer/application/`: workflow use cases and ports.
- `serial_writer/infrastructure/`: runtime dependency composition.
- `serial_writer/interfaces/`: Typer CLI adapter.
- `serial_writer/planner.py`: 200 episode beats organized across ten phases, with character turns, recurring threads, and hooks.
- `serial_writer/context.py` and `serial_writer/store.py`: replayed characters, relationships, facts and threads; spaced older summaries; three-episode window; role token budgets.
- `serial_writer/pipeline.py`: draft → extract → judge → deterministic length/hook gates.
- `serial_writer/trace.py` and `serial_writer/llm.py`: JSONL decisions, retries, token use, latency, cost, and per-episode/total budget enforcement.

## Cost, time, and limitations

Run `python -m serial_writer estimate --run <run-name> --target-episodes 200` after a representative **live** run. Projection uses observed per-episode calls, cost, latency, and backoff with a 15% reserve. Zero-cost fake traces are not valid real-model estimates. Use lower-cost extraction/judging chains, bounded summaries, context caching, and avoid unnecessary revision calls to reduce spend. Live latency depends on provider quota and retries.

LLM judges can miss subtle continuity errors; summary compression is lossy; and model/API/schema changes can pause a run. The replayable state, stale markers, JSONL trace, and resumable files make these failures visible and recoverable, not impossible.

A short HITL recording script is in [docs/SCREEN_RECORDING_SCRIPT.md](docs/SCREEN_RECORDING_SCRIPT.md). See [docs/DELIVERY_CHECKLIST.md](docs/DELIVERY_CHECKLIST.md) for the live-run and real-recording items that still require your credentials and screen recorder; neither is falsely represented as complete here.
