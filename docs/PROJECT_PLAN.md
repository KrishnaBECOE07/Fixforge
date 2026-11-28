# FixForge — product and execution plan

Start date: **16 November 2026**, Asia/Kolkata. Updated 17 November: target a usable private beta by **13 December 2026** and a portfolio-quality v1 by **20 December 2026**, one week earlier than the original 27 December target. Dates are planning targets, conditional on engineering time and evaluation results; no unattended daily work has been scheduled.

## 1. Product thesis

An engineering team should be able to hand FixForge a well-specified issue and receive a small, reviewable patch with an inspectable explanation of why it fixes the defect.

**Positioning:** an evidence-first repair workbench. The important artifact is a verified change with receipts: source revision, reproduction, unchanged existing tests, new regression, exact patch, execution record, limitations and human decision.

Initial users are individual maintainers and small teams with Python services and useful automated tests. Initial defects are deterministic logic, validation, parsing and boundary bugs. Distributed systems, UI defects, performance regressions and infrastructure changes come later.

## 2. What makes it stronger and distinctive

| Capability | User value | Delivery |
|---|---|---|
| Counterfactual verification | The same new test fails before a patch and passes afterward | Implemented in v0.1 |
| Patch-bound approval | A reviewer approves a specific digest, preventing accidental substitution | Implemented locally |
| Evidence record | Source, changes and logs are bound together and downloadable | Implemented; local hashes only |
| Causal investigation timeline | See the cause, attempted change and measured result in order | Implemented |
| Honest benchmark separation | Fixture recipes cannot inflate reported AI performance | Implemented counts; held-out AI evaluation planned |
| Impact-aware context | Combine AST symbols, imports and issue relevance | Python symbols/imports implemented; graph traversal planned |
| Adversarial verification | Reject deceptive test edits, probe scope and restore the bug to check regression strength | Test immutability and restored-code replay implemented; broader mutation checks planned |
| Risk budget | Limit changed files, compute, model calls and external privileges | Configurable context/output/time limits and usage receipts implemented; dollar caps planned |
| Failure intelligence | Explain when evidence is insufficient and abstain | Initial blocked verification paths implemented |

Avoid a vague percentage called “confidence.” Show observable evidence and named limitations. A green test result is a necessary gate, not a correctness or security proof.

## 3. Scope and non-goals

### First release

Local, single-user workbench; small Python/unittest projects; manually selected issues; bounded model call; isolated execution; human review; downloadable artifacts. The production checkout is read and copied, never patched in place.

### Private beta

GitHub App issue ingestion, revision-pinned worktrees, dependency-aware test adapters, durable workers, budgeted repair attempts, authenticated review, and explicit draft-PR publication.

### Deferred

Automatic merging, arbitrary internet access from agent workloads, production credentials inside sandboxes, multi-language support before the Python evaluation gate, universal autonomous engineering, public hostile-code hosting, and paid infrastructure before a measured need.

## 4. Architecture direction

React/TypeScript frontend → FastAPI control plane → persistent run state → bounded repair engine → code intelligence / model provider / sandbox runner → evidence and review gate → GitHub publisher.

Today: SQLite, one worker thread, Python `ast`, a fixed unittest harness, optional OpenAI adapter, Docker execution and local artifact export. Keep these explicit boundaries before adopting orchestration frameworks.

Next: PostgreSQL for multi-user state; a durable queue with job leases, cancellation and retry; object storage for artifacts; revision-pinned repository snapshots; GitHub App installation tokens. Introduce Tree-sitter only when a second language is justified by evaluation. Docker executes workloads on dedicated workers; a shared SaaS requires stronger isolation and independent security review.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the implemented data flow.

## 5. Delivery schedule

Assumption: one developer with approximately 20–25 focused hours per week. Adjust schedule after the first real repository repair. Development should advance by acceptance gates rather than feature count.

