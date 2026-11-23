"""Build and check the exact issue text and Python source sent for inference."""
from __future__ import annotations

import re

from .config import Settings
from .policy import validate_regression
from .store import digest


CREDENTIAL_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}"
               r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
               r"|(?:AKIA|ASIA)[A-Z0-9]{16})\b"),
    re.compile(r"""\b(?:password|api_key|access_token|client_secret)\s*['"]?\s*[:=]\s*['"][^'"\s]{12,}['"]""",
               re.IGNORECASE),
)


def contains_credential(text: str) -> bool:
    return any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS)


def prepare_disclosure(settings: Settings, run: dict, files: dict[str, str],
                       index: list[dict], revision: dict) -> dict:
    provider = run["provider"]
    issue = {"title": run["title"], "body": run["body"]}
    if any(contains_credential(text) for text in issue.values()):
        raise ValueError("Potential credential in issue text. Remove it before reviewing source for inference.")

    selected = []
    budget = settings.inference_limits(provider)["context_chars"]
    reviewed_input = dict(issue=issue, untrusted_repository=selected)
    if (regression := run.get("supplied_regression")) is not None:
        if contains_credential(regression):
            raise ValueError("Potential credential in the supplied regression. Remove it before reviewing source.")
        try:
            validate_regression(regression, files)
        except SyntaxError as exc:
            location = f" on line {exc.lineno}" if exc.lineno is not None else ""
            raise ValueError(f"Supplied regression has invalid Python syntax{location}.") from None
        budget -= len(regression)
        if budget <= 0:
            raise ValueError("Supplied regression leaves no room for repository source. Shorten the test.")
        reviewed_input["supplied_regression"] = regression
    for entry in index:
        path = entry["path"]
        source = files[path]
        if len(source) > budget:
            continue
        if contains_credential(path):
            raise ValueError("Potential credential in a selected Python path. Review the checkout before continuing.")
        if contains_credential(source):
            raise ValueError(f"Potential credential in {path}. Remove it before reviewing source for inference.")
        selected.append({"path": path, "source": source})
        budget -= len(source)
        if len(selected) == 20:
            break
    if not selected:
        raise ValueError("No Python file fits the configured source context budget.")

    disclosure = dict(repository_id=run["repository_id"], issue_url=run.get("issue_url"),
                      provider=provider, model=settings.model_for(provider),
                      source_identity_sha256=revision["identity_sha256"],
                      input=reviewed_input)
    return {**disclosure, "sha256": digest(disclosure)}


def require_review(expected: str | None, disclosure: dict) -> None:
    if expected != disclosure["sha256"]:
        raise ValueError("Source, issue, regression, model, or provider changed since review. Review source again before starting.")
