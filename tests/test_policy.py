from pathlib import Path

import pytest

from fixforge.fixtures import FIXTURES
from fixforge.intelligence import index_repository, safe_path, snapshot
from fixforge.policy import validate_proposal
from fixforge.sandbox import docker_command, run_tests


@pytest.mark.parametrize("path", ["../secret.py", "/etc/passwd", "a/../../secret", "C:/secret.py", ".env", "a/.git/config", "a\\b.py", "a.py:ads", "a//b.py", "./a.py"])
def test_paths_cannot_escape_or_access_hidden_files(tmp_path, path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, path)


def proposal():
    fixture = FIXTURES["payment-zero"]
    return {"edits": [{"path": fixture.path, "content": fixture.replacement}], "regression": fixture.regression}


def test_existing_tests_are_immutable(tmp_path):
    value = proposal()
    value["edits"][0]["path"] = "tests/test_existing.py"
    with pytest.raises(ValueError, match="Existing tests"):
        validate_proposal(tmp_path, {"tests/test_existing.py": "# existing"}, value, "tests/test_new.py")


@pytest.mark.parametrize("source", ['import subprocess\nsubprocess.run(["whoami"])', 'eval("1+1")', 'import socket', 'import urllib.request'])
def test_unsafe_patch_is_rejected(tmp_path, source):
    value = proposal()
    value["edits"][0]["content"] = source
    with pytest.raises(ValueError, match="disallowed"):
        validate_proposal(tmp_path, {"payments.py": FIXTURES["payment-zero"].original}, value, "tests/test_new.py")


def test_regression_cannot_skip(tmp_path):
    value = proposal()
    value["regression"] = value["regression"].replace("def test_zero_invoice", '@unittest.skip("skip")\n    def test_zero_invoice')
    with pytest.raises(ValueError, match="cannot skip"):
        validate_proposal(tmp_path, {"payments.py": FIXTURES["payment-zero"].original}, value, "tests/test_new.py")


def test_snapshot_copies_only_bounded_python_source(tmp_path):
    source, target = tmp_path / "repo", tmp_path / "snapshot"
    source.mkdir()
    (source / "app.py").write_text("def payment():\n    return 1\n")
    (source / ".env").write_text("SECRET=must-never-be-sent")
    (source / ".git").mkdir()
    (source / ".git" / "ignored.py").write_text("# hidden")
    copied = snapshot(source, target)
    assert list(copied) == ["app.py"]
    assert not (target / ".env").exists()
    indexed = index_repository(copied, "payment crashes")
    assert indexed[0]["symbols"] == [{"name": "payment", "line": 1, "kind": "function"}]


def test_no_tests_is_never_a_passing_check(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    result = run_tests(tmp_path, True, "unused", "Empty suite")
    assert not result["passed"]
    assert result["report"]["tests"] == 0


def test_docker_is_restricted_without_a_host_fallback(tmp_path):
    image_id = "sha256:" + "a" * 64
    command = docker_command(tmp_path, image_id, "test-container")
    assert all(flag in command for flag in ["--network=none", "--read-only", "--cap-drop=ALL", "--user=65534:65534", "--pull=never", "--memory=256m", "--pids-limit=64"])
    assert not any("docker.sock" in part for part in command)
    assert all("readonly" in command[i + 1] for i, flag in enumerate(command) if flag == "--mount")
    assert command[-6:] == ["--entrypoint=python", image_id, "-I", "-B", "/harness.py", "/workspace"]
    with pytest.raises(ValueError, match="resolved"):
        docker_command(tmp_path, "python:3.11-slim", "test-container")