| Window | Milestone | Deliverables | Acceptance gate |
|---|---|---|---|
| **16 Nov** | M0 — working foundation | Workbench, actual fixture repairs, AST index, evidence, review, test suite, full plan | All curated cases reproduce and repair; failure paths tested; UI build passes |
| **17–20 Nov** | M1 — reliable real-repo pilot | Source revision fingerprints, stale-source approval checks, strict proposal schema, named-test evidence, failure classification, counterfactual replay, provider usage/limits, Docker pilot | Automated rejection tests pass; then repair 3 unseen pure-Python issues using a live configured provider and Docker; original checkout unchanged |
| **21–26 Nov** | M2 — GitHub workflow | GitHub App, signed webhook intake, issue selection, revision-pinned branch publisher, evidence bundle, explicit draft-PR publication | One issue becomes one draft PR at the expected base SHA; idempotency and stale-base checks pass; no merge permission |
| **27 Nov–3 Dec** | M3 — repair quality | pytest adapter, approved dependency images, bounded impact graph, independent verifier, up to 2 budgeted attempts | Held-out defect evaluation and adversarial regression tests pass before expanding supported repositories |
| **4–9 Dec** | M4 — reliability | Durable local job queue, leases, cancellation, restart recovery, bounded artifacts, practical usage/latency metrics and retention | Restart/cancel cannot duplicate a PR or leave a workload running; limits and cleanup verified |
| **10–13 Dec** | M5 — private beta gate | Held-out benchmark, repeated AI trials, prompt-injection cases, security review of the supported deployment, onboarding, 3–5 testers | Publish honest denominators and failure classes; no unresolved critical issue; a tester completes a verified repair using the docs |
| **14–20 Dec** | M6 — v1 completion | Pilot fixes, reproducible benchmark report, demonstration video, architecture case study, deployment and troubleshooting guide | All supported workflow acceptance gates pass and pilot feedback is triaged; publish an accurate scope and limitation list |

### Schedule control

The finish target is now **20 December**, with **13 December** as the earlier usable-beta target. These are targets, not a promise of unattended daily work. Keep correctness, source freshness, workload isolation, human review and evaluation gates intact.

To make the earlier date realistic, defer multi-tenant SaaS, a PostgreSQL migration, object storage, full OpenTelemetry rollout and TypeScript repair until after v1 unless a measured pilot need requires them. Finish the supported Python workflow before adding platforms. The beta can use a local control plane with a GitHub App and separately controlled workers; shared remote hosting needs its own authentication/isolation gate and must not be rushed into scope.

### Today — 17 November

Implemented in v0.2: named-test identity/outcome checks, conservative failure categories, restored-code counterfactual replay, Git/source fingerprints, stale-source approval prevention, strict structured proposals, bounded provider requests and usage receipts, evidence-v2 metadata binding, and the corresponding workbench views. These complete a substantial part of M1; live Docker/provider validation remains pending.

### 18 November progress

Added the scheduling pilot with three issues, per-run Docker image pinning, execution receipts, a readiness command, and a Linux CI smoke test for all four gates. After the WSL update, the local Docker smoke test and all five scheduling baseline tests passed. Live inference remains pending while the provider key and pilot checkout are unconfigured.

### 21 November progress

Registered the scheduling pilot as a clean local Git checkout. Added an exact source preview, blocking checks for common credential formats, and a review digest revalidated by the API and worker. Verified the preview in the browser and re-ran the four-gate Docker smoke test.

### 23 November progress

The first approved local Ollama patch passed all four Docker gates using an operator-supplied test. The local Git handoff builds the approved repair as one reproducible commit on its verified base and packages it with evidence. The public repository's first Windows, Linux and Docker CI jobs passed. The CLI draft publisher is implemented with tests for retry and stale-base handling. It still needs a live publication run against a configured GitHub target.

### 25 November progress

