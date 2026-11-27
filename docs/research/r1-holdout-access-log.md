# R1 holdout access log (#42)

Every operation that reads 2025–26 data, per [protocol §5](r1-confirmatory-protocol.md). Protocol SHA-256 `2159cc24344ffe30344fe04992cdfd8d52bbc5097abeb5c64839653422ddd045`, frozen at commit `470df09`. Raw files, rows, ratings and predictions stay under `data/`; this log records aggregates and digests only.

| UTC time | Commit | Command | What was read | Output digest |
| --- | --- | --- | --- | --- |
| 2026-11-27T01:35:44Z | `470df09` | `python -m bil.models.r1_holdout capture data/raw` | Raw bytes only (download, SHA-256 and size of the 2025–26 Bill Mill team and player game logs). Nothing parsed. One capture run, no retries. | snapshot.json `af41b22a07c83674dd56e26f2a3a26d4bc8acb4e1fb97c12e700416bf9a52d1b` |

## Pre-parse clarification of the §4.3 gate (option A, 2026-11-27)

Recorded and committed before any 2025–26 row is parsed. Only the capture bytes above had been read.

- **Gap.** §4.2 and §4.3 name "the unchanged #29 box-feature build (`bil.features.box_build`)". That builder is hard-wired to 2022–23: `build_box_features` calls `load_appearances` with its default `season_start_year=2022`, its `EXPECTED` profile counts are 2022–23's, and its window IDs end `-2022-23`. Run literally on 2025–26, it fails for reasons unrelated to the data.
- **Decision (user, option A).** The gate's "box-feature build completes" is the unchanged #29 contract validation, `load_appearances(season_start_year=2025)`, reached through the guarded `box_logs`. It refuses exactly the violations §4.3 lists: duplicate or invalid keys, unreciprocated team rows, disagreeing dates or home flags, and count-identity violations. The #36 runner already applied it to 2023–24 and 2024–25. The 2022–23-only view builder is not run. Coverage, the 97% limit and the warnings are unchanged.
- **Code.** `scripts/r1_gate.py` uses only unchanged library functions. Checked before the holdout on 2024–25 (`issue-52-v1`): 1,230 of 1,230 regular-season games covered, 4 minutes warnings and 5 games with no single home team. Reviewed by a fresh-context subagent before running; its three findings (self-paired rows, a score-column dependency through `team_games`, uncaught build errors) were fixed and the 2024–25 check rerun with the same result.
- **Labelling.** The R1 report states this as a pre-parse deviation from the literal §4.2 text and keeps the label *retrospective confirmatory*.

## Gate and later entries

| UTC time | Commit | Command | What was read | Output digest |
| --- | --- | --- | --- | --- |
| 2026-11-27T03:34:39Z | `5a82b9e` | `python scripts/r1_gate.py data/raw data/processed/r1/holdout-gate` | Rows of both pinned 2025–26 logs for contract validation and coverage. The team log's points were read only by `team_games` for its warning counts. No margin was printed or used. **Gate passed:** the contract validation completed (28,572 appearances), 1,230 of 1,230 regular-season games covered (100%, limit 97%) and 85 playoff games present. Warnings: 0 minutes mismatches, 5 games with no single home team. | gate.json `a3592ff2308288d69f7b1511035c18e9e2d07d6ff774efbf0938059aa9af3469` |
| 2026-11-27T03:34:49Z | `107accb` | `python -m bil.models.r1_holdout predict data/raw data/processed data/processed/r1/holdout-2025 --season 2025` | Box appearances strictly before each cutoff (R1 2025-10-01, R2 2025-12-01, R3 2026-02-01, R4 2026-04-01, P 2026-04-18, final 2026-07-01) and the pre-holdout rows. `predict` read the team log's margins only as team-rating history from earlier days. Scored games enter the predictions with no margin. `ei_oracle_minutes` uses each game's realized minutes, not its score, as in #39; it is a reported diagnostic only. 1,310 games predicted. predictions.csv `12219e02…b9b9`, ratings.csv `0fbbe4fd…3ae2`. pre-score manifest sha256: 7d49a867d40f73dea1810d75c91950a63ace9bf8b51e4cce0c2f27bd70704b0e | manifest.json `7d49a867d40f73dea1810d75c91950a63ace9bf8b51e4cce0c2f27bd70704b0e` |
| 2026-11-27T03:35:10Z | `8e6aa50` | `python -m bil.models.r1_holdout score data/raw data/processed/r1/holdout-2025` | **Refused before reading any outcome** (`HoldoutLocked`): the labelled digest above sat mid-row in the table, and the runner requires a line that ends with the label and digest. No results were written. The standalone line follows. | none |

pre-score manifest sha256: 7d49a867d40f73dea1810d75c91950a63ace9bf8b51e4cce0c2f27bd70704b0e

| UTC time | Commit | Command | What was read | Output digest |
| --- | --- | --- | --- | --- |
| 2026-11-27T03:35:25Z | `755c1e9` | `python -m bil.models.r1_holdout score data/raw data/processed/r1/holdout-2025` | Outcomes of the 1,310 predicted games, after the guard, the labelled log line and the manifest checks passed. Run once. **C1 `ei_worse`** (regular-season margin RMSE Δ +0.714, game 95% [0.494, 0.943], week 95% [0.432, 0.982]). **C2 `ei_worse`** (win log loss Δ +0.0404, game [0.0276, 0.0541], week [0.0262, 0.0541]). Aggregates are copied to `docs/research/r1-holdout/`. | results.json `677977d410e4240fc4d897157f336d8dc040ba9a92016c1f692091e2345e7dfd` |
| 2026-11-27T03:40Z | `951441f` | Wayback CDX listing of `dunksandthrees.com/epm`, 2026-06-15 to 2026-09-30, then `id_` fetches of all six captures, in timestamp order | Capture timestamps and embedded metadata only (form, season labels, season types, row counts, data dates), through a metadata-only inspector; no EPM values. All six captures (20260702010514, 20260705153728, 20260711203420, 20260722045652, 20260926063812, 20260927063648) hold only the `expected` form, 602 rows, season 2026, data date 2026-06-13. None is `json` or `columnar`, so §3.3 rule 3 selects **20260702010514**, labelled *expected*. Pinned in `r1-holdout-pins.json`. | capture `cb94230a5f6d154532fee05b59eb845279e8e72e2a8722fc5733f67174d4e3a0` |
