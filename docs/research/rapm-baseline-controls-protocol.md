# RAPM baseline controls: frozen protocol addendum (2022–23)

**Status:** Frozen before the first run of the remaining items of [issue #77](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/77). **Classification:** Original BIL design, an addendum to the [#23 baseline protocol](rapm-baseline-protocol.md) (fold design, estimator, response, bootstrap and reporting rules are inherited unchanged unless stated here). The context-only comparator of #77 was delivered by [#24](rapm-context-ablations-2022-23.md) and is not repeated. The results are in [the controls report](rapm-baseline-controls-2022-23.md), written after the run. Any change after the run starts is a deviation and is listed there.

## What was looked at before freezing

The #23 and #24 reports (public before this protocol) and ADR-0019. No split-penalty score, random-exclusion statistic or new diagnostic was computed before this freeze. The runner and tests were written alongside this document and are committed after it. The 49-cell grid and the number of draws were chosen from the #23 grid and the cost of a fit (about 0.3 s), not from any result.

## Frozen inputs

| Item | Value |
| --- | --- |
| Row set | `data/processed/2022-23/issue-82-canonical-v1` ([ADR-0019](../DECISIONS.md), identical to #59 `issue-59-v1` in `model_row.parquet`) |
| `manifest.json` SHA-256 | `bd25cd0a8fe3702f5ae9021a435571224a3022c036d529f80b6e8ce108b56488`, passed as `--pin-manifest-sha256`. The runner verifies it and the listed `model_row.parquet` and `game_reconciliation.parquet` digests, the `build_id` and the evidence tier before reading rows. |
| Evidence tier | `retrospective_capture_bound` |
| Scope | 2022–23 only (regular season and playoffs). No 2023–24 or later data and no EPM output is read, used or compared. |
| Output | `data/processed/2022-23/issue-77-v1` (new directory, never committed) |

## Item 1: separate offense and defense penalties

Estimator: the #6 sparse ridge with a different penalty on the offensive block and the defensive block ($\lambda_{off}$, $\lambda_{def}$), unit weights, an unpenalized intercept, zero prior, response 100 × points. This is the verified `_solve_rapm` path of [#61](rapm-prior-centered.md). It is checked against a dense augmented least-squares oracle on synthetic data, and a cell with equal penalties is the same code path as the #23 fit.

**Grid.** $\lambda_{off}, \lambda_{def} \in$ {500, 1,000, 2,000, 4,000, 8,000, 16,000, 32,000}, 49 cells, centered on the #23 $\lambda^\*$ = 4,000. If the best cell lies on an edge of either axis, that axis is extended by one factor of two on that side (new cells only) and selection repeats, at most 4 times in all. An extension is recorded as a deviation.

**Selection.** Every cell is fit on the fit rows of folds R1–R4 exactly as in #23 (fit rows strictly before each cutoff) and scored on the held-out blocks. The selected cell $(\lambda_{off}^\*, \lambda_{def}^\*)$ has the lowest pooled R1–R4 possession MSE. Ties go to the first cell in (offense, defense) order. The playoff fold P1 is fit and scored **only after** selection and never enters it.

**Comparators.** (1) The single-penalty fit at (4,000, 4,000), the #23 choice, fixed before this run. (2) The best equal-penalty (diagonal) cell on R1–R4, reported alongside. (3) The league mean B0.

**Reported.** The full 2-D pooled R1–R4 MSE surface. For the selected cell, per fold and pooled R1–R4 and for P1: MSE, delta against the single-penalty fit and against B0 on identical possessions (MSE(split) − MSE(comparator), negative is better), the offense-only and defense-only ablation deltas, and 95% game-clustered percentile intervals (2,000 resamples, seed 2023, the #23 bootstrap). The final fit on all rows at the selected cell, with the shift in estimates against the single-penalty final fit (RMS, maximum, correlation) and the estimate spread.

**Reading rule (frozen).** The pooled R1–R4 delta is **optimistic** because the cell was chosen among 49 on those folds. Only P1 is independent of the choice. The split penalty is reported as an improvement on held-out data only if the P1 delta against the single-penalty fit is negative with a 95% interval excluding zero. Otherwise it is reported as not distinguishable, whatever the R1–R4 numbers show. P1 is one 84-game block, so a null there is a weak statement, and the report says so.

## Item 2: size-matched random-game exclusion control

**Observed effect.** The #23 stratum exclusion: every game carrying a non-routine adjudication stratum (all strata except `same_clock_free_throw_substitution`, `technical_free_throw`, `overtime`) is dropped from the fit rows of every fold and of the final fit, with the penalty fixed at the single-penalty (4,000, 4,000) so the comparison reproduces #23. Held-out target sets never change.

**Statistics, for the observed set and every random set** (an exclusion fit compared with the full fit at the same penalty):
1. `mse_delta_regular`: pooled R1–R4 MSE of the exclusion fit minus MSE of the full fit on all held-out possessions.
2. `mse_delta_playoff`: the same on the P1 fold (fit rows: regular season only, so playoff games enter only through scoring).
3. `total_rms_shift`, `offense_rms_shift`, `defense_rms_shift`: root-mean-square shift of the final all-rows fit's estimates for players present in both fits (the #23 `estimate_shift`), and `total_correlation`.
4. `players_dropped`: players in the full fit and absent from the exclusion fit.
5. `possessions_removed`.

**Random draws.** The observed set has $n$ games, of which $n_t$ are of each season type $t$. A random set takes exactly $n_t$ games of each type, without replacement, from the accepted games that carry **no** non-routine stratum ("ordinary games"). Two matching variants are run:
- **A (primary):** match on size and season type.
- **B (secondary):** additionally match on the date block of #23 (the same $n$ games per block as the observed set, using blocks bounded by 2022-12-15, 2023-01-15, 2023-02-15, 2023-03-15 and 2023-04-15), so the number of excluded games inside each fold's fit window is comparable.

300 draws per variant. Draw $d$ of variant $v$ (A = 0, B = 1) uses `numpy.random.default_rng([77, v, d])`, drawing from the sorted game IDs of each matching cell. A cell with fewer ordinary games than the observed count aborts the run. The draws are fully reproducible from these seeds.

**Comparison.** For each statistic the observed value is placed in the draws' distribution: the draws' mean, sd, 2.5th and 97.5th percentile, and the empirical tail probability $p = (1 + \#\{\text{draws at least as extreme}\}) / (N + 1)$. "Extreme" means larger for the three RMS shifts and for $1 -$ `total_correlation` and `players_dropped`, and larger in absolute value for the two MSE deltas. The draws differ from the observed set in possessions removed, so the report also gives the draws' `possessions_removed` and repeats the comparison for the draws within ±10% of the observed possessions removed (with their count). These are descriptive. There is no multiplicity correction, and the empirical $p$ answers only "is the stratum effect unusual against removing the same number of ordinary games". It does not say the strata are harmless or harmful.

## Item 3: per-fit solver diagnostics

Every fit in the run is recorded in `results.json` under `fits`: stage, fold, penalties, rows, LSQR stop code, iterations, scaled residual norm, condition estimate and wall seconds. This covers the grid, P1, the exclusion fits, the final fits and every random-control fit. The `optimizer` block summarizes them (stop-code counts, iteration min, median and max, maximum condition estimate, total fit time) with peak resident memory of the run. The solver raises on a non-converged stop, so a completed run has every fit converged.

## Run manifest

As in #23: pinned inputs and verified digests, this document's SHA-256, the code commit and whether the working tree was clean, library versions, runtime, peak memory, output SHA-256 values and the evidence tier. The run is made once from a clean working tree after the runner commit.

## Not in scope

Priors, context terms and the split-half stability fit at the split penalty. The #23 stability result is not re-derived. Any repeat of the run with changed settings is a new, labelled sensitivity run.
