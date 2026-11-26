import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from fixforge.config import GitHubTarget, Settings
from fixforge.publisher import publish_repair


BASE = "a" * 40
HEAD = "b" * 40
REPO = "owner/project"
BRANCH = "codex/fixforge-123456789abc"
RECEIPT = dict(run_id="123456789abc", base_commit=BASE, prepared_commit=HEAD, branch=BRANCH,
               evidence_manifest_sha256="c" * 64, patch_sha256="d" * 64)


@pytest.fixture
def publication(tmp_path, monkeypatch):
    run = dict(repository_id="pilot", repo="owner / project", number=5,
               issue_url=f"https://github.com/{REPO}/issues/5", body="Private issue text")
    settings = Settings(data_dir=tmp_path, repositories={"pilot": tmp_path},
                        github_targets={"pilot": GitHubTarget(REPO, "main")}, github_publish_token="test-only")
    calls = []
    refs = {"main": BASE}
    pulls = []
    state = {}

    class Response(io.BytesIO):
        def __init__(self, status, data):
            super().__init__(json.dumps(data).encode())
            self.status = status

    class Connection:
        def __init__(self, host, *, timeout):
            assert host == "api.github.com" and timeout == 15

        def request(self, method, path, *, body, headers):
            assert headers["Authorization"] == "Bearer test-only"
            assert path.startswith(f"/repos/{REPO}/")
            url = urlsplit(path.removeprefix(f"/repos/{REPO}"))
            calls.append((method, url.path))
            if method == "GET" and url.path.startswith("/git/ref/heads/"):
                branch = url.path.removeprefix("/git/ref/heads/")
                if branch == BRANCH and branch in refs and state.get("hidden_reads", 0):
                    state["hidden_reads"] -= 1
                    self.response = Response(404, {})
                    return
                self.response = (Response(200, {"ref": f"refs/heads/{branch}",
                                               "object": {"type": "commit", "sha": refs[branch]}})
                                 if branch in refs else Response(404, {}))
            elif method == "GET":
                assert url.path == "/pulls"
                assert parse_qs(url.query) == {"head": [f"owner:{BRANCH}"], "state": ["all"], "per_page": ["2"]}
                self.response = Response(200, pulls)
            else:
                assert method == "POST" and url.path == "/pulls"
                payload = json.loads(body)
                assert payload["base"] == "main" and payload["head"] == BRANCH and payload["draft"] is True
                assert "Private issue text" not in payload["body"]
                if state.get("omit_issue"):
                    assert "Related issue #" not in payload["body"]
                else:
                    assert "Related issue #5." in payload["body"]
                if state.get("draft_denied"):
                    self.response = Response(403, {"message": "Resource not accessible by personal access token"})
                    return
                pull = dict(number=9, state="open", draft=True, body=payload["body"],
                            base=dict(ref="main", sha=state.get("created_base", BASE), repo={"full_name": REPO}),
                            head=dict(ref=BRANCH, sha=HEAD, repo={"full_name": REPO}))
                pulls.append(pull)
                self.response = Response(422, {}) if state.get("creation_race") else Response(201, pull)

        def getresponse(self):
            return self.response

        def close(self):
            pass

    def push(*args):
        calls.append(("PUSH", BRANCH))
        refs[BRANCH] = HEAD
        if state.get("branch_race"):
            raise ValueError("Git push did not confirm creation")
        if state.get("base_moves"):
            refs["main"] = "f" * 40

    monkeypatch.setattr("fixforge.publisher.http.client.HTTPSConnection", Connection)
    monkeypatch.setattr("fixforge.publisher.prepare_handoff", lambda *_: (tmp_path / "handoff.zip", RECEIPT))
    monkeypatch.setattr("fixforge.publisher.assert_source_current", lambda *_: None)
    monkeypatch.setattr("fixforge.publisher._push_branch", push)
    monkeypatch.setattr("fixforge.publisher.sleep", lambda _: None)
    return settings, run, refs, pulls, calls, state


