# Security and trust boundaries

FixForge v0.2 is a single-user loopback development application. It is not a hostile-code execution service and must not be exposed to the public network.

## Boundaries

1. **User intent vs external data.** Issue descriptions, repository comments, supplied regression code and model responses are data. None may grant access or alter repair policy. The control plane defines permissions independently of the model.
2. **Control plane vs workload.** API and GitHub credentials stay in server environment. They are not injected into the test container. The planner has no executable tools and returns a bounded proposed edit.
3. **Original checkout vs snapshot.** Browser requests select a server-registered repository ID. The engine reads a bounded copy; it does not write into the source checkout. Hidden paths, traversal, symlinks and known dependency/build directories are excluded.
4. **Candidate vs verified patch.** Existing tests cannot be edited. A regression must fail on original production code, existing named tests must remain green, and the identical named suite must pass after changes. Restored-code replay must bring back the same failure signature. Failed or incomplete work cannot be approved or exported as verified evidence.
5. **Verified patch vs publication.** A local decision binds the patch, source-identity and manifest digests. Repository approval revalidates source freshness and rejects changed or unregistered checkouts. The operator invokes publication separately using a repository allowlist and a scoped token. FixForge writes a repair branch and a draft only. The operator manages merge permissions and GitHub branch rules.

## Docker runner

Real runs use a pre-pulled image with `--pull=never`, non-root UID, no network, read-only root and source mounts, all capabilities dropped, no-new-privileges, a temporary limited `/tmp`, 64-process / 256 MB / one-CPU limits, and a 30-second test timeout. The immutable test harness is mounted outside the source tree. The Docker socket is never mounted inside the workload. Timeouts attempt to remove the named container as well as terminating the CLI. Output is continuously drained and only a bounded 256 KB tail is retained. Structured test outcomes are stored separately from the human-readable transcript. A report missing from the retained tail cannot pass verification.

These restrictions reduce the impact of mistakes; containers share a kernel and are not a complete boundary against malicious code. A hostile repository may tamper with Python internals, test discovery or output. Before a shared service, introduce stronger isolation, report collection outside the workload, pinned image digests, dedicated ephemeral workers and independent security review.

Only built-in deterministic fixture recipes can use local Python. Issue text and arbitrary user paths cannot opt into that mode. Never add a host execution fallback when Docker fails.

## Local web boundary

The launch command permits loopback binding only. The API validates Host against local names, rejects cross-origin writes, requires JSON for mutations, sends no permissive CORS policy, escapes content through React and sets basic browser security headers. The Vite development origin on port 5173 is explicitly allowed. These are defenses for a local tool, not a substitute for authenticated multi-user authorization.

## Data and retention

`.fixforge/` contains snapshots, diffs, issue content, test logs, review notes and an SQLite database. `.env` contains credentials. Both are ignored by Git. AI repairs require a local review of the exact issue text, selected source and any supplied regression. FixForge blocks common credential formats and some literal secret assignments. The check can miss credentials and other sensitive data. The operator can remove flagged content and request a fresh preview. The Ollama adapter connects directly to loopback, rejects models listed as remote, and uses Ollama with cloud features disabled in the documented setup. OpenAI receives the reviewed context over HTTPS with `store=false`. Provider account and retention policies still apply.

No automatic deletion policy is implemented. The operator manages local data. Do not put `.fixforge` into public sync or artifact storage. Snapshots accumulate; quotas and retention are planned. The default project folder may itself be synced by the operator's filesystem provider; set `FIXFORGE_DATA_DIR` outside synced storage for private work.

## Known limitations

- AST safety checks are heuristic and bypassable. They are a rejection filter, not a sandbox or a security proof.
- New tests can be weak, irrelevant or manipulated despite fail-before/pass-after checks. Human review, hidden evaluation and an independent verifier remain necessary.
- Failure classification rejects collection/import/environment and test-authoring errors as defect evidence. This is conservative, not a causal or semantic correctness proof. In-process Python tests can still tamper with Python internals; shared hostile workloads need stronger report isolation.
- Git and content checks observe state at capture, evidence sealing, approval and publication. The draft API can race a base update. FixForge checks the returned base and reports a mismatch for human review.
- Evidence uses local hashes, not cryptographic signatures or external timestamping.
- One local server/worker is assumed. Durable task leases, multi-process concurrency and authenticated users are not implemented.
- Model/network errors are not retried. Restarted incomplete work is marked failed.
- No arbitrary package installation or test command selection is supported.
- No production security guarantees are made from passing unit tests or Docker flag inspection.

Keep secrets out of issue text, source and test output. When reporting a vulnerability, provide a minimal local reproduction without real credentials or private repository data.
