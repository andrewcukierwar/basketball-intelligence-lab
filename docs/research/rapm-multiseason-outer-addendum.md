# Multi-season RAPM: frozen outer-validation addendum (2023–24 and 2024–25)

**Status:** Frozen. Committed after the [development run](rapm-multiseason.md) and before any code read a 2023–24 or 2024–25 row. **Classification:** Original BIL design, Phase 2 of the [development protocol](rapm-multiseason-protocol.md). The outer runner (`python -m bil.models.rapm.multiseason outer`) refuses to start unless it is given this file and its SHA-256, the file is committed with no local change, and the working tree is clean. It reads the configuration below from this file, records the file's digest, its commit and `HEAD` in its manifest, and is run once. No result from it can change anything here. A rerun for any reason other than a crash before results are written is a deviation and is reported.

## Frozen configuration

| Item | Frozen value | Development evidence |
| --- | --- | --- |
| Primary model `rapm` | `W2`: rows played 1 to 730 days before the cutoff, unit weight. $\lambda_o$ = 4,000, $\lambda_d$ = 8,000, in squared points-per-100 units with unit weights | Lowest pooled development MSE (14,109.76). −16.24 (−19.25 to −13.20) against the league mean and +12.28 (+7.61 to +16.71) against context in the regular season. First in all four sensitivity scenarios |
| Secondary model `rapm_context` | `rapm`'s candidate and penalties, fitted on the response minus the `context` offset (with `rapm`'s rows and weights) | −16.62 (−19.72 to −13.62) against context, regular season. Not used for selection |
| Baseline `league` | `W1`: weighted mean response of the 365 days before the cutoff | Selected by its own development MSE (14,126.00) |
| Baseline `context` | `W1`: weighted least squares on the #24 `home_score_time` columns, 365 days | Selected by its own development MSE (14,097.47) |
| Lineage | Development manifest SHA-256 `8cbb4e5e…536a` at `ec4f127`. Protocol SHA-256 `8787a112…4c99` | The runner checks both before reading any row |

The configuration was taken from the development run's `selected` block without change. The selection is a near-tie: four candidates are within 0.3 MSE units. That is a known limitation, not a reason to revisit the choice.

<!-- frozen-config -->
```json
{
  "issue": 26,
  "outer_seasons": [
    2023,
    2024
  ],
  "dev_run": "data/processed/multiseason/issue-26-dev-v1",
  "dev_manifest_sha256": "8cbb4e5e627eb9c5356ed3981851960078b9a649c5eb55410a038e314512536a",
  "dev_code_commit": "ec4f127ffec73cde69dda3a9687a2613d224337e",
  "protocol_sha256": "8787a1129cbcca0f72c90b8763349356adbd2e3a9d54116e6d3049878c544c99",
  "primary": {
    "temporal": "W2",
    "offense_ridge": 4000.0,
    "defense_ridge": 8000.0
  },
  "secondary": "rapm_context: primary temporal and penalties, home_score_time offset",
  "league_temporal": "W1",
  "context_temporal": "W1",
  "bootstrap": {
    "resamples": 2000,
    "seed": 2023,
    "clusters": [
      "game",
      "week"
    ]
  },
  "calibration_bins": 10
}
```

## Update policy

Walk-forward in each outer season with the development blocks: R1 (cutoff 1 October, regular-season games before 1 December), R2 (1 December, to 31 January), R3 (1 February, to 31 March), R4 (1 April, rest of the regular season) and P (cutoff the season's first playoff date, all playoff games). Each fit uses every eligible canonical row played before its cutoff that its temporal candidate admits, including earlier games of 2023–24 when fitting in 2024–25. Penalties and temporal candidates stay as frozen above. Nothing is re-tuned, re-selected or recalibrated. Held-out players absent from a fit's rows have zero effect. Ten refits per model in all.

## Models scored

| Name | Role | Definition |
| --- | --- | --- |
| `rapm` | **Primary** | Zero-prior offense/defense ridge, frozen candidate and penalties |
| `offense_only`, `defense_only` | Slices | `rapm` with the other block's effects set to zero |
| `rapm_context` | Secondary | `rapm` fitted on the response minus the `context` offset fitted with `rapm`'s rows and weights, offset added back |
| `league` | Baseline (intercept) | Weighted mean response under its frozen candidate |
| `context` | Baseline (#24 context only) | Weighted least squares on home, clipped margin, period 2–4, overtime, end of period and final two minutes, under its frozen candidate |

## Metrics, uncertainty and verdicts

- **Primary metric.** Per-possession squared error in (points per 100)², on identical possessions. Paired deltas: `rapm − league` and `rapm − context`. Negative favours `rapm`.
- **Primary sets.** The regular season pooled over 2023–24 and 2024–25, and the playoffs pooled over both seasons, reported separately and never combined. Each season's regular season and playoffs are also reported, with per-block deltas.
- **Secondary.** `rapm_context − context`, `rapm_context − league`, `context − league`, the offense-only and defense-only deltas against `league`, and team-game aggregate RMSE (as #23).
- **Uncertainty.** 95% percentile intervals from a game-clustered bootstrap (2,000 resamples, seed 2023). A calendar-week-clustered bootstrap with the same settings is reported beside it as a check on short-range temporal dependence. Per-block deltas show variation across refits.
- **Verdict rule (game-clustered interval).** *Better* if the interval is wholly below zero, *worse* if wholly above zero, otherwise *inconclusive*. The verdicts are reported for every comparison and set, including negative results.

## Coverage and calibration

- **Cohort coverage.** For each outer season and season type: games in the reconciliation, accepted and quarantined (quarantined games are not rows and are not scored), eligible canonical possessions, scored possessions and games (every eligible row is scored), and possessions with at least one player who has no fit rows at that block's cutoff.
- **Calibration of the predicted possession scoring rate**, for `rapm`, `rapm_context` and `context` (calibration-in-the-large only for `league`, whose prediction is constant within a block): mean outcome minus mean prediction with a game-clustered 95% interval; the ordinary least squares slope of outcome on prediction with a game-clustered 95% interval (1 means calibrated spread; below 1 means the predictions vary too much); and a table of ten prediction-quantile bins with mean prediction, mean outcome and a game-clustered interval for the outcome. No predictive interval is produced, so interval coverage is not reported.
- **Pins.** The manifest records each season's row-set and pilot digests and timing audit, the SHA-256 of the scored outcomes (sorted `game_id,possession_seq,points` lines) for each outer season and season type, this addendum's digest and commit, the code commit, library versions, runtime and peak memory.

**Evidence tier: `retrospective_capture_bound`.** Outer results are a chronological replay on realized lineups. They are development evidence for later registration, not confirmatory. 2025–26 stays untouched.
