from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def issue_payload(run: dict) -> dict:
    payload = {key: run.get(key) for key in ("id", "title", "body", "repo", "number", "provider", "fixture_id", "repository_id")}
    if "supplied_regression" in run:
        payload["supplied_regression"] = run["supplied_regression"]
    return payload


class Store:
    """Durable run records; individual writes and state transitions are atomic."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "fixforge.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    status TEXT NOT NULL, data TEXT NOT NULL
                );
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def create(self, **data: Any) -> dict:
        stamp = now()
        run = dict(id=uuid.uuid4().hex[:12], created_at=stamp, updated_at=stamp,
                   status="queued", stage="queued", events=[], checks=[], files=[],
                   index=[], evidence=None, decision=None, error=None, **data)
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
                       (run["id"], stamp, stamp, run["status"], canonical(run)))
        return run

    def get(self, run_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row["data"])

    def list(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT data FROM runs ORDER BY created_at DESC").fetchall()
        return [json.loads(row["data"]) for row in rows]

    def update(self, run_id: str, **changes: Any) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            run = json.loads(row["data"])
            run.update(changes, updated_at=now())
            db.execute("UPDATE runs SET updated_at=?, status=?, data=? WHERE id=?",
                       (run["updated_at"], run["status"], canonical(run), run_id))
        return run

    def event(self, run_id: str, stage: str, title: str, detail: str, **changes: Any) -> dict:
        run = self.get(run_id)
        event = dict(seq=len(run["events"]) + 1, at=now(), stage=stage, title=title,
                     detail=detail, previous=run["events"][-1]["hash"] if run["events"] else "0" * 64)
        event["hash"] = digest(event)
        return self.update(run_id, events=[*run["events"], event], stage=stage, **changes)

    def decide(self, run_id: str, decision: str, patch_digest: str, note: str,
               *, source_check: Callable[[dict], None] | None = None) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            run = json.loads(row["data"])
            if run["status"] != "review":
                raise ValueError("Only a verified run awaiting review can be decided")
            if not run["evidence"] or run["evidence"]["patch_sha256"] != patch_digest:
                raise ValueError("Patch digest does not match the verified patch")
            if not verify_record(run):
                raise ValueError("Evidence integrity check failed")
            if decision not in {"approve", "reject"}:
                raise ValueError("Unknown review decision")
            if decision == "approve" and run.get("provider") != "demo":
                if run["evidence"].get("version", 1) < 2 or source_check is None:
                    raise ValueError("Current source revision must be revalidated before approval; start a new repair")
                source_check(run)
            run.update(status="approved" if decision == "approve" else "rejected", updated_at=now(),
                       decision=dict(action=decision, patch_sha256=patch_digest, note=note, at=now(),
                                     source_identity_sha256=(run.get("source_revision") or {}).get("identity_sha256"),
                                     evidence_manifest_sha256=run["evidence"]["manifest_sha256"]))
            db.execute("UPDATE runs SET updated_at=?, status=?, data=? WHERE id=?",
                       (run["updated_at"], run["status"], canonical(run), run_id))
        return run

    def recover(self) -> None:
        for run in self.list():
            if run["status"] in {"queued", "running"}:
                self.event(run["id"], "interrupted", "Worker interrupted",
                           "The server restarted before verification completed. Start a new run.",
                           status="failed", error="Worker interrupted by server restart")


def verify_record(run: dict) -> bool:
    try:
        return _verify_record(run)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _verify_record(run: dict) -> bool:
    previous = "0" * 64
    for seq, original in enumerate(run["events"], 1):
        event = dict(original)
        claimed = event.pop("hash", None)
        if event.get("seq") != seq or event.get("previous") != previous or digest(event) != claimed:
            return False
        previous = claimed
    evidence = run.get("evidence")
    if evidence:
        payload = {k: v for k, v in evidence.items() if k != "manifest_sha256"}
        if digest(payload) != evidence.get("manifest_sha256"):
            return False
        if digest(run["files"]) != evidence.get("patch_sha256"):
            return False
        if digest(run["checks"]) != evidence.get("checks_sha256"):
            return False
        if evidence.get("event_head") not in [e["hash"] for e in run["events"]]:
            return False
        if evidence.get("version", 1) >= 2:
            if (digest(run.get("source_revision")) != evidence.get("source_revision_sha256")
                    or digest(run.get("provider_record")) != evidence.get("provider_record_sha256")
                    or digest(issue_payload(run)) != evidence.get("issue_sha256")
                    or digest({"rationale": run.get("rationale"), "plan": run.get("plan")}) != evidence.get("explanation_sha256")):
                return False
            if ((run.get("source_revision") or {}).get("snapshot_sha256") != evidence.get("source_sha256")
                    or run.get("source_sha256") != evidence.get("source_sha256")
                    or not run["events"] or run["events"][-1].get("stage") != "review"
                    or run["events"][-1].get("previous") != evidence.get("event_head")):
                return False
        if evidence.get("version", 1) >= 3:
            execution = run.get("execution_record")
            if not isinstance(execution, dict) or digest(execution) != evidence.get("execution_record_sha256"):
                return False
    return True
