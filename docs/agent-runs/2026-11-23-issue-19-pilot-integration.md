# Agent run: integrate the 1,292-game pilot into main

- **Date:** 2026-11-23
- **Status:** Awaiting review. The PR proposes closing issue #19.
- **Related issues:** [#19](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/19), [#5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5)
- **Branch / commit / PR:** `claude/issue-19-pilot-integration` from `b94dc14`. The merge is `0e2a37c`.

## Objective and authorized scope

The maintainer asked to start #19. [PR #17](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/17) merged into `claude/issue-5-external-verification` 19 seconds after that branch had merged into `main`, so the archived-feed adjudication never reached `main`.

## Work completed

- Merged `origin/claude/issue-5-external-verification` into `main`. The merge brings in exactly the #17 commits: `9b4f24d`, `b1a43ed`, `0d4f728`, `28c5374` and their merge `dd76c2c`.
- Two conflicts, both appended entries:
  - ADR-0011 from #17 and ADR-0012 from #18.
  - EXP-0004 from #17 and EXP-0005 from #18.

  Both pairs are now in numeric order. No code conflicted. #18 touched only RAPM code, packaging and docs, and none of the pilot files.
- Updated the README's M1 status to 1,292 games. Noted in the pilot guide that the evidence example and its table describe build `issue-5-v5`.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv sync --locked --extra dev --extra pilot --extra rapm`, `pytest -q`, Ruff lint and format, `mypy src` | 43 passed: 39 from `main` plus 4 from #17. All other checks pass. |
| Rebuild from snapshot `issue-5-v2` at `0e2a37c` into `issue-19-v6` | About 1 minute. 1,292 of 1,314 games accepted (1,208 regular season, 84 playoffs). 256,456 counted possessions, 2,756 excluded and 51 unresolved. |
| Compared with the recorded `issue-5-v6`, built at `b1a43ed` | The event, actor, lineup, stint, possession, score-allocation, review and quality-issue tables are byte-identical: equal SHA-256. In `game` and `game_stream`, only `ingested_at` differs. In the manifest, only `code_commit` and `generated_at` differ. |
| `check` | 25 of 25 pass |
| `evidence` | Same as recorded. All 33 liveData starter team-periods and both box-inferred ones match Bentes. V3 alone differs in 0022200107 and 0022200466. data.nba alone differs in 0022201098. |
| Independent review (fresh-context Claude Sonnet subagent) of `0e2a37c` | No blockers. It confirmed the resolution keeps both sides byte for byte, and that the diff contains only the expected commits. Applied its suggestion to label the v5 evidence example. |

## Remaining quarantines and independence limits

- The 22 quarantined games are unchanged and classified in the [pilot guide](../data-pilot.md).
- Under ADR-0011, liveData and data.nba are build inputs for three narrow decisions. For the affected games they are no longer independent checks:
  - starters in `livedata_starters` games;
  - the relabeled possessions;
  - period scores in `v3_period_defect` games.
- Bentes and pbpstats.com remain verification-only.
- Source restrictions are unchanged: private, noncommercial research, and nothing under `data/` is committed.

## Next actions

- Merge this PR, which closes #19. Then #20 and the deferred pilot checks in #54 can start.
- The project-plan status line in PR #50 says the pilot upgrade is "awaiting integration". Update it once this merges.
