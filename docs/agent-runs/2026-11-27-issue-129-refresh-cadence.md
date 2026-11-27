# Agent run: EI refresh cadence against the daily team rating

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #129, #39, #136, #43
- **Branch / commit / PR:** `claude/issue-129-refresh-cadence`. The registration and run commit is `28246bb`.

## Objective and authorized scope

Test whether weekly or daily EI refresh closes #39's team-level gap to the daily ridge team rating. Minutes and calibration are matched. Box refresh is separated from on-court refresh. A matched-cadence team comparator, a #136-eligible season-aware calibration and runtime measurements are reported. 2023–25 is reused as development evidence, and #42 stays as recorded.

## Work completed

- **`bil.models.refresh_cadence`.**
  - Four EI cadences: block, weekly, daily and daily box-only. Each refresh is prepared and fit on rows before its date, and possessions are scored by the covering refresh.
  - #135 as-of snapshots, plus matched-cadence team ratings.
  - Reproduction gates against the published #36 and #39 outputs.
  - #136 post-freeze calibrations per cadence, loaded through `load_calibration` with new registered parents.
  - The #39 scoring and verdict rule, with week-interval sensitivity.
- **Tests.** `tests/test_refresh_cadence.py` covers cadence plans, refresh lookup, the gap criterion and the scoring structure.
- **Docs.** The [protocol](../research/refresh-cadence-protocol.md), the [results](../research/refresh-cadence.md) and ADR-0038.

## Key decisions and discoveries

- **Result.** Daily and weekly refresh both close the gap. All of the game-level gain comes from on-court refresh. The team rating suffers more than EI from slow refresh. At matched block cadence, EI beats it by −0.182.
- **Runtime.** A refresh takes about 0.5 s, so daily refresh is cheap.
- **Pre-registration plumbing check.** It used reduced cutoffs and confirmed the gates. The post-freeze block calibration slope was printed, and it matches #136. No evaluation metrics were computed before registration.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q` | 478 passed, 3 skipped |
| `ruff check`, `ruff format --check`, `mypy src` | Pass |
| Registered run `issue-129-v1` | Clean tree at `28246bb`, 168 s, 1.95 GiB. Gates: possession 0.0, EI margin 2.3e-6, team margin 5.0e-7 |

## Blockers and remaining risks

- The per-refresh runtime totals double-count shared preparation. The 168 s wall clock is authoritative.
- No independent pre-run review was run. Review is requested on the PR.
- The pregame-minutes heuristic is unchanged and has no availability information.

## Next actions

Independent review, then merge. #142 to #144 should target daily refresh and reuse the measured costs.
