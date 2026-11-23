import copy

import pytest

from fixforge.verification import assess_baseline, assess_patch, assess_replay, assess_reproduction, valid_report

ORIGINAL = "test_existing.Payments.test_normal"
REGRESSION = "test_fixforge_regression.Zero.test_zero"


def check(outcomes=None, code=0):
    outcomes = outcomes or {ORIGINAL: outcome()}
    failed = sum(row["outcome"] == "failed" for row in outcomes.values())
    errors = sum(row["outcome"] == "error" for row in outcomes.values())
    report = dict(report_version=2, tests=len(outcomes), test_ids=list(outcomes), outcomes=outcomes,
                  failures=failed, errors=errors, skipped=0, expected_failures=0,
                  unexpected_successes=0, import_errors=0, successful=code == 0)
    return dict(report=report, exit_code=code, timed_out=False, passed=code == 0)


def outcome(kind="passed", category=None, frames=None):
    return dict(outcome=kind, category=category, exception=None, production_frames=frames or [],
                failure_categories=[category] if category else [])


def test_successful_three_gate_contract():
    baseline = check()
    before = check({ORIGINAL: outcome(), REGRESSION: outcome("error", "production_runtime", ["payments.py"])}, 1)
    after = check({ORIGINAL: outcome(), REGRESSION: outcome()})
    assert assess_baseline(baseline)["accepted"]
    assert assess_reproduction(baseline, before)["accepted"]
    assert assess_patch(before, after)["accepted"]


def test_same_test_count_with_different_test_identity_is_rejected():
    before = check({ORIGINAL: outcome(), REGRESSION: outcome("failed", "assertion")}, 1)
    substituted = check({ORIGINAL: outcome(), "test_replacement.Case.test_easy": outcome()})
    assert before["report"]["tests"] == substituted["report"]["tests"]
    assert not assess_patch(before, substituted)["accepted"]


@pytest.mark.parametrize("category", ["collection", "environment", "test_error"])
def test_non_defect_failures_do_not_count_as_reproduction(category):
    before = check({ORIGINAL: outcome(), REGRESSION: outcome("error", category)}, 1)
    assert not assess_reproduction(check(), before)["accepted"]


def test_original_tests_must_stay_green_during_reproduction():
    before = check({ORIGINAL: outcome("failed", "assertion"), REGRESSION: outcome()}, 1)
    assert not assess_reproduction(check(), before)["accepted"]


def test_mixed_subtest_failures_cannot_hide_an_environment_error():
    row = outcome("failed", "assertion")
    row["failure_categories"] = ["environment", "assertion"]
    assert not assess_reproduction(check(), check({ORIGINAL: outcome(), REGRESSION: row}, 1))["accepted"]


@pytest.mark.parametrize("mutation", ["duplicate_ids", "missing_outcome", "count", "invalid_outcome", "legacy", "false_report"])
def test_malformed_evidence_is_rejected(mutation):
    value = copy.deepcopy(check())
    if mutation == "duplicate_ids":
        value["report"]["test_ids"] *= 2
    elif mutation == "missing_outcome":
        value["report"]["outcomes"] = {}
    elif mutation == "count":
        value["report"]["tests"] = True
    elif mutation == "invalid_outcome":
        value["report"]["outcomes"][ORIGINAL]["outcome"] = "probably-passed"
    elif mutation == "legacy":
        value["report"].pop("report_version")
    else:
        value["report"] = False
    assert not valid_report(value)
    assert not assess_baseline(value)["accepted"]


def test_zero_discovered_tests_cannot_pass():
    value = check()
    value["report"].update(tests=0, test_ids=[], outcomes={})
    assert not assess_baseline(value)["accepted"]


def test_counterfactual_replay_must_restore_the_same_failure_signature():
    before = check({ORIGINAL: outcome(), REGRESSION: outcome("error", "production_runtime", ["payments.py"])}, 1)
    assert assess_replay(check(), before, copy.deepcopy(before))["accepted"]
    changed = copy.deepcopy(before)
    changed["report"]["outcomes"][REGRESSION]["exception"] = "DifferentException"
    result = assess_replay(check(), before, changed)
    assert not result["accepted"] and "nondeterminism" in result["reason"]


def test_counterfactual_replay_that_passes_is_not_verification():
    before = check({ORIGINAL: outcome(), REGRESSION: outcome("failed", "assertion")}, 1)
    replay = check({ORIGINAL: outcome(), REGRESSION: outcome()})
    assert not assess_replay(check(), before, replay)["accepted"]
