# Agent run: #35 and #36 Expected impact v1, the #30 closeout and outer validation

- **Date:** 2026-11-25
- **Status:** #35 merged (PR #126). #36 PR open
- **Related issues:** #30, #121 and #35 (closed), #36, #125 (new follow-up)
- **Branch / commit / PR:** `claude/issue-35-expected-impact`. The run used `0b605c7`. PR linked from #35.

## Work completed

- **#124 / #121.** Independently reviewed Codex's PR #124 on exact head `311fe75` (Claude, a different model family from the implementer). Re-hashed all 54 private outputs, checked every reported number, and ran the full checks. Merged as `edc1e29`. Closed #121 and #30.
- **#35 protocol.** Registered [the #35 protocol](../research/expected-impact-protocol.md) and ADR-0030, which uses #30's fits as a provisional prior and defers Estimated Skills inputs to #125.
- **Implementation.** `bil.models.expected_impact` reuses M2's `Analysis`, blocks and search. Six synthetic tests include an equivalence check against the verified `fit_prior_rapm`.
- **Review and run.** Independent pre-fit review (Sonnet subagent) found no blockers. Ran on a clean worktree. [Results](../research/expected-impact-v1.md).

## Key decisions

- **Model.** The rating is the SPM prior plus a deviation from residual ridge on `y − Zγ − prior offset`, with the `W2` window, M2 refit schedule and M2 penalty search on the eight inner regular blocks.
- **Prior inputs.** The SPM prior uses #120 §5 raw dated box snapshots. Estimated Skills are ineligible at the inner cutoffs because the #32 fit used 2022–23 outcomes.
- **Penalties.** λ_O = λ_D = 8,000.

## Verification performed

| Check | Result |
| --- | --- |
| `uv run pytest -q` | Pass (full suite) |
| `ruff check`, `ruff format --check`, `mypy src` | Pass |
| Real build | Exit 0 at clean `0b605c7` in 36 s. Manifest `db254b8c…e5d1` |
| Pre-fit independent review | No blockers. Non-blocking notes folded into the results doc |

## #36 outer validation

- **Addendum.** Frozen at `88d79a3`. Independent pre-run review (Sonnet) found no code blockers.
- **Crash and fix.** The first attempt crashed on load before any result: the 2024–25 neutral-site games have null home flags. The loader was fixed at `fe81b0a` and the run repeated once. [Results](../research/expected-impact-outer.md)
- **Verdict.** `ei_better` against every comparator on the regular season. Against context-offset RAPM, the primary: −4.59 [−5.80, −3.37].
- **ADR-0031.** Proposes EI v1 as the M5 reference.

## Next actions

1. **Merge.** Merge the #36 PR after the number check and CI.
2. **Unblocked work.**
   - #39: team outcomes with frozen lineups and pregame minutes. Note the team-level tension: plain RAPM has the best regular-season team-game RMSE.
   - #41: a retrospective Actual impact analogue.
   - #38: defensive tracking.
3. **#42.** Register the R1 confirmatory protocol for 2025–26 from the frozen reference set before any holdout access.
4. **Maintainer review.** ADR-0030 and ADR-0031 are agent decisions flagged for review.
