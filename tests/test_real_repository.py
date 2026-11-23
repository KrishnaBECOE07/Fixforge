"""Real repository/snapshot/review path using project-owned fixture code.

Only tests replace Docker and inference with known fixture execution. The product's
AI runner still has no host fallback, and no provider credentials are used here.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import time
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from fixforge.api import create_app
from fixforge.config import GitHubTarget, Settings
from fixforge.fixtures import FIXTURES
from fixforge.handoff import prepare_handoff
from fixforge.sandbox import docker_available
from fixforge.sandbox import run_tests as trusted_test_runner
from fixforge.policy import REGRESSION_PATH
from fixforge.publisher import _push_branch, run_git
from fixforge.store import digest, verify_record


def git(root, *args):
    result = subprocess.run(["git", "-c", "core.longpaths=true", "-C", str(root), *args],
                            capture_output=True, check=False, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


@pytest.fixture
def pilot(tmp_path, monkeypatch, request):
    mode = getattr(request, "param", "openai")
    use_docker = mode == "docker"
    provider = "ollama" if mode.startswith("ollama") else "openai"
    supplied = mode.endswith("-supplied")
    fixture = FIXTURES["payment-zero"]
    root = tmp_path / "pilot"
    (root / "tests").mkdir(parents=True)
    (root / fixture.path).write_text(fixture.original)
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_existing.py").write_text(fixture.existing_test)
    if mode.startswith("git"):
        ending = "\r\n" if mode == "git-crlf" else "\n"
        (root / fixture.path).write_bytes(fixture.original.replace("\n", ending).encode())
        (root / "notes.txt").write_bytes(b"Existing non-Python file.\n")
        if mode == "git-ignored":
            (root / ".gitignore").write_bytes(b"ignored.py\n")
            (root / "ignored.py").write_bytes(b"present = True\n")
        git(root, "init", "--template=")
        git(root, "config", "core.autocrlf", "false")
        git(root, "add", "--all")
        git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@localhost",
            "-c", "commit.gpgSign=false", "commit", "-m", "Pilot baseline")
    settings = Settings(data_dir=tmp_path / "data", api_key="test-only" if provider == "openai" else "",
                        inference_provider=provider, repositories={"pilot": root})
    proposal = dict(rationale=fixture.rationale, plan=["Capture the zero-value contract", "Apply the guard"],
                    edits=[dict(path=fixture.path, content=fixture.replacement)], regression=fixture.regression)
    if supplied:
        proposal.pop("regression")
    requests = []

    def respond(request, timeout):
        payload = json.loads(request.data)
        assert ("regression" in payload["text"]["format"]["schema"]["required"]) is not supplied
        requests.append(payload["input"])
        response = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(proposal)},
        ]}]}
        return io.BytesIO(json.dumps(response).encode())

    def respond_locally(path, payload, timeout):
        if path == "/api/show":
            return {}
        assert path == "/api/chat"
        assert ("regression" in payload["format"]["required"]) is not supplied
        requests.append(payload["messages"][1]["content"])
        return {"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": json.dumps(proposal)}}

    if provider == "ollama":
        monkeypatch.setattr("fixforge.providers.ollama_request", respond_locally)
    else:
        monkeypatch.setattr("urllib.request.urlopen", respond)

    def fixed_runner(workspace, trusted_demo, image, label):
        assert trusted_demo is False  # The engine selected the required non-demo boundary.
        assert workspace.is_relative_to(settings.data_dir / "workspaces")
        assert image == "sha256:" + "a" * 64
        return trusted_test_runner(workspace, True, image, label)

    if use_docker:
        assert docker_available(), "Docker integration needs a running Linux engine"
    else:
        monkeypatch.setattr("fixforge.api.docker_available", lambda: True)
        monkeypatch.setattr("fixforge.engine.resolve_docker_image", lambda _: ("sha256:" + "a" * 64, "amd64"))
        monkeypatch.setattr("fixforge.engine.run_tests", fixed_runner)
    with TestClient(create_app(settings)) as client:
        issue = {"repository_id": "pilot", "title": fixture.title, "body": fixture.body}
        regression = fixture.regression.rstrip("\n")
        if supplied:
            issue["supplied_regression"] = regression.replace("\n", "\r\n")
        preview = client.post("/api/source-preview", json=issue)
        assert preview.status_code == 200
        assert preview.headers["cache-control"] == "no-store"
        assert not requests
        disclosure = preview.json()
        if supplied:
            assert disclosure["input"]["supplied_regression"] == regression
            changed = client.post("/api/runs", json={**issue, "provider": provider,
                                  "supplied_regression": regression + "\n# Changed after review",
                                  "source_review_sha256": disclosure["sha256"]})
            assert changed.status_code == 409
            assert "changed since review" in changed.json()["detail"]
            assert client.get("/api/runs").json() == []
            assert not requests
        response = client.post("/api/runs", json={**issue, "provider": provider,
                                                 "source_review_sha256": disclosure["sha256"]})
        assert response.status_code == 202
        run_id = response.json()["id"]
        deadline = time.monotonic() + (150 if use_docker else 20)
        while time.monotonic() < deadline:
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(.05)
        assert run["status"] == "review", run
        assert (root / fixture.path).read_text() == fixture.original
        assert len(requests) == 1
        assert json.loads(requests[0]) == disclosure["input"]
        assert run["provider_record"]["disclosure"] == {
            "sha256": disclosure["sha256"],
            "paths": [file["path"] for file in disclosure["input"]["untrusted_repository"]],
        }
        assert run["integrity_valid"]
        yield client, root, run, settings


@pytest.mark.skipif(os.getenv("FIXFORGE_TEST_DOCKER") != "1", reason="requires a pre-pulled image and Linux Docker")
@pytest.mark.parametrize("pilot", ["docker"], indirect=True)
def test_docker_runs_all_four_gates_and_exports_runtime_evidence(pilot):
    client, _, run, _ = pilot
    assert len(run["checks"]) == 4
    assert all(check["runner"] == "Docker / network disabled" and check["assessment"]["accepted"]
               for check in run["checks"])
    assert run["execution_record"]["image_id"].startswith("sha256:")
    assert run["integrity_valid"]
    exported = client.get(f"/api/runs/{run['id']}/export/evidence").json()
    assert exported["evidence"]["execution_record_sha256"] == digest(exported["execution_record"])
    approved = client.post(f"/api/runs/{run['id']}/review",
                           json={"decision": "approve", "patch_sha256": run["evidence"]["patch_sha256"]})
    assert approved.status_code == 200


@pytest.mark.parametrize("pilot", ["ollama"], indirect=True)
def test_ollama_run_without_openai_key(pilot):
    client, _, run, settings = pilot
    assert not settings.api_key
    assert client.get("/api/config").json()["ai_provider"] == run["provider"] == "ollama"
    assert run["evidence"]["provider"] == settings.ollama_model
    assert all(check["assessment"]["accepted"] for check in run["checks"])
    assert client.get("/api/metrics").json()["ai_runs"] == 1


@pytest.mark.parametrize("pilot", ["ollama-supplied", "openai-supplied"], indirect=True)
def test_supplied_regression_is_preserved_through_verification_and_export(pilot):
    client, root, run, settings = pilot
    assert len(run["checks"]) == 4
    assert all(check["assessment"]["accepted"] for check in run["checks"])
    regression = run["supplied_regression"]
    workspace = settings.data_dir / "workspaces" / run["id"]
    for snapshot in ("original", "patched", "rollback"):
        assert (workspace / snapshot / REGRESSION_PATH).read_text() == regression
    assert not (root / REGRESSION_PATH).exists()
    exported = client.get(f"/api/runs/{run['id']}/export/patch").text
    assert exported.endswith("\\ No newline at end of file\n")
    review = client.get(f"/api/runs/{run['id']}/export/review").text
    assert "Regression test: Operator-supplied" in review
    assert not verify_record({**run, "supplied_regression": regression + "\n"})


def test_real_repository_approval_binds_source_and_manifest(pilot):
    client, _, run, _ = pilot
    result = client.post(f"/api/runs/{run['id']}/review", json={"decision": "approve", "patch_sha256": run["evidence"]["patch_sha256"]})
    assert result.status_code == 200
    assert result.json()["decision"]["source_identity_sha256"] == run["source_revision"]["identity_sha256"]
    assert result.json()["decision"]["evidence_manifest_sha256"] == run["evidence"]["manifest_sha256"]


def approve(client, run):
    response = client.post(f"/api/runs/{run['id']}/review",
                           json={"decision": "approve", "patch_sha256": run["evidence"]["patch_sha256"]})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("pilot", ["git", "git-crlf"], indirect=True)
def test_git_handoff_is_revision_pinned_importable_and_repeatable(pilot, tmp_path):
    client, root, run, settings = pilot
    with pytest.raises(ValueError, match="Approve a verified"):
        prepare_handoff(settings, run)
    run = approve(client, run)
    before = git(root, "show-ref")
    path, receipt = prepare_handoff(settings, run)
    first = path.read_bytes()
    assert prepare_handoff(settings, run) == (path, receipt)
    assert path.read_bytes() == first
    assert git(root, "show-ref") == before and not git(root, "status", "--porcelain")

    bundle = tmp_path / "repair.bundle"
    with ZipFile(path) as archive:
        assert json.loads(archive.read("handoff.json")) == receipt
        assert verify_record(json.loads(archive.read("evidence.json")))
        assert archive.read("review.md").startswith(b"# Fix: ")
        assert archive.read("repair.patch").decode() == "".join(change["diff"] for change in run["files"])
        bundle.write_bytes(archive.read("repair.bundle"))
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == receipt["bundle_sha256"]
    assert receipt["base_commit"] == run["source_revision"]["commit"]
    assert receipt["patch_sha256"] == run["evidence"]["patch_sha256"]

    receiver = tmp_path / "receiver.git"
    git(tmp_path, "init", "--bare", "--template=", str(receiver))
    shutil.copytree(root / ".git" / "objects", receiver / "objects", dirs_exist_ok=True)
    ref = f"refs/heads/{receipt['branch']}"
    git(receiver, "bundle", "verify", str(bundle))
    head = receipt["prepared_commit"]
    assert git(receiver, "bundle", "unbundle", str(bundle)).decode().split() == [head, ref]
    git(receiver, "update-ref", ref, head)
    assert git(receiver, "rev-list", "--parents", "-n", "1", ref).decode().split() == [head, receipt["base_commit"]]
    production, regression = run["files"]
    base_blob = git(receiver, "show", f"{receipt['base_commit']}:{production['path']}")
    ending = "\r\n" if b"\r\n" in base_blob else "\n"
    assert git(receiver, "show", f"{head}:{production['path']}") == production["after"].replace("\n", ending).encode()
    assert git(receiver, "show", f"{head}:{REGRESSION_PATH}") == regression["after"].encode()
    assert git(receiver, "show", f"{head}:notes.txt") == b"Existing non-Python file.\n"


@pytest.mark.parametrize("pilot", ["git"], indirect=True)
def test_handoff_rejects_mismatched_approval_and_stale_source(pilot):
    client, root, run, settings = pilot
    approved = approve(client, run)
    decision = {**approved["decision"], "evidence_manifest_sha256": "0" * 64}
    with pytest.raises(ValueError, match="Approval does not match"):
        prepare_handoff(settings, {**approved, "decision": decision})
    (root / "payments.py").write_bytes(b"# Changed after approval\n")
    with pytest.raises(ValueError, match="Repository changed since verification"):
        prepare_handoff(settings, approved)
    assert not (settings.data_dir / "handoffs").exists()


@pytest.mark.parametrize("pilot", ["git-ignored"], indirect=True)
def test_handoff_rejects_ignored_python_missing_from_base_commit(pilot):
    client, root, run, settings = pilot
    assert not git(root, "status", "--porcelain")
    approved = approve(client, run)
    with pytest.raises(ValueError, match="exactly the Python files verified"):
        prepare_handoff(settings, approved)
    assert not list((settings.data_dir / "handoffs").glob("*.zip"))


@pytest.mark.parametrize("pilot", ["git"], indirect=True)
def test_git_publisher_imports_the_approved_commit_and_only_creates_a_branch(pilot, monkeypatch):
    client, root, run, settings = pilot
    package, receipt = prepare_handoff(settings, approve(client, run))
    remote = GitHubTarget("owner/project", "main")
    pushes = []
    before = git(root, "show-ref")

    def inspect_push(work, *args, env, **kwargs):
        if args[0] != "push":
            return run_git(work, *args, env=env, **kwargs)
        ref = f"refs/heads/{receipt['branch']}"
        head = receipt["prepared_commit"]
        assert git(work, "rev-list", "--parents", "-n", "1", head).decode().split() == [head, receipt["base_commit"]]
        assert args == ("push", f"--force-with-lease={ref}:", "--", "https://github.com/owner/project.git", f"{head}:{ref}")
        assert env["GIT_ALLOW_PROTOCOL"] == "https"
        assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/owner/project.git.extraHeader"
        assert env["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
        assert "test-only" not in " ".join(args)
        pushes.append(head)

    monkeypatch.setattr("fixforge.publisher.run_git", inspect_push)
    _push_branch(root, package, receipt, remote, "test-only")
    assert pushes == [receipt["prepared_commit"]]
    assert git(root, "show-ref") == before and not git(root, "status", "--porcelain")


@pytest.mark.parametrize("change", ["source", "new_file", "removed_file", "unregistered"])
def test_changed_repository_cannot_be_approved(pilot, change):
    client, root, run, settings = pilot
    if change == "source":
        (root / "payments.py").write_text("# changed after verification\n")
    elif change == "new_file":
        (root / "added.py").write_text("value = 1\n")
    elif change == "removed_file":
        (root / "payments.py").unlink()
    else:
        settings.repositories.pop("pilot")
    response = client.post(f"/api/runs/{run['id']}/review", json={"decision": "approve", "patch_sha256": run["evidence"]["patch_sha256"]})
    assert response.status_code == 409
    assert client.get(f"/api/runs/{run['id']}").json()["status"] == "review"


def test_stale_candidate_can_still_be_rejected(pilot):
    client, root, run, _ = pilot
    (root / "payments.py").write_text("# changed\n")
    response = client.post(f"/api/runs/{run['id']}/review", json={"decision": "reject", "patch_sha256": run["evidence"]["patch_sha256"]})
    assert response.status_code == 200 and response.json()["status"] == "rejected"


def test_real_source_approval_cannot_bypass_the_freshness_callback(pilot):
    client, _, run, _ = pilot
    with pytest.raises(ValueError, match="revalidated"):
        client.app.state.store.decide(run["id"], "approve", run["evidence"]["patch_sha256"], "")
