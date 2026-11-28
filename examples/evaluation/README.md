# Four-case repair evaluation

This evaluation exercises FixForge against four functional defects in two small, project-owned Python repositories. It uses a live local model and independent `unittest` checks in Docker. The inventory and dispatch fixtures use only the standard library.

| Case | Expected behavior |
|---|---|
| `shipment_count` | Count a partial shipment and preserve integer precision for large orders |
| `restock_queue` | Sort by priority and preserve arrival order for ties |
| `normalize_zone` | Collapse mixed whitespace into a single hyphen separator |
| `next_departure` | Include departures at the exact ready hour |

## Results from 28 November 2026

All three trials used local `qwen3:4b`, one model attempt per issue, and the same Linux amd64 Docker image. Each independent test suite reproduced its target defect on the original code before inference.

| Trial | Reached review | Resolved by independent tests |
|---|---:|---:|
| Full-file edits, model-written regression | 0/4 | 0/4 |
| Exact text replacements, model-written regression | 0/4 | 0/4 |
| Exact text replacements, operator-supplied regression | 2/4 | 2/4 |

| Case | Full-file edits with model regression | Exact edits with model regression | Exact edits with operator regression |
|---|---|---|---|
| `shipment_count` | Ollama returned HTTP 500 | Regression omitted the production function import | Resolved. All 8 independent and public tests passed, including a large-integer precision check |
| `restock_queue` | Patch used an unsupported `sorted` argument | Regression omitted the production function import | Patch still sorted ties incorrectly |
| `normalize_zone` | Patch removed a neighboring function and mishandled tabs | Patched suite failed | Patch referenced `re` without importing it |
| `next_departure` | Proposal contained invalid Python | Proposal targeted a file outside the reviewed source | Resolved. All 7 independent and public tests passed, including midnight and end-of-day boundaries |

The first trial exposed collateral edits from full-file responses. Exact replacements let FixForge preserve the source outside the matched snippet and reject edits to unreviewed files. Generated regression errors and incorrect patches still prevented repairs. The attempts are a case study of the workflow and the failure gates. The same four defects were reused across trials, and model outputs can vary between runs.

The independent verification runs used image `sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`. The two resolved runs were `5b764cfe3fc0` and `c56a8df045c9`. Each passed the four workbench gates before independent verification.

## Reproduce the evaluation

Install the dependencies in `requirements.lock`, start the Linux Docker engine and pre-pull `python:3.11-slim`. Start [local Ollama](../../README.md#run-ollama-locally) with `qwen3:4b` available. From the FixForge root, run this in the project’s Python environment.

```text
python -m examples.evaluation.run
```

Use `--case next_departure` to run one case, or repeat `--case` to select several. `--model` and `--image` let you choose another local model or pre-pulled image. Each invocation creates a new trial directory under `.fixforge/evaluation/` by default. It saves the per-case workbench evidence and a JSON report with run IDs, source and acceptance-test hashes, the image ID, model limits, and independent test outcomes. An infrastructure failure before a case can be attempted stops the evaluation. A model attempt that fails a gate remains in the reported denominator.

Run `python -m examples.evaluation.run --operator-test` to measure the same cases with a short operator-supplied regression for each public issue example. The independent acceptance tests still run separately.

## How cases are scored

1. The runner copies the public fixture into a new workspace. The public baseline must pass, and independent tests must reproduce the target defect with the public tests still green.
2. It submits the case through FixForge’s source review and run API. Ollama receives the issue and the public Python files. The independent acceptance tests are kept outside the reviewed source tree. The model makes one attempt. By default it writes its own regression.
3. A candidate counts as **reached review** if FixForge completes all four gates and the evidence passes its integrity check.
4. The runner applies the candidate’s production edits to the independent-test workspace. A case counts as **resolved** if the same named public and independent tests all pass there.

The independent tests are published here so readers can reproduce the verification procedure.
