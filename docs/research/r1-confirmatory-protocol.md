# R1 joint confirmatory registration: 2025–26 holdout

**Status:** **DRAFT v2 for maintainer review.** Nothing in 2025–26 has been captured or read.

**Revision v2: box-only R1 (2026-11-26).** The maintainer chose to redesign R1 without 2025–26 play-by-play ("Redesign R1").
- **Why.** The pinned archive has no 2025–26 V2 events. Both registered validations of a V2-free event path failed ([#133](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/133), [validation](v3-event-path-validation.md), ADR-0033).
- **What remains.** R1 now reads only the 2025–26 NBA.com player and team game logs, plus the D1 EPM capture.
- **What is lost.** The possession-level analyses are unavailable. The team-game analysis becomes the primary claim.
- **What it confirms.** R1 confirms a weaker variant of EI: its box-score prior updates through the season, but its on-court part ends with 2024–25.

**Issue:** [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42).

**Classification:**
- Original BIL design under the [validation contract](../validation-strategy.md), R1 protocol v1.
- Partial-history methodology replication.
- Protocol v2: box-only, §3.

## 0. Freeze procedure

The registration freezes in two stages. No 2025–26 byte is fetched before stage B is complete.

- **Stage A, analysis plan (this document).**
  1. The maintainer reviews this plan.
  2. After approval the agent implements the holdout-ready code (§4.0). Nothing else in this document may change except the placeholders in the frozen block marked `set at freeze`.
- **Stage B, freeze commit.** This one commit does three things:
  1. Sets `status` to `frozen`.
  2. Fills in the code commit and the reproduction digests (§4.0).
  3. Commits the SHA-256 of this file as the constant `R1_PROTOCOL_SHA256` in `bil/models/r1_holdout.py`. The digest lives in code, not here.

  **Guard checks.** The holdout guards in the pilot, row, box, EI, team-outcome and EPM loaders lift only when all three of these hold:
  - this file's digest equals that constant;
  - the file is committed unchanged;
  - the working tree is clean.

  A digest passed on the command line cannot lift a guard. Anyone changing the constant needs a new registration, reviewed in its own PR.

## 1. Claim and evidence class

- **Evidence class: retrospective confirmatory historical holdout**, for the team-game claim (C1) only.
  - **Frozen first.** The model code, configurations, inclusion rules, update schedule, cohorts, baselines, metrics and verdict rules are all frozen before BIL captures or reads any 2025–26 box line, team log or rating.
  - **Not claimed.** The 2025–26 outcomes are already public, and the sources are captured after the season (capture-bound). No strict historical or prospective pregame claim is made. Strict eligible cohorts are reported as unavailable (#55).
  - **Retuning.** Any change after holdout access converts 2025–26 to development evidence for the changed method (validation contract).
- **What is confirmed.**
  - **The variant.** R1 tests the variant `ei` of §3.1: Expected impact v1 as frozen, run when no 2025–26 possession data exist. Its SPM prior updates from 2025–26 box appearances before each cutoff. Its on-court deviation and context fit use only the 2023–24 and 2024–25 possessions inside the `W2` window.
  - **What it cannot confirm.** The possession-level advantage found in #36.
- **Single shot.** The run happens once.
  - **A crash before any score is written** allows a rerun from the same frozen code and inputs. The crash is reported.
  - **A failed quality gate** (§4.3) ends the confirmatory attempt and is reported as such.

## 2. Prior exposure of 2025–26 within BIL

| Exposure | Status |
| --- | --- |
| Raw or processed 2025–26 data | None. `data/raw` ends at 2024–25. The #133 validations read 2023–24 and 2024–25 only. The pilot, row, target, EI, team-outcome and EPM loaders refuse seasons from 2025–26 on (`HOLDOUT_START_YEAR = 2025`). |
| Model choices | Frozen in accepted ADR-0025, ADR-0026, ADR-0030, ADR-0031 and ADR-0032, and in the #36 addendum and #39 protocol. All were made on 2021–22 through 2024–25 evidence. |
| EPM | #40 read archived EPM for 2021–22 through 2024–25 only (newest data date 2025-06-22). |
| Incidental | <ul><li>**Live EPM page.** During #40's structure probe the agent opened the live free EPM page, which shows **2026–27** values only: expected EPM as of 2026-11-27 and scores of 2026–27 games. One low-resolution screenshot of its top rows was taken. No value was recorded or used, and every choice here was frozen earlier.</li><li>**Archive capture list.** It showed timestamps of 2025–26 captures, with no content.</li><li>**Provider file inventory (2026-11-26, stage B start).** Metadata only: GitHub tree file names for `shufinskiy/nba_data`, Bentes release asset names, and HTTP headers (status, size, modification date) for the two Bill Mill logs. No file body was downloaded. It showed that the archive has no `nbastats` (V2), `datanba` or `pbpstats` file for 2025–26 (see the blocker in the handoff).</li></ul> |
| Maintainer | General public awareness of the 2025–26 season cannot be excluded. Choices were frozen on 2021–25 evidence. |

## 3. Registered analyses

**Cohort window.**
- **Dates.** Official Eastern played dates in `[2025-07-01, 2026-07-01)`.
- **Included.** Official regular-season (`002`) and playoff (`004`) games only.
- **Excluded and counted.** Preseason (`001`), All-Star (`003`), play-in (`005`) and NBA Cup final (`006`) games, in every analysis.

| ID | Analysis | Role |
| --- | --- | --- |
| **C1** | Team regular-season margin RMSE: `ei` (pregame minutes) vs `team_rating` | **Primary claim** (the only one) |
| C2 | Team regular-season win log loss: `ei` vs `team_rating` | Secondary, adjudicated, no multiplicity correction |
| T2 | `ei` vs `hca`; `ei_oracle_minutes`; `ei_preseason` | Reported |
| S | Rating stability within 2025–26, and year over year from 2024-10-01 (`issue-36-v1`) to 2025-10-01 | Reported |
| D1 | External agreement with 2025–26 EPM | Diagnostic, after all scores are committed |
| U | Possession-level MSE: `ei` vs `rapm_context` and the other comparators (protocol v1 P1 and P2) | **Unavailable**: no 2025–26 play-by-play (ADR-0033) |
| X | Defensive tracking (ADR-0032) and Actual impact (#41) | Status reported, not run |

**Verdict rule (C1, C2).** This rule is deliberately stricter than #39's two-season rule.
- **Intervals.** Two-sided 95% percentile bootstrap intervals, computed by resampling games and, separately, by resampling Monday-to-Sunday weeks.
- **`ei_better`.** The point delta is below 0 and **both** intervals exclude 0.
- **`ei_worse`.** The mirror image.
- **`inconclusive`.** Anything else. The report names which interval included 0.
- **Scope.** Regular season only. Playoffs are reported, not adjudicated.

**Why C1 is primary.** With no possession outcomes, team margins are the only outcome left that EI's frozen #39 pipeline scores. Margin RMSE was #39's first-listed metric.

**Known handicap.** `team_rating` updates from 2025–26 results, while `ei` updates only its box prior. C1 tests EI as it could be run under this data limitation. It is not a like-for-like test of the #36 method.

### 3.1 EI snapshots without 2025–26 possession data (S, and the inputs to C1, C2 and T2)

- **Configuration.** This is exactly the frozen `ei` configuration of the [#36 addendum](expected-impact-outer-addendum.md).
  - **Unchanged:** penalties, `W2` window and the locked SPM fit `final_contiguous_fit.json` (origin `contiguous@2023-06-13`, SHA-256 `1025774a…dd90`). No comparator fit is scored.
  - **Rows.** Only the `issue-93-v1` canonical rows for 2023–24 and 2024–25. A refit at cutoff `c` uses the rows of its window dated strictly before `c`. By R4 (2026-04-01) the window holds only rows from 2024-04-01 on.
  - **Box logs.** 2024–25 is `issue-52-v1` (`e34398e7…b9bd`), and 2025–26 is the new pinned capture. The prior at `c` uses box appearances dated strictly before `c` (the dated retrospective view).
- **Cutoffs.** These are unchanged from protocol v1: R1 2025-10-01, R2 2025-12-01, R3 2026-02-01 and R4 2026-04-01. P is the earliest played date of a `004` game in the pinned 2025–26 team log. A final snapshot at 2026-07-01 is written for S, D1 and later use.
- **`ei_preseason`.** The R1 snapshot held for every date. Reported in T2 to show the in-season box updates.
- **Cold rating.** A player absent from a snapshot (a rookie or call-up, for example) gets the snapshot's cold rating (#39 §1).
  - **The #36 rule.** `team_outcomes.load_ratings` reads the cold rating from a ratings row with no box history and no window possessions, and uses 0.0 if there is none. In every `issue-36-v1` snapshot such a row exists, and its rating is **−0.375704**: the locked SPM fit's no-history prior, with zero deviation.
  - **Why v2 differs.** With row seasons 2023 and 2024 only, early v2 snapshots may have no such row, so the rule would silently give 0.0.
  - **v2 rule.** v2 therefore fixes the cold rating at −0.375704 for every snapshot. The runner passes it explicitly, and it checks agreement to 1e-6 against any cold row present, since ratings are written to six decimals. `load_ratings` stays unchanged for the #39 reproduction.
  - **Reported.** The cold rating and the share of predicted minutes it covers, by block.
- **Prior results.** These are context only, not a decision input. With in-season possession rows, #39's 2023–25 margin RMSE delta against `team_rating` was +0.142 (game [+0.018, +0.262], week [−0.021, +0.298]). That would be `inconclusive` under this rule.

### 3.2 Team and game (C1, C2, T2)

- **Configuration.** These are exactly the frozen [#39 protocol](team-outcomes-protocol.md) and the values of run `team_outcomes/issue-39-v1`. Its manifest is `8486bf8c…1cee`, and its `results.json` is `ef0dd71e…0cee9`.
- **Frozen values:**
  - **Pace:** 99.92825203252032.
  - **Team baseline:** half-life 60 days, ridge 4.
  - **Calibrations:** `ei`, `team_rating` and `hca`, read by digest from that file. The `ei` calibration is applied unchanged to the §3.1 variant.
  - **Minutes:** the 10-game minutes rule with previous-season fallback, and the roster heuristic.
- **Inputs.**
  - **EI snapshots** come from §3.1. The rating at date `D` is the latest snapshot with `as_of ≤ D`.
  - **Team and player logs** for 2024–25 (`issue-52-v1`) are used for opening-week minutes and the team rating's 365-day look-back. 2025–26 uses the new capture.
  - Games without a single home team are excluded and counted.
- **Seed.** 2,000 resamples with seed 39.
- **Oracle minutes** are reported only, as a diagnostic.
- **Early-season slice.** C1 and C2 deltas over the R1 and R2 blocks are reported, not adjudicated. That is where a result-based team rating has the least 2025–26 evidence.

### 3.3 External agreement (D1)

- **When it runs.** Only after C1–T2 results, manifests and the access log are committed.
- **Method.** It applies the [#40 protocol](epm-agreement-protocol.md) unchanged. The EI side is the 2026-07-01 snapshot of §3.1, so its on-court part ends with 2024–25. The report states this.
- **Capture selection** uses only capture timestamps and embedded metadata, never EPM values:
  1. List captures of `dunksandthrees.com/epm` with timestamps from 2026-06-15 to 2026-09-30.
  2. In timestamp order, select the **first** capture whose embedded records hold 2025–26 season EPM: `season = 2026`, in #40's `json` or `columnar` form, with regular-season rows (`seasontype = 2` where present).
  3. If there is none, select the first `expected`-form capture with `season = 2026` and a data date from 2026-06-01 on, labelled *expected*.
  4. If there is still none, D1 is unavailable.

  Captures holding only 2026–27 content are skipped. The selected capture is pinned by SHA-256 and logged.
- **Use.** EPM is used under the recorded written permission, non-commercial only, and changes nothing above.

### 3.4 Not part of R1

- **Tracking-enhanced defense.** Unavailable: no pinned matchup data after 2022–23 (ADR-0032).
- **Actual impact (#41).** Optional, not implemented. Its status is reported.
- **#125 and #129.** Development follow-ups, outside R1.

## 4. Implementation, capture, build and gate

### 4.0 Holdout-ready code (between stages A and B)

- **What changes.**
  - Parametrize the #35/#36 EI runner and the #39 runner by season, cutoffs, row seasons and run inputs. That covers the hard-coded `expected_impact_outer` `OUTER_SEASONS`, `ROW_SEASONS`, `FINAL_CUTOFF`, the `outer_logs` date check and `parse_config`'s season checks, and `team_outcomes`' season constants, `RATING_RUNS` and target.
  - Build the R1–R4 and P blocks from the fixed cutoffs and the team log. They cannot come from `season_blocks`, which needs rows of the scored season.
  - Pass the fixed cold rating of §3.1.
  - Implement §3's verdict rule.
  - Add the guard mechanism of §0.
  - No modelling function changes.
- **Guards.** The pilot, row and V3-event guards never lift for R1 v2. Only the box, EI, team-outcome and EPM guards lift.
- **Reproduction proof, before freeze.** The parametrized code, run with #36's and #39's own inputs (row seasons 2021–2024), must reproduce:
  - #36's 2024–25 ratings snapshots;
  - #39's 2024–25 game predictions.

  Identical file digests are required. If they differ, the maximum absolute difference must be at most 1e-9, and the difference is reported. This proves the parametrization. The reproduction uses the unchanged cold rule, read from the ratings file, never the v2 explicit value. The v2 configuration itself is exercised by the dry run.
- **Dry run, before freeze.** Run the R1 v2 configuration on 2024–25 as if it were the holdout: rows 2022–23 and 2023–24 only, and 2024–25 box logs. Run it twice and require identical digests.
  - **What is read before freeze.** Only digests, coverage counts, the cold minute share and runtime. The cold minute share comes from predicted minutes and ratings only, with no outcomes.
  - **Sealed scores.** The runner writes the scores file with mode 000 and prints only its digest. The freeze commit records the digest and the file's access time, which must predate the freeze.
  - **Not an input.** C1, C2, the verdict rule, the gate and every configuration above are fixed in stage A, before the dry run. If any of them changes after the dry-run scores are opened, the registration is relabelled as development evidence.
- **Digests.** The digests of the reproduction and dry runs are recorded in the frozen block.
- **Review.** Independent code review of this diff. CI is green on the code commit.

### 4.1 Capture (stage B done)

- **One capture run** of the 2025–26 Bill Mill player and team game logs, with the same provider and pipeline as 2024–25 (`issue-52-v1`).
- **Not captured.** No play-by-play, V3, liveData or shot file is captured or read.
- **Pins.** Bytes, SHA-256 and retrieval times are written at capture and committed in a pins commit before any parse.
- **Retries.** A download may be retried only for a network error or a size or digest mismatch on the same URL before any parse. There is no recapture or source substitution after parsing has begun.
- **Missing input.** If either log is missing, stop. R1 confirmatory is then unavailable.

### 4.2 Build

Run the unchanged #29 box-feature build (`bil.features.box_build`) on the 2025–26 logs, and the unchanged #39 team-log loading.

### 4.3 Quality gate

- **Box reconciliation.** The box-feature build completes. It refuses any player or team row that violates the [box-score feature contract](box-score-feature-contract.md): unique keys, reciprocal team rows, agreeing dates and home flags, and count identities.
- **Game coverage.** The pinned team log holds at least 97% of the 1,230 scheduled regular-season games (30 teams × 82 ÷ 2), each with two reciprocal team rows and player rows for both sides.

- **Warnings, reported only:**
  - team-games whose summed player minutes differ from 240 plus 25 per overtime by more than one minute;
  - the count of games excluded for lacking a single home team.

Warnings are not acted on. The limits and rules cannot change after capture. If either fails, the confirmatory attempt ends and is reported failed. A repaired attempt needs a new registration and is labelled development evidence.

### 4.4 Order of operations

1. **Reads permitted before scoring:**
   - capture bytes;
   - the box build and the gate, which read outcomes for reconciliation;
   - box appearances strictly before each cutoff, and the pre-holdout rows.
2. **Fit and freeze.** For R1, R2, R3, R4, P and the final snapshot in turn, fit and write the ratings snapshot. Then write the team-game pregame predictions, with no outcomes joined. The digests of all of these go in a pre-score manifest.
3. **Log and commit.** The access log (§5) is committed with the pre-score manifest digest.
4. **Score.** The scoring step refuses to run unless the committed log contains that digest and the prediction files match it.
5. **D1.** After scoring results are committed, D1 runs under §3.3.

## 5. Access log and artifacts

- **Log file:** `docs/research/r1-holdout-access-log.md`. Every operation that reads 2025–26 data gets an entry with:
  - the UTC time;
  - the commit;
  - the command;
  - what was read (raw bytes, rows, predictions, outcomes or scores);
  - the output digest.
- **Commit points.** The log is committed:
  - with the pins commit;
  - after the gate;
  - before scoring (§4.4);
  - before D1;
  - with the results.
- **Repository contents.** Aggregates only. Raw files, rows, ratings and predictions stay under `data/`.
- **Manifests.** Each run's manifest records:
  - the protocol digest and commit;
  - every input digest;
  - code and package versions;
  - the prediction digests;
  - runtime.

## 6. Report

The R1 report (`docs/research/r1-report.md`) covers each of these separately:
- **Implementation correctness:** tests, reconciliation and the §4.0 reproduction.
- **Methodology fidelity:** documented versus inferred choices, and gaps against the [EPM specification](epm-methodology.md).
- **Predictive validity:** C1, C2 and T2, with coverage, uncertainty and negative results. The possession-level analyses are reported as unavailable.
- **External agreement:** #40 and D1.
- **Reproducibility.**

It labels each result as one of:
- retrospective reconstruction;
- eligible replay (none);
- genuinely frozen forecast (none);
- **retrospective confirmatory** (this run).

It also records unresolved fidelity gaps and the status of Actual impact. Results are reported whatever their direction.

<!-- frozen-config -->
```json
{
  "issue": 42,
  "status": "draft",
  "protocol_version": 2,
  "holdout_inputs": ["bill_mill_player_log_2025", "bill_mill_team_log_2025", "epm_capture_d1"],
  "holdout_season": 2025,
  "cohort": {"dates": ["2025-07-01", "2026-07-01"], "game_prefixes": ["002", "004"]},
  "code_commit": "set at freeze",
  "reproduction_digests": "set at freeze",
  "protocols": {
    "validation_strategy": "7f4b7a041ade4a7df0006eb24d1a655698507f54fa90fedc7346cccc516e9e13",
    "expected_impact_protocol": "28869a50993ce93e598997b3dd56cce246c5a3915c1205cff30975ccaf64889d",
    "outer_addendum": "1076ab0bcfd022f39b68e99eaf9398ce7bec6d99985933821bf8f8bd68762d7c",
    "team_outcomes_protocol": "c4b7cb8fef86a09ca723d0db01b7006d864e8354aa5b85109daf22fe43562302",
    "epm_agreement_protocol": "0152e248ff95965284dbdeadb1ca888d91c3915db40435ae86aaa55ed9ed6bf5",
    "season_quality": "68461aa454795a8481989f54efd37abe67adab57540a33da41337d787fe3b2a8"
  },
  "ratings": {
    "dev_manifest_sha256": "db254b8c450034a0142255c40301e74cd6ddc59d505ab6d7aef983f846fce5d1",
    "outer_manifest_sha256": "f74fc2a5e76b7a22964ca8b96736344bc49f3611dd0acf37fbdaeb9ae130a131",
    "spm_fit_sha256": "1025774a8d327cbb25f6c284b49b9cbd80406e88a0406108a0877bf77b1edd90",
    "row_seasons": [2023, 2024],
    "cutoffs": {"R1": "2025-10-01", "R2": "2025-12-01", "R3": "2026-02-01", "R4": "2026-04-01", "P": "first 004 played date in the team log"},
    "final_snapshot": "2026-07-01",
    "possession_scoring": "unavailable (ADR-0033)",
    "cold_rating": -0.375704
  },
  "team": {
    "run_manifest_sha256": "8486bf8c42a30c708b12717c4955617d43aef044c4cf0cbc5b6da5fa8b1b1cee",
    "results_sha256": "ef0dd71e5b9723534eec4d8ee292f4110ce88b905f1fbb4671913ba2b980cee9",
    "pace": 99.92825203252032,
    "team_config": {"half_life": 60.0, "ridge": 4.0},
    "bootstrap": {"resamples": 2000, "seed": 39},
    "primary": {"metric": "regular_season_margin_rmse", "model": "ei", "comparator": "team_rating"},
    "secondary": [{"metric": "regular_season_win_log_loss", "model": "ei", "comparator": "team_rating"}],
    "reported": ["hca", "ei_oracle_minutes", "ei_preseason", "early_season_slice: blocks R1 and R2", "cold_minute_share by block"]
  },
  "verdict": "two-sided 95% percentile; ei_better/ei_worse need game and week intervals both excluding 0; regular season only",
  "box_logs": {
    "2024": {"snapshot": "issue-52-v1", "sha256": "e34398e754233203759f1e6ab8866dc6b61a11afcc3166b6ac9c099feca8b9bd"},
    "2025": "pinned at capture"
  },
  "quality_gate": {"box_feature_build": "completes (contract reconciliation)", "min_regular_game_coverage": 0.97, "scheduled_regular_games": 1230, "manifest_warnings": ["minutes_off_by_more_than_1", "excluded_no_single_home_team"]},
  "d1": {"capture_window": ["2026-06-15", "2026-09-30"], "selection": "first season-EPM capture, else first expected capture, else unavailable"}
}
```
