# Box-score SPM priors

**Registration:** [#120](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/120), part of [#30](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/30). Independent protocol review precedes the [#121](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/121) fit. **Classification:** original BIL design and experimental evidence under [ADR-0026](../DECISIONS.md#adr-0026--maintainer-decisions-of-2026-11-24-m2-acceptance-informed-rapm-comparators-and-partial-history-spm-targets). All outputs carry `partial-history methodology replication` and `retrospective_capture_bound`. The estimands are separate additive offensive and defensive priors in points per 100 possessions, with positive defense denoting points prevented.

## 1. Input pins and evidence boundary

Use the [#28 protocol](rapm-targets-protocol.md) and its provisional `K365` targets accepted under ADR-0027. The private input is `data/processed/rapm_targets/issue-28-v1`, with manifest SHA-256 `40fcfba98a3a243377612292d59860541a710a5be902011ec03ec276118fe043`. Verify the manifest-listed digests for `targets.csv`, `evaluation_labels.csv`, `frozen_targets.json` and `results.json`. Use #28's canonical historical rows and existing row and pilot manifest pins for on-court scoring. These include only accepted regular-season and playoff games. Keep the source verification strata as recorded by #28.

Use [#29's box-v1 definitions](box-score-feature-contract.md) with the following NBA.com player and team log snapshots. Verify the bytes of each snapshot record and both named log files against the record; the raw inputs, private predictions and individual labels stay out of version control.

| Season | Raw snapshot | `snapshot.json` SHA-256 |
| --- | --- | --- |
| 2005–06 | `issue-97-v1` | `78b57d0481f95b9c0c54d6d0670480c4d3ef607129f92b7180c85cf240a3e824` |
| 2006–07 | `issue-97-v1` | `9433786ea2eaac54ba948127274bbe9626c4eb59eb159dee287cf486098c3098` |
| 2007–08 | `issue-97-v1` | `7e3189d65ba78fb37a07b302e9dddae9646021a4d2432263863781d28fa1ae49` |
| 2015–16 | `issue-98-v1` | `1a49c70c29cc45ecd9bb87aa824716e1071c4524c3eaeb6d894bbf276ed24fdd` |
| 2016–17 | `issue-96-v1` | `7489dc412ef5a36ca7d7748c0b5035ebe432ad8421864913a3c1906e434a8d88` |
| 2018–19 | `issue-25-v1` | `3dddf8dd0731630f838b1375fc4f494e27cf8aecb4895618ba07154defdabfe1` |
| 2019–20 | `issue-25-v1` | `b3d131f42a5588b9b39a2d2ee4a034c85a0addc10ce68ee04c728099baa8827b` |
| 2020–21 | `issue-25-v1` | `45a78182453945572e404418c411b1490a7f20a21d4a00124ffaa94017e293df` |
| 2021–22 | `issue-25-v1` | `d634e22e6db4bcfcf4b0933b13835f034e32de62c564db9a4e5934ebd4c4570c` |
| 2022–23 | `issue-5-v2` | `348eb8a072534659956082fd64cf3106c2d07092c87b5aca6f9d0ca056ae6611` |

The allowlist is exactly the ten seasons in the table and dates before 2023-07-01. Refuse requests outside it before constructing data paths. The registered run reads neither 2023–24 nor 2024–25. The 2025–26 holdout stays reserved. EPM ratings, tracking data, Estimated Skills fits, roster and biography sources have no input role. Registration used the code, prior documented research, input paths and hashes, and private CSV schemas (header only). No private target values or new score/fitting results informed these choices. All historical source versions carry capture bounds later than the historical origins. Strict and prospective coverage are unavailable. Report coverage and exclusions under the [validation contract](../validation-strategy.md).

## 2. Fit origins, calibration rows and weights

For each reference, use #28's `chronological_registration` with its exact target-set keys and cutoffs. Use only the frozen `K365` version closing the preceding eligible season for each evaluation season. A calibration row joins one target (`player_id`, `target_season`) to the same season's complete box logs, with game dates strictly before the target-set cutoff. The window pools regular season and playoffs by summing the underlying numerators and denominators across all player's teams. Box logs can include official games quarantined from RAPM when their box logs pass #29 identity checks. The common calibration window is the full season, with each source's game coverage reported separately. Positive-minute appearances define feature and minutes history. Play-in and preseason are excluded. Count target-only and box-only keys, missing features and calibration updates separately.

Train on player-seasons with at least 250 possessions in **each** role and positive-minute box history. For each modeled side, give eligible training row weight `n / (n + 1000)`, with `n` that side's integer possession exposure in the target season. This substitutes an exposure proxy for reliability. #28 emits bootstrap standard errors at the final origin only, so they do not enter any fit. One-sided labels (`forward_support=false`) remain eligible with full proxy weight. One-sidedness is collective season-level kernel support, which includes the last available season at each fit. A predeclared sensitivity multiplies the proxy by 0.5 for these rows. Retain the same cohort in the unweighted comparator.

The contiguous reference is primary. Fit extended folds with all earlier seasons in their original chronology, including 2005–08. For common modern evaluation seasons (2019–20 through 2022–23), fit a companion extended sensitivity excluding 2005–08 calibration rows. Its other targets still come from the extended target fit, so the sensitivity measures pooling of training examples, conditional on that label construction. Show early, bridge and modern cohorts separately. In extended evaluation, 2015–16 and 2018–19 cross gaps. Record their elapsed time and cold-history counts. The first season of each reference has no prior target set and is unavailable. Freeze a final contiguous prior coefficient set at the #28 origin closing 2022–23 for later eligible #35 use, with its cutoff and original fit inputs. It has no downstream validation here.

## 3. Fixed linear specifications

Use separate weighted ridge fits for offense and defense. Offense uses `fg2_pct`, `fg3_pct`, `ft_pct`, `fg3_share`, `fga_per_36`, `fta_per_36`, `ast_per_36`, `tov_per_36`, and `oreb_per_36`. Defense uses `dreb_per_36`, `stl_per_36`, `blk_per_36`, and `pf_per_36`. For each side and candidate, replace nulls with the weighted mean of the known training rows, then standardize by the weighted mean and population standard deviation of the imputed training column. All-null or constant columns contribute zero. Fit an unpenalized intercept and minimize weighted mean squared error plus `0.05 * sum(coefficients ** 2)`. Apply the training transforms at evaluation. Use the side intercept when the inputs for its selected feature set are all missing. Sum the two sides for total. Store both coefficient vectors, imputation and scaling parameters, and model intercepts. No clipping.

| Candidate | Fixed rule |
| --- | --- |
| Zero | Zero offense and defense |
| Mean | Exposure-proxy-weighted side means from training |
| One-stat | `fga_per_36` and `stl_per_36` for offense and defense respectively, fit by the primary recipe |
| Full | All registered side features and the primary reliability proxy |
| Full unweighted | All side features and unit training weights |
| Full one-sided sensitivity | All side features and the one-sided downweight |
| Offense without shooting | Omit the four fractions plus `fga_per_36` and `fta_per_36`; defense is Full |
| Offense without playmaking and rebounding | Omit `ast_per_36`, `tov_per_36`, `oreb_per_36`; defense is Full |
| Defense without events | Omit `stl_per_36`, `blk_per_36`; offense is Full |
| Defense without rebounds and fouls | Omit `dreb_per_36`, `pf_per_36`; offense is Full |

No candidate, hyperparameter or feature group is selected with outcomes. Full is registered in advance. The primary comparison metric is equal-player-season RMSE for each side separately. Report total RMSE, MAE and signed bias as secondary. Evidence of improved K0 agreement for a side requires lower paired RMSE than both Zero and One-stat on the common modern folds, with the corresponding 95% paired player-cluster bootstrap intervals excluding zero. Mean and all other contrasts remain descriptive. K0 agreement and on-court outcome evidence answer different questions. No nonlinear candidates or further tuning are registered.

## 4. Chronological agreement with K0 labels

Score #28's frozen season-only `evaluation_K0` label for the matching evaluation reference and season. Evaluate the prior as of the first date of the evaluation season from the pinned calendar, using box history from the immediately preceding calendar season only if it is eligible in the reference. Current-season outcomes never enter this season-opening snapshot. No older seasons roll forward across gaps. Use #28's minimum-exposure scoring cohort. Report the eligible keys, scored keys, and misses by reason, including neutral cold inputs (intercept or Zero). For comparisons across references on common seasons, pair on players with at least 250 possessions per side under both labels and use the contiguous K0 scoring truth for both; report each reference's own K0 results separately. K0 penalties were chosen in #28 at the final origin and the K0 rows serve solely as the scorer's benchmark, with no influence on predictions, fit or selection. No K0 result is a held-out game forecast.

Minutes bands use positive-minute appearances available at the snapshot: no history, less than 15, 15 to under 25, and 25 or more minutes per game. Report both role effects and partitions by label-side minimum exposure (250–999, 1000–1999, 2000+ smaller of the offense and defense counts), where exposure is a retrospective scoring attribute. Player age and basketball role/position have no validated dated source here. Record age and basketball-role breakdowns as unavailable, with cohort counts, and do not infer them from outcomes or player IDs. The offense/defense sides are model components and do not substitute for basketball role.

## 5. Strictly earlier inputs to the realized-lineup diagnostic

Use all accepted canonical possessions of each chronological evaluation season. Hold SPM coefficients and comparator fits fixed throughout that season. For an evaluation date `D`, aggregate box logs from the immediately preceding calendar season if eligible in the reference and the current season's games with official played date `< D`. The previous season is also filtered by the same date rule. Pool regular and postseason history under §2. Evaluate these date-specific, prior-only snapshots for the ten players identified by the scorer on each realized possession. Neither their current minute totals nor any same-date box outcome enters a prior. Final game lineups, pre-possession context and accepted possessions define the scoring cohort only. Age and basketball-role slices remain unavailable. For minutes slices, classify the offensive lineup by the mean of known earlier minutes per appearance (same cutoffs as §4, no-history if none), and report a separate flag if any of the ten players lacks history. Count fallback players and possessions. The result is a realized-lineup diagnostic under retrospective source bounds.

Use the preceding eligible season's complete accepted rows, strictly before the evaluation season's first date, for all on-court comparator fits, including folds that cross gaps. Freeze the earlier unit-weight scoring mean and the repository's standard context-only regression on pre-possession covariates. Compare those with standalone zero-prior RAPM and jointly context-adjusted zero-prior RAPM, both with fixed offense/defense penalties 4000/8000 and zero for unseen players. Compare context plus Full SPM, context plus One-stat SPM and context plus the offense-only and defense-only Full contributions. The prediction adds the five offensive priors and subtracts the five defensive priors from the context-only possession baseline, all in points per 100. No informed RAPM is fit here. The later #35/#36 comparisons retain all four ADR-0026 comparators.

Score paired MSE in points per possession squared, overall and by regular season/playoffs, evaluation fold, minutes and history slices. Also report represented team-game points-per-possession RMSE and represented game-margin MAE and RMSE using sums of canonical model points on the same accepted rows. Represented margin follows the pinned row contract and may differ from the official final margin. This diagnostic does not validate pregame minutes or a pre-tip forecast. Evidence of independent on-court value relative to context requires a lower pooled common-modern possession MSE for context plus Full, with a 95% paired week-block interval excluding zero. Report deltas against both RAPM comparators regardless of sign.

## 6. Reproducibility and stopping

Use 1,000 paired resamples with seed 30. For K0, resample whole players with their available season rows. For possession MSE, resample Monday-through-Sunday Eastern calendar weeks within each evaluation season and keep whole games. Weight bootstrap draws by the applicable observation denominator within each draw. Do not represent sparse slices as confirmatory.

Record protocol SHA-256 and commit, exact input digests, build and package versions, origin cutoffs and coverage, model and prediction digests, fallback counts, overlap checks, private forecasts and aggregate results. Store dated priors with fit IDs and candidate ancestry. Frozen date-specific predictions precede joining evaluation labels and scores in the runner. Add synthetic tests for train-only transforms and weights, side signs, cohort and origin joins, and poisoning current/later box rows and outcomes with no change to earlier predictions. A clean-tree run with verified pins writes one new private version, with recovery after a failed run documented. Report unavailable folds and deviations. Preserve results regardless of direction. Any methodological change requires its own registered revision before a new fit.
