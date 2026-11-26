# Agreement between Expected impact v1 and published EPM

This is the [#40](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/40) run of the [registered protocol](epm-agreement-protocol.md) (SHA-256 `0152e248…d6bf5`). EPM data come from dunksandthrees.com (archived public page) and are used with written permission, non-commercial only.

**Evidence class:**
- **External agreement diagnostic.** This is not predictive validity, and it selected and tuned nothing. EI v1 was frozen before any EPM value was read (ADR-0031, ADR-0032).
- **Not read:** EPM for 2025–26 or later, and the holdout.
- **Run:** clean commit `12a225d`, 0.5 s. Manifest SHA-256 `bbebb1a6b2b8cf2179dd7cf36441a3b8097ac186ef0e77ae3376b59029aaec8c`.

## Sources and alignment

| EPM season | Archive capture | EPM content | EI snapshot | EPM players | Primary matched |
| --- | --- | --- | --- | ---: | ---: |
| 2021–22 | 2022-07-03 | Season EPM, regular season | 2022-10-01 | 592 | 478 |
| 2022–23 | 2023-07-05 | Season EPM, regular season | 2023-07-01 | 497 | 450 |
| 2023–24 | 2024-07-01 | Season EPM, regular season | 2024-10-01 | 518 | 457 |
| 2024–25 | 2025-07-18 | Expected EPM as of 2025-06-22 | 2025-07-01 | 587 | 482 |

- **Matching.** All EPM players matched an EI player by NBA ID, except 8 in 2024–25.
- **Dropped rows.** Rows with missing `off` or `def` (57 in 2022–23, 77 in 2023–24) were dropped and counted.
- **No multi-stint rows** appeared.
- **Primary cohort.** EI window possessions of at least 1,000. It covers 1,867 player-seasons from 690 players.
- **Known differences** in scope were not adjusted:
  - EI uses a two-season window with playoffs.
  - Season EPM covers one regular season.
  - The 2024–25 EPM is a forward-looking expected rating, so it is the closest match to EI's snapshot.

## Pooled agreement (primary cohort)

Units are points per 100 possessions. Bias is EI minus EPM. The bracketed figures are 95% player-cluster bootstrap intervals.

| Side | EI Pearson r | Spearman ρ | MAE | RMSE | Bias | SPM prior alone r | EI r − prior r |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Offense | 0.862 [0.840, 0.880] | 0.821 | 1.07 | 1.33 | +0.56 | 0.840 | +0.022 [+0.007, +0.038] |
| Defense | 0.699 [0.671, 0.727] | 0.695 | 0.73 | 0.93 | +0.19 | 0.481 | +0.218 [+0.172, +0.265] |
| Total | 0.825 [0.799, 0.846] | 0.798 | 1.41 | 1.77 | +0.75 | 0.762 | +0.063 [+0.042, +0.087] |

- **Overall.** EI and EPM agree strongly on offense and total and moderately on defense. The defense sign conventions agree.
- **On-court update.** It brings EI much closer to EPM on defense, where the box-only prior is weakest.
- **Level offset.** EI sits above EPM on average, by +0.75 total. The gap is largest for lower-exposure players, at +1.6 to +2.4 total in the 1,000–2,999 window-possession band. That is consistent with different centering and shrinkage targets, which this diagnostic does not resolve.

## By season (primary cohort, total)

| Season | EI r | Prior r | EI defense r | EI bias | Top 25 shared | Top 50 shared |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021–22 | 0.817 | 0.719 | 0.702 | +0.63 | 76% | 66% |
| 2022–23 | 0.798 | 0.759 | 0.610 | +0.77 | 72% | 64% |
| 2023–24 | 0.839 | 0.794 | 0.690 | +0.87 | 80% | 72% |
| 2024–25 (expected) | 0.874 | 0.806 | 0.842 | +0.74 | 76% | 68% |

- **Top-N overlap** is the share of EPM's top N by total that is also in EI's top N.
- **Exposure.** Agreement rises with exposure. In the 3,000+ window-possession slice, total r is 0.79–0.88. In the 1,000–2,999 slice it is 0.68–0.81.
- **No cold-start players.** No matched player was on the SPM intercept fallback.

## Deviations and review notes

- **Alignment gaps.** The protocol asks for the gap between each EPM capture and its EI snapshot, but the runner did not write it. Computed from the pinned dates, the capture minus EI `as_of` is −90, +4, −92 and +17 days. The 2024–25 data date (2025-06-22) is 9 days before its EI snapshot. The season captures carry no data date. The page describes them as covering the regular season, and for the 2021–22 JSON form that cannot be checked from the records.
- **Private artifacts.** The protocol lists a separate parsed EPM table with its digest, but the run wrote only the matched table (`matched.csv`). That table contains every parsed player except the 8 unmatched in 2024–25, so the analysis is unaffected.
- **Total.** EPM `tot` was not read. A post-run check found it equal to `off + def` within 0.0001 in every capture.
- **Rerun recovery.** The runner's `.partial` stage directory had to be removed by hand after a crash. This is fixed after the run, and it changes no result.

## What this does and does not show

- **Shows.** It is **Experimental** evidence on EPM-U12. A from-scratch, EPM-independent pipeline built from public data broadly reproduces EPM's player ordering. The closest agreement is the like-for-like 2024–25 expected rating, at total r 0.87 and defense r 0.84.
- **Does not show.** Agreement is not accuracy. Both models share box-score and on-court inputs, and higher agreement would not make either one more predictive. The predictive evidence is in #35, #36 and #39.
- **Not used.** No result here changes EI v1 or any #42 candidate.
- **Limitations:**
  - The captures are archive snapshots, with capture dates rather than publication logs.
  - Season EPM and EI differ in window and scope.
  - Plain RAPM was not stored, so it is not compared.
- **Artifacts.** The private run directory holds the matched table. Only these aggregates are in the repository.
