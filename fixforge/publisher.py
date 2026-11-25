"""Publish an approved Git handoff to an explicitly configured GitHub target."""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import re
from pathlib import Path
from urllib.parse import quote, urlencode
from zipfile import BadZipFile, ZipFile

from .config import GitHubTarget, Settings
from .git_transport import git_environment, isolated_repository, run_git
from .handoff import approved_base, prepare_handoff, repair_branch
from .provenance import assert_source_current
from .store import digest


class GitHubAPI:
    def __init__(self, target: GitHubTarget, token: str):
        self.target = target
        self.token = token

    def _request(self, method: str, path: str, data: dict | None = None, *, missing_ok: bool = False):
        connection = http.client.HTTPSConnection("api.github.com", timeout=15)
        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}",
                   "User-Agent": "FixForge", "X-GitHub-Api-Version": "2026-03-10"}
        try:
            if data is not None:
                headers["Content-Type"] = "application/json"
            connection.request(method, f"/repos/{self.target.repo}{path}",
                               body=json.dumps(data).encode() if data is not None else None, headers=headers)
            with connection.getresponse() as response:
                if response.status == 404 and missing_ok:
                    return None
                if response.status != (201 if method == "POST" else 200):
                    raise ValueError(f"GitHub {method} returned HTTP {response.status}. "
                                     "Check the configured repository and publication permissions.")
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ValueError("GitHub returned an oversized publication response")
                return json.loads(raw)
        except (json.JSONDecodeError, UnicodeError):
            raise ValueError("GitHub returned invalid publication data") from None
        except (OSError, http.client.HTTPException):
            raise ValueError("GitHub did not confirm the request. Retry publication to check its status.") from None
        finally:
            connection.close()

    def branch_sha(self, branch: str) -> str | None:
        ref = f"refs/heads/{branch}"
        result = self._request("GET", f"/git/ref/heads/{quote(branch, safe='/')}", missing_ok=True)
        if result is None:
            return None
        if not isinstance(result, dict) or result.get("ref") != ref:
            raise ValueError("GitHub did not return the exact requested branch")
        obj = result.get("object")
        sha = obj.get("sha") if isinstance(obj, dict) and obj.get("type") == "commit" else None
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("GitHub returned an invalid branch commit")
        return sha

    def existing_pull(self, branch: str) -> dict | None:
        owner = self.target.repo.split("/")[0]
        query = urlencode({"state": "all", "head": f"{owner}:{branch}", "per_page": 2})
        pulls = self._request("GET", f"/pulls?{query}")
        if not isinstance(pulls, list) or len(pulls) > 1 or any(not isinstance(pull, dict) for pull in pulls):
            raise ValueError("GitHub did not identify a unique pull request for the repair branch")
        return pulls[0] if pulls else None

    def open_draft(self, branch: str, title: str, body: str) -> dict:
        return self._request("POST", "/pulls", dict(head=branch, base=self.target.base, draft=True,
                                                     title=title, body=body))


def _publication_target(settings: Settings, run: dict) -> GitHubTarget:
    target = (settings.github_targets or {}).get(run.get("repository_id"))
    if target is None:
        raise ValueError("Configure a GitHub publication target for this registered repository")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", settings.github_publish_token):
        raise ValueError("Set a valid FIXFORGE_GITHUB_PUBLISH_TOKEN locally")
    return target


def preview_publication(settings: Settings, run: dict) -> dict:
    base_commit = approved_base(run)
    target = _publication_target(settings, run)
    branch = repair_branch(run["id"])
    if target.base == branch or len(base_commit) != 40:
        raise ValueError("GitHub publication requires a separate target branch and a SHA-1 Git base")
    evidence = run["evidence"]
    preview = dict(repo=target.repo, base=target.base, base_commit=base_commit, branch=branch,
                   patch_sha256=evidence["patch_sha256"], evidence_sha256=evidence["manifest_sha256"])
    return {**preview, "sha256": digest({**preview, "run_id": run["id"], "decision": run["decision"]})}


