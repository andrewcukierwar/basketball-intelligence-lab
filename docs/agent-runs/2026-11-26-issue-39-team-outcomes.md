# Agent run: #39 team outcomes with frozen lineups and pregame minutes

- **Date:** 2026-11-26
- **Status:** PR open
- **Related issues:** #39, #36, #55 (blocked: pregame availability capture), #42
- **Branch / commit:** `claude/issue-39-team-outcomes`. The run used `4bcb200`.

## Work completed

- **Protocol.** Registered the [protocol](../research/team-outcomes-protocol.md) and `bil.models.team_outcomes`, which produces:
  - pregame minutes from each team's last 10 strictly earlier games, using a roster heuristic and no availability information;
  - an oracle-minutes diagnostic;
  - a home-court baseline and a ridge team-rating baseline (grid chosen on 2021–23);
  - calibration on the development folds, with scoring on 2023–25.
- **Run.** Independent pre-run review (Sonnet subagent) found no blockers. Ran on a clean worktree. [Results](../research/team-outcomes.md)

## Key results

- **Against the team rating:** `ei_worse` on margin RMSE (+0.142 [+0.018, +0.262]). Log loss is inconclusive.
- **Against home court:** EI is much better.
- **Oracle minutes:** they recover 0.09 of the 0.14 gap.

## Verification

| Check | Result |
| --- | --- |
| `uv run pytest -q` | Pass |
| `ruff check`, `ruff format --check`, `mypy src` | Pass |
| Run | Clean `4bcb200`, manifest `8486bf8c…1cee` |

## Next actions

- **Follow-up (not tuned here).** Test whether daily or weekly EI refreshes, or season-aware calibration, close the team-level gap. This needs a registered revision and should be a new issue.
- **#42.** Register the joint R1 confirmatory protocol. It also needs #38 (defensive tracking) and #40 (EPM agreement diagnostics, which depend on #38).
