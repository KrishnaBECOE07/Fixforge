from collections import Counter, defaultdict
from math import ceil


ACTIVE_STATUSES = {"queued", "running"}
FAILURE_PHASES = {
    "index": "setup",
    "baseline": "baseline",
    "plan": "proposal",
    "reproduce": "reproduction",
    "patch": "verification",
    "verify": "verification",
    "evidence": "evidence",
}


def failure_category(run: dict) -> str:
    if run.get("stage") == "interrupted":
        return "interrupted"
    if (run.get("provider_timed_out")
            or run.get("error") == "Local Ollama did not respond before the request deadline."):
        return "provider_timeout"
    events = run.get("events", [])
    checks = run.get("checks", [])
    if checks and checks[-1].get("timed_out"):
        return "test_timeout"
    for event in reversed(events):
        phase = FAILURE_PHASES.get(event["stage"])
        if phase:
            return phase
    return "unknown"


def model_outcomes(runs: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for run in runs:
        if run["provider"] == "demo":
            continue
        receipt = run.get("provider_record") or {}
        model = receipt.get("model") or run.get("reviewed_model") or ""
        origin = "operator" if "supplied_regression" in run else "model"
        groups[run["provider"], model, origin].append(run)

    outcomes = []
    for (provider, model, origin), group in sorted(groups.items()):
        completed = [run for run in group if run["status"] not in ACTIVE_STATUSES]
        failures = Counter(failure_category(run) for run in completed if run["status"] == "failed")
        durations = sorted(run["duration_ms"] for run in completed if run.get("duration_ms") is not None)
        outcomes.append(dict(
            provider=provider, model=model or None, regression_origin=origin,
            completed=len(completed), in_progress=len(group) - len(completed),
            reached_review=sum(run["status"] in {"review", "approved", "rejected"} for run in completed),
            failures=dict(sorted(failures.items())), timed_runs=len(durations),
            p50_duration_ms=durations[ceil(len(durations) * .50) - 1] if durations else None,
            p95_duration_ms=durations[ceil(len(durations) * .95) - 1] if durations else None,
        ))
    return outcomes
