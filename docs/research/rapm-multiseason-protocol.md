# Multi-season RAPM: development protocol (2018–19 through 2022–23)

**Status:** Frozen before any real-data fit for [issue #26](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/26). **Classification:** Original BIL design, applying the [evaluation contract](../validation-strategy.md) and the maintainer's decision on #26 (primary window 2018–19 through 2022–23; 2023–24 and 2024–25 are the chronological outer-validation seasons; 2025–26 is the untouched confirmatory holdout). Results go in [the multi-season report](rapm-multiseason.md), written after the runs. Any change to this document after the development run starts is a deviation and is listed in that report.

This protocol has two phases. **Phase 1** (this document) selects candidates on development folds inside 2018–19 through 2022–23 and runs the stability and sensitivity analyses. **Phase 2** evaluates only the configuration(s) frozen in a separate, committed **outer-validation addendum** on 2023–24 and 2024–25. No code reads a 2023–24 or 2024–25 outcome before that addendum is committed. The 2025–26 and 2026–27 seasons are never opened, listed or read.

## What was looked at before freezing

Before writing this document, only these were inspected: the row-set and pilot manifests and their SHA-256 values for 2018–19 through 2024–25, and, for the five development seasons only, row counts, distinct games, date ranges, period counts, the `weight` column (1.0 everywhere) and player counts. No model was fitted on real data and no held-out score exists. The fit speed of the reference solver was timed on synthetic data only. The earlier single-season results ([#23](rapm-baseline-2022-23.md), [#24](rapm-context-ablations-2022-23.md), [#82](rapm-no-action-2022-23.md)) and the [season-quality report](season-quality-2017-2025.md) were public before this protocol and informed the design (penalty grid centre, the context family, the sensitivity list).

## Frozen inputs

Canonical row sets (ADR-0019, contract `rapm-historical-rows-issue-82-v2`) from [#93](../agent-runs/2026-11-24-issue-93-multiseason-rows.md), at `data/processed/<season>/issue-93-v1/`, each pinned by its `manifest.json` SHA-256. The runner hashes the manifest, checks `build_id`, `evidence_tier = retrospective_capture_bound`, `variant = canonical` and `season_start_year`, and hashes `model_row.parquet` and `game_reconciliation.parquet` against the digests the manifest lists. Any mismatch aborts before a row is read.

| Season | Role | Row-set `manifest.json` SHA-256 | Pilot build (context only) | Pilot `manifest.json` SHA-256 |
| --- | --- | --- | --- | --- |
| 2018–19 | Development (conditional) | `c0fa49896b96827ec9ff6864bbcf5d3ddb55e8b6079ed693f4a88ebd4b1e1df1` | `issue-25-v1` | `a5f52e4880666fb8eb887d82eecedf6cf7ebd1e6c5e5ba42e6fea25fdb43ce35` |
| 2019–20 | Development | `f17dfd1bd9b39cdd022375656be2681cc119c65b5f66b97466f2992bbd6ed777` | `issue-25-v1` | `334daf0237f3f9669d76ca807929802426bf667ad68f0932ffdcdfd0a0a52ac6` |
| 2020–21 | Development | `231f742dbf7aeeb02e99c5a4b1ff8c2c3eed5e5bfb484390d307ecf0d8c5e756` | `issue-25-v1` | `c3c75d43236a93070fd8fb3dd90200f572894af6aa5f5c05b8f38881ede72a11` |
| 2021–22 | Development (conditional) | `58fed85cce0822865e7b3bf369e55b5ba5a280f6a1347d19832381df383cc298` | `issue-25-v1` | `49bb4a91c71d2f255a17ba1c52a3ae6e5c2737f1a8c6716c0405980949947075` |
| 2022–23 | Development | `2affb62a8d875963f05e5eb39e2e36d8e8fbab4df43840f1dc0062deb581a1ac` | `issue-19-v6` | `89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570` |
| 2023–24 | Outer validation (Phase 2 only) | `38bb59c537164df9a2a1cb8042fa51187737deadeadfd216b3edce1e1877bad4` | `issue-52-v1` | `1d6ba700ea75ddd984f9b306e018af84c5b90ec8937ad598ec31c20daba3176a` |
| 2024–25 | Outer validation (Phase 2 only) | `86b0ea747849b70c7321806599f25a8864301f16026b79b4be1daa1f5202972b` | `issue-52-v1` | `ad72e1f0b1b97a8ef95f1c040d353254588d9d9ecf40e3064a7b7e131d195978` |

- The pilot build supplies only the context covariates, as in #24: `event.parquet`, `game.parquet` and `score_allocation.parquet`. Each must match the digest that both the pilot manifest and the row-set manifest (`pilot_input_tables`) record, and the row-set manifest's `pilot_manifest_sha256` must equal the pinned pilot manifest digest.
- 2017–18 is not read (outside the primary cohort, ADR-0022). The season registry has no entry for 2025–26 or later, and every loader refuses `season_start_year >= 2025`. The development runner refuses any season other than 2018–2022 and asserts that every loaded date is before 2023-07-01.
- No EPM output is read, used or compared.

## Rows, response and estimator

- **Rows.** One unit-weight row per canonical model row: accepted game, pilot-accepted possession, a single stable lineup pair (ADR-0013, ADR-0019). Quarantined games are not rows and are never scored; their counts are reported. Response is `model_points × 100` (points per 100 possessions). Player IDs are integers.
- **Estimator.** Zero-prior ridge with an unpenalized intercept, a penalty $\lambda_o$ on every offensive coefficient and $\lambda_d$ on every defensive coefficient, positive defense preventing points, and each block centred over its observed players (ADR-0012). The solver is the verified sparse LSQR reference (`bil.models.rapm.reference`, the two-penalty path behind `fit_prior_rapm` with no prior), reused by import. Separate offense and defense penalties are the [#77](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/77) item; #77 is not merged, so this protocol selects them itself with the reference solver's existing two-penalty interface (below). `baseline.py` is not modified.
- **Design reuse.** The runner builds one sparse design for all loaded rows, with the reference column layout (intercept, sorted offensive IDs, the same defensive IDs), and solves each fit on its row subset. Columns of players absent from a fit's rows are unused and get exactly zero effect, as in the reference. On one fold per temporal family the runner also fits the same rows through `fit_dated_prior_rapm` (decay) or `fit_prior_rapm` (windows) on `Possession` objects and aborts if any coefficient differs by more than 1e-6 points per 100.
- **Unseen players.** A held-out player absent from a fit's rows has zero offense and defense effect. Possessions with one are counted.

## Temporal candidates

Dates are Eastern played dates. For a fit cutoff $C$, a row is eligible only if `played_date < C` (the shared `played_before` rule). Age is `(C − played_date).days`, at least 1. Weights are not renormalized and penalties are not rescaled (ADR-0015), so penalties are selected jointly with each temporal candidate.

| Name | Rows used | Weight |
| --- | --- | --- |
| `W1`, `W2`, `W3`, `W5` | age ≤ 365, 730, 1095, 1825 days | 1 |
| `H90`, `H180`, `H365`, `H730` | age ≤ 1825 days | `0.5 ** (age / h)` with half-life `h` in days |

A "season" here is 365 days of calendar history, so a window always spans roughly the same number of games whatever the cutoff. The development data start on 2018-10-16, so `W5` and the 1,825-day decay cap are truncated in every development fold (to at most about three seasons for 2021–22 folds and four for 2022–23 folds), and `W3` equals `W5` at the first 2021–22 cutoff. This is recorded, not corrected.

## Chronological development folds

Scored seasons are 2021–22 and 2022–23, as the evaluation contract's inner checks specify. Earlier seasons are fitting history only. Each scored season has five blocks. Fit rows are all loaded rows played before the cutoff that the temporal candidate admits; scored rows are the block's whole games.

| Block | Fit cutoff | Scored rows |
| --- | --- | --- |
| R1 | 1 October | regular season, played before 1 December |
| R2 | 1 December | regular season, 1 December to 31 January |
| R3 | 1 February | regular season, 1 February to 31 March |
| R4 | 1 April | regular season, from 1 April |
| P | the season's first playoff date | playoffs |

A game has one played date, so it is wholly in one block; the runner checks that no game is on both sides of a cutoff and that every scored date is on or after its cutoff. Selection uses the eight regular-season blocks (R1–R4 of both seasons) pooled. The two P blocks are a check, scored after selection and never used to choose.

## Candidate selection

The selection metric is the **pooled held-out possession mean squared error (MSE)** over the eight regular-season blocks, in (points per 100)². For each temporal candidate:

1. **Shared penalty.** $\lambda_o = \lambda_d = \lambda$ on the grid {1,000, 2,000, 4,000, 8,000, 16,000, 32,000}. If the best value is at an edge, the grid extends by factors of two on that side, up to five times (the #23 rule, `select_penalty`).
2. **Defense penalty.** Holding $\lambda_o = \lambda^\*$, try $\lambda_d \in \lambda^\* \times$ {1/4, 1/2, 2, 4}, keeping $\lambda^\*$ if none is better. An edge optimum extends by a further factor of two, up to three times.
3. **Offense penalty.** Holding $\lambda_d$ at the stage-2 value, try $\lambda_o \in \lambda^\* \times$ {1/4, 1/2, 2, 4} with the same extension rule.

This is a one-pass coordinate search, not a full two-dimensional grid. The **selected configuration** is the (candidate, $\lambda_o$, $\lambda_d$) with the lowest pooled MSE over all eight candidates. Exact ties go to the earlier candidate in the table order above. No EPM value, player-level quantity or outer-season row informs any choice. Selection scores are optimistic for the chosen configuration because the same folds chose it.

## Baselines

Every baseline sees the same cutoff, rows and target as the model.

- **B0, league mean (intercept only).** The weighted mean response of the fit rows under a temporal candidate.
- **CTX, context only.** Weighted least squares of the response on an intercept and the #24 `home_score_time` columns (home ±1, clipped pre-possession margin, period 2–4 and overtime indicators, end of period, final two minutes), built from pilot events strictly before each possession with the #24 SQL, timing audit and abort rules (`bil.models.rapm.context_ablation`). A column that is constant zero in a fit's rows is dropped from that fit and gets coefficient 0. Neutral-site flags are null in every pilot, so every game is coded by its nominal home team, including the 2019–20 bubble games.

Each baseline's temporal candidate is selected by its own pooled regular-season development MSE, the same way, so that the comparison is against a tuned baseline. These choices are frozen with the model's.

**Secondary model, RAPM + context offset.** The #24 eligible-offset construction: the CTX fit (with the RAPM candidate's rows and weights) supplies a fixed offset, the player model is fitted on the response minus the offset with the selected penalties, and the prediction adds the offset back. It uses the primary configuration's candidate and penalties and is not tuned. It is reported in development for information and is not used for selection.

## Metrics, uncertainty and effective scales

- Per-possession squared error, unweighted, on the scored rows. Paired deltas use identical possessions: model minus B0, model minus CTX. Negative favours the model. Root-mean-square error, offense-only and defense-only slices (the other block's effects zeroed) and the team-game aggregate RMSE (as #23) are secondary.
- Uncertainty: a game-clustered percentile bootstrap, 2,000 resamples, seed 2023, 95% intervals (as #23 and #24). Temporal dependence across blocks is not modelled; per-block deltas are reported so that it is visible. Regular season and playoffs are reported separately and never pooled.
- Effective scales, per fit: rows, total weight, Kish effective sample size $(\sum w)^2 / \sum w^2$, the median weighted offensive and defensive possessions per observed player, and the ratios $\lambda_o$ and $\lambda_d$ to those medians (the effective shrinkage per typical player).

## Coefficient stability (development data only)

For each temporal candidate at its own selected penalties, with exposure bands by unweighted on-court possessions (offense plus defense) in the relevant fit rows: under 2,000, 2,000–5,000, 5,000–10,000 and 10,000 or more.

- **Split halves.** At cutoff 2023-07-01 (all development data), alternate the window's games in chronological order into two halves, fit each with the full-window weights, and correlate offense, defense and total estimates for players with at least 250 possessions in each role in both halves (the #23 rule), overall and by band.
- **Year over year.** Fits at cutoffs 2022-07-01 and 2023-07-01: correlation and root-mean-square change of totals for players in both, overall and by band. Fixed one-season windows are disjoint here; longer windows and decays overlap, which raises the correlation mechanically, and is reported as such.
- **Refit volatility.** Within each scored season, consecutive cutoffs (R1→R2, R2→R3, R3→R4, R4→P): root-mean-square change and correlation of totals for players in both fits, by band.
- **Season type.** For each scored season, the fit at its P cutoff (regular season complete) against the fit at 1 July (playoffs added): root-mean-square change and correlation, by band. Held-out results are also reported for the regular-season blocks and the P blocks separately.

## Sensitivity analyses (maintainer requirement)

Each scenario removes rows from both fitting and scoring and reruns the **whole selection** (all candidates, the full penalty search):

| Scenario | Rows removed |
| --- | --- |
| `exclude_2018_19` | season 2018–19 |
| `exclude_2021_22` | season 2021–22 (its scored blocks disappear, so scoring is 2022–23 only) |
| `exclude_overtime` | possessions in period 5 or later |
| `exclude_no_livedata` | games carrying the `no_livedata` stratum in `game_reconciliation` (all of 2018–19 and 2019–20) |

**Pre-run clarification (2026-11-24, before any real-data fit).** The synthetic end-to-end test showed that a candidate can have no fit rows at a cutoff: under `exclude_2021_22`, `W1` at the 2022-10-01 cutoff covers only 2021–22. A candidate whose window is empty at any scored block's cutoff in a scenario is **infeasible** there. It is not searched, scored or selectable in that scenario, for the model or a baseline, and the report lists it. Rank comparisons use the candidates that are feasible in both analyses. In the primary analysis every candidate is feasible. This clarification was added after the protocol commit `86790ae` and before the development run.

Reported for each: the selected configuration and its pooled delta against B0; the primary-selected configuration's score and rank; the rank correlation of the per-candidate best MSEs with the primary analysis; the paired MSE difference, on the scenario's scored rows, between the primary configuration fitted on the reduced rows and on all rows; and the shift of the primary configuration's final development fit (cutoff 2023-07-01) against the full-data fit (root-mean-square change, correlation, by band). **Sensitivity results never change the primary selection.**

## Freeze and Phase 2

After the development run, an addendum, `docs/research/rapm-multiseason-outer-addendum.md`, is written and committed before any code reads 2023–24 or 2024–25 rows. It contains a machine-readable block naming the exact selected configuration (candidate and both penalties), the secondary RAPM + context-offset model, the frozen temporal candidates of B0 and CTX, and the development results manifest digest. It also fixes the outer refit schedule, metrics, uncertainty method, coverage definition and verdict rule. The intended Phase 2 design, which the addendum may make more precise but not change after any outer result exists:

- Walk-forward in each outer season with the same five blocks and cutoffs. Every fit uses all eligible rows before its cutoff that the frozen candidate admits, including earlier outer-season games, with the frozen penalties. Nothing is re-tuned.
- Primary comparisons: model minus B0 and model minus CTX, per outer season and pooled over both outer seasons, regular season and playoffs separately, with the game-clustered bootstrap above and a calendar-week-clustered bootstrap as a temporal-dependence check.
- Coverage: eligible and scored possessions and games by season type, quarantined games not scored, possessions with an unseen player; and calibration of the predicted possession scoring rate (calibration-in-the-large, calibration slope and a decile table, with game-clustered intervals).
- The Phase 2 runner refuses to start unless it is given the addendum and its SHA-256, the addendum is committed with no local change, and the working tree is clean. It records all of these in its manifest, reads the frozen configuration from the addendum itself, and runs once.

## Outputs and manifest

The development run writes to a new directory `data/processed/multiseason/issue-26-dev-v1/` (refusing an existing one): `results.json` (aggregates only), private player estimates of the selected configuration's final development fit, and `manifest.json` with the pinned inputs and verified digests, this document's SHA-256, the code commit and whether the tree was clean, library versions, per-fit solver diagnostics, runtime and peak memory. Committed reports carry aggregates only, with no named players or rankings.

**Evidence tier: `retrospective_capture_bound`.** Every result is a chronological replay on realized lineups, not a strict rolling-origin backtest or a pregame forecast.

| Claim | Label |
| --- | --- |
| Zero-prior sparse ridge solver and the dated clock | **Documented** in this repository ([#6](rapm-synthetic.md), [#64](rapm-dated-weights.md)) |
| Candidates, folds, search, baselines, stability and sensitivity design | **Original** |
| Every development and outer number | **Experimental**, retrospective |
