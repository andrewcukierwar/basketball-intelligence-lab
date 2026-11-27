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
