# R1 report: box-only replication and its 2025–26 confirmatory test

**Issue:** [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42). **Protocol:** [R1 confirmatory protocol v2](r1-confirmatory-protocol.md), frozen at `470df09`, SHA-256 `2159cc24…d045`. **Access log:** [r1-holdout-access-log.md](r1-holdout-access-log.md). **Aggregates:** [r1-holdout/](r1-holdout/).

**Evidence class.** C1, C2 and T2 are **retrospective confirmatory**. They are not a genuinely frozen forecast: the 2025–26 season had already been played when the protocol was frozen, but no 2025–26 row was read before then. No result here is an eligible replay or a genuinely frozen forecast. The other results cited are retrospective reconstructions from earlier issues.

EPM data: dunksandthrees.com (archived public page), used with written permission, non-commercial. EPM was used only for D1, after scoring. It was never used for training, calibration, feature selection or tuning.

## 1. Result in one paragraph

On the 2025–26 regular season (1,225 games), Expected impact (EI) predicts game margins and winners **worse** than the frozen team-rating baseline. Both registered claims are `ei_worse`, with the game and week intervals both excluding 0:
- **C1:** margin RMSE 15.258 against 14.544, Δ +0.714 [+0.494, +0.943] game, [+0.432, +0.982] week.
- **C2:** win log loss 0.6352 against 0.5948, Δ +0.0404 [+0.0276, +0.0541] game, [+0.0262, +0.0541] week.

EI clearly beats home court alone and its own preseason snapshot, so its in-season box-score updates carry signal. The gap to the team rating is about five times the 2024–25 gap in #39 (+0.136). D1 agreement with Dunks & Threes' Expected EPM is strong but lower than in #40: total r 0.779 against 0.874. In 2025–26, EI's on-court component no longer improves on its box-score prior.

## 2. Implementation correctness

- **Tests and checks.** At the freeze, the full suite passed: 454 passed and 3 skipped. Ruff and strict mypy were clean, and CI was green on the code commit `fd9352a`.
- **Reproduction proof (§4.0).** The parametrized runners, given #36's and #39's own inputs, reproduced #36's 2024–25 ratings and #39's 2024–25 predictions byte for byte:
  - ratings `f7798d60…8e31`;
  - predictions `ac18d79c…b4f8d`.
