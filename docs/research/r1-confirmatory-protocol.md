# R1 joint confirmatory registration: 2025–26 holdout

**Status:** **DRAFT for maintainer review.** Nothing in 2025–26 has been captured or read. The registration freezes on the commit that marks it `Frozen`, after maintainer approval. That commit's SHA-256 of this file becomes the runner's required digest.

**Issue:** [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42).

**Classification:**
- Original BIL design under the [validation contract](../validation-strategy.md), R1 protocol v1.
- Partial-history methodology replication.

## 1. Claim and evidence class

- **Evidence class: retrospective confirmatory historical holdout.**
  - **What is frozen first.** The model code, configurations, inclusion rules, update schedule, cohorts, baselines, metrics and verdict rules are all frozen here, before BIL captures or reads any 2025–26 row, box line, team log or rating.
  - **What is not claimed.** The 2025–26 outcomes are already public. The sources are captured after the season (capture-bound), so no strict historical or prospective pregame claim is made. Strict eligible cohorts are reported as unavailable (#55).
  - **Retuning rule.** Any change after holdout access converts 2025–26 to development evidence for the changed method (validation contract).
- **Single shot.** The run happens once.
  - **A crash before any score is written** allows a rerun from the same frozen state, and the crash is reported.
  - **A data-quality failure** of the capture gate (§4) stops the run before scoring. A fix needs a registered revision that names the failure, and the revision cannot depend on any score.

## 2. Prior exposure of 2025–26 within BIL

| Exposure | Status |
| --- | --- |
| Raw or processed 2025–26 data | None. `data/raw` ends at 2024–25. The pilot, row, target, EI and team-outcome loaders refuse seasons from 2025–26 on (`HOLDOUT_START_YEAR = 2025`). |
| Model choices | Frozen in accepted ADR-0025, ADR-0026, ADR-0030, ADR-0031 and ADR-0032, and in the #36 addendum and #39 protocol. All were made on 2021–22 through 2024–25 evidence. |
| EPM | #40 read archived EPM only for 2021–22 through 2024–25 (newest data date 2025-06-22). |
| Incidental | <ul><li>**Live EPM page.** During #40's structure probe the agent opened the live free EPM page. It showed 2026–27 expected values and recent 2026–27 scores. One low-resolution screenshot of the top rows was taken. No value was recorded or used, and every choice here was frozen before it.</li><li>**Archive capture list.** The capture list showed 2025–26 timestamps only, with no content.</li></ul> |
| Maintainer | General public awareness of the 2025–26 season cannot be excluded. Choices were frozen on 2021–25 evidence. |

## 3. Registered analyses

| ID | Analysis | Role |
| --- | --- | --- |
| **P1** | Possession-level held-out MSE: `ei` vs `rapm_context` | **Primary claim** |
| P2 | `ei` vs `rapm`, `context`, `league`, and ablations `ei_zero_prior`, `spm_only`, `ei_offense_only`, `ei_defense_only` | Secondary, each adjudicated, no multiplicity correction claimed |
| T1 | Team margin RMSE and win log loss: `ei` (pregame minutes) vs `team_rating` | Secondary claim |
| T2 | `ei` vs `hca`; `ei_oracle_minutes` diagnostic | Reported |
| S | Rating stability within 2025–26 and year over year from 2024-10-01 to 2025-10-01 | Reported |
| D1 | External agreement with 2025–26 end-of-season EPM | Diagnostic, run only after all scores are frozen |
| X | Defensive tracking (ADR-0032) and Actual impact (#41) | Unavailable or not part of R1; status reported |

### 3.1 Possession level (P1, P2, S)

- **Configuration.** These are exactly the frozen configurations of the [#36 addendum](expected-impact-outer-addendum.md), with the following holdout settings.
  - `outer_seasons` becomes `[2025]`.
  - Canonical rows for 2024–25 and 2025–26 are used.
  - The locked SPM fit `final_contiguous_fit.json` (origin `contiguous@2023-06-13`, SHA-256 `1025774a…dd90`) is unchanged.
  - Box snapshots: 2024–25 is `issue-52-v1` (`e34398e7…b9bd`), and 2025–26 is the new pinned capture (§4).
- **Update policy.** As in #36:
  - Walk-forward refits at 1 October 2025, 1 December, 1 February 2026, 1 April and the first playoff date.
  - Every eligible earlier row in the `W2` window is used, including earlier 2025–26 games.
  - Box snapshots update at each cutoff.
  - Penalties, windows and SPM coefficients stay frozen.
  - A final snapshot at 2026-07-01 is written for D1 and later use.
- **Scores.**
  - Possession MSE in (points per 100)², with paired deltas of the model minus each comparator.
  - Uncertainty: game-clustered and Monday-week-clustered bootstraps, 2,000 resamples, seed 2023.
  - Regular season and playoffs are reported separately and never pooled. Play-in is excluded.
- **Verdict per comparator, regular season.**
  - `ei_better` requires a delta below 0 with **both** the game-clustered and week-clustered 95% intervals excluding 0. This replaces #36's two-season sign condition for a single season.
  - `ei_worse` is the mirror image.
  - Anything else is `inconclusive`.
  - **The primary claim is P1's verdict.** Playoffs are reported, not adjudicated.
- **Also reported:**
  - Each block.
  - Team-game RMSE.
  - The #36 slices: liveData; lineups with all ten players at 1,000 or more window possessions; all with box history.
  - Coverage and fallback counts.
- **Prior expectation.** This is not a decision input. On the outer folds, `ei_better` held against every comparator (#36).

### 3.2 Team and game (T1, T2)

- **Configuration.** These are exactly the frozen [#39 protocol](team-outcomes-protocol.md) and run `team_outcomes/issue-39-v1` (manifest `8486bf8c…1cee`).
- **Frozen inputs, read from that manifest-verified `results.json`:**
  - Pace: 99.928 possessions per team-game.
  - Calibrations for `ei`, `team_rating` and `hca`, fitted on 2021–23.
  - Team baseline half-life of 60 days and ridge 4.
  - The 10-game minutes rule with previous-season fallback and the roster heuristic.
  - Metrics.
- **EI snapshots.** These come from §3.1's 2025–26 walk-forward. The rating at date `D` is the latest snapshot with `as_of ≤ D`.
- **Games and minutes.**
  - Games are official 2025–26 regular-season and playoff games in the pinned team logs. Games without a single home team are excluded and counted.
  - Minutes use box lines dated before `D`, with 2024–25 used for opening-week fallbacks.
- **Verdict, regular season.** For `ei − team_rating` on margin RMSE and on log loss separately:
  - `ei_better` requires a delta below 0 with both the game-resampling and week-cluster 95% intervals excluding 0 (2,000 resamples, seed 39).
  - `ei_worse` is the mirror image.
  - Anything else is `inconclusive`.
- **Prior expectation.** This is not a decision input. On 2023–25, margin RMSE was `ei_worse` and log loss was inconclusive (#39).
- **Diagnostic.** Oracle minutes are reported separately and adjudicate nothing.

### 3.3 External agreement (D1)

- **Timing.** It runs only after P1–T2 results and their manifests are written and committed.
- **Method.** It applies the [#40 protocol](epm-agreement-protocol.md) unchanged to the 2025–26 season.
  - **Source.** One Internet Archive capture of the free EPM page: the first capture on or after 2026-07-01 that holds 2025–26 season EPM, or the nearest such capture. Its SHA-256 is pinned at capture and logged.
  - **EI side.** The 2026-07-01 snapshot.
- **Unavailable case.** If no such capture exists, D1 is reported unavailable.
- **Use.** EPM is used under the recorded written permission, non-commercial only, and never changes any result above.

### 3.4 Unavailable or out-of-scope components

- **Tracking-enhanced defense.** Unavailable: no pinned matchup data after 2022–23 (ADR-0032).
- **Actual impact (#41).** Optional, not implemented, and not part of R1. Its status is reported.
- **Estimated Skills feeding the prior (#125)** and **refresh cadence (#129)** are not part of R1.

## 4. Holdout capture, build and quality gate

These steps happen only after this file is frozen and the freeze commit is pushed.

1. **Capture.**
   - Capture 2025–26 sources with the same providers, feeds and pipeline as 2023–24 and 2024–25: the pilot inputs and evidence feeds, Bill Mill player and team logs, and liveData where available.
   - The pins (bytes, SHA-256, retrieval times) are written at capture and committed in a separate pins commit before the build.
   - The loaders' holdout refusal is lifted only for these code paths, and only when they are given this registration's digest.
2. **Build and rows.**
   - Run the unchanged pilot build, check and evidence commands, the `rapm_rows` row build, and the #29 box-feature build for 2025–26.
   - Parser version and options are as for 2024–25: default path, no order repair.
3. **Quality gate.** Use the unchanged acceptance rules of the multi-season row build (#93) and the [season-quality](season-quality-2017-2025.md) hard limits:
   - regular-season game coverage of at least 97%;
   - a season unresolved-possession share of at most 0.1%.

   Report accepted and excluded games by reason, and report warnings without acting on them. If 2025–26 fails a hard limit, stop before any model fit and report it. Every season from 2018–19 through 2024–25 met the hard limits; 2017–18 did not.
4. **Order of operations.**
   - Predictions and dated ratings for every analysis are written, and their digests recorded in the manifest, before any outcome join or score.
   - The runner refuses to score if the prediction files are missing or their digests differ.

## 5. Access log and artifacts

- **Access log.** Every operation that reads 2025–26 data is appended to `docs/research/r1-holdout-access-log.md` before the run's PR merges. Each entry records:
  - the UTC date;
  - the commit;
  - the command;
  - what was read (raw bytes, rows, predictions, outcomes or scores);
  - the output digest.
- **Repository contents.** Only aggregates are committed. Raw, row, rating and prediction files stay under `data/`.
- **Manifests.** The manifest of each run records:
  - this file's SHA-256 and commit;
  - every input digest, including the frozen #36 and #39 artifacts;
  - code and package versions;
  - the prediction digests written before scoring;
  - runtime.

## 6. Report

The R1 report (`docs/research/r1-report.md`) separates the following:
- **Implementation correctness:** tests, reconciliation and reproduction checks.
- **Methodology fidelity:** documented versus inferred choices, and remaining gaps against the [EPM specification](epm-methodology.md).
- **Predictive validity:** P1, P2, T1 and T2, with coverage, uncertainty and negative results.
- **External agreement:** #40 and D1.
- **Reproducibility.**

It labels each result as one of:
- retrospective reconstruction;
- eligible replay (none);
- genuinely frozen forecast (none);
- **retrospective confirmatory** (this run).

It also records unresolved fidelity gaps and the status of Actual impact. Results are reported whatever their direction.

<!-- frozen-config: to be finalized at freeze; values below are the draft -->
```json
{
  "issue": 42,
  "status": "draft",
  "holdout_season": 2025,
  "possession": {
    "addendum": "docs/research/expected-impact-outer-addendum.md",
    "addendum_sha256": "1076ab0bcfd022f39b68e99eaf9398ce7bec6d99985933821bf8f8bd68762d7c",
    "outer_manifest_sha256": "f74fc2a5e76b7a22964ca8b96736344bc49f3611dd0acf37fbdaeb9ae130a131",
    "spm_fit_sha256": "1025774a8d327cbb25f6c284b49b9cbd80406e88a0406108a0877bf77b1edd90",
    "primary_comparator": "rapm_context",
    "bootstrap": {"resamples": 2000, "seed": 2023},
    "verdict": "game and week intervals both exclude 0"
  },
  "team": {
    "run_manifest_sha256": "8486bf8c42a30c708b12717c4955617d43aef044c4cf0cbc5b6da5fa8b1b1cee",
    "bootstrap": {"resamples": 2000, "seed": 39},
    "verdict": "game and week intervals both exclude 0"
  },
  "box_logs": {
    "2024": {"snapshot": "issue-52-v1", "sha256": "e34398e754233203759f1e6ab8866dc6b61a11afcc3166b6ac9c099feca8b9bd"},
    "2025": "pinned at capture (§4)"
  },
  "quality_gate": {"min_regular_game_coverage": 0.97, "max_season_unresolved_share": 0.001}
}
```
