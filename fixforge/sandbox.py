from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

HARNESS = Path(__file__).with_name("harness.py")
MAX_LOG = 256_000
IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}")


def runner_env() -> dict[str, str]:
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "DOCKER_HOST",
               "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
               "HOME", "USERPROFILE"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "info", "--format", "{{.OSType}}"], capture_output=True,
                                text=True, timeout=5, check=False, env=runner_env())
        return result.returncode == 0 and result.stdout.strip() == "linux"
    except (OSError, subprocess.TimeoutExpired):
        return False


def harness_fingerprint() -> str:
    return hashlib.sha256(HARNESS.read_bytes()).hexdigest()


def resolve_docker_image(reference: str) -> tuple[str, str]:
    """Resolve the configured local tag or digest once, before running any tests."""
    if not reference or reference.startswith("-") or any(char.isspace() for char in reference):
        raise ValueError("Configure a valid local Docker image in FIXFORGE_SANDBOX_IMAGE")
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}} {{.Os}} {{.Architecture}}", reference],
            capture_output=True, text=True, timeout=8, check=False, env=runner_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Could not inspect the sandbox image. Check the Linux Docker engine.") from None
    if result.returncode:
        raise ValueError("Sandbox image is unavailable locally. Check Docker and pre-pull the configured image.")
    fields = result.stdout.split()
    if len(fields) != 3 or not IMAGE_ID.fullmatch(fields[0]) or fields[1] != "linux":
        raise ValueError("Sandbox image must resolve to a Linux image with a full SHA-256 ID")
    return fields[0], fields[2]


def docker_command(workspace: Path, image: str, name: str) -> list[str]:
    if not IMAGE_ID.fullmatch(image):
        raise ValueError("Sandbox execution requires a resolved SHA-256 image ID")
    return ["docker", "run", "--rm", "--pull=never", "--name", name,
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=64", "--memory=256m", "--cpus=1",
            "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
            "--mount", f"type=bind,source={workspace.resolve()},target=/workspace,readonly",
            "--mount", f"type=bind,source={HARNESS.resolve()},target=/harness.py,readonly",
            "--workdir=/workspace", "--entrypoint=python", image,
            "-I", "-B", "/harness.py", "/workspace"]


def run_tests(workspace: Path, trusted_demo: bool, image: str, label: str) -> dict:
    """Only fixed curated code can use the host runner. AI/repository code requires Docker."""
    name = "fixforge-" + uuid.uuid4().hex[:16]
    command = [sys.executable, "-I", "-B", str(HARNESS), str(workspace)] if trusted_demo else docker_command(workspace, image, name)
    # Never inherit API keys or user credentials in local trusted demo execution.
    env = runner_env()
    started = time.monotonic()
    chunks: list[bytes] = []
    retained = 0
    timed_out = False
    process = subprocess.Popen(command, cwd=workspace, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

    def consume() -> None:
        nonlocal retained
        assert process.stdout is not None
        # Drain continuously but retain a bounded tail, including the harness report.
        while chunk := process.stdout.read(4096):
            chunks.append(chunk)
            retained += len(chunk)
            while retained > MAX_LOG and len(chunks) > 1:
                retained -= len(chunks.pop(0))

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
    finally:
        if not trusted_demo:
            # Kill the container as well as the CLI on timeout; don't leave a runaway workload.
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=8, check=False, env=env)
            except (OSError, subprocess.TimeoutExpired):
                pass
        process.wait(timeout=5)
        reader.join(timeout=3)
        if process.stdout:
            process.stdout.close()
    log = b"".join(chunks).decode("utf-8", errors="replace")[-MAX_LOG:]
    report = None
    for line in log.splitlines():
        if line.startswith("FIXFORGE_RESULT="):
            try:
                report = json.loads(line.split("=", 1)[1])
            except json.JSONDecodeError:
                pass
    display_log = "\n".join(line for line in log.splitlines() if not line.startswith("FIXFORGE_RESULT="))
    return dict(label=label, exit_code=process.returncode, timed_out=timed_out, report=report,
                passed=not timed_out and process.returncode == 0 and bool(isinstance(report, dict) and report.get("successful") and type(report.get("tests")) is int and report["tests"] > 0),
                duration_ms=round((time.monotonic() - started) * 1000), log=display_log,
                runner="trusted fixture / local Python" if trusted_demo else "Docker / network disabled")