def test_draft_publication_and_retry_reuse_the_same_pr(publication):
    settings, run, refs, pulls, calls, _ = publication
    initial = publish_repair(settings, run)
    assert initial == dict(url=f"https://github.com/{REPO}/pull/9", number=9, state="open", draft=True, reused=False)
    assert publish_repair(settings, run) == {**initial, "reused": True}
    pulls[0].update(state="closed")
    assert publish_repair(settings, run) == {**initial, "state": "closed", "reused": True}
    assert refs == {"main": BASE, BRANCH: HEAD}
    assert calls.count(("PUSH", BRANCH)) == calls.count(("POST", "/pulls")) == 1


def test_publication_omits_issue_url_if_it_conflicts_with_the_verified_issue(publication):
    settings, run, _, _, _, state = publication
    run["issue_url"] = f"https://github.com/{REPO}/issues/6"
    state["omit_issue"] = True
    assert publish_repair(settings, run)["draft"] is True


@pytest.mark.parametrize("condition, expected_pushes", [
    ("already_stale", 0), ("base_moves", 1), ("branch_conflict", 0),
])
def test_publication_stops_when_refs_do_not_match(publication, condition, expected_pushes):
    settings, run, refs, pulls, calls, state = publication
    if condition == "already_stale":
        refs["main"] = "f" * 40
    elif condition == "branch_conflict":
        refs[BRANCH] = "f" * 40
    else:
        state[condition] = True
    with pytest.raises(ValueError, match="base|approved commit"):
        publish_repair(settings, run)
    assert calls.count(("PUSH", BRANCH)) == expected_pushes
    assert not pulls and ("POST", "/pulls") not in calls


def test_retry_handles_concurrent_branch_and_draft_creation(publication):
    settings, run, _, pulls, calls, state = publication
    state.update(branch_race=True, creation_race=True)
    assert publish_repair(settings, run)["reused"] is True
    assert len(pulls) == 1 and calls.count(("POST", "/pulls")) == 1


@pytest.mark.parametrize("branch_race", [False, True])
def test_draft_waits_for_pushed_branch_to_appear(publication, branch_race):
    settings, run, _, pulls, calls, state = publication
    state.update(hidden_reads=2, branch_race=branch_race)
    assert publish_repair(settings, run)["draft"] is True
    assert len(pulls) == 1 and calls.count(("PUSH", BRANCH)) == 1
    assert calls.count(("GET", f"/git/ref/heads/{BRANCH}")) == 4


def test_retry_reuses_the_pushed_branch_after_visibility_timeout(publication):
    settings, run, _, pulls, calls, state = publication
    state["hidden_reads"] = 4
    with pytest.raises(ValueError, match="has not confirmed the repair branch yet"):
        publish_repair(settings, run)
    assert not pulls
    assert publish_repair(settings, run)["draft"] is True
    assert calls.count(("PUSH", BRANCH)) == calls.count(("POST", "/pulls")) == 1


def test_draft_permission_error_identifies_the_required_access(publication):
    settings, run, refs, pulls, _, state = publication
    state["draft_denied"] = True
    with pytest.raises(ValueError, match="read and write access to Pull requests"):
        publish_repair(settings, run)
    assert refs[BRANCH] == HEAD and not pulls


def test_moved_base_in_creation_response_never_reports_success(publication):
    settings, run, _, pulls, calls, state = publication
    state["created_base"] = "f" * 40
    for _ in range(2):
        with pytest.raises(ValueError, match="pull request base changed"):
            publish_repair(settings, run)
    assert len(pulls) == 1 and calls.count(("POST", "/pulls")) == 1


@pytest.mark.parametrize("repo, branch", [("https://github.com/owner/repo", "main"), ("owner/repo", "foo//bar"),
                                         ("owner/repo", "refs/../main"), ("owner/.git", "main")])
def test_publication_target_rejects_urls_and_invalid_branches(repo, branch):
    with pytest.raises(ValueError, match="GitHub target"):
        GitHubTarget(repo, branch)
