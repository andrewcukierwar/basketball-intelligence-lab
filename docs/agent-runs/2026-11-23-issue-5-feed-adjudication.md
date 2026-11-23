# Agent run: adopt archived-feed adjudication for the 2022–23 pilot

- **Date:** 2026-11-23
- **Status:** Awaiting review.
- **Related issues:** [#5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) (closed by #15)
- **Branch / commit / PR:** `claude/issue-5-feed-adjudication`, stacked on `claude/issue-5-external-verification` (PR #16). The code is in `9b4f24d` and `b1a43ed`, and the final build is `issue-5-v6` at `b1a43ed`. [PR #17](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/17).

## Objective and authorized scope

The user asked to implement all three ADR-0010 proposals. That makes the already approved and pinned liveData and data.nba archives build inputs for those decisions only.

## Work completed

- `pilot_sources.SOURCES` adds the four archives, so the source snapshot is now `issue-5-v2`. `pilot_inputs.cross_feeds` reads period-end scores, between-period substitutions and per-event offense team from them.
- `pilot_parser` fills a starter gap after the first period from the previous period's closing lineup and liveData's between-period substitutions, when consistent with the period's events. It records which team-periods were settled this way, and resets that record when the parser rebuilds its events.
- `pilot._build_game` accepts V3-only period-score defects, and the possession builder relabels unresolved possessions from unanimous data.nba offense with an adjacency guard. Each rule has a warning and a stratum.
- The `evidence` command checks liveData-chosen starters against Bentes.
- Four tests were added, for 21 in total. They cover the reader, starter consistency including too few known starters, period-defect evidence including missing periods, and relabeling with the adjacency guard. Updated the pilot guide, the source ledger, ADR-0011 and EXP-0004.

## Key decisions and discoveries

- **Previous-period lookup.** pbpstats does not link a period start to the previous period's end. The hook captures the loader's event list to find it.
- **Starter choice is now independent of the box.** liveData starters reproduced the same lineups as the box-selected ones in all 29 games, so the box is again an independent check there.
- **Relabeling helped less than estimated.** Only 3 unresolved possessions could be relabeled. Unanimity is common, but the unanimous label usually repeats a neighbor's offense, which means a boundary is missing.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run --extra dev --extra pilot pytest -q`, Ruff, `mypy src` | Pass, 21 tests |
| Build `issue-5-v6` at `b1a43ed` | 1,292 of 1,314 games (1,208 regular season, 84 playoffs). 256,456 counted possessions and 51 unresolved. All 79 regular-season overtime games accepted. |
| `check` | 25 of 25 pass |
| Diff with `issue-5-v5` | Identical event, lineup and stint rows for the 1,290 previously accepted games. Six possession rows and two allocation rows differ, in two games: the relabels. No game was newly quarantined. |
| `evidence` | Lineups agree with Bentes on 99.97% of court time in 1,292 of 1,292 games. All 33 liveData starter team-periods and both box-inferred ones match Bentes. Possession counts equal pbpstats.com's in 1,260 games. Live-ball offense, excluding the two relabeled games, agrees on 323,336 of 323,370 events. |
| Independent review (fresh-context Claude Sonnet subagent) of `9b4f24d` | Three blockers, all fixed in `b1a43ed`:<br>• missing periods counted as defect evidence<br>• stale starter labels after the parser's repair retries<br>• relabeled possessions inflating data.nba agreement<br>Suggestions applied: a minimum of three known starters, guards against malformed numbers, the new lower-trust strata, and documented order dependence. The rebuild matched. |

## Blockers and remaining risks

- 22 quarantines remain.
- For the affected games, the liveData and data.nba evidence comparisons are no longer independent. Bentes and pbpstats.com remain verification-only.

## Next actions

- Review and merge #16, then this PR.
- Start issue #6.
