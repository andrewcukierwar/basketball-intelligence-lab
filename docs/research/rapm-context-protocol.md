# Context ablations of the zero-prior RAPM baseline: frozen protocol (2022–23)

**Status:** Frozen before the first evaluation run of [issue #24](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/24). It also covers the first item of [#77](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/77), the context-only comparator. **Classification:** Original BIL design. Every context family is an **Experimental** BIL hypothesis about [EPM-U08](epm-uncertainties.md). It does not replicate EPM's unpublished home-court and rubber-band adjustment. The results go in [the ablation report](rapm-context-ablations-2022-23.md), which is written after the run. Any change to this document after the run starts is a deviation and is listed in that report.

## What was looked at before freezing

The runner and tests were written before this document. Before freezing, only covariates were inspected: the timing audit below, neutral-site flags, possession counts by stratum, the margin distribution and column means. No response, residual or held-out score was computed for any variant. The #23 results ([report](rapm-baseline-2022-23.md)) were public before this protocol, and they fix the folds and $\lambda$.

## Frozen inputs

| Item | Value |
| --- | --- |
| Row set | [#59](rapm-historical-rows.md) `issue-59-v1`, the same pins as [#23](rapm-baseline-protocol.md): `build_id` `bc7b0174…b45`, `manifest.json` `0accaa15…a22`, `model_row.parquet` `ebadd151…d90`, `game_reconciliation.parquet` `c0c4fee3…eb0e2` |
| Pilot | #19 build `issue-19-v6`. `manifest.json` SHA-256 `89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570`, which the #59 manifest records as its `pilot_manifest_sha256` |
| Pilot tables read | `event.parquet` `6658c1b7…d211`, `game.parquet` `0f7694ea…1a42`, `score_allocation.parquet` `753968fb…d4bb`. Each must match both the frozen value and the pilot manifest. |
| Evidence tier | `retrospective_capture_bound` |
| Scope | 2022–23 only. The runner refuses any `season_start_year` other than 2022 in the rows or the game table. No 2023–24, 2024–25 or 2025–26 data and no EPM output is read. |

## Pre-possession covariates

A possession's covariates come only from pilot events whose stream sequence is strictly less than the possession's `start_seq` (its first event). The prior event is the last such event in the same game stream (a DuckDB `ASOF` join on `start_seq > seq`).

- **Score before the possession:** the cumulative `home_delta` and `away_delta` through the prior event. Margin is offense minus defense. Dead-ball and unresolved points already recorded count, because they were on the scoreboard.
- **Clock before the possession:** the prior event's game `elapsed_ms`, raised to the period start if it is earlier. A possession with no prior event (the game's first) has 0 elapsed and a 0–0 score. The clock of the possession's own first event is not used, because that event already belongs to the possession (for example, the made shot that ends it).
- **Home:** +1 if the offense is the game's home team, −1 if away, 0 if the pilot flags the game as neutral-site.

**Timing audit.** It runs on every load, and its counts go in results.json.
1. A possession's own `control_possession` allocations sequenced before its `start_seq`. Must be 0, or the run aborts, because the outcome would leak into the covariate.
2. The pre-possession score from the event ledger and from an independent cumulative sum of the score-allocation ledger. Disagreements must be 0, or the run aborts.
3. Own allocations sequenced at or after `end_seq`. Reported. They can affect only later possessions' state.
4. A prior-event clock later than the possession's first-event clock. Reported.
5. Clamps to the period start, and possessions without a prior event. Reported.

A pre-freeze run of the audit on the pinned inputs gave 0 for items 1 to 4 and for the clamps, and 1,291 possessions without a prior event, each a game's first eligible possession.

## Context families (column definitions)

| Family | Columns |
| --- | --- |
| `home` | home (±1, or 0 at a neutral site) |
| `score_linear` | margin clipped to [−20, 20], in points |
| `score_binned` | indicators for margin ≤ −15, −14 to −8, −7 to −3, 3 to 7, 8 to 14, ≥ 15 (reference −2 to 2) |
| `score_late` | clipped margin, and clipped margin × 1[period ≥ 4] |
| `time` | indicators for period 2, 3 and 4, overtime (reference period 1), end of period (≤ 24 s left in the period), and final two minutes (period ≥ 4 and ≤ 120 s left) |
| `home_score_time` | home, clipped margin and the six time columns |

**Late blowout:** period ≥ 4 and pre-possession |margin| ≥ 20. This simple BIL definition is **Original**. It is not a published garbage-time rule.

## Variants

All variants use the #23 estimator and conventions: response 100 × points, an unpenalized intercept, one ridge on every player coefficient, positive defense preventing points, zero effect for unseen players, and **$\lambda$ = 4,000 frozen from #23 for every variant. $\lambda$ is not re-tuned.** Context columns are unpenalized.

| Variant | Definition |
| --- | --- |
| **C0** | Zero context: the #23 fit, the explicit baseline for every comparison |
| `H_fit`, `S_fit`, `Sbin_fit`, `Slate_fit`, `T_fit`, `HST_fit` | **Fitted control.** The family's columns are estimated jointly with the players (unpenalized). |
| `H_off`, `S_off`, `T_off`, `HST_off` | **Eligible offset.** A context-only least-squares fit on the same fold's fit rows (no players) gives fixed coefficients. Their offset is subtracted from the response before the player fit and added back when predicting. It uses only fit-window rows, so it is eligible at the cutoff. |
| `W_half` | **Exposure weight.** Late-blowout fit rows get weight 0.5, then all fit weights are rescaled to mean 1, so $\lambda$ keeps its per-unit-possession meaning. |
| `W_drop` | Late-blowout fit rows are excluded from the fit, with unit weights. |
| `CTX_<family>` | **Context-only comparator** (#77): intercept and family columns by least squares on the fit rows, with no player terms. |
| `league` | B0 from #23: the fit-window mean. |

The weight-scale equivalence (multiplying every weight by $c$ equals multiplying $\lambda$ by $1/c$) is a property of the objective. It is checked in synthetic tests rather than re-run, and the #23 penalty grid already shows the effect of the overall scale. Held-out scoring always uses every held-out possession with equal weight, whatever the fit weights.

The solver projects the weighted span of $[1, Z]$ out of the player design (Frisch–Waugh–Lovell), solves the penalized player problem with sparse LSQR, then recovers the intercept and context coefficients by weighted least squares on the player residual. Synthetic tests check it against a dense closed-form oracle. With no context columns it equals the #23 solver, and the runner also checks this on every real fold.

## Folds, metrics and uncertainty

Folds R1–R4 and P1 are exactly as in [#23](rapm-baseline-protocol.md): fit rows strictly before the cutoff, whole scored games, and regular season and playoffs never pooled. The primary metric is **the pooled R1–R4 paired held-out squared-error delta of each variant against C0** (negative is better), in (points per 100)². Its uncertainty is a 95% percentile game-clustered bootstrap with 2,000 resamples and seed 2023, which ignores dependence across folds. Each variant is also scored against the league mean. Secondary results:

- The same deltas for each fold and for P1.
- Team-game RMSE for the full regular-season and playoff sets.
- The fitted-minus-offset delta for H, S, T and HST.
- **Strata:** held-out late-blowout and non-blowout possessions, separately for the pooled regular season and the playoffs. Stratum game indices are re-indexed before the bootstrap.

**Verdict rule (frozen):** for each variant on the pooled R1–R4 delta against C0, **supported** if the 95% interval lies wholly below 0, **rejected** if the point delta is ≥ 0, otherwise **inconclusive**. P1 is a check and never changes a verdict. A verdict is development evidence on one season. It does not admit a context family to a reference specification. That needs a registered outer-fold protocol.

**Neutral court.** The pilot `game.neutral_site` field is null for every game, so no possession can be flagged as neutral. All games are coded by nominal home team. The neutral-court stratum is reported as skipped with that reason, and no external neutral-site list is added.

## Fit and coefficient sensitivity

Each variant also gets one final in-sample fit on all 224,039 rows at $\lambda$ = 4,000. For each, report:
- In-sample MSE and its delta against C0.
- The intercept and context coefficients.
- The shift against C0 in player offense, defense and total (RMS, maximum and correlation, for players in both fits).
- Context coefficients by fold (R1–R4, P1) as a stability check.

Context-only coefficients on all rows get game-clustered 95% bootstrap intervals (2,000 resamples, seed 2023). Player-level estimates stay in the private output directory.

## Run

```sh
uv run python -m bil.models.rapm.context_ablation \
  data/processed/2022-23/issue-59-v1 data/processed/2022-23/issue-19-v6 \
  data/processed/2022-23/issue-24-v1
```

Run it once from a clean working tree after the code commit. The manifest records the code commit, a clean-tree flag, this document's SHA-256, the input pins, library versions, runtime, peak memory and output digests. results.json stores per-fit LSQR diagnostics.
