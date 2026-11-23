from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from .config import Settings
from .disclosure import prepare_disclosure, require_review
from .fixtures import FIXTURES
from .intelligence import index_repository, safe_path
from .policy import REGRESSION_PATH, validate_proposal
from .providers import propose
from .proposals import parse_proposal
from .provenance import assert_source_current, capture_source, source_revision
from .sandbox import harness_fingerprint, resolve_docker_image, run_tests
from .store import Store, digest, issue_payload, now
from .verification import assess_baseline, assess_patch, assess_replay, assess_reproduction


class Engine:
    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store

    def execute(self, run_id: str) -> None:
        started = time.monotonic()
        try:
            self._execute(run_id, started)
        except Exception as exc:
            if hasattr(exc, "provider_record"):
                self.store.update(run_id, provider_record=exc.provider_record)
            # Exception bodies from network clients may expose tokens. Provider adapters sanitize them.
            message = str(exc)[:1000] if isinstance(exc, (ValueError, SyntaxError)) else f"{type(exc).__name__}: execution failed; inspect local configuration"
            self.store.event(run_id, "failed", "Verification stopped", message, status="failed", error=message,
                             duration_ms=round((time.monotonic() - started) * 1000))

    def _execute(self, run_id: str, started: float) -> None:
        run = self.store.get(run_id)
        demo = run["provider"] == "demo"
        root = self.settings.data_dir / "workspaces" / run_id
        original, patched = root / "original", root / "patched"
        original.mkdir(parents=True)
        self.store.event(run_id, "index", "Mapping the repository",
                         "Building a bounded source snapshot and a Python AST symbol index.", status="running")
        if demo:
            fixture = FIXTURES[run["fixture_id"]]
            files = {fixture.path: fixture.original, "tests/__init__.py": "",
                     "tests/test_existing.py": fixture.existing_test}
            for relative, content in files.items():
                target = safe_path(original, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            revision = source_revision(files, dict(kind="trusted_fixture", commit=None, dirty=False,
                                                   git_status_sha256=None))
        else:
            repository = (self.settings.repositories or {}).get(run["repository_id"])
            if repository is None:
                raise ValueError("Repository is not in the server allowlist")
            files, revision = capture_source(repository, original)
        index = index_repository(files, run["title"] + " " + run["body"])
        disclosure = None
        if not demo:
            disclosure = prepare_disclosure(self.settings, run, files, index, revision)
            require_review(run.get("source_review_sha256"), disclosure)
        harness_sha = harness_fingerprint()
        if demo:
            execution = {"runner": "local Python", "python_version": sys.version.split()[0]}
            image_id = None
        else:
            image_id, architecture = resolve_docker_image(self.settings.image)
            execution = {"runner": "Docker", "image_id": image_id,
                         "image_reference": self.settings.image, "architecture": architecture}
        execution["harness_sha256"] = harness_sha

        def execute_check(workspace: Path, label: str) -> dict:
            if harness_fingerprint() != harness_sha:
                raise ValueError("Test harness changed during verification. Start a new repair.")
            check = run_tests(workspace, demo, image_id or "", label)
            if harness_fingerprint() != harness_sha:
                raise ValueError("Test harness changed during verification. Start a new repair.")
            return check

        source_sha = digest(files)
        self.store.event(run_id, "baseline", "Checking the starting point",
                         f"Indexed {len(files)} files. Running the existing unittest suite before making changes.",
                         index=index, source_sha256=source_sha, source_revision=revision,
                         execution_record=execution)
        baseline = execute_check(original, "Existing suite · original code")
        baseline["assessment"] = assess_baseline(baseline)
        self.store.update(run_id, checks=[baseline])
        if not baseline["assessment"]["accepted"]:
            raise ValueError(baseline["assessment"]["reason"])
        self.store.event(run_id, "plan", "Forming a bounded repair",
                         "Using a deterministic fixture recipe." if demo else
                         "Sending the reviewed issue text and Python source to the configured model.")
        raw_proposal = propose(self.settings, run, disclosure)
        if not isinstance(raw_proposal, dict):
            raise ValueError("Repair proposal must be an object")
        provider = raw_proposal.get("_provider", dict(model="deterministic fixture" if demo else disclosure["model"],
                                                     usage=dict(input_tokens=0, output_tokens=0, total_tokens=0) if demo else None,
                                                     attempts=0 if demo else 1, limits={}))
        self.store.update(run_id, provider_record=provider)
        proposal = parse_proposal({k: v for k, v in raw_proposal.items() if k != "_provider"})
        supplied = run.get("supplied_regression")
        if supplied is not None and proposal["regression"] != supplied:
            raise ValueError("The repair proposal changed the supplied regression.")
        changes = validate_proposal(original, files, proposal, REGRESSION_PATH)
        reproduction_detail = ("Running the supplied regression on the original code. A genuine failure is required."
                               if supplied is not None else
                               "Running the proposed regression on the original code. A genuine failure is required.")
        self.store.event(run_id, "reproduce", "Testing the failure hypothesis",
                         reproduction_detail,
                         files=changes, rationale=proposal["rationale"], plan=proposal.get("plan", []))
        regression = safe_path(original, REGRESSION_PATH)
        regression.parent.mkdir(parents=True, exist_ok=True)
        regression.write_text(proposal["regression"], encoding="utf-8")
        reproduction = execute_check(original, "New regression · original code")
        reproduction["assessment"] = assess_reproduction(baseline, reproduction)
        checks = [baseline, reproduction]
        self.store.update(run_id, checks=checks)
        if not reproduction["assessment"]["accepted"]:
            raise ValueError(reproduction["assessment"]["reason"])
        self.store.event(run_id, "patch", "Applying the candidate patch",
                         "The new test fails on the original. Applying production edits to an isolated copy.")
        shutil.copytree(original, patched)
        for change in changes:
            target = safe_path(patched, change["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change["after"], encoding="utf-8")
        self.store.event(run_id, "verify", "Checking the counterfactual",
                         "Running the identical tests against the patched source. Existing tests must remain intact.")
        verification = execute_check(patched, "Full suite · patched code")
        verification["assessment"] = assess_patch(reproduction, verification)
        checks.append(verification)
        self.store.update(run_id, checks=checks)
        if not verification["assessment"]["accepted"]:
            raise ValueError(verification["assessment"]["reason"])
        self.store.event(run_id, "verify", "Replaying the counterfactual",
                         "Restoring original production code in a third copy. The same regression failures must return.")
        rollback = root / "rollback"
        shutil.copytree(patched, rollback)
        for change in changes:
            if change["kind"] == "modified":
                safe_path(rollback, change["path"]).write_text(change["before"], encoding="utf-8")
        replay = execute_check(rollback, "Counterfactual replay · restored code")
        replay["assessment"] = assess_replay(baseline, reproduction, replay)
        checks.append(replay)
        self.store.update(run_id, checks=checks)
        if not replay["assessment"]["accepted"]:
            raise ValueError(replay["assessment"]["reason"])
        if not demo:
            assert_source_current(repository, revision)
        self.store.event(run_id, "evidence", "Sealing the verification record",
                         "Binding the source snapshot, exact patch, test output and event history with SHA-256 digests.")
        current = self.store.get(run_id)
        evidence = dict(version=3, generated_at=now(), source_sha256=source_sha,
                        patch_sha256=digest(changes), checks_sha256=digest(checks),
                        source_revision_sha256=digest(revision), provider_record_sha256=digest(provider),
                        execution_record_sha256=digest(execution),
                        issue_sha256=digest(issue_payload(current)),
                        explanation_sha256=digest({"rationale": proposal["rationale"], "plan": proposal["plan"]}),
                        event_head=current["events"][-1]["hash"],
                        execution_mode="trusted_demo" if demo else "docker",
                        provider=provider["model"],
                        contracts={"baseline_passed": True, "regression_failed_before": True,
                                   "full_suite_passed_after": True, "existing_tests_preserved": True,
                                   "test_identities_preserved": True, "failure_classification_passed": True,
                                   "counterfactual_replayed": True,
                                   "source_identity_captured": True,
                                   "patch_policy_passed": True, "human_review_required": True},
                        limitations=["Passing tests do not prove semantic correctness or security.",
                                     "Event hashes detect accidental changes; they are not externally signed attestations.",
                                     "Static policy checks are heuristic, not a security proof."])
        evidence["manifest_sha256"] = digest(evidence)
        self.store.event(run_id, "review", "Ready for human review",
                         "Verification contracts passed. Review the diff and evidence before recording a decision.",
                         status="review", evidence=evidence,
                         duration_ms=round((time.monotonic() - started) * 1000))


def review_markdown(run: dict) -> str:
    evidence = run.get("evidence") or {}
    revision = run.get("source_revision") or {}
    provider = run.get("provider_record") or {}
    execution = run.get("execution_record") or {}
    regression_author = ("Operator-supplied" if "supplied_regression" in run else
                         "Curated fixture" if run["provider"] == "demo" else "Model-generated")
    rows = "\n".join(f"| {c['label']} | {'PASS' if c['passed'] else 'FAIL (expected counterfactual)' if (c.get('assessment') or {}).get('accepted') else 'FAIL'} | "
                     f"{(c.get('report') or {}).get('tests', 'n/a')} | {c['duration_ms']} ms |" for c in run["checks"])
    return (f"# Fix: {run['title']}\n\nRepository: {run['repo']}\nRun: `{run['id']}`\n\n"
            f"## Root cause and change\n\n{run.get('rationale', 'Verification did not complete.')}\n\n"
            f"## Verification\n\nRegression test: {regression_author}\n\n"
            f"| Check | Result | Tests | Duration |\n|---|---|---|---|\n{rows}\n\n"
            f"## Evidence\n\nSource snapshot: `{evidence.get('source_sha256', 'unverified')}`\n\n"
            f"Git commit: `{revision.get('commit') or 'not available / curated fixture'}`\n\n"
            f"Source identity: `{revision.get('identity_sha256', 'legacy record')}`\n\n"
            f"Sandbox image ID: `{execution.get('image_id', 'not recorded / curated fixture')}`\n\n"
            f"Test harness: `{execution.get('harness_sha256', 'legacy record')}`\n\n"
            f"Patch: `{evidence.get('patch_sha256', 'unverified')}`\n\n"
            f"Manifest: `{evidence.get('manifest_sha256', 'unverified')}`\n\n"
            f"Mode: {run['provider']}\nDecision: {(run.get('decision') or {}).get('action', 'pending')}\n\n"
            f"Provider usage: `{provider.get('usage')}`\n\n"
            "## Review notes\n\nPassing tests do not prove correctness. Check issue scope and edge cases. "
            "This is a local review package; no branch was pushed and no pull request was opened.\n")
