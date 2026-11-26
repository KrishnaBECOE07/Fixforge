# Development log

## 26 November 2026 — GitHub issue intake

- The issue reader checks the GitHub repository configured for the selected checkout and verifies the canonical issue returned by GitHub. Source review links to the imported issue. A published draft only references an issue that matches the verified repository and issue number.
- Added regression coverage for mismatched repositories, transferred issues, pull request URLs, and publication links that disagree with the verified record.
- The Windows suite passed 153 tests. The frontend production build passed.
- Imported [billing issue #4](https://github.com/KrishnaBECOE07/Fixforge/issues/4) through the live GitHub API and ran it with local Qwen3 4B and an operator-supplied regression. The first run timed out. A retry with shorter proposal instructions reached review, and a narrower follow-up (`b3b208316067`) used 344 output tokens. Docker recorded 5 passing baseline tests, 2 expected failures in the 9-test reproduction, all 9 tests passing with the patch, and the same 2 failures after restoring the original code. The candidate is awaiting human review.

## 25 November 2026 — workbench draft publication

- Added a publication preview for approved Git repairs. It shows the configured destination, verified base commit, repair branch, and patch and evidence digests. An explicit confirmation uses the same publisher as the CLI and returns the GitHub pull request link.
- Tested approval and confirmation requirements, changed destinations, and cross-origin requests. Verified cancellation, retry, and the returned pull request link in Chrome with simulated GitHub responses. The Windows suite passed 143 tests, the separate four-gate Docker integration test passed, and the frontend production build passed.
- FixForge now waits briefly for GitHub's refs API to see a successful push before opening the draft. The publisher update passed the Windows, Ubuntu, and Docker CI jobs.
- Published the approved scheduling repair through the workbench API to [draft PR #2](https://github.com/KrishnaBECOE07/Fixforge/pull/2). GitHub returned the verified base `3062a02` and prepared commit `61f69fd`. A second publication request returned the same draft.

## 23 November 2026 — GitHub draft publisher

- Added the explicit `python -m fixforge publish RUN_ID` command. It uses a configured repository and base branch, checks the approved source and exact GitHub base, and opens a draft from a new repair branch.
- Covered duplicate prevention, retry after ambiguous responses, a changed target base, and a conflicting head through GitHub API mocks. A Git integration test imports the actual approved bundle and checks the branch push arguments.
- All 143 automated tests passed with Docker enabled, and the production frontend build passed.
- Published the scheduling fixture at `codex/scheduling-pilot` and checked its remote SHA through Git and the GitHub API. The live draft test awaits a repository-scoped publication token.

## 23 November 2026 — Git handoff for approved repairs

- Added `python -m fixforge handoff RUN_ID`. It checks the recorded approval and evidence, verifies the clean Git base and its Python blobs, and places a reproducible single-commit branch in a ZIP with the patch and review evidence.
- Prepared `codex/fixforge-16d916bc68c7` from the approved scheduling run. Commit `61f69fd` has the verified base `3062a02` as its only parent. Imported it into a disposable checkout, checked the bundle and approved patch, and ran all seven tests in Docker. The original checkout and its refs stayed unchanged.
- All 132 automated tests passed with Docker integration enabled. Handoff tests cover repeatable archives, importing the commit, CRLF preservation, mismatched approvals, stale source, and verified Python files absent from the Git base.
- GitHub draft PR publication is the next implementation step. A live publication test and remote CI will need a target repository.

## 23 November 2026 — operator-supplied regressions

- Added an optional Python `unittest` module to repository repairs. The source review shows the supplied test and includes it in the digest checked at submission. Ollama and OpenAI return production edits in this mode. FixForge runs the reviewed test in the same four verification gates and labels its origin in the review package.
- Passed 127 automated tests, the separate Docker integration test, and the production frontend build. The browser flow previewed the test and started local inference with Ollama cloud features disabled.
- Live Qwen3 4B run `b3973418f92d` verified the scheduling fix with an independently authored regression. The five baseline tests passed, the seven-test suite reproduced the bug and passed with the patch, and rollback reproduced the same failure. Its diff also changed type annotations and moved the module docstring, so it remained pending review.
- With tighter issue wording and the same regression, run `16d916bc68c7` passed all four gates. The production diff changes the two overlap comparisons and removes the final newline. The unified patch passes `git apply --check`. The checkout remains at `3062a02`, and the run awaits human review.

## 21 November 2026 — local Ollama inference

- Added Ollama as an optional local provider. Source reviews bind the destination provider and model. The adapter connects to loopback, rejects cloud models, and sends the reviewed input with a structured repair schema.
- The inference receipt records the provider, model, input digest, selected paths and reported tokens. Ollama and OpenAI repairs use the same four Docker gates and human review.
- Verified the production frontend build and the local source preview in the browser. All 123 automated tests passed with the Docker integration test enabled.
- Configured this workstation to run portable Ollama 0.40.17 with cloud inference disabled and Qwen3 4B selected. Local inference uses its own timeout to accommodate CPU and GPU generation.
- A live Qwen3 4B run (`79e3d7363155`) proposed strict comparisons for adjacent half-open meetings. FixForge stopped the workbench run when its generated regression raised a `NameError`.
- Independently checked that exact production edit against a separately authored regression in Docker. The five original tests passed. The six-test suite reproduced the defect, passed with the patch, and reproduced the same failure after the original code was restored. The independent check preserved the workbench's rejection and the pilot checkout at `3062a02`.

## 21 November 2026 — source review before inference

- Registered the project-owned scheduling pilot as a standalone Git checkout at `.fixforge/pilot` (baseline `3062a02`). The local `.env` registers it as `scheduling-pilot`.
- Added a browser preview of the resolved issue and exact Python source selected for OpenAI. Common credential patterns block review. The source review digest is checked at submission and by the worker before tests. Successful inference evidence includes the digest and file paths.
- Passed 116 automated tests and the separate opt-in Docker smoke test through all four verification gates using a mocked model response. All five scheduling baseline tests passed in Docker. Verified the production frontend build and the browser path through source review and back to the issue.
- The first live provider run awaits a locally configured `OPENAI_API_KEY`. Remote CI awaits a remote repository.

## 18 November 2026 — pilot setup and execution evidence

- Added a dependency-free scheduling project with three independent repair issues. All five baseline tests pass and all three documented bugs reproduce locally.
- FixForge resolves the pre-pulled Docker image to a local image ID before testing. All four gates use that ID. Evidence v3 binds the image, architecture and harness checksum. Demos record the local Python version.
- Added `python -m fixforge doctor` to check local pilot prerequisites and a Linux CI smoke test that exercises the container runner with a known patch.
- Verified evidence v3 in a live demo in the workbench. The production frontend build passed. After Docker setup, the complete suite passed **111 tests**, including the Docker smoke test.

After Docker Desktop and WSL were updated, the Linux engine became available. The Docker smoke test passed all four gates with a known patch and confirmed evidence export and approval. All five scheduling baseline tests passed in the same `python:3.11-slim` image. The live AI pilot still needs a configured provider key and registered checkout. The Linux CI job awaits a remote run.

## 17 November 2026 — v0.2 verification and source provenance

The delivery target moved forward to **20 December 2026**, with a usable private beta targeted for **13 December**. Shared SaaS hosting, additional language support and nonessential infrastructure remain outside the earlier v1 scope. The acceptance gates remain required.

### Delivered today

- **Four-gate verification:** baseline passes → new regression fails → identical named suite passes with the patch → restored original production code reproduces the same named failure signatures.
- A third, independent rollback snapshot preserves the patched artifact while testing the restored code.
- Structured per-test identities, outcomes, exception classes, failure categories and production traceback paths. Matching test counts with substituted IDs cannot satisfy the gate.
- Conservative rejection of collection, missing dependency/import, syntax and test-authoring errors as defect evidence. Existing tests must remain green during reproduction; skipped/expected-failure tests cannot satisfy verification.
- Source provenance: Git HEAD when available, Git status digest, per-file Python hashes and snapshot identity; capture checks detect concurrent changes.
- Repository freshness checks before sealing evidence and inside the approval transaction. Modified, added or removed source files, new commits and unregistered repositories block approval; stale candidates can still be rejected.
- Strict structured-output schema plus independent local Pydantic validation. Extra keys, invalid types, excessive sizes and malformed response envelopes are rejected without echoing private source into errors.
- Configurable selected-source/output-token/request-time limits, one model attempt per run and provider-reported token usage. Usage is retained for incomplete or schema-rejected responses when supplied. This is not a dollar spend cap.
- Evidence v2 additionally binds issue metadata, source revision, explanation and provider receipt. Approval records the source identity and evidence manifest as well as the patch digest. Corrupted record shapes fail closed.
- Workbench views for named test outcomes, per-gate acceptance reasons, source identity, inference receipts and restored-code replay. Legacy v1 artifacts stay readable.
- Updated roadmap, architecture, threat model, setup instructions, environment example and version to 0.2.0.

### Verification

| Check | Result |
|---|---|
| Complete automated suite | **104 passed** on Windows / Python 3.11.9 |
| TypeScript strict compilation and Vite production build | **Passed** |
| All three curated defects | All four gates pass with actual Python subprocess execution |
| Git provenance | Real temporary Git repositories exercised committed/dirty/untracked content, empty commits and capture-time drift |
| Repository approval integration | Controlled fixture repositories exercised full API/engine/snapshot/review paths, freshness rejection and source-bound approval |
| Failure rejection | Same-count test substitution, existing-test failure, test-authoring errors, mixed subtest environment errors, changed replay signatures, malformed records and schema-invalid responses rejected |
| Browser workflow | Fresh payment repair completed all four gates; named outcomes, restored-code `ZeroDivisionError`, intact evidence v2 and fixture/inference receipts inspected |
| Responsive UI | Desktop 1440 × 1000 and narrow 390 × 844 inspected; no page-wide horizontal overflow in the narrow evidence view |
| Preview artifacts | `verification-v02.jpg` and `evidence-v02.jpg` saved under `docs/screenshots/` |

The existing Starlette/httpx TestClient deprecation warning remains nonfatal.

### Limits and next work

No live AI API key was configured or used. The Docker Linux engine was unavailable. Repository integration tests intentionally replaced inference and Docker with known, project-owned fixture code; they validate control-plane behavior, not live AI repair quality or container isolation. Production AI execution retains its mandatory Docker boundary and has no host fallback.

Next: configure a reviewed pilot repository and provider locally, run Docker, validate unseen issues, pin the sandbox image digest and implement revision-bound, idempotent draft-PR publication. Freshness checks observe state at defined points; future publication must revalidate again. The source fingerprint covers supported Python content rather than every ignored or binary file. Passing/replayed tests still do not prove semantic correctness, security or externally signed authorship.

See [the revised project plan](PROJECT_PLAN.md) for the accelerated milestones.

## 16 November 2026 — first working vertical slice

Built the project from an empty repository in the provided Fixforge workspace.

### Delivered

- Product plan, six-week dated roadmap, architecture decisions and threat model.
- FastAPI local control plane, React/TypeScript workbench and a single-worker repair engine.
- Persistent SQLite run history, checkpoints and restart handling for incomplete runs.
- Python AST symbol/import indexing and bounded relevance-ranked source context.
- Three complete curated defect cases using real Python unittest execution.
- Original-suite baseline, regression-fails-before and full-suite-passes-after verification.
- Immutable existing tests, bounded source/patch policy and isolated working copies.
- Optional OpenAI Responses adapter and GitHub issue reader, configured server-side.
- Restricted Docker command path for all non-demo repository execution.
- Linked event hashes, source/patch/log digests and exportable verification records.
- Exact-patch approval/rejection and patch/evidence/review-description downloads.
- Benchmark lab, repository setup, settings, field guide, search, filters and reload-safe repair links.
- Windows startup script, pinned Python/Node dependency records and CI definition.

### Verification performed

| Check | Result |
|---|---|
| Backend automated suite | **42 passed** on Windows / Python 3.11.9 |
| TypeScript strict compilation and Vite production build | **Passed** |
| Payment defect | Baseline: 2 passing tests; original + regression: 4 tests with 2 expected defect errors; patched suite: all 4 pass |
| Pagination and slug defects | Real fail-before/pass-after workflows passed in automated tests and live browser runs |
| Negative verification paths | No-op regression, broken patch, zero tests, invalid paths, existing-test edits and disallowed code are rejected |
| Evidence integrity and review | Event/patch/log/manifest changes detected; wrong-digest, early and duplicate decisions rejected |
| Provider adapter contracts | Mocked response, incomplete output, untrusted input separation and sanitized errors passed |
| API boundaries | Unknown runs/cases, unconfigured AI, invalid exports, cross-origin writes and non-local Host rejected |
| Browser workflow | Demo creation, diff, original failure log, exact-patch approval, saved decision, benchmark and unconfigured AI setup verified |
| Browser search/filter | Repository search and approved filter each returned the expected single row |
| Responsive layout | Desktop at 1440 × 1000 and narrow viewport at 390 × 844 inspected; no page-wide horizontal overflow at narrow width |
| Preview artifact | `docs/screenshots/workbench.jpg` saved from the running application |

One dependency deprecation warning is emitted by Starlette's httpx-based TestClient. Tests pass; migrate to its newer supported client when updating the development dependencies.

### Not yet verified or delivered

- Paid/live AI provider requests: no API key configured or used.
- Actual Docker container execution: Docker CLI is present; the Linux engine was not running. Flag construction is tested, but this does not replace integration testing.
- GitHub authentication, private issue retrieval and real repository repair: require the operator's configuration.
- GitHub branch push, draft PR creation, merge or deployment: not implemented or performed.
- Linux CI execution: workflow is defined but has not run in a remote repository.
- General AI repair success rate: not measured. Three demo recipes are not a model benchmark.

### Next milestone

Validate one unseen issue on a reviewed Python repository with Docker and a configured provider; record actual usage, pin the source revision and improve failure classification. See [the project plan](PROJECT_PLAN.md) for priorities and acceptance gates.
