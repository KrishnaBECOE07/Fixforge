# Four-case repair evaluation

This evaluation exercises FixForge against four functional defects in two small, project-owned Python repositories. It uses a live local model and independent `unittest` checks in Docker. The inventory and dispatch fixtures use only the standard library.

| Case | Expected behavior |
|---|---|
| `shipment_count` | Count a partial shipment and preserve integer precision for large orders |
| `restock_queue` | Sort by priority and preserve arrival order for ties |
| `normalize_zone` | Collapse mixed whitespace into a single hyphen separator |
| `next_departure` | Include departures at the exact ready hour |

## Reproduce the evaluation

Install the dependencies in `requirements.lock`, start the Linux Docker engine and pre-pull `python:3.11-slim`. Start [local Ollama](../../README.md#run-ollama-locally) with `qwen3:4b` available. From the FixForge root, run this in the project’s Python environment.

```text
python -m examples.evaluation.run
```

Use `--case next_departure` to run one case, or repeat `--case` to select several. `--model` and `--image` let you choose another local model or pre-pulled image. Each invocation creates a new trial directory under `.fixforge/evaluation/` by default. It saves the per-case workbench evidence and a JSON report with run IDs, source and acceptance-test hashes, the image ID, model limits, and independent test outcomes. An infrastructure failure before a case can be attempted stops the evaluation. A model attempt that fails a gate remains in the reported denominator.

## How cases are scored

1. The runner copies the public fixture into a new workspace. The public baseline must pass, and independent tests must reproduce the target defect with the public tests still green.
2. It submits the case through FixForge’s source review and run API. Ollama receives the issue and the public Python files. The independent acceptance tests are kept outside the reviewed source tree. The model makes one attempt and writes its own regression.
3. A candidate counts as **reached review** if FixForge completes all four gates and the evidence passes its integrity check.
4. The runner applies the candidate’s production edits to the independent-test workspace. A case counts as **resolved** if the same named public and independent tests all pass there.

This is a small reproducible evaluation of the project-owned cases. The independent tests are published here so others can rerun them. Replays can vary with the model, and the sample only covers these four defects.