- **Dry run (§4.0).** The R1 v2 configuration run on 2024–25 as if it were the holdout gave identical prediction and ratings digests across four runs. Its scores were written sealed (mode 000) and were not opened before the freeze. They are still unopened, because nothing here depends on them.
- **Holdout guard.** Every 2025–26 read required a protocol file matching the frozen digest, committed unchanged on a clean tree. The score step refused once before reading any outcome, because the labelled pre-score digest line was missing (§4 below).
- **Gate (§4.3).** It passed:
  - the contract validation completed on 28,572 appearances;
  - 1,230 of 1,230 regular-season games had two reciprocal team rows and player rows for both sides, against a 97% limit;
  - 85 playoff games were present.

  Warnings: 0 team-games with minutes off by more than one minute, and 5 games with no single home team (excluded from scoring, as in #39).

## 3. Predictive validity (C1, C2, T2)

**Cutoffs:** R1 2025-10-01, R2 2025-12-01, R3 2026-02-01, R4 2026-04-01, P 2026-04-18 (the first `004` date) and final 2026-07-01. **Scored:** 1,225 regular-season games and 85 playoff games.

### 3.1 Regular season, 2025–26

| Model | MAE | RMSE | Log loss | Brier | Accuracy | Calibration slope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Home court only (`hca`) | 13.111 | 16.430 | 0.6873 | 0.2471 | 0.554 | 0.05 |
| Team rating (ridge) | **11.364** | **14.544** | **0.5948** | **0.2036** | **0.698** | 1.26 |
| EI, pregame minutes | 12.057 | 15.258 | 0.6352 | 0.2222 | 0.641 | 1.10 |
| *EI, oracle minutes (diagnostic)* | *11.886* | *15.039* | *0.6243* | *0.2171* | *0.658* | *1.22* |
| EI, preseason snapshot | 12.154 | 15.374 | 0.6398 | 0.2244 | 0.627 | 1.04 |

**EI minus comparator** (95% game-resampling / week-cluster intervals):

| Comparator | RMSE Δ | Log-loss Δ | Status |
| --- | --- | --- | --- |
| Team rating | +0.714 [+0.494, +0.943] / [+0.432, +0.982] | +0.0404 [+0.0276, +0.0541] / [+0.0262, +0.0541] | **C1 and C2: `ei_worse`** |
| Home court | −1.172 [−1.439, −0.863] / [−1.467, −0.823] | −0.0521 [−0.0682, −0.0355] / [−0.0694, −0.0326] | reported (T2) |
| EI preseason | −0.116 [−0.170, −0.061] / [−0.169, −0.068] | −0.0047 [−0.0075, −0.0018] / [−0.0076, −0.0016] | reported (T2) |

### 3.2 Reported slices

- **Early season (R1 and R2 blocks).** EI is worse than the team rating even before December: RMSE Δ +0.348 [+0.051, +0.636] / [+0.078, +0.642], log loss Δ +0.0339 [+0.0162, +0.0513] / [+0.0140, +0.0557]. Against the preseason snapshot it is within noise (RMSE Δ −0.029 [−0.082, +0.021]). A player-based prior was expected to help most early, when team margins are few, so this is a **negative result**.
- **Oracle minutes.** Knowing who played and for how long recovers 0.22 RMSE of the 0.71 gap. That is not enough to overtake the team rating, the same pattern as #39.
- **Playoffs** (85 games, not adjudicated). RMSE: team rating 15.65, home court 17.43, EI 17.89. Log loss: 0.638, 0.688 and 0.710.
- **Cold minute share by block.** It is the share of predicted minutes given the fixed cold rating (−0.375704): R1 0.071, R2 0.0035, R3 0.0076, R4 0.0033, P 0.0.

### 3.3 Interpretation

- **Inferred.** Under R1 v2 there is no 2025–26 possession data (ADR-0033), so EI's on-court component ends with 2024–25. In-season changes to EI come only from the box-score prior updating on 2025–26 appearances. The team rating refits on every 2025–26 margin. That asymmetry is the most direct explanation for the gap growing from +0.136 (#39, 2024–25, with in-season on-court updates) to +0.714. This run does not isolate it. #129 (refresh cadence) and a possession path for 2025–26 would.
- **Documented.** C1 and C2 are adjudicated by the frozen strict rule. The result is reported as it fell, and no rule changed after capture except the pre-parse gate clarification in §4.

## 4. Deviations and incidents

All were recorded in the access log at the time.

1. **Gate clarification before any parse (user decision, option A).** §4.2 and §4.3 named "the unchanged #29 box-feature build". That builder is hard-wired to 2022–23: its season check, profile counts and window IDs are all 2022–23-specific. The gate ran instead as the unchanged #29 contract validation, `load_appearances(season_start_year=2025)`, which applies exactly the checks §4.3 lists, plus the unchanged coverage rule.
   - It used `scripts/r1_gate.py`, checked first on 2024–25 (1,230 of 1,230).
   - A fresh-context review found three issues, all fixed before the holdout run: self-paired rows could count, coverage depended on the score column, and some build errors were uncaught.
   - Stage A's review missed this gap.
2. **Score refusal.** The first score attempt was refused before reading any outcome. The pre-score digest sat mid-row in the log table, and the runner requires a line ending in the labelled digest. A standalone line was committed and scoring then ran once.
3. **D1 runner.** `scripts/r1_d1.py` calls the #40 functions unchanged (`match`, `slices`, `summarize`, `top_overlap`, `bootstrap`) on a single season. The #40 runner itself has hard-coded pins for 2021–2024.

## 5. External agreement

### 5.1 #40 (earlier seasons)

#40 compared EI with archived EPM for 2021–22 to 2024–25. On 1,867 primary player-seasons, the pooled total r was 0.825, and the on-court update added +0.063 [+0.042, +0.087] over the SPM prior. See [the #40 report](epm-agreement.md).

### 5.2 D1 (2025–26)

**Capture selection (§3.3).** Six archive captures fall in 2026-06-15 to 2026-09-30. All hold only the `expected` form (602 rows, season 2026, data date 2026-06-13), so rule 3 selected the first: 20260702010514, SHA-256 `cb94230a…e3a0`. The result is labelled **expected EPM**, like #40's 2024–25 row.

**EI side.** The R1 final snapshot (2026-07-01). Its on-court part ends with 2024–25, and 2025–26 enters through the box prior only.

**Matching.** 594 players matched (8 EPM-only, 208 EI-only). The primary slice, EI window possessions of at least 1,000, holds 398 players.

| Side (primary) | EI r [95%] | Spearman | RMSE | SPM prior r | EI r − prior r [95%] |
| --- | --- | ---: | ---: | ---: | --- |
| Offense | 0.823 [0.782, 0.859] | 0.764 | 1.16 | 0.851 | [−0.055, −0.002] |
| Defense | 0.691 [0.633, 0.739] | 0.666 | 0.80 | 0.614 | [+0.017, +0.139] |
| Total | 0.779 [0.734, 0.819] | 0.748 | 1.57 | 0.789 | [−0.044, +0.027] |

- **Top overlap, total:** top 25, EI 60% against prior 64%; top 50, 52% against 56%.
- **Comparison with #40's 2024–25 expected row:** total r 0.874, prior 0.806.
- **Experimental reading.** A year-old on-court deviation still moves EI toward EPM on defense. On offense and total it no longer beats the updated box prior, consistent with the staleness discussed in §3.3.
- The intercept-fallback slice has only 3 players, so its correlations are undefined.

## 6. Methodology fidelity and unresolved gaps

- **Documented versus inferred** follows the [EPM specification](epm-methodology.md). Inferred choices include the ridge objective, window and decay, the SPM functional form and the minutes rule.
- **Unavailable in R1:**
  - possession-level scoring and 2025–26 on-court updates (ADR-0033: the V3 event path failed validation);
  - tracking-enhanced defense (ADR-0032).
- **Not part of R1:**
  - Estimated Skills feeding the SPM prior (#125);
  - refresh cadence (#129).
- **Actual impact (#41):** optional and not implemented. There is no Actual-impact result.

## 7. Reproducibility

- **Pins:** [r1-holdout-pins.json](r1-holdout-pins.json) holds the box-log snapshot `af41b22a…2d1b` and the EPM capture.
- **Manifests:** the pre-score manifest `7d49a867…b0e` records the protocol digest, input digests, code commit `107accb`, package versions and runtime.
- **Commands,** from a clean tree at or after the freeze, with private data under `data/`:

```sh
python -m bil.models.r1_holdout capture data/raw
python scripts/r1_gate.py data/raw data/processed/r1/holdout-gate
python -m bil.models.r1_holdout predict data/raw data/processed data/processed/r1/holdout-2025 --season 2025
python -m bil.models.r1_holdout score data/raw data/processed/r1/holdout-2025
python scripts/r1_d1.py data/raw data/processed/r1/holdout-2025 data/processed/r1/d1
```

- **Single shots.** Scoring refuses an existing results file, and the gate and D1 runners refuse an existing output directory. A rerun of `predict` must reproduce the manifest digest before any rescore would be meaningful.
