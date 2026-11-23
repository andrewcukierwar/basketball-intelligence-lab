# Agent run — Synthetic offensive and defensive RAPM

- **Date:** 2026-11-23
- **Status:** Implementation and independent review complete. Awaiting maintainer review and merge.
- **Related issue:** [#6](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/6)
- **Branch, commit and PR:** `codex/issue-6-synthetic-rapm`, code at `51b00c6`, [PR #18](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/18).

## Objective and scope

Verify a sparse, zero-prior RAPM fit using known offense and defense effects, a dense reference and sensitivity cases. All model inputs are generated. The run uses no NBA data, published ratings or historical cutoffs.

## Work completed

- Read Claude’s M1 handoffs and checked the branch ancestry. The 1,290-game pilot and the external verification in [PR #16](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/16) are integrated into `main` at `cd673dd`. The 1,292-game archived-feed adjudication in [PR #17](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/17) was merged into `claude/issue-5-external-verification`. Issue #6 starts from `main` and has no data dependency on #17.
- Added a typed five-on-five possession design, sparse weighted ridge estimation and a reproducible generator. The estimator uses separate signs and player blocks, an unpenalized intercept and zero-mean player effects in each block. [Estimator specification](../research/rapm-synthetic.md) · [ADR-0012](../DECISIONS.md#adr-0012--center-the-zero-prior-rapm-player-blocks-separately)
- Independent review found a wrong intercept on an extreme penalty and effects lost on tiny nonzero outcomes. Fixed the first with exact weighted profiling of the intercept and the second with response rescaling. Added regression checks for both and for common rescaling of weights and penalty. [Fixes](https://github.com/andrewcukierwar/basketball-intelligence-lab/compare/c092767...51b00c6)

## Verification

| Check | Observed result |
| --- | --- |
| Locked Python 3.12.13 with `dev`, `pilot` and `rapm`; `python -m pytest -q` | 39 passed, including 22 RAPM cases. |
| Locked Python 3.11.17 with `dev` and `rapm`; `python -m pytest -q tests/test_rapm.py` | 22 passed. |
| `ruff check .`, `ruff format --check .`, `mypy src` and `git diff --check` | All passed. |
| `python -m bil.models.rapm.synthetic` | Effect RMSE 0.000005501 on the noiseless fixture. The paired rotation hides individual effects even when combined fitted rates are accurate. The weak-ridge 48-row fit scores worse than the baseline. [EXP-0005](../experiment-log.md#exp-0005--synthetic-offensivedefensive-rapm) |
| Fresh-context GPT-6.2 Astra review of GPT-6.2 Sol’s implementation | Both numerical issues fixed and rechecked. Reviewer cleared code at `51b00c6` and reran the 22 RAPM tests. |
| GitHub Actions | See the [checks for the current PR head](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/18/checks). |

## Limits and next actions

The synthetic result covers one additive data-generating process. It does not establish NBA exposure or regularization choices. Before a historical fit, specify the canonical possession-to-row mapping, disposition of rows that span lineup changes, and contamination and exclusion checks by reconciliation stratum. Record which pilot revision feeds that fit, then follow the [rolling-origin contract](../validation-strategy.md).
