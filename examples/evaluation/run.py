"""Exercise the FixForge API on four project-owned defects with independent Docker checks."""

import argparse
import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from fixforge.api import create_app
from fixforge.config import DEFAULT_OLLAMA_MODEL, Settings
from fixforge.intelligence import safe_path
from fixforge.metrics import ACTIVE_STATUSES, failure_category
from fixforge.policy import REGRESSION_PATH
from fixforge.providers import check_ollama_model
from fixforge.sandbox import resolve_docker_image, run_tests
from fixforge.store import now
from fixforge.verification import assess_baseline, assess_patch, assess_reproduction


HERE = Path(__file__).resolve().parent
CASES = {
    "shipment_count": (
        "inventory", "A partial shipment is dropped",
        "shipment_count(13, 4) returns 3 but needs 4 shipments. Count a partially filled shipment. "
        "Keep zero units, exact multiples, and validation working. Limit changes to shipment_count.",
    ),
    "restock_queue": (
        "inventory", "The restock queue reorders equal priorities",
        "restock_queue should keep arrival order among items sharing a priority. For example, "
        "[(\"alpha\", 2), (\"beta\", 2), (\"urgent\", 3)] should become "
        "[(\"urgent\", 3), (\"alpha\", 2), (\"beta\", 2)]. Keep descending priority and the input list intact. "
        "Limit changes to restock_queue.",
    ),
    "normalize_zone": (
        "dispatch", "Mixed whitespace produces invalid zone labels",
        "normalize_zone(' north  west\\tbay ') should return 'NORTH-WEST-BAY'. Treat a run of whitespace "
        "as one separator inside a label. Keep uppercase, existing hyphens, and the blank-label error. "
        "Limit changes to normalize_zone.",
    ),
    "next_departure": (
        "dispatch", "Orders miss departures at their ready hour",
        "next_departure(10, [18, 9, 10]) returns 18 but should return 10. The ready hour is inclusive. "
        "Keep the earliest suitable hour regardless of input order, None when unavailable, and hour validation. "
        "Limit changes to next_departure.",
    ),
}
REPRODUCTIONS = {
    "shipment_count": ("stock", (13, 4), 4),
    "restock_queue": ("stock", ([("alpha", 2), ("beta", 2), ("urgent", 3)],),
                      [("urgent", 3), ("alpha", 2), ("beta", 2)]),
    "normalize_zone": ("routing", (" north  west\tbay ",), "NORTH-WEST-BAY"),
    "next_departure": ("routing", (10, [18, 9, 10]), 10),
}


def operator_regression(case: str) -> str:
    module, arguments, expected = REPRODUCTIONS[case]
    return f"""import unittest

from {module} import {case}


class IssueRegression(unittest.TestCase):
    def test_issue_example(self):
        self.assertEqual({case}(*{arguments!r}), {expected!r})
"""


def repair(client: TestClient, issue: dict) -> dict:
    preview = client.post("/api/source-preview", json=issue)
    preview.raise_for_status()
    response = client.post("/api/runs", json={**issue, "source_review_sha256": preview.json()["sha256"]})
    response.raise_for_status()
    endpoint = f"/api/runs/{response.json()['id']}"
    while True:
        response = client.get(endpoint)
        response.raise_for_status()
        run = response.json()
        if run["status"] not in ACTIVE_STATUSES:
            return run
        time.sleep(0.25)


def evaluate_case(client: TestClient, output: Path, case: str, repository: Path, image: str,
                  *, operator_test: bool = False) -> dict:
    repo_id, title, body = CASES[case]
    workspace = shutil.copytree(repository, output / case, ignore=shutil.ignore_patterns("__pycache__"))
    private_test = (HERE / "acceptance" / f"{case}.py").read_bytes()
    control = run_tests(workspace, False, image, "Independent control · public baseline")
    (workspace / REGRESSION_PATH).write_bytes(private_test)
    before = run_tests(workspace, False, image, "Independent acceptance · original code")
    reproduction = assess_reproduction(control, before)
    if not assess_baseline(control)["accepted"] or not reproduction["accepted"]:
        raise ValueError(f"{case}: the independent suite did not isolate the expected defect: {reproduction['reason']}")

    issue = dict(repository_id=repo_id, title=title, body=body, provider="ollama")
    if operator_test:
        issue["supplied_regression"] = operator_regression(case)
    run = repair(client, issue)
    (output / f"{case}-run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    verdict = run["status"] == "review" and run["integrity_valid"]
    after = None
    if verdict:
        for change in run["files"]:
            if change["path"] != REGRESSION_PATH:
                safe_path(workspace, change["path"]).write_text(change["after"], encoding="utf-8")
        after = run_tests(workspace, False, image, "Independent acceptance · patched code")

    acceptance = assess_patch(before, after) if after else None
    return dict(case=case, repository=repo_id, run_id=run["id"], status=run["status"], verified=verdict,
                stop_reason=run["error"], stop_category=failure_category(run) if run["status"] == "failed" else None,
                edit_format=(run.get("provider_record") or {}).get("edit_format"),
                usage=(run.get("provider_record") or {}).get("usage"), duration_ms=run.get("duration_ms"),
                source_sha256=run.get("source_sha256"), acceptance_test_sha256=hashlib.sha256(private_test).hexdigest(),
                independent_before=before["report"], independent_after=after["report"] if after else None,
                resolved=bool(acceptance and acceptance["accepted"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL, help="A locally installed Ollama model")
    parser.add_argument("--image", default="python:3.11-slim", help="A pre-pulled Linux Docker image")
    parser.add_argument("--case", action="append", choices=CASES, help="Select a case. Repeat to select several.")
    parser.add_argument("--operator-test", action="store_true", help="Supply a regression for the public issue example")
    parser.add_argument("--output", type=Path, default=Path(".fixforge/evaluation"))
    args = parser.parse_args()

    try:
        check_ollama_model(args.model)
        image, architecture = resolve_docker_image(args.image)
        args.output.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix="trial-", dir=args.output.resolve()))
        repositories = {name: shutil.copytree(HERE / "repositories" / name, output / "sources" / name,
                                             ignore=shutil.ignore_patterns("__pycache__"))
                        for name in ("inventory", "dispatch")}
        settings = Settings(data_dir=output / "workbench", repositories=repositories, image=image,
                            inference_provider="ollama", ollama_model=args.model)
        cases = list(dict.fromkeys(args.case or CASES))
        report = dict(started_at=now(), provider="ollama", model=args.model, image_id=image,
                      regression_origin="operator" if args.operator_test else "model",
                      architecture=architecture, limits=settings.inference_limits("ollama"),
                      requested_cases=cases, cases=[])
        print(f"Local trial directory: {output}", flush=True)
        with TestClient(create_app(settings)) as client:
            for case in cases:
                print(f"Running {case}", flush=True)
                row = evaluate_case(client, output, case, repositories[CASES[case][0]], image,
                                    operator_test=args.operator_test)
                report["cases"].append(row)
                (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                result = "independent tests passed" if row["resolved"] else row["stop_category"] or "independent tests failed"
                print(f"{case}: {result} ({row['run_id']})", flush=True)
    except ValueError as error:
        parser.exit(1, f"Evaluation stopped: {error}\n")

    print(f"Reached review: {sum(row['verified'] for row in report['cases'])}/{len(cases)}")
    print(f"Resolved: {sum(row['resolved'] for row in report['cases'])}/{len(cases)}")


if __name__ == "__main__":
    main()
