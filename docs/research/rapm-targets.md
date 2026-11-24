# RAPM training targets for box-score SPM: results (issue #28)

**This is a _partial-history methodology replication_, not a full historical EPM replication** ([ADR-0026](../DECISIONS.md#adr-0026--maintainer-decisions-of-2026-11-24-m2-acceptance-informed-rapm-comparators-and-partial-history-spm-targets)). EPM's box-score SPM target spans 2003–04 through 2022–23. These targets use the 10 eligible seasons: 2005–06 to 2007–08, 2015–16, 2016–17, and 2018–19 to 2022–23.

[Issue #28](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/28) built provisional, independent long-window RAPM labels for training box-score SPM (#30), with offense and defense kept separate. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). Labels for individual players stay in the private run directory, so this report gives aggregates only, with no named players or rankings.

**Evidence tier: `retrospective_capture_bound`.** Every number is **Experimental**. No EPM output, outer-season row (2023–24, 2024–25) or holdout file (2025–26 and later) was read.

## Provenance

- **Protocol.** [Revision 2](rapm-targets-protocol.md), SHA-256 `5fade9a4b45662cc1d7fa241fb1d729426afae759a776ad81085156456b4ed2c`, committed at `2261ec7` before any real-data fit. Revision 1 (`0195f99`) was changed after an independent review that found two blockers: an evaluation label whose meaning varied by fold, and a two-stage context offset. Protocol §13 gives the history.
- **Code.** `e36ba78` is the robustness and checkpoint fix that the re-review asked for before the run. It records a failed stage instead of stopping, and it adds resumable checkpoints. It did not change the protocol, which the re-review had approved.
- **Run.** It ran once, from a clean tree at `e36ba78`, into `data/processed/rapm_targets/issue-28-v1/`. The manifest SHA-256 is `40fcfba9…e043`. The runner checked that the protocol was committed and unchanged, and recorded its digest, commit and the tree state in the manifest and in every frozen-target record.
- **Runtime.** The run was not interrupted, and no stage was resumed from a checkpoint.
  - 6,755 s wall (1 h 53 min); peak resident memory 3.0 GiB.
  - 8,828 sparse joint fits, all converged (LSQR stop code 2): 11 to 81 iterations, largest condition estimate 165, median fit 0.49 s.
- **Failures.** No stage failed and no origin was marked unavailable by a failure.
- **Inputs.** 2,117,689 canonical rows from 12,640 accepted games, pinned by row-set and pilot manifest digests (protocol §2). All timing audits were zero. No season contains the ADR-0023 repair stratum.

| Claim | Label |
| --- | --- |
| Long-window independent RAPM as the SPM target, with home and score-state adjustment and playoffs included | **Documented** (EPM methodology) |
| Season-centred `K365` kernel, joint context fit, in-window CV penalties, origins, centring, cohorts | **Original** |
| Every number below | **Experimental**, retrospective |
| Explanations marked "Inferred" | **Inferred** |

## Origins and penalties

| Reference | Origin (closes) | Seasons | Rows | $\lambda_o$ / $\lambda_d$ |
| --- | --- | --- | ---: | --- |
| contiguous | 2019-06-14 (2018–19) | 1 | 223,686 | 4,000 / 4,000 |
| contiguous | 2020-10-12 (2019–20) | 2 | 418,814 | 4,000 / 4,000 |
| contiguous | 2021-07-21, 2022-06-17, 2023-06-13 | 3–5 | 619,070 to 1,066,152 | 2,000 / 4,000 |
| extended | 2006-06-21, 2007-06-15, 2008-06-18 (2005–08) | 1–3 | 205,754 to 620,566 | 1,000 / 4,000 |
| extended | 2016-06-20 to 2023-06-13 (7 origins) | 4–10 | 835,653 to 2,117,689 | 2,000 / 4,000 |

- **Every origin was fitted.** The only unavailable origins are the gaps the protocol fixed in advance: 2008–09 to 2014–15 and 2017–18 in the extended reference. The first season of each reference has no earlier target to train on.
- **No optimum fell on a grid edge.** The in-window cross-validation surface is flat: the selected pair is within 1 to 4 (points per 100)² of its neighbours. The defense penalty is twice the offense penalty (4,000 against 2,000) at most origins, as in #26. The first two contiguous origins chose 4,000 for both roles, and the 2005–08 origins chose a lower offense penalty (1,000).
- **The `evaluation_K0` labels** (season-only, the #30 evaluation labels) selected 2,000 / 4,000 in both references.
- **Fitted context.** The end-of-period coefficient is about −29 points per 100 in every fit, the run-out structure kept under ADR-0019. Season-type levels put playoff scoring 0.4 to 3.4 points per 100 below the same season's regular season.

## Reliability (final origin, primary `K365` labels)

Split-half results pair players with at least 250 possessions in the role in both halves. The two halves share no possession. SB is the Spearman–Brown full-sample reliability.

| Group | Contiguous offense r / SB (pairs) | Contiguous defense r / SB | Extended offense r / SB (pairs) | Extended defense r / SB |
| --- | --- | --- | --- | --- |
| All | 0.49 / **0.66** (1,988) | 0.46 / **0.63** | 0.53 / **0.69** (3,805) | 0.47 / **0.64** |
| Under 2,000 possessions in the season | 0.24 / 0.38 | 0.40 / 0.57 | 0.24 / 0.39 | 0.37 / 0.54 |
| 2,000–5,000 | 0.28 / 0.44 | 0.34 / 0.51 | 0.27 / 0.43 | 0.37 / 0.54 |
| 5,000–10,000 | 0.48 / 0.65 | 0.53 / 0.69 | 0.50 / 0.67 | 0.52 / 0.69 |
| 10,000 or more | 0.58 / 0.74 | 0.54 / 0.70 | 0.65 / 0.79 | 0.52 / 0.69 |
| One team in the season | 0.51 / 0.67 | 0.47 / 0.64 | 0.54 / 0.70 | 0.48 / 0.65 |
| More than one team | 0.35 / 0.52 | 0.36 / 0.52 | 0.38 / 0.55 | 0.35 / 0.52 |
| Era 2005–08 | — | — | 0.58 / 0.73 | 0.53 / 0.69 |
| Era 2015–17 | — | — | 0.53 / 0.70 | **0.37 / 0.55** |
| Era 2018–23 | 0.49 / 0.66 | 0.46 / 0.63 | 0.50 / 0.67 | 0.47 / 0.64 |
| `no_livedata` (2018–19, 2019–20) | 0.48 / 0.65 | 0.47 / 0.64 | 0.51 / 0.67 | 0.48 / 0.65 |
| liveData (2020–21 to 2022–23) | 0.50 / 0.67 | 0.45 / 0.62 | 0.50 / 0.67 | 0.45 / 0.62 |

By season, contiguous offense SB is 0.60 to 0.72 and defense SB is 0.57 to 0.68. The 2022–23 labels are among the lowest (0.62 and 0.57), because they have only backward support.

**Bootstrap** (100 game-clustered replicates; no replicate failed). The reliability below is $1 - \overline{SE^2}/\mathrm{Var}$ by exposure band. The mean standard error is 0.5 to 1.1 points per 100.

| Band | Contiguous offense | Contiguous defense | Extended offense | Extended defense |
| --- | ---: | ---: | ---: | ---: |
| Under 2,000 | 0.36 | 0.38 | 0.37 | 0.41 |
| 2,000–5,000 | 0.44 | 0.53 | 0.42 | 0.54 |
| 5,000–10,000 | 0.64 | 0.61 | 0.65 | 0.64 |
| 10,000 or more | 0.73 | 0.67 | 0.76 | 0.66 |

**Spread.** In the minimum-exposure cohort (at least 250 possessions in each role), offense labels have a standard deviation of about 1.6 to 1.9 points per 100 by season and defense labels about 1.0 to 1.2. Under 2,000 possessions, offense standard deviation is about 1.1 and defense about 0.7, because ridge shrinkage holds low-exposure labels toward the season average.

## Stability

**Label revision as later seasons arrive** (contiguous; correlation with the final-origin label, all labelled players):

| Label | At its own origin (one-sided) | One origin later | Two or more origins later |
| --- | --- | --- | --- |
| Offense | r 0.86 to 0.94, RMS 0.56 to 0.95 | r 0.97 to 0.98, RMS 0.31 to 0.59 | identical (r 1, RMS 0) |
| Defense | r 0.86 to 0.94, RMS 0.35 to 0.56 | r 0.97 to 0.98, RMS 0.20 to 0.28 | identical |

- **Penalty versus data.** With the final penalties held fixed, most of these revisions remain, so they come from the new data. The exception is the early origins whose penalty differed. The 2018–19 offense label at the 2020 origin moves by RMS 0.59 as frozen and 0.34 under the final penalties. Extended 2005–08 labels move by RMS 0.56 to 0.60 on offense when $\lambda_o$ rises from 1,000 to 2,000 at the 2016 origin, and they are identical under fixed penalties.
- **Why labels freeze.** The 730-day cap stops labels from changing two origins on. That is also why every history-season label is final from the 2016 origin onward.

**Contiguous against extended** (final origin): 2018–19 labels agree with r 0.968 on offense (RMS 0.40) and 0.975 on defense (RMS 0.23). The 2019–20 to 2022–23 labels are **identical**, because 2016–17 lies beyond the 730-day cap of those seasons and the selected penalties are the same.

**Year-to-year persistence of season-only (`K0`) labels.** These labels share no data across seasons, and the comparison covers all labelled players in both seasons.

| Pair | Elapsed days | Players | Offense r | Defense r | Total r |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2005→2006, 2006→2007 | 369 to 371 | 362 to 366 | 0.42 | 0.32 | 0.40 to 0.43 |
| 2007→2015 | 2,922 | 121 | 0.12 | 0.14 | 0.19 |
| 2015→2016 | 386 | 361 | 0.37 | 0.25 | 0.40 |
| 2016→2018 | 726 | 329 | 0.27 | 0.21 | 0.34 |
| 2018→2019 to 2021→2022 | 401 to 450 | 316 to 428 | 0.23 to 0.35 | 0.20 to 0.34 | 0.27 to 0.38 |

For players with 10,000 or more possessions, the correlations rise to 0.27–0.67 on offense and 0.19–0.66 on defense, but these bands hold only a few dozen players each. The primary `K365` labels correlate with the `K0` labels of the same season at 0.71 to 0.88.

**Sensitivity** (contiguous, final origin; correlation with the primary labels by season):

| Scenario | Penalties | Offense r (RMS) | Defense r (RMS) |
| --- | --- | --- | --- |
| `two_stage_offset` (revision-1 estimator) | 2,000 / 4,000 | 0.998 (0.10–0.13) | 0.998–0.999 (0.06–0.07) |
| `regular_only` | 2,000 / 4,000 | 0.986–0.990 (0.23–0.28) | 0.981–0.986 (0.17–0.21) |
| `K730` | 2,000 / 4,000 | 0.959–0.988 (0.28–0.46) | 0.947–0.983 (0.23–0.35) |
| `exclude_no_livedata` (2020–21 to 2022–23) | 2,000 / 4,000 | 0.950–1.000 (0–0.54) | 0.914–1.000 (0–0.43) |
| `pooled_window` | 4,000 / 4,000 | 0.872–0.961 (0.49–0.76) | 0.858–0.948 (0.42–0.64) |

## Findings

- **Reliability.** The labels are moderately reliable and **not reliable for low-exposure players**. Full-sample split-half reliability is about 0.66–0.69 for offense and 0.63–0.64 for defense. It falls to about 0.4 on offense below 2,000 target-season possessions. Players who changed teams have lower reliability (0.52–0.55) than single-team players (0.65–0.70). Inferred: they have fewer possessions with each set of teammates.
- **Defense.** Defensive labels are nearly as reliable as offensive ones at the level of a season. This differs from #26, where defense-only predictions did not beat the league mean. Reliability measures internal consistency, not predictive validity. The 2015–17 era has the weakest defensive reliability (0.55).
- **Persistence.** Single-season impact persists weakly: K0 year-to-year correlations are 0.2–0.4, and about 0.1–0.2 across the 2007–08 to 2015–16 gap. The `K365` labels therefore mix in neighbouring seasons, and SPM trained on them inherits that smoothing (Inferred).
- **The extended reference adds history-season labels but almost no information to modern labels.** Only the 2018–19 labels differ from the contiguous ones. #30's choice between references is mainly whether to train on the 2005–08 and 2015–17 player-seasons.
- **The joint fit barely differs from the two-stage fit on real data** (r 0.998). Revision 2 was right in principle, and the composition bias the review identified is small here.
- **One-sided labels at their own origin differ materially from their final values** (r about 0.86–0.94). #30 must register how it uses them (protocol §6).
- **Playoffs and verification strata matter little.** Removing playoffs changes labels by r of at least 0.98. The `no_livedata` seasons are as reliable as the liveData seasons, and excluding them shifts the 2020–21 labels by r 0.95 and 0.91.

## Cohorts and the #30 registration

- **Final-origin label cohort (primary targets):** 5,076 extended player-season labels (all 10 seasons) and 2,746 contiguous ones.
- **Minimum-exposure cohort (at least 250 possessions in each role):** 2,276 contiguous labels and 4,315 extended labels.
- **Chronological folds and evaluation labels.** The machine-readable folds are in `results.json` (`chronological_registration`), with the season-only evaluation labels in `evaluation_labels.csv`.
- **Unavailable folds:** 2018–19 (contiguous) and 2005–06 (extended).

## Deviations

1. **Output directory.** Protocol §10 names `data/processed/targets/issue-28-v1/`. The run wrote to `data/processed/rapm_targets/issue-28-v1/`, as the coordinator directed. Only the location differs.
2. **Runner commit.** The run used `e36ba78`, one commit after the protocol commit `2261ec7`. That commit implements §10's failure rule and adds checkpoints. It does not touch the protocol or any estimation path. The protocol digest the runner verified is the frozen one.

No other deviation. The run ran once and was not resumed.

## Limitations

- **Coverage and evidence tier.** This is a partial history: 10 of EPM's 20 seasons, with a seven-season gap. The data are capture-bound retrospective, and the labels are stable-lineup possessions only (ADR-0013).
- **Fixed choices.** The kernel half-life and cap were fixed, not tuned. The CV surface is flat, so the penalties are weakly determined.
- **Bootstrap.** Its standard errors describe the shrunken estimator. They are not the error against a true effect.
- **Context.** Neutral sites are uncoded, including the 2019–20 bubble. The home effect is common within each fit.
- **Validity.** No predictive validity of the labels is claimed here. That belongs to #30 and to later informed RAPM.
