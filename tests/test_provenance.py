import subprocess

import pytest

from fixforge.provenance import assert_source_current, capture_source


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n")
    git(root, "init", "--initial-branch=main")
    git(root, "add", "app.py")
    git(root, "-c", "user.name=FixForge Tests", "-c", "user.email=tests@example.invalid", "commit", "-m", "Initial test source")
    return root


def test_snapshot_records_commit_and_detects_same_length_dirty_changes(tmp_path):
    root = repository(tmp_path)
    files, revision = capture_source(root, tmp_path / "snapshot")
    assert revision["kind"] == "git" and revision["dirty"] is False
    assert revision["commit"] == git(root, "rev-parse", "HEAD").stdout.strip()
    assert revision["file_count"] == len(files) == 1
    assert_source_current(root, revision)
    (root / "app.py").write_text("value = 2\n")
    with pytest.raises(ValueError, match="changed since verification"):
        assert_source_current(root, revision)


def test_new_commit_without_source_changes_is_stale(tmp_path):
    root = repository(tmp_path)
    _, revision = capture_source(root, tmp_path / "snapshot")
    git(root, "-c", "user.name=FixForge Tests", "-c", "user.email=tests@example.invalid", "commit", "--allow-empty", "-m", "New revision")
    with pytest.raises(ValueError, match="changed since verification"):
        assert_source_current(root, revision)


def test_untracked_python_content_is_bound_even_when_git_status_names_match(tmp_path):
    root = repository(tmp_path)
    extra = root / "extra.py"
    extra.write_text("value = 1\n")
    _, revision = capture_source(root, tmp_path / "snapshot")
    assert revision["dirty"] is True
    extra.write_text("value = 2\n")
    with pytest.raises(ValueError, match="changed since verification"):
        assert_source_current(root, revision)


def test_ordinary_directory_is_content_bound_without_git(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n")
    _, revision = capture_source(root, tmp_path / "snapshot")
    assert revision["kind"] == "directory"
    assert_source_current(root, revision)
    (root / "added.py").write_text("value = 2\n")
    with pytest.raises(ValueError):
        assert_source_current(root, revision)


def test_checkout_changes_during_snapshot_are_rejected(tmp_path, monkeypatch):
    root = repository(tmp_path)
    from fixforge.provenance import snapshot
    def racing_snapshot(source, target):
        files = snapshot(source, target)
        (source / "app.py").write_text("value = 2\n")
        return files
    monkeypatch.setattr("fixforge.provenance.snapshot", racing_snapshot)
    with pytest.raises(ValueError, match="while taking the snapshot"):
        capture_source(root, tmp_path / "snapshot")
