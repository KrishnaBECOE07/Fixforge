from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__

from .config import ROOT, InferenceProvider, Settings
from .disclosure import prepare_disclosure, require_review
from .engine import Engine, review_markdown
from .fixtures import FIXTURES
from .intelligence import index_repository
from .providers import check_ollama_model, read_github_issue
from .provenance import assert_source_current, capture_source
from .sandbox import docker_available
from .store import Store, verify_record


class IssueInput(BaseModel):
    repository_id: str | None = None
    title: str = Field(default="", max_length=250)
    body: str = Field(default="", max_length=20_000)
    issue_url: str = Field(default="", max_length=1000)
    supplied_regression: str = Field(default="", max_length=8000)


class RunInput(IssueInput):
    provider: Literal["demo", "openai", "ollama"] = "demo"
    fixture_id: str | None = None
    source_review_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SourcePreviewInput(IssueInput):
    provider: InferenceProvider | None = None


class ReviewInput(BaseModel):
    decision: Literal["approve", "reject"]
    patch_sha256: str = Field(min_length=64, max_length=64)
    note: str = Field(default="", max_length=2000)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir)
    engine = Engine(settings, store)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fixforge")
    submission_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.recover()
        yield
        pool.shutdown(wait=True, cancel_futures=False)

    app = FastAPI(title="FixForge", version=__version__, lifespan=lifespan)
    app.state.store, app.state.engine = store, engine

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        # This edition is a single-user loopback app, not an Internet-facing service.
        host = urlparse("//" + request.headers.get("host", "")).hostname
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "FixForge is a local-only service"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {f"http://{request.headers.get('host')}", "http://127.0.0.1:5173", "http://localhost:5173"}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Cross-origin writes are forbidden"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Use application/json"}, status_code=415)
            try:
                if int(request.headers.get("content-length", "0")) > 40_000:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; frame-ancestors 'none'"
        return response

    def get_run(run_id: str) -> dict:
        try:
            return store.get(run_id)
        except KeyError:
            raise HTTPException(404, "Run not found") from None

    def resolve_issue(data: IssueInput) -> tuple[Path, dict]:
        repository = (settings.repositories or {}).get(data.repository_id)
        if repository is None:
            raise HTTPException(422, "Select a server-registered repository")
        values = dict(title=data.title.strip(), body=data.body, repo=data.repository_id,
                      number=None, repository_id=data.repository_id, fixture_id=None, tags=["AI repair"])
        if data.issue_url.strip():
            try:
                values.update(read_github_issue(data.issue_url.strip(), settings.github_token))
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
        if not values["title"].strip() or not values["body"].strip():
            raise HTTPException(422, "Provide an issue title and description, or a GitHub issue URL")
        if data.supplied_regression.strip():
            values["supplied_regression"] = data.supplied_regression.replace("\r\n", "\n").replace("\r", "\n")
        return repository, values

    def preview_source(repository: Path, values: dict, provider: InferenceProvider) -> dict:
        try:
            files, revision = capture_source(repository)
            index = index_repository(files, values["title"] + " " + values["body"])
            return prepare_disclosure(settings, {**values, "provider": provider}, files, index, revision)
        except (OSError, UnicodeError):
            raise HTTPException(422, "Could not read the registered Python source as UTF-8") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/config")
    def config():
        provider = settings.inference_provider
        limits = settings.inference_limits(provider)
        return {"version": __version__, "model": settings.model_for(provider), "ai_provider": provider,
                "ai_configured": bool(settings.ollama_model if provider == "ollama" else settings.api_key),
                "repositories": list((settings.repositories or {}).keys()),
                "demo_available": True, "github_configured": bool(settings.github_token),
                "limits": {"context_chars": limits["context_chars"],
                           "output_tokens": limits["output_tokens"],
                           "provider_timeout_seconds": limits["timeout_seconds"],
                           "attempts": 1},
                "edition": "local-first", "scope": "Python · standard library · unittest"}

    @app.get("/api/fixtures")
    def fixtures():
        return [fixture.public() for fixture in FIXTURES.values()]

    @app.post("/api/source-preview")
    def source_preview(data: SourcePreviewInput):
        repository, values = resolve_issue(data)
        preview = preview_source(repository, values, data.provider or settings.inference_provider)
        return JSONResponse(preview, headers={"Cache-Control": "no-store"})

    @app.get("/api/runs")
    def runs():
        return store.list()

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str):
        run = get_run(run_id)
        return {**run, "integrity_valid": verify_record(run)}

    @app.post("/api/runs", status_code=202)
    def create_run(data: RunInput):
        if sum(run["status"] in {"queued", "running"} for run in store.list()) >= 4:
            raise HTTPException(429, "The local queue is full. Wait for a run to finish.")
        if data.provider == "demo":
            fixture = FIXTURES.get(data.fixture_id or "payment-zero")
            if fixture is None:
                raise HTTPException(422, "Unknown demo case")
            values = {**fixture.public(), "fixture_id": fixture.id}
            values.pop("id")
        else:
            if data.provider == "openai" and not settings.api_key:
                raise HTTPException(409, "Configure OPENAI_API_KEY in .env first")
            if data.provider == "ollama" and not settings.ollama_model:
                raise HTTPException(409, "Configure FIXFORGE_OLLAMA_MODEL in .env first")
            if data.source_review_sha256 is None:
                raise HTTPException(409, "Review source before starting an AI repair")
            repository, values = resolve_issue(data)
            if not docker_available():
                raise HTTPException(409, "Start the Linux Docker engine before running repository code")
            disclosure = preview_source(repository, values, data.provider)
            try:
                require_review(data.source_review_sha256, disclosure)
                if data.provider == "ollama":
                    check_ollama_model(settings.ollama_model)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            values["source_review_sha256"] = data.source_review_sha256
        with submission_lock:
            if sum(run["status"] in {"queued", "running"} for run in store.list()) >= 4:
                raise HTTPException(429, "The local queue is full. Wait for a run to finish.")
            run = store.create(provider=data.provider, **values)
            pool.submit(engine.execute, run["id"])
        return run

    @app.post("/api/runs/{run_id}/review")
    def review(run_id: str, data: ReviewInput):
        try:
            return store.decide(run_id, data.decision, data.patch_sha256, data.note,
                                source_check=lambda run: assert_source_current(
                                    (settings.repositories or {}).get(run.get("repository_id")), run.get("source_revision")))
        except KeyError:
            raise HTTPException(404, "Run not found") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/runs/{run_id}/export/{kind}")
    def export(run_id: str, kind: Literal["patch", "evidence", "review"]):
        run = get_run(run_id)
        if not run.get("evidence") or not verify_record(run):
            raise HTTPException(409, "Only an intact verified run can be exported")
        if kind == "patch":
            content, extension, media = "".join(f["diff"] for f in run["files"]), "patch", "text/plain"
        elif kind == "review":
            content, extension, media = review_markdown(run), "md", "text/markdown"
        else:
            content = json.dumps({**run, "integrity_valid": True}, indent=2)
            extension, media = "json", "application/json"
        return Response(content, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="fixforge-{run_id}.{extension}"'})

    @app.get("/api/metrics")
    def metrics():
        runs = store.list()
        done = [r for r in runs if r["status"] not in {"queued", "running"}]
        verified = [r for r in done if r.get("evidence")]
        return dict(total=len(runs), completed=len(done), verified=len(verified),
                    approved=sum(r["status"] == "approved" for r in runs),
                    failed=sum(r["status"] == "failed" for r in runs),
                    success_rate=round(100 * len(verified) / len(done), 1) if done else None,
                    mean_duration_ms=round(sum(r.get("duration_ms", 0) for r in done) / len(done)) if done else None,
                    demo_runs=sum(r["provider"] == "demo" for r in runs),
                    ai_runs=sum(r["provider"] != "demo" for r in runs))

    dist = ROOT / "web" / "dist"
    if dist.is_dir():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Unknown endpoint")
            return FileResponse(dist / "index.html")
    else:
        @app.get("/")
        def no_frontend():
            return {"message": "Build the interface: cd web; npm install; npm run build", "docs": "/docs"}

    return app
