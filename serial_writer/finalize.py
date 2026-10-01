"""Create the submission bundle and decision log template."""

from __future__ import annotations

import shutil
from pathlib import Path


def finalize_run(workspace_root: Path | None = None, run_dir: Path | None = None) -> Path:
    root = Path(workspace_root) if workspace_root is not None else Path(__file__).resolve().parent.parent
    submission = root / "submission"
    submission.mkdir(parents=True, exist_ok=True)

    for name in ("README.md", "DECISIONS.md", "HITL_DEMO.md"):
        source = root / name
        if source.exists():
            shutil.copy2(source, submission / name)

    if run_dir is not None:
        source_run = Path(run_dir).resolve()
        if not source_run.is_dir():
            raise FileNotFoundError(f"Run directory does not exist: {source_run}")
        destination = submission / "demo_run"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_run, destination)

    return submission
