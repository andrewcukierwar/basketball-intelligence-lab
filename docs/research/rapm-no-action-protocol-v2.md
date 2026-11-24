# Period-end pseudo-possession exclusion: frozen addendum protocol v2 (2022–23)

**Status:** Frozen before any evaluation run on the variant B row set `issue-82-B-v1` ([issue #82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82)). **Classification:** Original BIL design. It follows the maintainer decision of 2026-11-23 recorded in [ADR-0019](../DECISIONS.md) and supersedes the [v1 addendum](rapm-no-action-protocol.md) for the canonical row set. The v1 addendum and its results stay as the sensitivity record for variant A. Results go in [the no-action report](rapm-no-action-2022-23.md), written after the runs. A change here after a run starts is a deviation and is listed in that report.

## Decision and eligibility rule

Variant **B** (canonical) excludes from model rows only accepted possessions whose first event is `period_end`. The [period-end audit](../../scripts/audit_period_end_possessions.py) confirmed on the pinned pilot that these 962 possessions have no shot, free throw, turnover, foul, violation or jump ball, no score delta or allocation, zero game-clock duration, and no period-boundary span, and are followed by `period_start` or the end of the stream. Eligibility depends on the possession's first event, never on later actions or realized outcomes. Real possessions with intentional run-outs, held balls or other no-action outcomes stay in model rows.

The rule was fixed by the maintainer's decision, not chosen by comparing RAPM with the context-only comparator, and no comparison below can change it.

| Variant | Rule | Role |
| --- | --- | --- |
| B | Exclude accepted possessions whose first event is `period_end` (`period_end_pseudo`) | Canonical |
| A | Exclude accepted possessions with no shot, free throw, turnover, foul or violation event (`no_action`) | Sensitivity (`issue-82-v1`) |
| C | Keep all | Sensitivity (`issue-59-v1`) |

By construction the eligible sets are nested, A within B within C. The runner checks it.

## Frozen inputs

| Item | Value |
| --- | --- |
| B row set | `issue-82-B-v1`, 223,077 model rows from 1,292 accepted games, built at `d404c2da036ce0129914ae310cf53230c149f46f` from pilot `issue-19-v6` (manifest SHA-256 `89cb2e82…1570`) |
| B `build_id` | `7b8c6449085bbc49aead39cde681bd7fe9ae7e9a5952f3ac04342cdd1892eac3` |
| B `manifest.json` SHA-256 | `2cc2b765c2f6ff4e1802098fa03c7040f458208c9a535906da8f804e08692c20` |
| B `model_row.parquet` SHA-256 | `cf1236b71aedf51513414bf3d7c57ac8a3b69978f0c989276ad1f9a312702a86` |
| B `game_reconciliation.parquet` SHA-256 | `5a0d001711ac29889c2be955fdbec0874330c8bd91689548aafb5abfa254a008` |
| A row set | `issue-82-v1`, manifest SHA-256 `507e11c545027719f8c8580220862665bfb6803b5d6b95a6ef939d47c2556d7f`, 223,036 rows |
| C row set | `issue-59-v1`, the frozen #59 pins, 224,039 rows |
| Evidence tier | `retrospective_capture_bound` |
| Scope | 2022–23 only. No 2023–24 or later data and no EPM output is read. |

The A and C model rows are unchanged by the later builder revision (the row contract revision changed only to add variants). Runners verify each manifest digest and the listed table digests before reading rows.

## Runs

Unchanged from #23 and #24: folds R1 to R4 and P1, the `played_before` fit rule, estimator, response scale, penalty grid {250 … 32,000}, $\lambda$ = 4,000 for all #24 variants, bootstrap (2,000 game-clustered resamples, seed 2023, 95% percentile), variants and verdict rule.

1. **#23 baseline on B:** `bil.models.rapm.baseline` to `issue-82-B-baseline-v1`, with `--pin-manifest-sha256` of B. The grid reselects $\lambda$. If it is not 4,000, that is reported.
2. **#24 context ablation and #77 comparators on B:** `bil.models.rapm.context_ablation` to `issue-82-B-context-v1`.
3. **Common-cohort comparison of A, B and C:** `bil.models.rapm.cohort_comparison` to `issue-82-cohort-v1`. Each variant's zero-context RAPM ($\lambda$ = 4,000) is fit on that variant's own rows at each fold, and the league mean is the fit-window mean of the same rows. All three are scored on the same held-out possessions.
   - **Primary:** the strictest cohort, held-out rows in R1–R4 eligible under A. Reported per variant: MSE for RAPM and league, and RAPM minus league with a game-clustered interval. Paired differences of RAPM MSE: B−C, A−C and A−B, with intervals.
   - **Secondary:** each variant's own held-out cohort (RAPM minus league per variant). MSE levels are not comparable across cohorts.
   - Context terms are not part of the common-cohort comparison. They are reported on B's own cohort in run 2.

All runs start from a clean working tree, write to new directories and use the same code commit.

## Reported comparisons

- Reconciliation of B against C and A (counts and points).
- B's #23 and #24 results beside the published C (#23, #24) and the A results from the v1 report.
- The common-cohort table. It estimates how the exclusion changes the fit on identical test possessions. It does not choose a rule.
