# Agent run — OpenRAPM solver benchmark

- **Date:** 2026-11-23
- **Status:** Implementation and verification complete. Independent review and publication pending.
- **Issue:** [#21](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/21)
- **Branch and implementation:** `codex/issue-21-open-rapm-benchmark`, base `d3d01f3`, code and results `5feced5`.

## Scope and decisions

Benchmark BIL's sparse zero-prior solver using generated possessions, without accessing historical outcomes. The adapter runs OpenRAPM's own matrix and weighted ridge routines at a pinned MIT-licensed revision. The comparison uses the same two role blocks, supplied sample weights, raw scoring response scale and free intercept. OpenRAPM's defense coefficients use the opposite sign. The benchmark uses the least-squares objective shared by both libraries, with published pipeline settings outside the comparison. [Specification and results](../research/rapm-open-benchmark.md)

## Verification

| Check | Observed result |
| --- | --- |
| `uv run --locked --extra rapm --with pandas==3.0.6 python scripts/benchmark_openrapm.py "$openrapm_dir"` | Four cases passed. Largest player coefficient and fitted-rate deltas were `3.429e-10` and `6.790e-10` points per 100 possessions against `1e-8` tolerance. |
| Same command with `--offline` after dependency resolution | Same four results with Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1 and pandas 3.0.6. |
| Run with an altered copy of the reference source | Rejected the file on SHA-256 mismatch. |
| `python -m pytest -q`, `ruff check`, `ruff format --check`, `mypy src`, `git diff --check` | 43 tests passed with the existing locked environment. All other checks passed. |

The first offline attempt lacked a cached pandas wheel for Python 3.14. One online dependency resolution made subsequent runs offline. No repository dependency changes were needed.

## Next action

Review the precise implementation diff and benchmark evidence before marking the issue complete. Use the historical RAPM row contract and rolling-origin evaluation for subsequent real-data fit work.
