from subprocess import CompletedProcess

import pytest

from fixforge.sandbox import resolve_docker_image


@pytest.mark.parametrize(
    "returncode, output, message",
    [(1, "", "unavailable locally"), (0, "sha256:abcd linux amd64", "full SHA-256"),
     (0, f"sha256:{'a' * 64} windows amd64", "Linux image")],
)
def test_image_resolution_rejects_missing_or_unsupported_images(monkeypatch, returncode, output, message):
    monkeypatch.setattr("fixforge.sandbox.subprocess.run",
                        lambda *args, **kwargs: CompletedProcess([], returncode, output))
    with pytest.raises(ValueError, match=message):
        resolve_docker_image("python:3.11-slim")


def test_image_reference_is_resolved_to_content_id(monkeypatch):
    image_id = "sha256:" + "b" * 64

    def inspect(command, **kwargs):
        assert command[:3] == ["docker", "image", "inspect"]
        assert command[-1] == "python:3.11-slim"
        assert "OPENAI_API_KEY" not in kwargs["env"]
        return CompletedProcess(command, 0, f"{image_id} linux arm64\n")

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr("fixforge.sandbox.subprocess.run", inspect)
    assert resolve_docker_image("python:3.11-slim") == (image_id, "arm64")
