"""Prepare a local Git bundle from an approved repair and its verified base."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from functools import partial
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .config import Settings
from .engine import review_markdown
from .git_transport import git_environment, isolated_repository, run_git
from .intelligence import EXCLUDED, safe_path
from .policy import REGRESSION_PATH
from .provenance import capture_source
from .store import digest, verify_record


def approved_base(run: dict) -> str:
    run_id = run["id"]
    if not re.fullmatch(r"[0-9a-f]{12}", run_id):
        raise ValueError("Invalid repair ID")
    if run["provider"] not in {"ollama", "openai"} or run["status"] != "approved" or not run.get("evidence"):
        raise ValueError("Approve a verified repository repair before preparing a Git handoff")
    if not verify_record(run):
        raise ValueError("The repair evidence failed its integrity check")

    revision, evidence = run.get("source_revision") or {}, run["evidence"]
    decision = run.get("decision") or {}
    decision_fields = dict(action="approve", patch_sha256=evidence["patch_sha256"],
                           source_identity_sha256=revision.get("identity_sha256"),
                           evidence_manifest_sha256=evidence["manifest_sha256"])
    if any(decision.get(key) != value for key, value in decision_fields.items()):
        raise ValueError("Approval does not match the patch, evidence, and verified source")

    base = revision.get("commit")
    if revision.get("kind") != "git" or revision.get("dirty") is not False or not (
        isinstance(base, str) and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", base)
    ):
        raise ValueError("Prepare the repair from a clean Git checkout with a base commit")
    return base


def repair_branch(run_id: str) -> str:
    return f"codex/fixforge-{run_id}"


def prepare_handoff(settings: Settings, run: dict) -> tuple[Path, dict]:
    base = approved_base(run)
    run_id = run["id"]
    revision = run["source_revision"]
    evidence = run["evidence"]
    decision = run["decision"]
    repository = (settings.repositories or {}).get(run.get("repository_id"))
    if repository is None:
        raise ValueError("The repair repository is no longer registered")

    try:
        approved_at = datetime.fromisoformat(decision.get("at", ""))
    except (TypeError, ValueError):
        raise ValueError("Approval timestamp is missing or invalid") from None
    if approved_at.utcoffset() is None:
        raise ValueError("Approval timestamp must include a timezone")
    git_date = f"{int(approved_at.timestamp())} +0000"
    env = git_environment()
    env.update(GIT_AUTHOR_NAME="FixForge", GIT_AUTHOR_EMAIL="fixforge@localhost", GIT_AUTHOR_DATE=git_date,
               GIT_COMMITTER_NAME="FixForge", GIT_COMMITTER_EMAIL="fixforge@localhost", GIT_COMMITTER_DATE=git_date)
    git = partial(run_git, env=env)

    top_level = Path(os.fsdecode(git(repository, "rev-parse", "--show-toplevel").rstrip(b"\r\n")))
    if top_level.resolve() != repository.resolve():
        raise ValueError("Register the Git repository root before preparing a handoff")
    files, current = capture_source(repository)
    if current["identity_sha256"] != revision["identity_sha256"]:
        raise ValueError("Repository changed since verification. Start a new repair from the intended base.")
    object_format = "sha1" if len(base) == 40 else "sha256"
    output = settings.data_dir / "handoffs"
    branch = repair_branch(run_id)
    ref = f"refs/heads/{branch}"
    destination = output / f"fixforge-{run_id}.zip"
    with isolated_repository(repository, object_format, env) as isolated:
        tree = git(isolated, "ls-tree", "-rz", "--full-tree", base)
        tracked: dict[str, tuple[bytes, bytes]] = {}
        for entry in tree.split(b"\0")[:-1]:
            metadata, name = entry.split(b"\t", 1)
            mode, _, object_id = metadata.split()
            path = os.fsdecode(name)
            parts = path.split("/")
            if path.endswith(".py") and not any(part.startswith(".") or part in EXCLUDED for part in parts):
                tracked[path] = mode, object_id
        if tracked.keys() != files.keys():
            raise ValueError("The base commit does not contain exactly the Python files verified in the repair")
        endings = {path: _verified_endings(text, *tracked[path], object_format) for path, text in files.items()}

        git(isolated, "read-tree", base)
        staged = []
        expected_paths = set()
        for change in run["files"]:
            path = change["path"]
            safe_path(isolated, path)
            if path in expected_paths:
                raise ValueError("The approved patch contains duplicate paths")
            expected_paths.add(path)
            if change["kind"] == "modified" and path in tracked and change["before"] == files[path]:
                mode, _ = tracked[path]
                ending = endings[path]
            elif change["kind"] == "added" and path == REGRESSION_PATH and path not in tracked and not change["before"]:
                mode, ending = b"100644", "\n"
            else:
                raise ValueError("An approved edit does not match the verified base")
            replacement = change["after"]
            if "\r" not in replacement:
                replacement = replacement.replace("\n", ending)
            blob = replacement.encode()
            object_id = git(isolated, "hash-object", "-w", "--stdin", data=blob).strip()
            staged.append(mode + b" " + object_id + b"\t" + os.fsencode(path) + b"\0")
        git(isolated, "update-index", "-z", "--index-info", data=b"".join(staged))
        prepared_tree = git(isolated, "write-tree").strip().decode("ascii")
        message = (f"FixForge repair {run_id}\n\nPatch-SHA256: {evidence['patch_sha256']}\n"
                   f"Evidence-SHA256: {evidence['manifest_sha256']}\n")
        commit = git(isolated, "commit-tree", prepared_tree, "-p", base, "-F", "-", data=message.encode())
        head = commit.strip().decode("ascii")
        paths = git(isolated, "diff-tree", "--no-renames", "--name-only", "-r", "-z", "--no-commit-id", base, head)
        if {os.fsdecode(path) for path in paths.split(b"\0")[:-1]} != expected_paths:
            raise ValueError("The prepared commit changed files outside the approved diff or omitted approved edits")

        git(isolated, "update-ref", ref, head)
        bundle_path = isolated.parent / "repair.bundle"
        git(isolated, "bundle", "create", str(bundle_path), ref, f"^{base}")
        git(isolated, "bundle", "verify", str(bundle_path))
        bundle = bundle_path.read_bytes()
        receipt = dict(version=1, run_id=run_id, repository_id=run["repository_id"], base_commit=base,
                       prepared_commit=head, branch=branch, patch_sha256=evidence["patch_sha256"],
                       evidence_manifest_sha256=evidence["manifest_sha256"], approval_sha256=digest(decision),
                       bundle_sha256=hashlib.sha256(bundle).hexdigest())
    members = (
        ("repair.bundle", bundle),
        ("repair.patch", "".join(change["diff"] for change in run["files"])),
        ("handoff.json", json.dumps(receipt, indent=2) + "\n"),
        ("evidence.json", json.dumps({**run, "integrity_valid": True}, indent=2) + "\n"),
        ("review.md", review_markdown(run)),
    )
    output.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=".handoff-", suffix=".zip", dir=output, delete=False) as pending:
        package = Path(pending.name)
    try:
        with ZipFile(package, "w") as archive:
            for name, content in members:
                archive.writestr(ZipInfo(name), content, compress_type=ZIP_DEFLATED)
        if capture_source(repository)[1]["identity_sha256"] != revision["identity_sha256"]:
            raise ValueError("Repository changed during handoff preparation. Start a new repair.")
        os.replace(package, destination)
    finally:
        package.unlink(missing_ok=True)
    return destination, receipt


def _verified_endings(text: str, mode: bytes, object_id: bytes, object_format: str) -> str:
    if mode not in {b"100644", b"100755"}:
        raise ValueError("A verified Python path is not a regular Git file at the base commit")
    for ending in ("\n", "\r\n"):
        source = text.replace("\n", ending).encode()
        content = f"blob {len(source)}\0".encode() + source
        if hashlib.new(object_format, content).hexdigest().encode("ascii") == object_id:
            return ending
    raise ValueError("A committed Python file differs from the verified source or uses mixed line endings")
