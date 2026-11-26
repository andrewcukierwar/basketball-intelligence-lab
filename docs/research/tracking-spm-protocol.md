# Tracking-enhanced defensive SPM against the box-only reference

**Registration:** [#38](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/38). This protocol is committed before any tracking-enhanced fit or score.

**Classification:**
- Original BIL design.
- Experimental evidence for EPM-U03 and EPM-U04 ([uncertainty register](epm-uncertainties.md)).
- Outputs carry `partial-history methodology replication` and `retrospective_capture_bound`.

**Evidence boundary:**
- **Strict historical eligibility is empty.** The [#37 audit](nba-defensive-tracking-audit.md) found no dated revision of the matchup archive that predates any origin, so every comparison here is retrospective.
- **Not read:** any EPM output, the 2023–24 and later seasons, and the 2025–26 holdout.
- **Registration inputs:** the code, the #30 protocol and results, the #37 audit's aggregate coverage counts and the parquet schema. No tracking-enhanced fit or score informed these choices.

## 1. Target, reference and folds

- **Target.** Use #28's contiguous `K365` chain, exactly as the [#30 protocol](box-spm-protocol.md) uses it. Calibration rows, the 250-possession minimum, the exposure-proxy weights, ridge 0.05 and fit-only imputation and scaling are all unchanged.
  - These targets are independent of EPM, built from BIL possessions, and chronologically eligible at each origin.
  - **Why no pooled six-season target.** The EPM author fits tracking SPM to one multi-season RAPM over the six-season window. Such a target contains outcomes after every evaluation origin in the window, so it is ineligible for any chronological fold here. The per-origin `K365` chain is the eligible substitute. This is an **Inferred** methodological deviation from the documented recipe.
- **Reference.** The frozen box-only `full` candidate of #30, refitted on identical inputs. Its contiguous fits must reproduce #30's realized-lineup MSE for context plus Full (see §5).
- **Folds.** The contiguous reference: evaluation seasons 2019–20 through 2022–23, trained on target seasons from 2018–19.
  - 2017–18 is inside the documented tracking window but has no #28 target or #30 box pin, so it is unused. Report it as lost window coverage.
  - Box logs use #30's `LOG_PINS` for 2018–2022.

## 2. Tracking inputs and features

- **Source.** The six SportsDataverse `game_matchups_{end year}.parquet` revisions pinned in the [asset register](nba-tracking-audit-assets.csv). Verify each file's SHA-256 and size before reading. The runner reads the five files for 2018–19 through 2022–23.
- **Rows.** Directed offensive–defensive pairs. Keep only games with an official regular-season (`002`) or playoff (`004`) ID.
- **Defender-game totals.** Sum `partial_possessions`, `matchup_turnovers`, `matchup_field_goals_attempted` and `matchup_field_goals_made` over each `(game_id, def_person_id, def_team_id)`.
- **Linkage.** A defender-game links only if it joins a positive-minute box appearance with the same game, player and team. Its date is that appearance's official date. Unlinked defender-games and rows with nonfinite or negative quantities, or makes above attempts, are dropped and counted.
- **Window features.** For a window, sum the linked totals of a player's games with date `< cutoff`, pooling both season types and all teams. The three defense features are:

  | Code | Definition | Null when |
  | --- | --- | --- |
  | `mtov_per_100` | 100 × turnovers / partial possessions | partial possessions = 0 |
  | `mfga_per_100` | 100 × attributed FGA / partial possessions | partial possessions = 0 |
  | `mfg_pct` | attributed FGM / FGA | FGA = 0 |

  These are rates among credited matchups. They are not team defensive outcomes or causal credit.
- **Windows.** Training rows use the target season's linked games before the fit cutoff, as box features do in #30. Predictions use the same history rule as #30's box features: the opening snapshot uses the preceding season, and dated snapshots add current-season games with date `< D`.

## 3. Candidates and combination policy

Offense is the #30 Full offense in every candidate, so offense predictions are identical to `full`.

| Candidate | Defense features | Role |
| --- | --- | --- |
| `zero`, `one_stat`, `full` | As in #30 | Controls and reference |
| `full_tracking` | The four Full box defense features plus the three tracking features | **Primary** |
| `tracking_defense_only` | The three tracking features | Descriptive |
| `full_tracking_regular_only` | As `full_tracking`, with tracking windows restricted to regular-season games | Playoff-inclusion sensitivity |

- **Fitting.** Each candidate uses #30's weighted ridge recipe on the same training rows as `full`. Null tracking values are imputed with the training weighted mean, as box nulls are.
- **Fallback.** A player whose tracking features are all null at a snapshot gets `full`'s defense prediction. The intercept fallback for players without box history is unchanged and identical across candidates.
- **Fixed in advance.** No feature, threshold, weight or penalty is selected with outcomes.

## 4. K0 agreement

Score #28's frozen contiguous `evaluation_K0` labels at each season-opening snapshot, using #30's minimum-exposure cohort. Errors are per 100 possessions, with positive defense meaning points prevented.

- **Paired cohort.** Scored players whose opening tracking features are not all null.
- **Full cohort.** All scored players, with the fallback applied. This validates the fallback.
- **Primary K0 metric.** The pooled 2019–22 paired-cohort **defense** RMSE of `full_tracking` minus `full`.
- **Uncertainty.** 1,000 player-cluster resamples with seed 30 (the #30 bootstrap).
- **Criterion.** "Tracking improves K0 defense agreement" requires a negative delta whose 95% interval excludes 0.
- **Also reported:**
  - Total RMSE.
  - The full cohort.
  - Each season.
  - The other candidates against `full`.
  - Opening minutes bands (#30 cutoffs).
  - Players with no opening box history, standing in for rookies.
  - Label-exposure bands.
  - **Defensive specialists.** Players in the top quintile of the scored players' opening `full` defense prior, a pre-origin quantity.

## 5. Realized-lineup diagnostic

Reuse #30 §5's dated snapshot rule and canonical rows.

- **Context baseline.** M2's `home_score_time` context-only regression, fit on the preceding eligible season's complete rows.
- **Predictions.** Context plus the five offensive priors minus the five defensive priors, for `full`, `full_tracking` and `full_tracking_regular_only`. Also context plus each candidate's defense part alone.
- **Consistency checks.** Both run before any tracking result is written, and a mismatch stops the run.
  - Every fold's `full` coefficients must match the stored #30 `issue-30-v2` contiguous `fit.json` to 1e-10. That run's manifest SHA-256 is `376d89ce…786d`.
  - Pooled context plus `full` must match #30's `court_common_modern_pool.contiguous` MSE (reported as 1.409115 points per possession squared) to relative tolerance 1e-9.
- **Primary court metric.** The pooled 2019–22 possession MSE of context plus `full_tracking` minus context plus `full`.
- **Uncertainty.** Monday-week block resampling within each season, as #30 does (1,000 resamples, seed 30).
- **Criterion.** "Tracking adds on-court value" requires a negative delta whose 95% interval excludes 0.
- **Also reported:**
  - Regular season and playoffs.
  - Each season.
  - Possessions where all five defenders have dated tracking against the rest.
  - Possessions with any defender lacking box history.
  - The defense-only contrast.

## 6. Coverage, freeze and artifacts

- **Coverage.**
  - Linked defender-games against positive-minute box appearances, by season and type.
  - Dropped rows by reason.
  - Training rows with all-null tracking.
  - Snapshot players on the tracking fallback.
  - Unused window seasons.
- **Learned features.** Store every fold's coefficient vectors, imputation means and scales, and the final contiguous `full_tracking` fit at `contiguous@2023-06-13`.
- **Freeze for M7.** The pinned tracking archive ends with 2022–23. With no pinned tracking for 2023–24 or later, a tracking comparison is **unavailable** for the M7 outer and confirmatory seasons without a new registered capture. Record that limitation together with the frozen result.
- **Artifacts.** Dated predictions are frozen before labels or outcomes are joined. Aggregates only go in the repository.
- **Tests.**
  - Synthetic tests poison later tracking and box rows and check that earlier features are unchanged.
  - Further tests check linkage drops, the fallback, and the reproduction of `full` from #30's fit.
- **Run discipline.**
  - The run uses a clean tree and writes one new private version.
  - A crash before results allows a rerun of the same protocol.
  - Any methodological change needs a registered revision.
  - Results are preserved regardless of direction.
