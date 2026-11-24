# Agent run: backfill batch 4, 2001–02 and 2003–04

- **Date:** 2026-11-24
- **Status:** Awaiting review
- **Related issues:** #108 (parent #53), #105, #97, #98
- **Branch / PR:** `claude/backfill-batch-4-2001-04`, not pushed, no PR

## Objective and scope

Pin, capture, build, check and record 2001–02 and 2003–04 from the default path (no ADR-0023 order repair), run `season_quality.py`, build canonical row sets only for seasons that pass the ADR-0022 hard gates, and add the seasons to the eligibility matrix. Data only: no model fitted, no network, no 2025–26 or later files, nothing under `data/` committed.

## Work completed

- **Pins:** 2001 and 2003 added to `pilot_sources.py`, generated from the #51 register CSVs. The existing register test passes and the season-list test now expects both. Commit `4d45fb76c0909fe611a9bc025ed88a7790578dc5`, used as `--code-commit`.
- **Capture:** `--from-local` from `data/raw/historical-feed-audit/2026-11-23`, 8 inputs and 4 evidence files per season, size and SHA-256 verified. Every payload was present.
- **Builds:** `batch4-v1` for each season, 36 to 38 s, at most 0.75 GB. `check` 26 of 26 each. `evidence` run for each. `season_quality.py` into `data/processed/quality/batch4-v1`.
- **Row sets:** none. Neither season passes the hard gates, so `batch4-rows-v1` was not built.
- **`check-seasons`:** 20 builds (25,823 games), zero violations; with the 2010–11 probe build, 21 builds (27,134 games), zero violations.
- **Docs:** `docs/data-pilot.md` has the batch 4 section, two eligibility-matrix rows and the pin list.

## Results

| Season | Regular | Playoffs | Unresolved (reg / po / season) | Revised class |
| --- | ---: | ---: | --- | --- |
| 2001–02 | 1,149 of 1,189 (96.6%) | 62 of 71 (87.3%) | 0.189% / 0.305% / 0.195% | Fails hard limit |
| 2003–04 | 1,166 of 1,189 (98.1%) | 79 of 82 (96.3%) | 0.023% / 0.035% / 0.024% | Fails hard limit |

- 2001–02 fails three hard gates (both coverage floors and the unresolved limit). 2003–04 misses the playoff floor by one game.
- 2001–02 V3 period-defect games (register exception): `0020100084`, `0020100763`, `0020101171`. V3 has end-of-period scores for periods 1 to 3 only. All three are quarantined as `v3_box_final_mismatch`. Game `0020100064` is a separate `v3_period_score_mismatch` quarantine.
- Quarantine causes are in `docs/data-pilot.md`.

## Decisions and risks

- Both seasons are unavailable under ADR-0022. No hard gate was relaxed and no order repair was used.
- No pipeline code changed beyond the pins, so no 2022–23 equivalence rebuild was needed. No ADR or experiment-log entry.
- No season from 2001–02 to 2004–05 is eligible (2002–03, 2001–02, 2003–04 and 2004–05 all fail). Recovering any would need the ADR-0023 order repair or a maintainer gate decision, neither in scope.
- Independent review not run.

## Next actions

Independent review, then push and PR on the lead's authorization.
