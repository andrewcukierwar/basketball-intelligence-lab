# R1 joint confirmatory registration: 2025–26 holdout

**Status:** **DRAFT for maintainer review.** Nothing in 2025–26 has been captured or read.

**Issue:** [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42).

**Classification:**
- Original BIL design under the [validation contract](../validation-strategy.md), R1 protocol v1.
- Partial-history methodology replication.

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

- **Evidence class: retrospective confirmatory historical holdout.**
  - **Frozen first.** The model code, configurations, inclusion rules, update schedule, cohorts, baselines, metrics and verdict rules are all frozen before BIL captures or reads any 2025–26 row, box line, team log or rating.
  - **Not claimed.** The 2025–26 outcomes are already public, and the sources are captured after the season (capture-bound). No strict historical or prospective pregame claim is made. Strict eligible cohorts are reported as unavailable (#55).
  - **Retuning.** Any change after holdout access converts 2025–26 to development evidence for the changed method (validation contract).
- **Single shot.** The run happens once.
  - **A crash before any score is written** allows a rerun from the same frozen code and inputs. The crash is reported.
  - **A failed quality gate** (§4.3) ends the confirmatory attempt and is reported as such.

## 2. Prior exposure of 2025–26 within BIL

| Exposure | Status |
| --- | --- |
| Raw or processed 2025–26 data | None. `data/raw` ends at 2024–25. The pilot, row, target, EI, team-outcome and EPM loaders refuse seasons from 2025–26 on (`HOLDOUT_START_YEAR = 2025`). |
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
| **P1** | Possession-level held-out MSE: `ei` vs `rapm_context` | **Primary claim** (the only one) |
| P2 | `ei` vs `rapm`, `context` and `league`, and the ablations `ei_zero_prior`, `spm_only`, `ei_offense_only` and `ei_defense_only` | Secondary, each adjudicated, no multiplicity correction |
| T1 | Team regular-season margin RMSE, and separately win log loss: `ei` (pregame minutes) vs `team_rating` | Secondary, two separate verdicts, no combined verdict |
| T2 | `ei` vs `hca`; `ei_oracle_minutes` diagnostic | Reported |
| S | Rating stability within 2025–26, and year over year from 2024-10-01 (`issue-36-v1`) to 2025-10-01 | Reported |
| D1 | External agreement with 2025–26 EPM | Diagnostic, after all scores are committed |
| X | Defensive tracking (ADR-0032) and Actual impact (#41) | Status reported, not run |

**Verdict rule (P1, P2, T1).** This rule is deliberately stricter than #36's and #39's two-season rules.
- **Intervals.** Two-sided 95% percentile bootstrap intervals, computed by resampling games and, separately, by resampling Monday-to-Sunday weeks.
- **`ei_better`.** The point delta is below 0 and **both** intervals exclude 0.
- **`ei_worse`.** The mirror image.
- **`inconclusive`.** Anything else. The report names which interval included 0.
- **Scope.** Regular season only. Playoffs are reported, not adjudicated.

### 3.1 Possession level (P1, P2, S)

- **Configuration.** These are exactly the frozen configurations of the [#36 addendum](expected-impact-outer-addendum.md): `ei`, the four ADR-0026 comparators and the ablations.
  - **Unchanged:** penalties, windows and the locked SPM fit `final_contiguous_fit.json` (origin `contiguous@2023-06-13`, SHA-256 `1025774a…dd90`).
  - **Rows.** The `issue-93-v1` canonical rows for 2023–24 and 2024–25, plus the new 2025–26 rows (§4). The `W2` window covers up to 730 days before a cutoff, so the October to April fits reach into 2023–24, including its playoffs.
  - **Box logs.** 2024–25 is `issue-52-v1` (`e34398e7…b9bd`), and 2025–26 is the new pinned capture.
- **Cutoffs.** These follow M2's `season_blocks` rule.

  | Cutoff | Date | Scored rows |
  | --- | --- | --- |
  | R1 | 2025-10-01 | Regular-season games before 2025-12-01 |
  | R2 | 2025-12-01 | Regular-season games before 2026-02-01 |
  | R3 | 2026-02-01 | Regular-season games before 2026-04-01 |
  | R4 | 2026-04-01 | All remaining regular-season games, including any played after the playoffs began |
  | P | The earliest played date of a `004` game in the pinned 2025–26 rows | All playoff rows |

  Play-in games never define P.
- **Refits.**
  - Each refit uses every row of its window dated strictly before its cutoff, including earlier 2025–26 games.
  - Box snapshots update at each cutoff.
  - A final snapshot at 2026-07-01 is written for S, D1 and later use.
- **Scores.**
  - Possession MSE in (points per 100)², as paired deltas of `ei` minus each comparator.
  - Uncertainty: 2,000 resamples with seed 2023.
  - Also reported:
    - each block;
    - team-game RMSE;
    - the #36 slices: liveData; lineups with all ten players at 1,000 or more window possessions; lineups with all ten with box history;
    - coverage and fallback counts.
- **Prior results.** These are context only, not a decision input. On 2023–25, against `rapm_context`, the regular-season delta was −4.59 [−5.80, −3.37] game and [−5.60, −3.53] week (#36). That would also be `ei_better` under this rule.

### 3.2 Team and game (T1, T2)

- **Configuration.** These are exactly the frozen [#39 protocol](team-outcomes-protocol.md) and the values of run `team_outcomes/issue-39-v1`. Its manifest is `8486bf8c…1cee`, and its `results.json` is `ef0dd71e…0cee9`.
- **Frozen values:**
  - **Pace:** 99.92825203252032.
  - **Team baseline:** half-life 60 days, ridge 4.
  - **Calibrations:** `ei`, `team_rating` and `hca`, read by digest from that file.
  - **Minutes:** the 10-game minutes rule with previous-season fallback, and the roster heuristic.
- **Inputs.**
  - **EI snapshots** come from §3.1's 2025–26 walk-forward. The rating at date `D` is the latest snapshot with `as_of ≤ D`.
  - **Team and player logs** for 2024–25 (`issue-52-v1`) are used for opening-week minutes and the team rating's 365-day look-back. 2025–26 uses the new capture.
  - Games without a single home team are excluded and counted.
- **Prior results.** These are context only. Under this stricter rule, #39's 2023–25 margin RMSE delta of +0.142 (game [+0.018, +0.262], week [−0.021, +0.298]) would be `inconclusive`, not the `ei_worse` that #39's own rule gave.
- **Seed.** 2,000 resamples with seed 39.
- **Oracle minutes** are reported only, as a diagnostic.

### 3.3 External agreement (D1)

- **When it runs.** Only after P1–T2 results, manifests and the access log are committed.
- **Method.** It applies the [#40 protocol](epm-agreement-protocol.md) unchanged. The EI side is the 2026-07-01 snapshot.
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

- **What changes.** Parametrize the #36 and #39 runners by season, cutoffs and run inputs. Implement §3's verdict rule. Add the guard mechanism of §0. No modelling function changes.
- **Reproduction proof, before freeze.** The parametrized code, run on the already-scored 2024–25 season as if it were the holdout, must reproduce two things:
  - #36's 2024–25 EI and comparator possession predictions in every block;
  - #39's 2024–25 game predictions.

  Each must match with a maximum absolute difference of 0.

  The digests of these reproduction runs are recorded in the frozen block.
- **Review.** Independent code review of this diff. CI is green on the code commit.

### 4.1 Capture (stage B done)

- **One capture run** of 2025–26 with the same providers, feeds and pipeline as 2024–25:
  - pilot inputs and evidence feeds;
  - Bill Mill player and team logs;
  - liveData.
- **Pins.** Bytes, SHA-256 and retrieval times are written at capture and committed in a pins commit before any parse.
- **Retries.** A download may be retried only for a network error or a size or digest mismatch on the same URL before any parse. There is no recapture or source substitution after parsing has begun.
- **Missing feeds.**
  - If liveData or another evidence feed is missing, the existing pipeline labels apply (for example `no_livedata`). The run proceeds and the gap is reported.
  - If a required input is missing (play-by-play events or the player and team logs), stop. R1 confirmatory is then unavailable.

### 4.2 Build

Run the unchanged commands, with the same default parser path and no order repair:
- pilot `build`, `check` and `evidence`;
- `rapm_rows`;
- the #29 box-feature build.

### 4.3 Quality gate

These are the unchanged rules of the [season-quality report](season-quality-2017-2025.md) (ADR-0022):
- **Correctness invariants.** All of pilot `check`'s correctness invariants pass, as for every earlier season.
- **Game coverage.** Regular-season game coverage is at least 97%: accepted `002` games over official `002` games in the pinned 2025–26 NBA.com team log.
- **Unresolved possessions.** The season unresolved-possession share is at most 0.1%. It pools regular and playoff possessions in accepted games, as in the report.

Warnings are reported and not acted on. The limits, quarantine rules and parser cannot change after capture. If any hard limit fails, the confirmatory attempt ends and is reported failed. A repaired attempt needs a new registration and is labelled development evidence.

### 4.4 Order of operations

1. **Reads permitted before scoring:**
   - capture bytes;
   - the build, check and evidence steps, and the gate, which read outcomes for reconciliation;
   - fit rows strictly before each cutoff.
2. **Fit and freeze.** For R1, R2, R3, R4, P and the final snapshot in turn, fit and write the ratings snapshot. Then write the possession predictions for every scored row: realized lineups, context and frozen ratings, with no `y`. Then write the team-game pregame predictions. The digests of all of these go in a pre-score manifest.
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
- **Predictive validity:** P1, P2, T1 and T2, with coverage, uncertainty and negative results.
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
  "possession": {
    "dev_manifest_sha256": "db254b8c450034a0142255c40301e74cd6ddc59d505ab6d7aef983f846fce5d1",
    "outer_manifest_sha256": "f74fc2a5e76b7a22964ca8b96736344bc49f3611dd0acf37fbdaeb9ae130a131",
    "spm_fit_sha256": "1025774a8d327cbb25f6c284b49b9cbd80406e88a0406108a0877bf77b1edd90",
    "row_seasons": [2023, 2024, 2025],
    "cutoffs": {"R1": "2025-10-01", "R2": "2025-12-01", "R3": "2026-02-01", "R4": "2026-04-01", "P": "first 004 played date"},
    "final_snapshot": "2026-07-01",
    "primary_comparator": "rapm_context",
    "bootstrap": {"resamples": 2000, "seed": 2023}
  },
  "team": {
    "run_manifest_sha256": "8486bf8c42a30c708b12717c4955617d43aef044c4cf0cbc5b6da5fa8b1b1cee",
    "results_sha256": "ef0dd71e5b9723534eec4d8ee292f4110ce88b905f1fbb4671913ba2b980cee9",
    "pace": 99.92825203252032,
    "team_config": {"half_life": 60.0, "ridge": 4.0},
    "bootstrap": {"resamples": 2000, "seed": 39}
  },
  "verdict": "two-sided 95% percentile; ei_better/ei_worse need game and week intervals both excluding 0; regular season only",
  "box_logs": {
    "2024": {"snapshot": "issue-52-v1", "sha256": "e34398e754233203759f1e6ab8866dc6b61a11afcc3166b6ac9c099feca8b9bd"},
    "2025": "pinned at capture"
  },
  "quality_gate": {"check_invariants": "all pass", "min_regular_game_coverage": 0.97, "max_season_unresolved_share": 0.001},
  "d1": {"capture_window": ["2026-06-15", "2026-09-30"], "selection": "first season-EPM capture, else first expected capture, else unavailable"}
}
```
