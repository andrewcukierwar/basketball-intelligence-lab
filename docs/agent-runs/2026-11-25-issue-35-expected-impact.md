# Agent run: #35 Expected impact v1 and the #30 closeout

- **Date:** 2026-11-25
- **Status:** Awaiting review and merge of the #35 PR
- **Related issues:** #30 (closed), #121 (closed), #35, #36, #125 (new follow-up)
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

## Next actions

1. **Merge.** Final review of the results PR, then merge. #35 then moves to done.
2. **#36 outer addendum.**
   - Register an outer-validation addendum before reading any 2023–24 or 2024–25 row or box log. It covers the frozen configuration above and the locked pre-window SPM `final_contiguous_fit.json`.
   - The runner refuses to start without the committed addendum, as in M2's `outer_main`.
   - It compares EI with all four ADR-0026 comparators plus SPM-only and part ablations.
   - Box logs for both outer seasons exist in `data/raw/2023-24/issue-52-v1` and `data/raw/2024-25/issue-52-v1`, but #30's `LOG_PINS` does not pin them yet. Their `snapshot.json` digests must be pinned in the addendum.
3. **Maintainer review.** ADR-0030 is an agent decision flagged for review.
