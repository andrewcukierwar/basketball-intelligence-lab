# Defensive tracking against the box-only SPM reference

This is the [#38](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/38) run of the [registered protocol](tracking-spm-protocol.md) (SHA-256 `d7b8881d…a132`).

**Evidence class:**
- Partial-history methodology replication under retrospective capture bounds.
- Strict historical eligibility is empty, because no dated matchup revision predates any origin ([#37 audit](nba-defensive-tracking-audit.md)).
- Not read: EPM output, 2023–24 and later, and the 2025–26 holdout.

**Run:**
- Clean commit `38718f9`, 11 s, 0.98 GiB peak memory.
- Manifest SHA-256 `236795ae5b296215d3233de9ee61b94c9828798e86d4a596c9caa8fe620b5962`.
- **Pre-run review.** An independent Sonnet subagent found no blockers. Its non-blocking points were fixed in `38718f9` before any fit: null-quantity handling, wording, and a reporting-path test.

**Reproduction checks passed.** Every fold's refitted `full` matched #30's stored coefficients. Context plus `full` reproduced #30's pooled MSE exactly: 1.4091153 points per possession squared.

## Coverage against the documented window

- **Unused window season.** The documented window is 2017–18 through 2022–23. The contiguous `K365` chain begins in 2018–19, so 2017–18 tracking is unused: it has no #28 target and no #30 box pin.
- **Seasons used.** Tracking for 2018–19 through 2022–23 is used for training windows and snapshots. The scored folds are 2019–20 through 2022–23.
- **Linked defender-games** reproduce the #37 audit, and 10 were unlinked in total.

  | Season | Regular linked / box | Playoffs linked / box |
  | --- | ---: | ---: |
  | 2018–19 | 25,930 / 26,098 | 1,756 / 1,761 |
  | 2019–20 | 22,290 / 22,392 | 1,688 / 1,692 |
  | 2020–21 | 23,036 / 23,054 | 1,861 / 1,864 |
  | 2021–22 | 26,003 / 26,036 | 1,889 / 1,891 |
  | 2022–23 | 25,875 / 25,892 | 1,721 / 1,728 |

- **Other exclusions:**
  - No pair rows had null quantities or null IDs.
  - Rows outside regular season and playoffs were excluded: 146, 1,141, 999 and 950 in 2019–20 through 2022–23. These are play-in and other game types.
- **Missingness:**
  - Every training row had tracking.
  - At each opening snapshot, at most one player used the Full-defense fallback.
  - 834,494 of 842,466 scored possessions had all five defenders tracked at their dated snapshot.
- **Playoff inclusion** is unresolved in the EPM documentation, so it is handled by the regular-only sensitivity below.

## K0 agreement (season-opening snapshot)

The paired cohort is 1,545 player-seasons with opening tracking, out of 1,829 scored. The 284 others had no opening history and get identical intercept predictions under every candidate. Errors are per 100 possessions, and deltas are candidate RMSE minus `full` with 95% player-cluster intervals.

| Candidate | Defense RMSE delta | Total RMSE delta |
| --- | --- | --- |
| **`full_tracking` (primary)** | **+0.089** [+0.047, +0.145] | +0.050 [+0.010, +0.111] |
| `full_tracking_regular_only` | +0.076 [+0.038, +0.125] | +0.046 [+0.009, +0.101] |
| `tracking_defense_only` | +0.104 [+0.049, +0.179] | +0.068 [+0.013, +0.147] |

`full` defense RMSE on the paired cohort is 0.969.

**Registered K0 criterion: not met.** Tracking makes season-opening K0 defense agreement **worse**. The four seasons give +0.045, +0.179, +0.100 and +0.025.

**The deterioration is concentrated in thin exposure** (full cohort, defense delta):

| Slice | Players | `full_tracking` − `full` |
| --- | ---: | --- |
| Opening minutes under 15 | 315 | +0.376 [+0.230, +0.558] |
| 15 to under 25 | 571 | +0.029 [−0.013, +0.066] |
| 25 or more | 659 | −0.013 [−0.039, +0.013] |
| Label exposure 250–999 | 432 | +0.265 [+0.139, +0.434] |
| Label exposure 1,000+ | 1,397 | +0.029 [+0.003, +0.062] |
| Defensive specialists (top fifth of opening `full` defense) | 368 | +0.040 [−0.017, +0.097] |

Rookies, meaning players with no opening history, are unaffected by construction.

## Realized-lineup diagnostic (dated snapshots)

The pool has 842,466 possessions in 2019–20 through 2022–23. Deltas are in points per possession squared, with 95% week-block intervals.

| Contrast | Delta |
| --- | --- |
| **Context + `full_tracking` − context + `full` (primary)** | **−0.000247** [−0.000311, −0.000185] |
| Regular-only tracking − `full` | −0.000242 [−0.000301, −0.000186] |
| Defense parts only, `full_tracking` − `full` | −0.000254 [−0.000316, −0.000190] |
| Context + `full` − context (the #30 result, for scale) | −0.001130 [−0.001231, −0.001029] |

**Registered on-court criterion: met.**
- Tracking-enhanced defense lowers realized-lineup MSE, which is about a fifth more improvement over context than box-only Full provides.
- The delta is negative in every season: −0.000401, −0.000091, −0.000190 and −0.000310. The 2020–21 interval includes 0.
- The regular season gives −0.000235 and the playoffs −0.000412.
- On the 7,972 possessions with an untracked defender, the delta is −0.000197, with an interval that includes 0.

## Interpretation

- **The two registered metrics disagree.**
  - **Possession-weighted scoring** is dominated by regular rotation players. For them, matchup rates add defensive information that box defense lacks.
  - **Equal-player K0 agreement** weights each player-season the same. Low-minute players' previous-season matchup rates are noisy, and the fixed linear fit amplifies them.
  - This pattern is **Inferred** from the slices, not tested. The rates are unshrunk.
- **Learned features.** The final contiguous `full_tracking` defense fit (origin `contiguous@2023-06-13`) has these standardized coefficients:

  | Group | Features |
  | --- | --- |
  | Box | `dreb` +0.197, `stl` +0.188, `blk` +0.063, `pf` −0.107 |
  | Tracking | `mtov_per_100` +0.262, `mfga_per_100` −0.037, `mfg_pct` −0.353 |

  Lower allowed matchup FG% and more forced matchup turnovers predict better defensive RAPM, and they absorb part of the steal and block signal. The per-fold coefficients, means and scales are in the private fits.
- **Combination policy.** Tracking features are appended to the box defense set, and players with all-null tracking fall back to Full defense. No shrinkage, threshold or weighting was tuned.
- **Untested hypothesis for a later registered revision:** exposure-shrunk matchup rates, or a minutes gate, might remove the low-minute K0 penalty.

## Frozen for M7

- **Comparison frozen as recorded here.** The tracking comparison is frozen at this result: mixed, with on-court value but worse equal-player K0 agreement.
- **M7 comparison unavailable.** The pinned matchup archive ends with 2022–23. With no pinned tracking for 2023–24, 2024–25 or the holdout, a tracking comparison is **unavailable** for the M7 outer and confirmatory seasons unless a new capture is registered.
- **EI v1 is unchanged.** It stays box-only ([ADR-0031](../DECISIONS.md#adr-0031--expected-impact-v1-as-the-m5-integrated-reference)).
- **Final fit.** The private final contiguous `full_tracking` fit is kept for the record.
