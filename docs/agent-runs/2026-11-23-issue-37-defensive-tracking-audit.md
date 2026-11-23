# Issue #37 public defensive tracking audit

- **Date** 2026-11-23
- **Status** Independently reviewed
- **Issue** [#37](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/37)
- **Branch** `codex/issue-37-defensive-tracking-audit`, based on `d3d01f3`

## Scope and deliverable

Audited public NBA defensive tracking and hustle for regular season and playoffs from 2017–18 through 2022–23. The [report](../research/nba-defensive-tracking-audit.md) records verified opportunities, linkage, missingness, publication evidence, rights and the candidate paired cohort. The [source pins](../research/nba-tracking-audit-assets.csv) cover 12 Shufinskiy matchup files, 24 SportsDataverse files, and six positive-minute player-box reference partitions. No confirmatory payloads were accessed. Source files are in the Git-ignored private directory `data/raw/defensive-tracking-audit/2026-11-23` (36 files, 52,452,676 bytes) and reused #51 box capture.

## Findings and decisions

- SportsDataverse's documented directed roles and 88 additional 2019–20 games make it the candidate matchup revision for a private retrospective paired comparison. It covers 7,542 of 7,562 box games and all 503 playoff games in the window. Of 160,241 positive-minute box appearances, 159,691 have linked, positive matchup exposure. Of those, 154,455 also have positive matchup FGA. These are coverage ceilings before the independent RAPM and #29 joins.
- The mirrors agree on compared values for 1,394,967 of 1,395,420 shared directed pair rows. The shared upstream and revision differences were recorded. Matchup attempts reconcile to complete positive box FGA in 62,662 of 152,182 matched shooter-games, so matchup opportunities stay on their own scale.
- The SportsDataverse hustle and rim archives both contain the six regular and six playoff season totals. The official historical defend and closest-defender web queries did not yield inspectable rows in the audit tool. These families remain outside the per-game candidate. Provider timestamps do not establish exact historical availability. Strict historical evaluation is unavailable on these captures.

## Verification

| Check | Observed result |
| --- | --- |
| Publisher and local pins | Verified 42 assets, including original Git blob IDs for Shufinskiy and publisher SHA-256 for SportsDataverse. |
| `scripts/audit_defensive_tracking.py` | Scanned all 12 partitions and reproduced the aggregate JSON byte-for-byte. |
| Linkage and opportunities | Positive-minute opponents joined on game and player IDs. No duplicate matchup keys. All 1,412,492 SportsDataverse rows passed audited numeric opportunity checks. |
| Confirmatory isolation | The downloaded filenames and profiler are limited to the six audit seasons. |
| Repository checks | `pytest -q` passed all 43 tests. Ruff lint and format, mypy on `src` and the profiler, and `git diff --check` passed. |

The independent reviewer verified all 42 pins and reproduced the 2019–20 regular and 2022–23 playoff partition results exactly. No acceptance blockers remained. The #37 and #51 changes to the source ledger combine cleanly in a local integration checkout.

## Next actions

Use the documented retrospective cohort and box-only fallback when [#38](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/38) reaches its dependencies. Register the denominator, sensitivity and missingness policy before comparison, then measure intersection with accepted target rows and #29. Preserve the strict evidence gap and the holdout.
