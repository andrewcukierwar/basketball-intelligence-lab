# Agent run — Alternate lineup exposure in RAPM

- **Date:** 2026-11-24
- **Issue:** [#110](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/110)
- **Status:** Development study completed locally. Independent review and publication pending.
- **Branch:** `codex/issue-110-lineup-exposure-study` from `3749944`
- **Protocol and run code:** `b76e2c41e2ec7e4e52198a01b83f224b994af387` frozen before profiling and fits, runner `d5b319aaa7ca1e5e95a894fc346b2127fd8788ad`.

## Scope and results

Profiled multiple-lineup exclusions in 2021–22 and 2022–23. Excluded opportunities are concentrated by period, clock and score state, and their omitted exposure varies by player and team. Compared entry lineups and clock-fractional training exposures with frozen W2 on the exact same stable held-out possessions. Both alternatives failed the frozen recommendation gate. The recommendation retains the stable-lineup reference. [Protocol](../research/rapm-lineup-exposure-protocol.md) · [Aggregate report](../research/rapm-lineup-exposure.md)

The runner accessed only the 2019–20 through 2022–23 pinned development inputs. It wrote the aggregate run output to `/tmp/bil-issue-110-development-v1.json`, SHA-256 `dad70ea4f24d8ab7c8bfed7a4a8a993a452f79de83f88c078a172a3444ff4cd2`. Source data and outcome rows stayed outside version control. File names in the processed-data parent were visible during setup. The runner loaded no outer or confirmatory season content.

## Verification

| Check | Observed result |
| --- | --- |
| Signed ledger, disposition and sequence/clock overlap audits | Four seasons passed. All accepted control points reconciled to source allocations. Stable rows matched canonical dates, lineups, point totals and unit weights. |
| W2 reproduction, only the development scores | Matched 418,731 regular and 28,351 playoff stable possessions and prior pooled MSE and team-game RMSE to the runner's tolerance. |
| 30 reference/entry/fractional fits | Converged. Total run time 17.9 s, peak memory 1,494 MiB. |
| `PYTHONPATH=src python -m pytest -q` with shared project Python | 338 passed, 2 skipped. Focused SQL and fractional design fixtures passed. |
| `ruff check`, `ruff format --check`, `mypy src`, `git diff --check` | All passed. |

The first ad hoc reporting command used an older system Python that did not support `zip(strict=True)`. Running it in the project environment produced the recorded summaries. No protocol or fit configuration changed.

## Next action

Review and integrate the report and study runner. The results do not justify changing the canonical estimand. A future substitution-specific model would need separately registered scoring coverage for multiple-lineup possessions.
