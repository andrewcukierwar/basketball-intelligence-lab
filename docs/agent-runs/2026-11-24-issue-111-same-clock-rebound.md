# Agent run: same-clock shot, tip and rebound ordering rule

- **Date:** 2026-11-24
- **Status:** Awaiting review (PR open, not merged)
- **Related issues:** #111 (parent #53), #99 (order repair, untouched), ADR-0022, ADR-0028, EXP-0018
- **Branch / PR:** `claude/issue-111-same-clock-rebound`. Builds ran at `15923601`. The last commit adds only a warning note for a game that `--order-repair` rescues after the rule declined it, plus two tests and doc edits.

## Objective and scope

Derive, implement and validate an opt-in ordering rule for same-clock shot, tip and rebound sequences, rebuild 2008–09 through 2011–12 and other relevant seasons, and reassess ADR-0022 eligibility. No threshold or check relaxed, no data committed, no download, no 2025–26 or later file read, `--order-repair` untouched.

## Work completed

- Pins for 2008–09, 2009–10 and 2011–12 generated from the #51 register CSVs (the register test covers them). Captured with `--from-local`: 8 inputs and 4 evidence files each, all verified.
- `src/bil/data/pilot_clock_order.py`: rule `same-clock-v1`. `build --same-clock-rule` runs it only after the V2 and V3-primary attempts fail, so no previously accepted game is offered it. Manifest `same_clock_rule` lists every applied, declined and rejected game; accepted games carry stratum `same_clock_order` and a per-move warning.
- 17 synthetic and integration tests (tip-in, team rebound, block, and-one, period end, ambiguity, jump ball, determinism, raw rows untouched).
- Docs: research report, ADR-0028, EXP-0018, data-pilot section and eligibility matrix.

## Key decisions and discoveries

- Failure mechanism: V2 tie order within one clock puts a late tip attempt after the rebound that follows it. Rule: an orphan rebound takes the single later same-team missed field goal of its clock group. Zero or several candidates decline the whole game. An earlier version took the lowest event number among same-team candidates; Bentes disagreed on the one game where that mattered, so ties are quarantined.
- The first rule version treated a rebound after a jump ball as orphaned, which the parser accepts. Fixed to mirror the parser. Early `UnboundLocalError` for games that fail before the hook was found by the test suite and fixed.
- 44 of 55 declined games in the target seasons are a different defect: a team rebound after a free throw whose text lacks `MISS ` and points. A rule using the unchanged score would recover most remaining quarantines. Proposed as a follow-up issue, not implemented.

## Verification performed

| Check | Result |
| --- | --- |
| `uv run pytest -q` | 322 passed, 2 skipped |
| `uv run ruff check .`, `ruff format --check .`, `mypy src` | Pass |
| 17 rule builds (2001–02 to 2016–17, 2018–19), `check` | 26 of 26 each |
| Rows of previously accepted games, six tables, versus default builds | 0 differing in all 17. 2018–19 unchanged entirely |
| `season_quality.py` (`quality/issue-111-v2`, default comparison `issue-111-base-v1`) | 2010–11, 2004–05, 2014–15 meet. 2011–12, 2012–13, 2013–14, 2001–02 to 2003–04 fail |
| `evidence` for 2008–09 to 2011–12, 2004–05, 2014–15 | Bentes lineup share 1.0 (2014–15: 0.99996). pbpstats equal in 97 to 98% of games |
| Bentes order versus moves, target seasons | 47 of 48 agree (the other is a tie) |

Not run: a re-run of builds after the final logging-only commit (default path and rule behavior are unchanged by it; the unit tests and suite pass).

## Independent review

A fresh subagent read the diff and the builds. No blocker. It suggested logging a declined game rescued by `--order-repair` (done), more tests (two added), and doc wording (fixed, including the Bentes caveat). It did not replay the rule on real data.

## Open items

- 2011–12 playoffs 81 of 84 and 2012–13 regular 1,192 of 1,229 are each one game short. No row sets built for the newly eligible 2010–11, 2004–05, 2014–15. Whether to adopt the versioned datasets as primary history is the maintainer's call.
- Follow-up: free-throw missing-marker rule; cross-clock `unsupported_reorder` games.
- Obsolete scratch builds (`issue-111-rule-v1` to `v3`) remain under `data/processed` and can be deleted by the maintainer.
