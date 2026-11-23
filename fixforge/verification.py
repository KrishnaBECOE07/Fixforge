"""Conservative verification gates based on named tests, not just a green exit code."""
from __future__ import annotations

from .store import digest

ALLOWED_OUTCOMES = {"passed", "failed", "error", "skipped", "expected_failure", "unexpected_success"}


def valid_report(check: dict) -> bool:
    report = check.get("report")
    if not isinstance(report, dict) or report.get("report_version") != 2:
        return False
    ids, outcomes = report.get("test_ids"), report.get("outcomes")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 200 or not all(isinstance(i, str) for i in ids):
        return False
    if len(set(ids)) != len(ids) or not isinstance(outcomes, dict) or set(ids) != set(outcomes):
        return False
    if type(report.get("tests")) is not int or report["tests"] != len(ids):
        return False
    if any(type(report.get(key)) is not int or report[key] < 0 for key in
           ("failures", "errors", "skipped", "expected_failures", "unexpected_successes", "import_errors")):
        return False
    if type(report.get("successful")) is not bool:
        return False
    for row in outcomes.values():
        if (not isinstance(row, dict) or not isinstance(row.get("outcome"), str)
                or row["outcome"] not in ALLOWED_OUTCOMES
                or not isinstance(row.get("production_frames"), list)
                or not all(isinstance(frame, str) for frame in row["production_frames"])
                or not (row.get("category") is None or isinstance(row["category"], str))
                or not isinstance(row.get("failure_categories"), list)
                or not all(isinstance(category, str) for category in row["failure_categories"])):
            return False
    return True


def _success(check: dict) -> bool:
    return bool(valid_report(check) and not check.get("timed_out") and check.get("exit_code") == 0
                and check["report"]["successful"]
                and not any(check["report"][key] for key in
                            ("failures", "errors", "skipped", "expected_failures", "unexpected_successes", "import_errors"))
                and all(row["outcome"] == "passed" for row in check["report"]["outcomes"].values()))


def _assessment(check: dict, accepted: bool, reason: str, **details) -> dict:
    report = check.get("report")
    ids = report.get("test_ids", []) if isinstance(report, dict) else []
    return dict(accepted=accepted, reason=reason, test_identity_sha256=digest(ids), **details)


def assess_baseline(check: dict) -> dict:
    accepted = _success(check)
    return _assessment(check, accepted, "All original test identities passed" if accepted else
                       "Existing suite must pass, report named tests, and contain no skipped tests before repair. Check baseline logs.")


def assess_reproduction(baseline: dict, check: dict) -> dict:
    reason = "Regression did not demonstrate a valid new failure on the original code"
    if not valid_report(baseline) or not valid_report(check) or check.get("timed_out") or check.get("exit_code") != 1:
        return _assessment(check, False, reason + ": missing, invalid, or interrupted test evidence")
    report = check["report"]
    old = set(baseline["report"]["test_ids"])
    current = set(report["test_ids"])
    added = current - old
    if not old.issubset(current) or not added or not all(name.startswith("test_fixforge_regression.") for name in added):
        return _assessment(check, False, reason + ": original tests changed or the regression was not discovered")
    outcomes = report["outcomes"]
    if any(outcomes[name]["outcome"] != "passed" for name in old):
        return _assessment(check, False, reason + ": an existing test stopped passing")
    if report["successful"] or any(report[key] for key in ("skipped", "expected_failures", "unexpected_successes", "import_errors")):
        return _assessment(check, False, reason + ": collection errors or skipped tests are not defect evidence")
    failing = [outcomes[name] for name in added if outcomes[name]["outcome"] != "passed"]
    if (not failing or report["failures"] + report["errors"] < 1
            or any(row["outcome"] not in {"failed", "error"} or
                   row.get("category") not in {"assertion", "production_runtime"} or
                   not isinstance(row.get("failure_categories"), list) or
                   not row["failure_categories"] or
                   not all(category in {"assertion", "production_runtime"} for category in row["failure_categories"]) or
                   (row.get("category") == "production_runtime" and not row["production_frames"])
                   for row in failing)):
        return _assessment(check, False, reason + ": test-authoring and environment errors are not accepted")
    return _assessment(check, True, "New named regressions failed while all original tests stayed green",
                       original_tests=len(old), regression_tests=len(added),
                       expected_failure=True,
                       failure_categories=sorted({row["category"] for row in failing}))


def assess_patch(before: dict, check: dict) -> dict:
    same = valid_report(before) and valid_report(check) and set(before["report"]["test_ids"]) == set(check["report"]["test_ids"])
    accepted = bool(same and _success(check))
    return _assessment(check, accepted, "The identical named test suite passed after the patch" if accepted else
                       "Patched suite failed, skipped tests, or changed test identities. Review the logs.")


def assess_replay(baseline: dict, before: dict, replay: dict) -> dict:
    assessment = assess_reproduction(baseline, replay)
    if not assessment["accepted"] or not valid_report(before):
        return {**assessment, "accepted": False, "reason": "Counterfactual replay did not reproduce a valid defect failure"}

    def signature(check: dict) -> dict:
        return {name: {key: row.get(key) for key in ("outcome", "category", "exception", "failure_categories")}
                for name, row in check["report"]["outcomes"].items() if row["outcome"] != "passed"}

    if set(before["report"]["test_ids"]) != set(replay["report"]["test_ids"]) or signature(before) != signature(replay):
        return {**assessment, "accepted": False, "reason": "Counterfactual replay changed failure identities or signatures; possible nondeterminism"}
    return {**assessment, "reason": "Restoring the original production code reproduced the same named failures",
            "failure_signature_sha256": digest(signature(replay))}
