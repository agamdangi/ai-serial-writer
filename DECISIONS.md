# Decisions

## Memory at episode 150

Do not put 149 full episodes into the prompt. Replay approved deltas into a canonical character/relationship/fact/thread state; combine that with the arc beat, standing directives, spaced summaries of older episodes, and the latest three full episodes. Trim summaries/window entries to the role token budget. The state store is the durable source; summaries are lossy navigation aids.

## Human control and retroactive changes

The arc approval gate precedes writing. Each episode is drafted, extracted, checked, and judged before explicit approve/edit/reject/feedback choices. Feedback is either episode guidance, a forward directive, or a bounded future-arc replan; each action is traced. A past edit replaces its delta, marks later episodes stale, and requests a 15-episode replan. The checked-in offline demo shows two **scripted** interventions and their changed later beats/prose; it is not presented as a recording of human use.

## Model and workflow choices

Use one Gemini client with configured role chains: stronger models for prose/planning, lower-cost models for extraction/judging, with fallback and quota handling. Keep deterministic word-count, hook, call-limit, and budget checks outside the LLM judge. Sequential orchestration is easier to inspect and resume than a graph framework for this scope.

## Cost and time estimate

Use `python -m serial_writer estimate --run assignment_demo --target-episodes 200` to see an assumption-based scenario using configured model prices, role RPMs, 1 draft + 1 extraction + 1 judge per episode, stated token sizes, and a 15% reserve; it excludes human review. This is a planning estimate, not a quote. For measured projections, run the command on a representative Gemini-backed trace. The fake demo's actual live cost/time is deliberately unavailable. Reduce spend by routing routine extraction/judging to Flash-Lite, keeping only compact old summaries, caching stable context, and avoiding unnecessary revision calls after deterministic checks pass. API quota waits make wall-clock time variable.

## Known failure modes

- LLM extraction or judging can miss subtle contradictions; model output is not proof of continuity.
- Summary compression can omit a detail; replayable deltas and recent full episodes mitigate, not eliminate, this.
- Provider quotas, network failures, and model/schema drift can pause a run. Trace records and resumable files preserve progress.
- The included fake provider demonstrates contracts and control flow, not literary quality. Evaluate the live model's prose and human interventions separately.
