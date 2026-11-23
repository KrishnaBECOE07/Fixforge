from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
InferenceProvider = Literal["openai", "ollama"]
DEFAULT_OLLAMA_MODEL = "qwen3:4b"


def load_env() -> None:
    """Small local .env reader; no expansion or code evaluation."""
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_key: str = ""
    model: str = "gpt-4.1"
    image: str = "python:3.11-slim"
    github_token: str = ""
    repositories: dict[str, Path] | None = None
    max_context_chars: int = 90_000
    max_output_tokens: int = 10_000
    provider_timeout_seconds: int = 90
    inference_provider: InferenceProvider = "openai"
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    ollama_timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if self.inference_provider not in {"openai", "ollama"}:
            raise ValueError("FIXFORGE_INFERENCE_PROVIDER must be openai or ollama")
        for name, low, high in (("max_context_chars", 1000, 120_000),
                                ("max_output_tokens", 256, 16_000),
                                ("provider_timeout_seconds", 5, 120),
                                ("ollama_timeout_seconds", 5, 600)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer between {low} and {high}")

    def model_for(self, provider: InferenceProvider) -> str:
        return self.ollama_model if provider == "ollama" else self.model

    def inference_limits(self, provider: InferenceProvider) -> dict[str, int]:
        if provider == "ollama":
            return dict(context_chars=min(self.max_context_chars, 16_000),
                        output_tokens=min(self.max_output_tokens, 4096),
                        timeout_seconds=self.ollama_timeout_seconds)
        return dict(context_chars=self.max_context_chars, output_tokens=self.max_output_tokens,
                    timeout_seconds=self.provider_timeout_seconds)

    @classmethod
    def from_env(cls) -> "Settings":
        load_env()
        repos = json.loads(os.getenv("FIXFORGE_REPOSITORIES", "{}"))
        if not isinstance(repos, dict):
            raise ValueError("FIXFORGE_REPOSITORIES must be a JSON object")
        return cls(
            data_dir=Path(os.getenv("FIXFORGE_DATA_DIR", str(ROOT / ".fixforge"))).resolve(),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("FIXFORGE_MODEL", "gpt-4.1"),
            image=os.getenv("FIXFORGE_SANDBOX_IMAGE", "python:3.11-slim"),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            repositories={k: Path(v).resolve() for k, v in repos.items()},
            max_context_chars=int(os.getenv("FIXFORGE_MAX_CONTEXT_CHARS", "90000")),
            max_output_tokens=int(os.getenv("FIXFORGE_MAX_OUTPUT_TOKENS", "10000")),
            provider_timeout_seconds=int(os.getenv("FIXFORGE_PROVIDER_TIMEOUT_SECONDS", "90")),
            inference_provider=os.getenv("FIXFORGE_INFERENCE_PROVIDER", "openai"),
            ollama_model=os.getenv("FIXFORGE_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            ollama_timeout_seconds=int(os.getenv("FIXFORGE_OLLAMA_TIMEOUT_SECONDS", "300")),
        )
