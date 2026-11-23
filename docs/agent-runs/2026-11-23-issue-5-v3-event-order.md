# Agent run: resolve issue #5 event-order quarantines offline

- **Date:** 2026-11-23
- **Status:** Awaiting review. Issue #5 stays open for the remaining quarantine groups.
- **Related issues:** [#5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5)
- **Branch / commit / PR:** `claude/issue-5-v3-event-order` from `4c14f22`. Code is in `e098dca` and `4bbf68e`. The PR is linked from issue #5.

## Objective and authorized scope

Continue issue #5 from the [previous handoff](2026-11-23-issue-5-possession-pilot.md). Its next step was to test archived event-order evidence for the largest quarantine group, `unresolved_event_order` (79 games). The pilot had to stay offline, pinned and fully reconciled.

## Work completed

- `pilot_inputs.v3_games` now records each game's event numbers in V3 `actionId` order, keeping the first occurrence of each.
- `pilot_parser.parse_game` replaces the parser's live data.nba.com reorder with that V3 order, only when V3 covers exactly the V2 events. It rechecks rebound order on `Rebound` events and reports whether the fallback ran.
- Games that used the fallback get a `v3_event_order_applied` warning and a `v3_event_order` stratum.
- The parser version is now `pbpstats-1.3.11-bil-v2`.
- Added tests for the V3 order reader and for the reorder guard, which rejects missing, extra or duplicate events.
- Rebuilt the full season under `data/processed/2022-23/issue-5-v3-order-v2/`. Updated the [pilot guide](../data-pilot.md), [ADR-0008](../DECISIONS.md) and [EXP-0001](../experiment-log.md).

## Key decisions and discoveries

- In the pinned archives, V3 `actionNumber` equals V2 `EVENTNUM`. V3 also has an `actionId` sequence, so it can supply the same kind of evidence as data.nba.com order without a network request.
- 70 of the 79 games passed every existing check with V3 order. The other nine still fail on plus-minus (3), parser errors (3), score allocation (2) and a substitution conflict (1).
- Using V3 order from the start for other groups recovered only 4 of 22 parser errors and 2 of 4 unsupported reorders. It was rejected to keep the change narrow.
- The remaining risk is a same-clock ordering difference that changes no reconciled quantity. The stratum lets analyses separate these games.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run --extra dev --extra pilot pytest -q`, Ruff lint and format, `mypy src` | Pass: 9 tests, no lint, format or type issues. |
| Full build at `e098dca` (`issue-5-v3-order-v1`) and at `4bbf68e` (`issue-5-v3-order-v2`) | Both: 1,201 of 1,314 games accepted (1,121 regular, 80 playoff), 237,923 counted possessions. |
| Separate DuckDB checker that does not import pipeline code, 26 checks | Pass on both new builds and on the earlier `issue-5-final-v1`. Covers manifest digests and row counts, five distinct players, lineup sides, stints tiling each period, half-open possession intervals, final scores from events and from allocations, shooters on court, minutes within 2,000 ms and exact plus-minus. |
| Previously accepted games, old vs new build | 0 row differences across the event, actor, lineup, stint, possession and allocation tables for the 1,131 games. No game was newly quarantined. |
| Independent review of `e098dca` (fresh-context Claude Sonnet subagent) | No blockers. Two suggestions applied in `4bbf68e`. The suggested integration fixture for the fallback path was not added. |
| CI | See the PR. |

## Blockers and remaining risks

- 113 games remain quarantined. The largest groups are unresolved starters (33), parser errors (25), plus-minus mismatches (21) and score allocation (10).
- Regular-season overtime coverage is 53 of 79 games.
- The checker script lives in the session scratchpad and is not committed.
- The capture is retrospective and has no historical availability claim.

## Next actions

- Find period-starter evidence for the 33 `unresolved_starters` games. The pinned inputs contain no period-level box. Inferring starters from box minutes would use the reconciliation target as an input, so it needs an explicit decision first.
- Decide whether to commit an independent output checker as a repository script.
