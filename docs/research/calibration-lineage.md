# Chronological margin-calibration lineage: results (#136)

- **Protocol:** [calibration-lineage-protocol.md](calibration-lineage-protocol.md), SHA-256 `47bb3454…f826`, registered in commit `a461ddc` before the run.
- **Run:** `data/processed/team_outcomes/issue-136-v1`, from a clean checkout at `a461ddc`. `calibration.json` SHA-256 `d7d2f613…`, `results.json` `29c52674…`. The examples file is private.
- **Evidence class:** **Original** (construction). The comparison is development evidence on previously examined 2023–25 seasons. No 2025–26 data was read.
- **Decision:** [ADR-0036](../DECISIONS.md#adr-0036--post-freeze-margin-calibration-with-checked-lineage)

## What changed

`bil.models.calibration_lineage` implements the registered post-freeze construction.

- **Lineage per example.** Each calibration example records its parent run and selection, the date through which that parent read outcomes, the snapshot date and ID, the game date, and the digest of its source file.
- **Consumer check.** `load_calibration(directory, origin)` re-checks every example against the registered parents. It also re-derives the digest and coefficients, and refuses a cutoff after the origin.
- **Tests.** Mutating outcomes after the cutoff leaves the fit and digest unchanged, while mutating an earlier outcome changes the digest. The four lineage conditions are tested one at a time. The normal loading path refuses a parent whose selection read outcomes past its snapshots, and it refuses tampered examples.

## Support

| Calibration | Eligible origins | Examples |
| --- | --- | ---: |
| Frozen #39 (2021–23 games, `ei:issue-35-v1` snapshots) | None. Every example fails "parent froze before snapshot" | 0 eligible |
| Post-freeze, fit cutoff 2024-07-01 (2023–24 regular season, `ei:issue-36-v1` snapshots) | 2024-07-01 and later | 1,230 per source |

All 2021–23 origins and the 2023–24 season have no chronologically eligible calibration under this construction. The #42 2025–26 run loaded the frozen #39 calibration. Its result stands as recorded, but it does not satisfy the strict lineage claim for calibration.

## Coefficients

| Source | #39 frozen a / b / σ | Post-freeze a / b / σ |
| --- | --- | --- |
| EI | 2.021 / 0.950 / 13.54 | 2.217 / 1.097 / 14.28 |
| Team rating | 2.087 / 0.982 / 13.58 | 2.233 / 1.029 / 14.15 |
| Home only | 2.111 / — / 14.51 | 2.146 / — / 15.64 |

## 2024–25 regular season (1,225 games, development comparison)

Under the frozen calibration, the scores equal the published #39 2024–25 values: EI RMSE 14.1624, team 14.0268, EI log loss 0.61259. This confirms that the raw inputs recovered from the #39 predictions are exact to reporting precision.

| | EI RMSE | Team RMSE | EI log loss | Team log loss | EI − team RMSE [game 95%] | EI − team log loss [game 95%] |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| #39 frozen calibration | 14.1624 | 14.0268 | 0.61259 | 0.60651 | +0.136 [−0.044, +0.305] | +0.0061 [−0.0037, +0.0156] |
| Post-freeze calibration | 14.1483 | 14.0191 | 0.61160 | 0.60650 | +0.129 [−0.079, +0.319] | +0.0051 [−0.0053, +0.0154] |

Post-freeze minus frozen:

- **EI.** RMSE −0.014 [−0.067, +0.040] and log loss −0.0010 [−0.0027, +0.0007].
- **Team rating.** RMSE −0.008 [−0.026, +0.012] and log loss 0.0000.

All intervals are game-cluster bootstraps. Week-cluster intervals are in `results.json`.

## Interpretation

The chronological construction removes the calibration leak without changing the team-level conclusion on 2024–25. EI still trails the daily team rating by about 0.13 margin RMSE and 0.005 log loss, and both intervals include zero. The post-freeze EI slope is larger (1.10 vs 0.95). The frozen calibration also left the 2024–25 recalibration slope at 1.15, so the 2021–23 fit understated EI's scale on later seasons. The upstream EI and team-rating parents for 2021–23 origins remain non-chronological. This work does not address them (protocol §6).

## Use

New calibrated forecasts (#129, #43) should build examples with `Example`, fit them with `fit_post_freeze` and load them with `load_calibration` at each origin. A calibration for 2025–26 origins could use 2023–25 examples with cutoff 2025-07-01. Any such use needs its own registration.
