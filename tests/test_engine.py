import copy

import pytest

from fixforge.fixtures import FIXTURES
from fixforge.store import verify_record
from conftest import create_fixture


@pytest.mark.parametrize("fixture_id", list(FIXTURES))
def test_real_fail_to_pass_workflow(setup_engine, fixture_id):
    engine, store = setup_engine
    initial = create_fixture(store, fixture_id)
    engine.execute(initial["id"])
    run = store.get(initial["id"])
    assert run["status"] == "review", run["error"]
    assert len(run["checks"]) == 4
    baseline, before, after, replay = run["checks"]
    assert baseline["passed"] and baseline["report"]["tests"] > 0
    assert before["exit_code"] == 1 and not before["passed"]
    assert before["report"]["tests"] > baseline["report"]["tests"]
    assert after["passed"] and before["report"]["tests"] == after["report"]["tests"]
    assert not replay["passed"] and replay["assessment"]["accepted"]
    assert all(check["assessment"]["accepted"] for check in run["checks"])
    assert all(run["evidence"]["contracts"].values())
    assert verify_record(run)
    fixture = FIXTURES[fixture_id]
    assert (engine.settings.data_dir / "workspaces" / run["id"] / "original" / fixture.path).read_text() == fixture.original
    assert (engine.settings.data_dir / "workspaces" / run["id"] / "patched" / fixture.path).read_text() == fixture.replacement
    assert (engine.settings.data_dir / "workspaces" / run["id"] / "rollback" / fixture.path).read_text() == fixture.original


def test_non_reproducing_regression_cannot_be_verified(setup_engine, monkeypatch):
    engine, store = setup_engine
    fixture = FIXTURES["payment-zero"]
    monkeypatch.setattr("fixforge.engine.propose", lambda *args: {
        "rationale": "Wrong regression test", "plan": ["Try a regression"], "edits": [{"path": fixture.path, "content": fixture.replacement}],
        "regression": 'import unittest\nclass WrongTest(unittest.TestCase):\n    def test_nothing(self):\n        self.assertTrue(True)\n',
    })
    run = create_fixture(store)
    engine.execute(run["id"])
    result = store.get(run["id"])
    assert result["status"] == "failed" and result["evidence"] is None
    assert "valid new failure" in result["error"]


def test_broken_patch_cannot_be_verified(setup_engine, monkeypatch):
    engine, store = setup_engine
    fixture = FIXTURES["payment-zero"]
    monkeypatch.setattr("fixforge.engine.propose", lambda *args: {
        "rationale": "Incorrect patch", "plan": ["Try a patch"], "edits": [{"path": fixture.path, "content": fixture.original + "\n# no actual fix\n"}],
        "regression": fixture.regression,
    })
    run = create_fixture(store)
    engine.execute(run["id"])
    result = store.get(run["id"])
    assert result["status"] == "failed" and result["evidence"] is None
    assert "Patched suite failed" in result["error"]


@pytest.mark.parametrize("target", ["event", "patch", "check", "manifest"])
def test_tampered_record_is_detected(setup_engine, target):
    engine, store = setup_engine
    run = create_fixture(store)
    engine.execute(run["id"])
    value = copy.deepcopy(store.get(run["id"]))
    if target == "event":
        value["events"][0]["detail"] = "modified"
    elif target == "patch":
        value["files"][0]["after"] = "modified"
    elif target == "check":
        value["checks"][0]["log"] = "modified"
    else:
        value["evidence"]["contracts"]["full_suite_passed_after"] = False
    assert not verify_record(value)


def test_approval_binds_exact_patch_and_is_single_decision(setup_engine):
    engine, store = setup_engine
    run = create_fixture(store)
    with pytest.raises(ValueError, match="awaiting review"):
        store.decide(run["id"], "approve", "a" * 64, "")
    engine.execute(run["id"])
    verified = store.get(run["id"])
    with pytest.raises(ValueError, match="digest"):
        store.decide(run["id"], "approve", "a" * 64, "")
    approved = store.decide(run["id"], "approve", verified["evidence"]["patch_sha256"], "Reviewed edge cases")
    assert approved["status"] == "approved"
    assert approved["decision"]["note"] == "Reviewed edge cases"
    with pytest.raises(ValueError, match="awaiting review"):
        store.decide(run["id"], "reject", verified["evidence"]["patch_sha256"], "")


def test_restart_never_marks_incomplete_work_successful(setup_engine):
    _, store = setup_engine
    run = create_fixture(store)
    store.update(run["id"], status="running")
    store.recover()
    assert store.get(run["id"])["status"] == "failed"
    assert store.get(run["id"])["evidence"] is None


@pytest.mark.parametrize("target", ["issue", "revision", "provider", "explanation", "source_hash", "review_event", "execution"])
def test_manifest_binds_source_usage_and_runtime_metadata(setup_engine, target):
    engine, store = setup_engine
    run = create_fixture(store)
    engine.execute(run["id"])
    value = store.get(run["id"])
    assert value["evidence"]["version"] == 3
    if target == "issue":
        value["title"] = "different issue"
    elif target == "revision":
        value["source_revision"]["commit"] = "a" * 40
    elif target == "provider":
        value["provider_record"]["usage"]["total_tokens"] = 99
    elif target == "explanation":
        value["rationale"] = "changed explanation"
    elif target == "source_hash":
        value["source_sha256"] = "a" * 64
    elif target == "execution":
        value["execution_record"]["harness_sha256"] = "a" * 64
    else:
        value["events"].pop()
    assert not verify_record(value)


def test_regression_authoring_error_cannot_be_verified(setup_engine, monkeypatch):
    engine, store = setup_engine
    fixture = FIXTURES["payment-zero"]
    monkeypatch.setattr("fixforge.engine.propose", lambda *args: {
        "rationale": "A regression with a broken name", "plan": ["Reproduce zero bug"],
        "edits": [{"path": fixture.path, "content": fixture.replacement}],
        "regression": 'import unittest\nclass BrokenTest(unittest.TestCase):\n    def test_bug(self):\n        undefined_helper()\n',
    })
    run = create_fixture(store)
    engine.execute(run["id"])
    result = store.get(run["id"])
    assert result["status"] == "failed" and result["evidence"] is None
    assert "test-authoring" in result["error"]
    assert not result["checks"][1]["assessment"]["accepted"]


@pytest.mark.parametrize("target", ["events", "evidence", "checks"])
def test_malformed_integrity_record_fails_closed(setup_engine, target):
    engine, store = setup_engine
    run = create_fixture(store)
    engine.execute(run["id"])
    value = store.get(run["id"])
    if target == "events":
        value["events"] = None
    elif target == "evidence":
        value["evidence"]["version"] = "invalid-version"
        # Even a recomputed manifest must not make an invalid record shape acceptable.
        from fixforge.store import digest
        value["evidence"]["manifest_sha256"] = digest({k: v for k, v in value["evidence"].items() if k != "manifest_sha256"})
    else:
        value.pop("checks")
    assert verify_record(value) is False


def test_harness_change_stops_verification_before_inference(setup_engine, monkeypatch):
    engine, store = setup_engine
    fingerprints = iter(["a" * 64, "a" * 64, "b" * 64])
    monkeypatch.setattr("fixforge.engine.harness_fingerprint", lambda: next(fingerprints))
    run = create_fixture(store)
    engine.execute(run["id"])
    result = store.get(run["id"])
    assert result["status"] == "failed" and result["evidence"] is None
    assert "Test harness changed" in result["error"]
    assert "provider_record" not in result
