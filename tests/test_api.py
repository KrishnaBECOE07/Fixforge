import time

import pytest
from fastapi.testclient import TestClient

from fixforge.api import create_app
from fixforge.config import GitHubTarget, Settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        yield client


def test_api_full_review_and_export(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/fixtures").json()) == 3
    response = client.post("/api/runs", json={"provider": "demo", "fixture_id": "payment-zero"})
    assert response.status_code == 202
    run_id = response.json()["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in {"queued", "running"}:
            break
        time.sleep(.05)
    assert run["status"] == "review", run
    assert run["integrity_valid"]
    for kind in ("patch", "review", "evidence"):
        exported = client.get(f"/api/runs/{run_id}/export/{kind}")
        assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
    patch = client.get(f"/api/runs/{run_id}/export/patch").text
    assert "+++ b/payments.py" in patch and "test_fixforge_regression.py" in patch
    response = client.post(f"/api/runs/{run_id}/review", json={"decision": "approve", "patch_sha256": run["evidence"]["patch_sha256"]})
    assert response.status_code == 200 and response.json()["status"] == "approved"
    assert client.get("/api/metrics").json()["approved"] == 1


def test_api_rejects_unconfigured_ai_and_unknown_fixture(client):
    assert client.post("/api/runs", json={"provider": "openai"}).status_code == 409
    assert client.post("/api/runs", json={"fixture_id": "nonexistent"}).status_code == 422
    assert client.get("/api/runs/not-found").status_code == 404
    assert client.get("/api/config").json()["ai_configured"] is False
    assert "api_key" not in client.get("/api/config").text


def test_cross_site_writes_and_dns_rebinding_are_rejected(client):
    assert client.post("/api/runs", json={}, headers={"origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/runs", content="{}", headers={"content-type": "text/plain"}).status_code == 415
    assert client.get("/api/health", headers={"host": "attacker.example"}).status_code == 403


def test_unverified_run_cannot_export_or_approve(client):
    store = client.app.state.store
    run = store.create(provider="demo", repo="test", title="not ready", body="test", number=None)
    assert client.get(f"/api/runs/{run['id']}/export/evidence").status_code == 409
    assert client.post(f"/api/runs/{run['id']}/review", json={"decision": "approve", "patch_sha256": "a" * 64}).status_code == 409


@pytest.fixture
def preview_repository(tmp_path):
    source = tmp_path / "checkout"
    source.mkdir()
    (source / "app.py").write_text("value = 1\n")
    (source / ".env").write_text("PRIVATE_VALUE=not-in-preview\n")
    issue = {"repository_id": "pilot", "title": "Fix boundary", "body": "Exact values should stay unchanged."}
    return source, issue


@pytest.mark.parametrize("location", ["issue", "source"])
def test_source_preview_blocks_suspected_credentials_without_echoing_them(tmp_path, preview_repository, location):
    source, issue = preview_repository
    credential = "api_key = 'synthetic-credential-1234'"
    if location == "issue":
        issue["body"] = credential
    else:
        (source / "app.py").write_text(credential)
    settings = Settings(data_dir=tmp_path / "data", repositories={"pilot": source})
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/source-preview", json=issue)
        assert response.status_code == 422
        assert "Potential credential" in response.json()["detail"]
        assert "synthetic-credential-1234" not in response.text
        assert client.get("/api/runs").json() == []


@pytest.mark.parametrize("changed", ["source", "issue", "github_issue"])
def test_unreviewed_and_stale_source_cannot_be_queued(tmp_path, monkeypatch, preview_repository, changed):
    source, issue = preview_repository
    monkeypatch.setattr("fixforge.api.docker_available", lambda: True)
    github = {"title": issue["title"], "body": issue["body"], "repo": "a / b", "number": 1}
    if changed == "github_issue":
        issue["issue_url"] = "https://github.com/a/b/issues/1"
        monkeypatch.setattr("fixforge.api.read_github_issue", lambda url, token, **options: {**github, "issue_url": url})
    settings = Settings(data_dir=tmp_path / "data", api_key="test-only", repositories={"pilot": source})
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/source-preview", json=issue)
        assert response.status_code == 200
        preview = response.json()
        assert preview["input"]["untrusted_repository"] == [{"path": "app.py", "source": "value = 1\n"}]
        assert preview["issue_url"] == issue.get("issue_url")
        run = {**issue, "provider": "openai"}
        assert client.post("/api/runs", json=run).status_code == 409
        if changed == "source":
            (source / "app.py").write_text("value = 2\n")
        elif changed == "github_issue":
            github["body"] = "Changed on GitHub."
        else:
            run["body"] = "Changed locally."
        response = client.post("/api/runs", json={**run, "source_review_sha256": preview["sha256"]})
        assert response.status_code == 409
        assert "changed since review" in response.json()["detail"]
        assert client.get("/api/runs").json() == []


def test_github_issue_must_match_the_configured_checkout(tmp_path, monkeypatch, preview_repository):
    source, issue = preview_repository
    issue["issue_url"] = "https://github.com/another/repository/issues/1"
    settings = Settings(data_dir=tmp_path / "data", api_key="test-only", repositories={"pilot": source},
                        github_targets={"pilot": GitHubTarget("owner/pilot", "main")})
    monkeypatch.setattr("fixforge.providers.http.client.HTTPSConnection",
                        lambda *_args, **_kwargs: pytest.fail("Mismatched issue reached GitHub"))
    monkeypatch.setattr("fixforge.api.capture_source", lambda *_: pytest.fail("Mismatched issue reached the checkout"))
    with TestClient(create_app(settings)) as client:
        responses = [client.post("/api/source-preview", json=issue),
                     client.post("/api/runs", json={**issue, "provider": "openai", "source_review_sha256": "a" * 64})]
        assert all(response.status_code == 422 and "owner/pilot" in response.json()["detail"] for response in responses)
        assert client.get("/api/runs").json() == []


def test_worker_rejects_drift_after_queueing_before_docker_or_inference(tmp_path, monkeypatch, preview_repository):
    source, issue = preview_repository
    monkeypatch.setattr("fixforge.api.docker_available", lambda: True)
    monkeypatch.setattr("fixforge.engine.resolve_docker_image", lambda _: pytest.fail("Worker reached Docker"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("Worker reached inference"))
    settings = Settings(data_dir=tmp_path / "data", api_key="test-only", repositories={"pilot": source})
    app = create_app(settings)
    execute = app.state.engine.execute

    def execute_after_change(run_id):
        (source / "app.py").write_text("value = 2\n")
        execute(run_id)

    monkeypatch.setattr(app.state.engine, "execute", execute_after_change)
    with TestClient(app) as client:
        preview = client.post("/api/source-preview", json=issue).json()
        response = client.post("/api/runs", json={**issue, "provider": "openai",
                                                "source_review_sha256": preview["sha256"]})
        assert response.status_code == 202
        run_id = response.json()["id"]
    run = app.state.store.get(run_id)
    assert run["status"] == "failed" and "changed since review" in run["error"]
    assert run["checks"] == []


def test_source_review_cannot_move_from_local_ollama_to_openai(tmp_path, monkeypatch, preview_repository):
    source, issue = preview_repository
    monkeypatch.setattr("fixforge.api.docker_available", lambda: True)
    settings = Settings(data_dir=tmp_path / "data", api_key="test-only", model="same-model",
                        ollama_model="same-model", repositories={"pilot": source}, inference_provider="ollama")
    with TestClient(create_app(settings)) as client:
        preview = client.post("/api/source-preview", json=issue).json()
        assert preview["provider"] == "ollama"
        response = client.post("/api/runs", json={**issue, "provider": "openai",
                                                "source_review_sha256": preview["sha256"]})
        assert response.status_code == 409
        assert "changed since review" in response.json()["detail"]
        assert client.get("/api/runs").json() == []


@pytest.mark.parametrize("regression, error", [
    ("class Unfinished(", "invalid Python syntax"),
    ('api_key = "example-credential"\n', "Potential credential"),
])
def test_supplied_regression_requires_valid_source_review(tmp_path, preview_repository, regression, error):
    source, issue = preview_repository
    settings = Settings(data_dir=tmp_path / "data", repositories={"pilot": source}, inference_provider="ollama")
    with TestClient(create_app(settings)) as client:
        preview = client.post("/api/source-preview", json={**issue, "supplied_regression": regression})
        assert preview.status_code == 422
        assert error in preview.json()["detail"]
        assert "example-credential" not in preview.text


def test_missing_ollama_model_is_reported_before_queueing(tmp_path, monkeypatch, preview_repository):
    source, issue = preview_repository
    monkeypatch.setattr("fixforge.api.docker_available", lambda: True)

    def no_model(model):
        raise ValueError("The configured Ollama model is missing.")

    monkeypatch.setattr("fixforge.api.check_ollama_model", no_model)
    settings = Settings(data_dir=tmp_path / "data", repositories={"pilot": source}, inference_provider="ollama")
    with TestClient(create_app(settings)) as client:
        preview = client.post("/api/source-preview", json=issue).json()
        response = client.post("/api/runs", json={**issue, "provider": "ollama",
                                                "source_review_sha256": preview["sha256"]})
        assert response.status_code == 409
        assert "Ollama model is missing" in response.json()["detail"]
        assert client.get("/api/runs").json() == []
