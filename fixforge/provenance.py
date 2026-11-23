"""Capture source identity without importing or executing repository Python code."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from .intelligence import read_sources, snapshot
from .store import digest, now


def git_state(root: Path) -> dict:
    if not shutil.which("git"):
        return dict(kind="directory", commit=None, dirty=None, git_status_sha256=None)

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                               "-C", str(root.resolve()), *args], capture_output=True, timeout=8, check=False)

    try:
        if git("rev-parse", "--is-inside-work-tree").stdout.strip() != b"true":
            return dict(kind="directory", commit=None, dirty=None, git_status_sha256=None)
        head = git("rev-parse", "--verify", "HEAD")
        status = git("status", "--porcelain=v1", "-z", "--untracked-files=normal", "--", ".")
        if status.returncode:
            raise ValueError("Could not capture Git checkout state")
        return dict(kind="git", commit=head.stdout.decode().strip() if head.returncode == 0 else None,
                    dirty=bool(status.stdout), git_status_sha256=hashlib.sha256(status.stdout).hexdigest())
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Git source identity could not be checked before the deadline") from None


def source_revision(files: dict[str, str], state: dict) -> dict:
    identity = dict(**state, snapshot_sha256=digest(files), file_count=len(files),
                    file_hashes={path: hashlib.sha256(source.encode()).hexdigest() for path, source in files.items()})
    return dict(**identity, identity_sha256=digest(identity), captured_at=now())


def capture_source(root: Path, destination: Path | None = None) -> tuple[dict[str, str], dict]:
    before = git_state(root)
    files = read_sources(root) if destination is None else snapshot(root, destination)
    if before != git_state(root) or digest(files) != digest(read_sources(root)):
        raise ValueError("Repository changed while taking the snapshot; start a new repair")
    return files, source_revision(files, before)


def assert_source_current(root: Path | None, expected: dict | None) -> None:
    if root is None or not expected:
        raise ValueError("Source revision is missing or its repository is no longer registered")
    before = git_state(root)
    files = read_sources(root)
    if before != git_state(root):
        raise ValueError("Repository changed during the freshness check; start a new repair")
    actual = source_revision(files, before)
    if actual["identity_sha256"] != expected.get("identity_sha256"):
        raise ValueError("Repository changed since verification; approval is blocked. Start a new repair.")