The workbench can review and confirm publication to a configured GitHub destination. The approved scheduling repair became [draft PR #2](https://github.com/KrishnaBECOE07/Fixforge/pull/2) at the verified base commit. Repeating publication returned the same draft. The scheduling pilot used a fine-grained token and an operator-supplied issue and regression.

### 28 November progress

The GitHub issue-intake and workbench publication changes are on `main`. Two approved scheduling fixes have live draft PRs. The token-based GitHub flow is verified. GitHub App installation and signed webhook intake remain open.

The Benchmark Lab now groups local AI runs by provider, model and regression author. It shows the count that reached review out of completed runs, failure categories and p50/p95 for runs with recorded durations. Older runs can appear with an unrecorded model. The held-out benchmark is tracked separately and remains a release gate.

Remaining effort is estimated at **35–55 focused hours to private beta** and **50–75 hours total to v1**, assuming one developer working within the existing Python-first scope. The largest items are held-out evaluation and repair quality, reliable restart and cancellation, GitHub App intake, then tester onboarding and the release report. The **13 December** beta and **20 December** v1 targets depend on passing the acceptance gates and getting tester feedback in time.

## 6. Prioritized backlog

### P0 — before trusting a real pilot

- Revision identity: implemented commit/status/content fingerprints and approval freshness checks; still validate against a live pilot.
- Provider schema validation: implemented strict structural schema plus local type/size limits; live model compatibility remains to be tested.
- Runner integration: immutable test harness, report collection, timeouts, process cleanup and resource limits on Linux/Windows Docker Desktop.
- Verification quality: implemented named outcomes and conservative failure classes; validate classification across unseen repositories.
- Generated test review: reject trivial assertions, unrelated failures, runner tampering and test-discovery manipulation. Static checks alone cannot fully solve this.
- Source handling: local allowlist, explicit disclosure review and blocking checks for common credential formats implemented. File-by-file disclosure settings and broader detection remain planned.
- Budget: one attempt with configurable source context, output tokens and timeout plus reported token usage is implemented; a dollar spend cap remains planned.

### P1 — essential private beta

- GitHub App read-issue and write-branch/draft-PR scopes separated from merge rights.
- Human approval bound to base revision, patch digest, verification version and publication intent.
- Duplicate webhook and retry idempotency keys.
- Durable tasks with restart-safe transitions and cancellation.
- Dependency/test adapters with curated images; no agent-selected host commands.
- Authentication, ownership checks, CSRF protections, secret storage and retention controls.
- Metrics segmented by repository, model, defect type and execution environment.

### P2 — after measured quality

- Independent reviewer/verifier roles and structured critique.
- Mutation score / restored-bug checks and test minimization.
- Read-only impact graph and reusable repository knowledge keyed by commit.
- Compare multiple candidates under a total cost cap.
- TypeScript support, then Tree-sitter indexing for a second language.
- CI integration and organization policy packs.

## 7. Verification contract

A candidate can reach review only when:

1. The starting test suite discovers tests and passes.
2. A new regression discovers additional tests and fails on original production code.
3. Collection/import failures, timeouts, skips and expected failures cannot masquerade as valid reproduction.
4. The production patch remains within allowed files and size limits; existing tests do not change.
5. The identical named test set passes on a separate patched copy; replacing tests while preserving the count is rejected.
6. Restoring the original production code in a third copy reproduces the same named failure signatures.
7. Source revision, issue, explanation, provider receipt, patch, execution results and event history receive consistent evidence digests.
8. A human reviews the exact patch and the checkout is revalidated before approval; downstream publication will check again.

Current implementation does not prove the new test is causally relevant to the issue; named outcomes, conservative failure classification and restored-code replay improve the evidence. An independent verifier and broader mutation testing remain planned; none of these checks proves semantic relevance.

## 8. Evaluation plan

Three fixture recipes test the plumbing. They are never a claim about model quality.

Build a versioned held-out set of at least 30 small Python defects across 5–8 repositories, including arithmetic boundaries, validation, parsing, state transitions and data handling. Record bug and correct revision, issue statement, setup image, public tests and hidden acceptance tests. Review licenses before redistribution. Keep evaluation fixes and hidden tests out of model context.

Use 20 cases for iterative development and a separate 10-case holdout for a first report; grow the holdout before broad claims. Run repeated trials with a fixed model and budgets. Report sample size and uncertainty.

| Metric | Definition |
|---|---|
| Resolved@1 | Hidden acceptance tests pass after one bounded attempt / all eligible attempted issues |
| Verified candidate rate | Runs satisfying the public verification contract / eligible completed runs |
| False verification rate | Verified candidates failing hidden checks or human correctness review / verified candidates |
| Regression strength | Hidden defect mutations caught by new tests / eligible mutations |
| Scope quality | Human-assessed issue relevance, unnecessary edits and API compatibility |
| Review acceptance | Patches accepted by a human / reviewed verified candidates |
| Cost per resolved issue | Total provider and worker cost / hidden-test-resolved issues |
| Latency | p50/p95 issue-to-review time, broken down by indexing, inference and execution |
| Abstention quality | Appropriate refusal when reproduction or validation is insufficient |

Initial beta goals are hypotheses: at least 40% Resolved@1 on the bounded holdout, below 10% false verification, no hidden test regressions for accepted patches, and no unbounded execution. Publish actual results even if goals are missed. Improve measured weaknesses before expanding scope.

## 9. Reliability and security

Treat issue text, repository content and model output as untrusted. Data cannot grant permissions. Keep provider/GitHub credentials in the control plane, never in a workload. No arbitrary shell generation. No automatic dependency installation from repository scripts. Limit files, runtime, logs, memory, processes, attempts and inference output.

For shared deployment, use separate workers with stronger kernel isolation, authentication, per-run ownership, encrypted credentials, network egress policies, artifact retention, incident response and a security review. Local SQLite hashes are useful integrity checks but can be rewritten by an operator controlling the database. Signed, externally anchored attestations are a later feature.

## 10. Cost and resourcing

The demo uses local compute and no paid API. Do not assume API pricing or create subscriptions as part of the plan. Start real pilots with a manually configured provider budget.

Per-run cost = input tokens × current input price + output tokens × current output price + worker seconds × worker rate + storage and network. Verify current prices when selecting a model and deployment service. Log actual usage before setting a dollar target. Enforce a maximum token budget, attempt count, wall time and concurrency independently of billing alerts.

Begin with one local control plane and one worker. Add hosted infrastructure only for the multi-user pilot. Budget engineering time for evaluation and failure analysis, not only new features: roughly 40% core repair, 25% verification/evaluation, 20% integration/reliability and 15% experience/docs during the initial five-week delivery window.

## 11. Risks and mitigations

| Risk | Response |
|---|---|
| Plausible incorrect fix passes weak tests | Hidden tests, independent verifier, human review and mutation checks |
| Malicious code escapes or tampers with runner | Local trusted-first scope, fixed commands, isolated dedicated workers, stronger sandbox before SaaS |
| Model follows repository instructions | Separate instructions/data, tools unavailable to planner, enforce permissions outside model |
| Dependency/environment failures appear to be bugs | Approved images, structured failure classes, baseline required, refuse ambiguous verification |
| Uncontrolled spend/retries | Hard per-run budgets, bounded attempts and recorded token usage |
| GitHub writes target wrong revision | Pin base/head, patch digest approval, stale-base rejection and idempotent draft publishing |
| Demo results overstate capability | Label demo mode throughout; separate recipe, AI and held-out metrics |
| Scope becomes too broad | Python first; cross-language and shared hosting require quality gates |

## 12. Portfolio and launch story

Show a three-minute demonstration: issue → actual failing regression → minimal patch → passing suite → diff and evidence → human review. Include one unsuccessful attempt to demonstrate abstention. Publish a clear architecture diagram, threat model, reproducible evaluation command, test/CI evidence and a candid limitation list. Distinguish implemented, evaluated and proposed capabilities on the project page.

## 13. Definition of done

Each milestone requires usable source, reproducible setup, appropriate automated checks, browser verification for interface changes, failure evidence, documented limitations and a concrete artifact a reviewer can inspect. “AI generated a patch” is insufficient; verified behavior and reviewability are the bar.
