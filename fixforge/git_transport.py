"""Git plumbing in a temporary repository with controlled configuration."""
from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


def git_environment() -> dict[str, str]:
    secrets = {"GITHUB_TOKEN", "GH_TOKEN", "FIXFORGE_GITHUB_PUBLISH_TOKEN", "OPENAI_API_KEY"}
    env = {name: value for name, value in os.environ.items()
           if not name.upper().startswith("GIT_") and name.upper() not in secrets}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_REPLACE_OBJECTS="1",
               GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    return env


def run_git(cwd: Path, *args: str, env: dict[str, str], data: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.longpaths=true",
                                 "-C", str(cwd), *args],
                                input=data, capture_output=True, env=env, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError(f"Could not run Git {args[0]}; check the Git installation and repository.") from None
    if result.returncode != 0:
        raise ValueError(f"Git {args[0]} failed while preparing the repair branch.")
    return result.stdout


@contextmanager
def isolated_repository(repository: Path, object_format: str, env: dict[str, str]):
    objects = run_git(repository, "rev-parse", "--path-format=absolute", "--git-path", "objects",
                      env=env).rstrip(b"\r\n")
    if b"\n" in objects or b"\r" in objects:
        raise ValueError("Git object directory path contains a newline")
    with TemporaryDirectory(prefix="fixforge-git-") as temporary:
        work = Path(temporary)
        isolated = work / "repository.git"
        run_git(work, "init", "--bare", "--template=", f"--object-format={object_format}", str(isolated), env=env)
        # Borrow base objects from the registered checkout. The temporary repo owns all writes.
        (isolated / "objects" / "info" / "alternates").write_bytes(objects + b"\n")
        yield isolated
