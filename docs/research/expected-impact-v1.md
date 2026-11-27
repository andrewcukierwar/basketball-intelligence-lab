# Expected impact v1: inner development results

This is the run for [#35](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/35) under the [frozen protocol](expected-impact-protocol.md) (SHA-256 `28869a50…4889d`). The evidence is a **partial-history methodology replication** under retrospective capture bounds. It is development evidence: the same eight regular-season blocks chose the penalties and scored them. Independent validity is the outer-fold question for [#36](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/36). No 2023–24 or later row, and no EPM output, was read. Estimated Skills inputs are unavailable at these cutoffs (ADR-0030, [#125](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/125)).

## Selected configuration

`W2` window (1–730 days, unit weight), context offset, SPM-centered residual ridge with **λ_O = 8,000 and λ_D = 8,000**. The M2 search evaluated 14 penalty pairs. The top six pooled MSEs lie within 0.84 (points per 100)², so the selection is a near-tie, as in ADR-0025. The zero-prior RAPM optimum chose λ_O = 4,000, so centering on the prior moved the offense penalty up one grid step.

## Development scores

The table shows pooled possession MSE in (points per 100)². Deltas are EI minus the comparator, with 95% game-clustered and calendar-week-clustered bootstrap intervals (2,000 resamples).

| Model | Regular MSE (418,731) | EI delta, regular | Playoffs MSE (28,351) | EI delta, playoffs |
| --- | ---: | --- | ---: | --- |
| EI (prior + RAPM + context) | 14,078.52 | — | 14,119.21 | — |
| RAPM + context offset (4,000/8,000) | 14,080.85 | −2.33 [−3.35, −1.30] / [−3.25, −1.40] | 14,119.75 | −0.54 [−3.04, 1.99] / [−4.14, 3.43] |
| SPM-only (context + prior) | 14,087.25 | −8.73 [−10.95, −6.58] / [−11.03, −6.39] | 14,125.23 | −6.03 [−13.24, 1.14] / [−12.49, 0.02] |
| Context only | 14,098.02 | −19.51 [−22.60, −16.55] / [−22.78, −16.20] | 14,128.32 | −9.11 [−19.70, 0.97] / [−14.35, −3.22] |
| Zero-prior RAPM | 14,109.76 | −31.24 [−34.52, −27.95] / [−34.54, −28.03] | 14,161.97 | −42.77 [−55.19, −30.81] / [−53.76, −35.26] |
| League mean | 14,126.62 | −48.11 [−52.33, −43.88] / [−52.34, −43.90] | 14,172.54 | −53.33 [−69.71, −38.06] / [−64.77, −44.70] |

- **Against context-offset RAPM**, the primary ADR-0026 comparator, EI is lower in both seasons: −2.33 in 2021–22 and −2.34 in 2022–23. It is lower in all eight regular blocks, by −1.31 to −6.77. In the playoffs it is a tie: −2.83 in 2021–22 and +1.78 in 2022–23.
- **Against SPM-only**, the on-court update improves on the prior in every block.
- **Parts.** Keeping only the offensive or only the defensive deviation is worse than both together on regular blocks (+3.62 and +8.13 MSE above EI).
- **Verification strata.** Both scored seasons are entirely liveData-verified, so the `no_livedata` stratum is empty.

## Ratings

The private `ratings.csv` has 863 players at each of 11 dates: the ten block cutoffs and the final development snapshot at 2023-07-01 with `final_contiguous_fit.json`. Each row gives the prior, deviation and rating per side, the total, window possessions, box-history flag, snapshot ID and SPM origin.

- **Spread.** Among players with at least 1,000 window possessions, the offense prior SD is 0.89–1.23 and the deviation SD is 0.71–0.78. The total rating SD is 1.63–1.79 points per 100.
- **Prior vs rating.** Offensive prior and rating correlate at 0.84–0.89.
- **Fallbacks.** 151 of the 863 design players had no box history at the final cutoff and received the SPM intercepts. This count is design-wide and includes players absent from the window. Box-only players would have exposure and deviation 0. None occurred at the final cutoff.

## As-of rating artifact (#135)

The v1 export, `ei-ratings-v1`, lists every player in the global multi-season design. Its roster, digest and inferred cold total therefore depend on players who first appear after the cutoff. Ratings are unaffected. Astra audit A1 reproduced the dependency on `1d29416`. `as_of_ratings()` writes `ei-ratings-as-of-v2` and changes three things:

- **Roster.** A player is on the roster if they have completed box history before the cutoff or exposure in the fit window.
- **Cold priors.** Each row carries `artifact_version` and the explicit per-side `cold_offense` and `cold_defense` priors, the SPM intercepts. `team_outcomes.load_ratings` uses them for any player absent from the roster.
- **Digest.** `snapshot_id` covers the values at the exported 6-decimal precision. A design that also indexes later players solves a larger system and moves the fit by about 1e-15.

Possession-level predictions still use the full design, so realized-lineup scoring is unchanged. A regression test appends a later on-court identity and a later box-only identity. It checks that the roster, ratings, coverage, cold priors, digest, unknown-player team score and keyed earlier predictions do not change. It also checks a snapshot with no no-history roster members.

The frozen #35/#36/#39/#42 runners still write and read v1, so their artifacts reproduce. In the frozen `issue-35-v1` and `issue-36-v1` files, every snapshot exports 96 to 265 players who are not eligible at its cutoff. All of them have exactly the inferred cold total, which is one value per snapshot. Their team margins therefore equal what v2 would give (**Inferred** from the artifacts, not rerun). The difference is in reported coverage. The #39 note that no projected minutes fell on the cold rating counts those players as rated. Under v2 their minutes would be cold minutes. New consumers (#43, #129) should write and read v2.

## Eligibility, provenance and runtime

- **Eligibility audit.** At every cutoff, the last window row, last box row and SPM origin are strictly before the cutoff, and no scored game is in its own window. At the final cutoff the window is 2021-07-01 to 2023-06-12, the box data ends 2023-06-12, and the SPM origin is `contiguous@2023-06-13`.
- **Run.** Clean commit `0b605c7`, 36 s, 1.69 GiB peak memory. All 143 LSQR fits converged (median 33 iterations, maximum condition estimate 124). Private output is `data/processed/expected_impact/issue-35-v1`, manifest SHA-256 `db254b8c450034a0142255c40301e74cd6ddc59d505ab6d7aef983f846fce5d1`.

## Limitations

- **Optimistic scores.** Selection and scoring share folds.
- **Comparator tuning.** The comparators are not re-tuned here. ADR-0025's 4,000/8,000 penalties were themselves chosen on these folds for zero-prior RAPM.
- **SPM status.** The SPM prior is provisional (ADR-0030): #30's K0 criterion did not pass on either side.
- **Coverage.** Two inner seasons. Single SPM coefficients per season. Box histories do not roll forward across older seasons, so players who returned after a missed season start from the intercepts.
- **Configuration for #36.** λ_O = λ_D = 8,000, `W2`, M2 refit schedule, context offset. The outer SPM policy is the locked pre-window `final_contiguous_fit.json` (cutoff 2023-06-13), registered in #36 before any outer read.
