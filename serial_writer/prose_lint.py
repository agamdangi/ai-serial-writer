"""Light-weight prose linting over approved episode text."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def _episode_texts(run_dir: Path) -> List[str]:
    episode_dir = Path(run_dir) / "episodes"
    texts: List[str] = []
    if not episode_dir.exists():
        return texts
    for path in sorted(episode_dir.glob("episode_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        text = data.get("content") or data.get("text") or ""
        if text:
            texts.append(text)
    return texts


def lint_run(run_dir: Path) -> Dict[str, Any]:
    texts = _episode_texts(Path(run_dir))
    if not texts:
        return {
            "episode_count": 0,
            "repeated_phrases": [],
            "common_openers": [],
            "average_sentence_length": 0.0,
            "question_share": 0.0,
            "hook_distribution": {},
            "models_used": [],
        }

    sentences = []
    episode_endings = []
    for text in texts:
        episode_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        sentences.extend(episode_sentences)
        if episode_sentences:
            episode_endings.append(episode_sentences[-1])

    three_grams = Counter()
    for text in texts:
        chunks = re.findall(r"\b\w+\b(?:\s+\b\w+\b){2}", text.lower())
        three_grams.update(chunks)

    openers = Counter()
    for sentence in sentences:
        opener = re.match(r"\b\w+\b", sentence.lower())
        if opener:
            openers[opener.group(0)] += 1

    sentence_lengths = [len(re.findall(r"\b\w+\b", sentence)) for sentence in sentences]
    question_share = sum(1 for s in episode_endings if s.endswith("?")) / max(len(episode_endings), 1)
    hook_distribution = {
        "question": sum(1 for sentence in episode_endings if sentence.endswith("?")),
        "other_hook": sum(1 for sentence in episode_endings if not sentence.endswith("?")),
    }

    models_used = []
    synthetic_trace = False
    trace_path = Path(run_dir) / "trace.jsonl"
    if trace_path.exists():
        with open(trace_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                model = event.get("model")
                if event.get("event") == "llm_call" and event.get("synthetic", False):
                    synthetic_trace = True
                if model and model not in models_used:
                    models_used.append(model)

    if synthetic_trace:
        models_used = ["FakeProvider (simulated; no live model call)"]

    return {
        "episode_count": len(texts),
        "repeated_phrases": [item for item, count in three_grams.most_common(5) if count > 1],
        "common_openers": [item for item, count in openers.most_common(5)],
        "average_sentence_length": round(sum(sentence_lengths) / max(len(sentence_lengths), 1), 2),
        "question_share": round(question_share, 4),
        "hook_distribution": hook_distribution,
        "models_used": models_used,
        "synthetic_trace": synthetic_trace,
    }