def publish_repair(settings: Settings, run: dict) -> dict:
    target = _publication_target(settings, run)
    token = settings.github_publish_token
    package, receipt = prepare_handoff(settings, run)
    branch, base, head = receipt["branch"], receipt["base_commit"], receipt["prepared_commit"]
    if target.base == branch or len(base) != 40:
        raise ValueError("GitHub publication requires a separate target branch and a SHA-1 Git base")
    repository = (settings.repositories or {})[run["repository_id"]]
    issue_url = run.get("issue_url") or ""
    linked_issue = re.fullmatch(rf"https://github\.com/{re.escape(target.repo)}/issues/([1-9][0-9]*)/?",
                                issue_url, re.IGNORECASE)
    marker = f"<!-- fixforge:{receipt['evidence_manifest_sha256']} -->"
    issue_line = f"\n\nRelated issue #{linked_issue[1]}." if linked_issue else ""
    body = (f"Verified and approved by the local FixForge workbench.\n\n"
            f"- Verified base `{base}`\n"
            f"- Prepared commit `{head}`\n"
            f"- Patch SHA-256 `{receipt['patch_sha256']}`\n"
            f"- Evidence manifest SHA-256 `{receipt['evidence_manifest_sha256']}`"
            f"{issue_line}\n\n{marker}")
    api = GitHubAPI(target, token)
    existing = api.existing_pull(branch)
    if existing is not None:
        return _publication(existing, target, receipt, marker, reused=True)
    if api.branch_sha(target.base) != base:
        raise ValueError("GitHub base has moved or is missing. Verify a new repair against the target branch.")

    remote_head = api.branch_sha(branch)
    if remote_head is None:
        assert_source_current(repository, run.get("source_revision"))
        try:
            _push_branch(repository, package, receipt, target, token)
        except ValueError:
            if api.branch_sha(branch) != head:
                raise
        remote_head = api.branch_sha(branch)
    if remote_head != head:
        raise ValueError("The GitHub repair branch does not point to the approved commit.")
    assert_source_current(repository, run.get("source_revision"))
    if api.branch_sha(target.base) != base:
        raise ValueError("GitHub base moved before draft creation. Verify a new repair against the updated base.")

    try:
        draft = api.open_draft(branch, f"FixForge repair {receipt['run_id']}", body)
    except ValueError:
        existing = api.existing_pull(branch)
        if existing is None:
            raise
        return _publication(existing, target, receipt, marker, reused=True)
    return _publication(draft, target, receipt, marker, reused=False)


def _publication(pull: dict, target: GitHubTarget, receipt: dict, marker: str, *, reused: bool) -> dict:
    try:
        number = pull["number"]
        head, base = pull["head"], pull["base"]
        body, state, draft = pull["body"], pull["state"], pull["draft"]
        base_sha = base["sha"]
        matches = (type(number) is int and number > 0 and isinstance(body, str) and marker in body
                   and state in {"open", "closed"} and type(draft) is bool
                   and head["repo"]["full_name"].lower() == base["repo"]["full_name"].lower() == target.repo.lower()
                   and head["ref"] == receipt["branch"] and head["sha"] == receipt["prepared_commit"]
                   and base["ref"] == target.base and (reused or (state == "open" and draft)))
    except (KeyError, TypeError, AttributeError):
        matches = False
    if not matches:
        raise ValueError("GitHub returned a pull request that does not match the approved repair. Check GitHub.")
    url = f"https://github.com/{target.repo}/pull/{number}"
    if base_sha != receipt["base_commit"]:
        raise ValueError(f"The pull request base changed at {url}. Verify a new repair before proceeding.")
    return dict(url=url, number=number, state=state, draft=draft, reused=reused)


def _push_branch(repository: Path, package: Path, receipt: dict, target: GitHubTarget, token: str) -> None:
    try:
        with ZipFile(package) as archive:
            bundle = archive.read("repair.bundle")
    except (BadZipFile, KeyError, OSError):
        raise ValueError("Could not read the approved Git bundle") from None
    if hashlib.sha256(bundle).hexdigest() != receipt["bundle_sha256"]:
        raise ValueError("The approved Git bundle failed its integrity check")

    env = git_environment()
    ref = f"refs/heads/{receipt['branch']}"
    head = receipt["prepared_commit"]
    url = f"https://github.com/{target.repo}.git"
    with isolated_repository(repository, "sha1", env) as isolated:
        bundle_path = isolated.parent / "repair.bundle"
        bundle_path.write_bytes(bundle)
        imported = run_git(isolated, "bundle", "unbundle", str(bundle_path), env=env).decode().split()
        if imported != [head, ref]:
            raise ValueError("The Git bundle does not match the approved branch")
        encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        # Scope the credential to the approved HTTPS URL and keep it out of command arguments.
        push_env = dict(env, GIT_ALLOW_PROTOCOL="https", GIT_CONFIG_COUNT="3",
                        GIT_CONFIG_KEY_0=f"http.{url}.extraHeader", GIT_CONFIG_VALUE_0=f"Authorization: Basic {encoded}",
                        GIT_CONFIG_KEY_1="http.followRedirects", GIT_CONFIG_VALUE_1="false",
                        GIT_CONFIG_KEY_2="http.sslVerify", GIT_CONFIG_VALUE_2="true")
        try:
            # An empty expected value only allows creation of a previously absent ref.
            run_git(isolated, "push", f"--force-with-lease={ref}:", "--", url, f"{head}:{ref}", env=push_env)
        except ValueError:
            raise ValueError("GitHub did not confirm creation of the new branch. Check token access and branch rules.") from None
