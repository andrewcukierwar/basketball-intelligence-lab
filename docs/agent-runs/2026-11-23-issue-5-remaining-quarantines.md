# Agent run: resolve the remaining issue #5 quarantines and meet the M1 gate

- **Date:** 2026-11-23
- **Status:** Awaiting review. The PR proposes closing issue #5.
- **Related issues:** [#5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5)
- **Branch / commit / PR:** `claude/issue-5-remaining-quarantines` from `7cdb8de`. The final build is at `92011a7`. [PR #15](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/15).

## Objective and authorized scope

The user asked to finish issue #5 and resolve it. Work continued from the [V3 event-order handoff](2026-11-23-issue-5-v3-event-order.md), which left 113 games quarantined and no defined coverage threshold for the M1 exit gate.

## Work completed

- `pilot_starters.py` and a parser hook replace the live starter request with a search over candidate starter sets. A game is accepted only when exactly one candidate reconciles, or when every reconciling candidate gives the same reconstruction.
- `pilot_parser.parse_game` returns a `ParseResult`, records back-to-back possessions instead of raising, and can write events in V3 order for a last-resort retry.
- `pilot_normalize` marks possessions with a contradicted offense as `unresolved`, allocates their points with the `unresolved` reason, and searches same-clock credited lineups when only plus-minus differs. The minutes tolerance now accounts for truncated final-minute clocks.
- `pilot_check.py` and `python -m bil.data.pilot check` check exported builds independently.
- Seven new tests: starter candidates and search, unresolved possessions, the back-to-back recorder, credit search, the tolerance rule, and checker pass and fail cases. There are 16 tests in total.
- Updated the [pilot guide](../data-pilot.md) with the methods, third build, strata and M1 acceptance table. Added ADR-0009 and EXP-0002, and updated the README status.

## Key decisions and discoveries

- **Starters.** 19 of the 33 starter gaps were overtime players who logged no event. The other 14 were players whose event preceded a missing substitution. In two games the parser discarded the early starter choice when it switched to V3 order.
- **Back-to-back possessions.** These come almost entirely from held-ball jump balls whose recorded tip contradicts the next action. Allocation conflicts come from flagrant fouls where the fouled team keeps the ball. Neither affects lineups or scores.
- **Plus-minus.** Mismatches were same-clock credit choices that the official box makes inconsistently.
- **Minutes.** Near-misses came from V2 truncating final-minute tenths.
- **Rejected policy.** Making a V3 substitution disagreement non-blocking recovered nothing and was reverted.
- **Coverage thresholds.** These were set after observing results and are stated as such.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run --extra dev --extra pilot pytest -q`, Ruff lint and format, `mypy src` | Pass, 16 tests |
| Full build at `92011a7` (`issue-5-v5`) | 1,290 of 1,314 games accepted (1,206 regular season, 84 playoffs), 256,042 counted possessions, 54 unresolved |
| `python -m bil.data.pilot check` on the new build and on `issue-5-v3-order-v2` | 25 of 25 pass on both |
| Previously accepted games, `issue-5-v3-order-v2` against the new build | 0 row differences across six tables for 1,201 games; none newly quarantined |
| Independent review (fresh-context Claude Sonnet subagent) of the six code commits | No blockers. Applied in `92011a7`: a credit-search budget, failure reasons from the starter search, a shooter-in-credited-lineup check, and tests for the ambiguous and capped credit paths. Deferred: checks that every same-offense pair is resolved or exempt, and integration tests through real pbpstats for the starter and V3-primary paths. A rebuild at `92011a7` matched the earlier build row for row. |

## Blockers and remaining risks

- 24 games remain quarantined as source conflicts.
- In 49 accepted games the box chose the reconstruction, so the box checks there confirm uniqueness only.
- The capture is retrospective, and usage rights beyond private research are unconfirmed.

## Next actions

- Review and merge the PR, which closes issue #5.
- Start [issue #6](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/6), the synthetic RAPM reference. Use accepted possessions and allow strata exclusions.
