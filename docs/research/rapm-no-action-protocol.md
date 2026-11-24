# No-action possession exclusion: frozen addendum protocol (2022–23)

**Status:** Frozen before any evaluation run on the `issue-82-v1` row set ([issue #82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82)). **Classification:** Original BIL design. It changes one input of the [#23 baseline protocol](rapm-baseline-protocol.md) and the [#24 context protocol](rapm-context-protocol.md), and nothing else. The results go in [the no-action report](rapm-no-action-2022-23.md), written after the runs. Any change here after a run starts is a deviation and is listed in that report.

## What changes and what does not

Only the row-set pin changes: `issue-59-v1` becomes `issue-82-v1`, built by `python -m bil.data.rapm_rows` from the same pinned pilot `issue-19-v6` (manifest SHA-256 `89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570`). The new build removes no-action possessions from the model rows, as [ADR-0019](../DECISIONS.md) decides. A no-action possession is an accepted possession with no shot, free throw, turnover, foul or violation event in its own half-open sequence interval. All such possessions score 0 control points, which the builder enforces.

Unchanged from #23 and #24: folds R1 to R4 and P1, the `played_before` fit rule, estimator and response scale, the penalty grid {250, 500, 1000, 2000, 4000, 8000, 16000, 32000}, $\lambda$ = 4,000 for every #24 variant, the game-clustered bootstrap (2,000 resamples, seed 2023, 95% percentile), the variants and verdict rule of #24, and the adjudication-strata sensitivity. Covariate construction and the timing audit are unchanged and read the same pilot tables.

## Frozen inputs

| Item | Value |
| --- | --- |
| Row set | `issue-82-v1`, 223,036 model rows from 1,292 accepted games |
| `build_id` | `b5a0a64093ffc7d09159998eb4147640dc0a8868cee10602a6fcf1a447909b5c` |
| `manifest.json` SHA-256 | `507e11c545027719f8c8580220862665bfb6803b5d6b95a6ef939d47c2556d7f` |
| `model_row.parquet` SHA-256 | `ce19cf3d47e92d4cf68371b779876b6278d1fa56e4dc2f39e72666978d6979a3` |
| `game_reconciliation.parquet` SHA-256 | `db4fa774da51c9e6a6ddbbedb92f19a50b26e131bae917c5a56ca02fe639dd07` |
| Row-builder commit | `d2f36a5919f1b5b714853964c61d3d8dec2bad7b` |
| Pilot and pilot tables | As in the #24 protocol |
| Evidence tier | `retrospective_capture_bound` |
| Scope | 2022–23 only. No 2023–24 or later data and no EPM output is read. |

The runners take `--pin-manifest-sha256 507e11c5…6d7f`. They verify that manifest digest and the digests it lists for the model rows and game reconciliation, and the `build_id`, before reading any row. The #23 and #24 pins remain the defaults.

## Runs

1. #23 baseline: `python -m bil.models.rapm.baseline <issue-82-v1> <issue-82-baseline-v1> --pin-manifest-sha256 …`. It reselects $\lambda$ on the grid by the #23 rule. If the selection is not 4,000, that is reported as a finding, and the 4,000 results are read from the grid table.
2. #24 context ablation: `python -m bil.models.rapm.context_ablation <issue-82-v1> <issue-19-v6> <issue-82-context-v1> --pin-manifest-sha256 …`, including the #77 context-only comparators.

Both runs start from a clean working tree and write to new directories.

## Reported comparisons

Each is the `issue-59-v1` value beside the `issue-82-v1` value, with the same intervals:
- The zero-context player delta against the league mean (pooled R1–R4 and P1), and the selected $\lambda$.
- The time (`T_fit`), score, home and `HST_fit` deltas against C0.
- The context-only comparators against the league mean, and player RAPM's further gain on top of context.
- The end-of-period coefficient, and in-sample shifts of the final player estimates.

The numbers on the `issue-59-v1` side are the published #23 and #24 values. They are not rerun. The two row sets differ in one respect, so the contrast is descriptive. The held-out possession set also changes with the exclusion, so MSE levels are not directly comparable and deltas are the quantities of interest. No variant or threshold is chosen from this comparison.
