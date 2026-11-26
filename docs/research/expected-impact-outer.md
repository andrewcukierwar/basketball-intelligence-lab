# Expected impact v1: outer validation, 2023–24 and 2024–25

This is the [#36](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/36) run of the [frozen addendum](expected-impact-outer-addendum.md) (SHA-256 `1076ab0b…762d7c`). It scores the [#35 configuration](expected-impact-v1.md) with nothing re-tuned.

**Evidence class:**
- Partial-history methodology replication under retrospective capture bounds.
- Outer-fold development evidence, not confirmatory. M2 had already scored the comparators on these seasons, as the addendum states.
- The 2025–26 holdout was not read. No EPM output was used.

## Run record and deviation

- **First attempt crashed before writing any result.** It stopped on load at `88d79a3`. The 2024–25 NBA.com team log leaves `home` null for both teams in five neutral-site regular-season games, which is the ADR-0017 case, and the box loader rejected those player rows.
- **Fix.** `fe81b0a` accepts a both-null pair, counts it, and still rejects a mixed or equal pair. It is a no-op for every season without null flags. Home is not an SPM input.
- **Rerun.** The single scored run used clean `fe81b0a` and took 15 s with 2.05 GiB peak memory.
  - All 41 fits converged.
  - 118 appearances from the unflagged games entered box history.
  - Manifest SHA-256 is `f74fc2a5e76b7a22964ca8b96736344bc49f3611dd0acf37fbdaeb9ae130a131`.
- **Addendum.** Unchanged. The addendum allows a rerun after a crash that precedes results.
- **Consistency check.** The frozen comparators reproduce M2's outer result. Context-offset RAPM minus `W1` context is −24.73 on the regular season, matching ADR-0025's 24.7.

## Possession MSE

The table shows (points per 100)². Deltas are EI minus the comparator, with 95% game-clustered and week-clustered bootstrap intervals. Regular-season blocks contain 418,479 possessions; playoffs contain 26,725.

| Comparator | Regular MSE | EI delta, regular | Verdict | Playoffs MSE | EI delta, playoffs |
| --- | ---: | --- | --- | ---: | --- |
| **EI** | 14,261.07 | — | — | 14,148.86 | — |
| **RAPM + context (primary)** | 14,265.66 | −4.59 [−5.80, −3.37] / [−5.60, −3.53] | `ei_better` | 14,153.58 | −4.71 [−7.53, −1.71] / [−7.02, −2.08] |
| Zero prior at EI penalties | 14,267.48 | −6.41 [−7.80, −5.01] / [−7.58, −5.23] | `ei_better` | 14,150.88 | −2.02 [−5.43, 1.34] / [−5.16, 1.83] |
| EI offense deviations only | 14,266.72 | −5.66 [−7.28, −3.99] / [−7.19, −4.12] | `ei_better` | 14,171.63 | −22.77 [−31.37, −14.38] / [−33.21, −13.98] |
| EI defense deviations only | 14,269.11 | −8.05 [−9.79, −6.31] / [−9.75, −6.34] | `ei_better` | 14,143.72 | +5.14 [−7.02, 17.73] / [−7.32, 19.85] |
| SPM-only | 14,272.72 | −11.65 [−13.77, −9.33] / [−13.43, −9.76] | `ei_better` | 14,157.91 | −9.05 [−19.35, 0.62] / [−18.69, 1.64] |
| Context (`W1`) | 14,290.39 | −29.32 [−32.72, −25.88] / [−32.34, −26.16] | `ei_better` | 14,165.19 | −16.33 [−31.41, −1.61] / [−29.00, −0.49] |
| Zero-prior RAPM | 14,299.21 | −38.14 [−41.87, −34.36] / [−41.94, −34.56] | `ei_better` | 14,180.75 | −31.89 [−46.85, −15.77] / [−49.06, −12.72] |
| League (`W1`) | 14,322.60 | −61.53 [−66.54, −56.55] / [−65.96, −56.85] | `ei_better` | 14,194.78 | −45.92 [−68.76, −23.87] / [−64.87, −25.77] |

- **Primary comparator.** Against context-offset RAPM, EI is lower in both seasons: −4.28 in 2023–24 and −4.91 in 2024–25. It is lower in all ten blocks, by −1.28 to −10.87, including both playoff blocks.
- **Prior at equal penalties.** EI beats the zero-prior ablation in every block (−1.09 to −14.48). So the SPM prior adds possession-level value, not merely a different penalty.
- **On-court update.** EI beats SPM-only in every block.
- **Playoffs.** These are reported, not adjudicated. The defense-only part is no worse than EI there, with an interval that includes 0.

## Team-game RMSE

Units are points of summed predictions per team-game.

| | EI | RAPM + context | Zero-prior at EI penalties | Zero-prior RAPM | Context | League | SPM-only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Regular | 10.947 | 11.017 | 11.051 | **10.614** | 11.508 | 11.081 | 11.235 |
| Playoffs | 11.580 | 11.648 | 11.537 | 11.462 | 11.539 | **11.453** | 11.707 |

EI improves on context-offset RAPM at team level too. Zero-prior RAPM without the context offset still has the lowest regular-season team-game RMSE. This matches #30's game-margin observation and ADR-0026's warning that one configuration need not win every objective. Possession-level MSE remains the registered metric. Team-level ranking is a reported tension for #39.

## Slices (regular season, EI minus RAPM + context)

| Slice | Possessions | Delta [game 95%] |
| --- | ---: | --- |
| All ten players ≥ 1,000 window possessions | 255,238 | −3.87 [−4.86, −2.85] |
| Some player under 1,000 | 163,241 | −5.73 [−8.32, −2.92] |
| All ten with box history | 354,184 | −4.91 [−6.11, −3.64] |
| Some player on the SPM intercept fallback | 64,295 | −2.87 [−6.43, 0.51] |

The gain is largest where exposure is thin. It is weakest where a player has no box history and the prior is only an intercept, which is what one would expect. Every scored game in both seasons has liveData verification.

## Stability

The stability set is players with at least 1,000 window possessions at both dates.

- **Within a season.** Total ratings correlate 0.94–0.99 between consecutive cutoffs, with an RMS change of 0.16–0.62 points per 100.
- **Year over year.** From 2023-10-01 to 2024-10-01, 434 players: r = 0.75, RMS change 1.28.

## Ratings and frozen state

The private `ratings.csv` holds 11 snapshots: the ten outer cutoffs, plus 2025-07-01. The 2025-07-01 snapshot is the pre-holdout state:
- window 2023-10-24 to 2025-06-22;
- box data through 2025-06-22;
- 926 players, of whom 232 are on the intercept fallback design-wide.

Per the addendum, `ei`, the four ADR-0026 comparators and the ablations are the frozen reference set for the R1 confirmatory protocol in #42.

## Limitations

- **Not confirmatory.** These are known seasons, so this is development evidence.
- **Frozen SPM.** The SPM is one locked pre-window fit, trained on targets through 2022–23. Its side-level K0 criterion did not pass in #30.
- **Cold starts.** Box histories do not roll forward past one season.
- **Team-level ranking.** It favors plain RAPM in the regular season.
- **Skills input.** Estimated Skills inputs remain unavailable (#125).
