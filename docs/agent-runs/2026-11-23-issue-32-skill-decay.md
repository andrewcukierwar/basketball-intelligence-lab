# Agent run: issue #32 stat-specific Estimated Skills decay and shrinkage

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** #32, inputs from #31, evidence EPM-U05 and EPM-U06
- **Branch / commit / PR:** `claude/issue-32-skill-decay`. Protocol `4e25451` (committed before any real-data run), code `33fd3d0` (the evaluated revision), docs in the following commit. No push, no PR, no issue edits.

## Objective and authorized scope

Freeze the loss, bounds and per-statistic tying. Fit exponential decay and league shrinkage with Differential Evolution in nested chronological folds within 2022–23. Compare day and possession clocks, and compare against the #31 baselines overall and for low-minute, sparse-career, post-layoff and rookie groups, with game-clustered intervals. Record seeds, cutoffs, parameters, failure cases and date-specific snapshots, and pick up the cheap #31 follow-ups (playoff pooling convention, exclusion reasons). Use 2022–23 only. Never read 2023–24, 2024–25 or 2025–26.

## Work completed

- `docs/research/skill-decay-protocol.md`: frozen protocol, committed first.
- `src/bil/features/skill_decay.py`: pure model. Pooled stream through the #31 `skill_rows`, possession estimate, padded per-player panel, vectorized discounted-sum recursion for the day, games and possessions clocks, prediction `(N + k m) / (D + k)`, vectorized #31 likelihood, DE fit with frozen bounds and seeds, fold plan, cluster bootstrap and as-of snapshots.
- `src/bil/features/skill_decay_build.py`: CLI. Loads pinned logs through the #62 loader, enforces the 2022–23 scope guard, verifies the #31 manifest digests and reconciles every regular-season row with `issue-31-v1`, fits, selects clocks in inner folds, scores outer blocks, records exclusions and #31 unscored-target reasons, writes Parquet and a manifest with runtime and peak memory. Refuses a dirty tree.
- `tests/test_skill_decay.py` (20 tests): brute-force oracle for all three clocks, reduction to #31 decay and career baselines, cold rows equal to league, vectorized loss against `loss_terms`, possession estimate by hand, pooled playoff history, fold nesting, poisoned scored-block outcomes leaving earlier fits unchanged, seed reproducibility and bounds, as-of snapshots against next-game state, bootstrap, scope guard, and a small end-to-end run including Parquet writing.
- Docs: `docs/research/skill-decay-2022-23.md` (results), `docs/data-pilot.md` section, ADR-0018 in `docs/DECISIONS.md` (0017 is used on the #52 branch), EXP-0007 in `docs/experiment-log.md`.
- Private output: `data/processed/2022-23/issue-32-v1/` (`content_id` `5dc36c1874aa...`).

## Key decisions and discoveries

- Playoff convention (registered): playoff targets pool regular-season and earlier playoff history and league reference. Parameters are never fitted on playoffs, which are a separate outer block. Implemented by relabeling the stream for the #31 engine, so the playoff baselines are the same #31 forecasters under pooling.
- The model beat every #31 baseline on all 13 statistics in the regular-season outer blocks, with intervals excluding zero. MSE gains were 0.6–3.7% over the best baseline, and gains were larger in sparse, low-minute and post-layoff groups. Playoff gains over the 90-day decay were mostly within the intervals.
- The shrinkage strength is stable across fits. Half-life is poorly identified. Clocks are statistically indistinguishable except that a pure day clock is worse for `fta_per_36`. Inner-fold clock choice changes between blocks for 12 of 13 statistics.
- `fg3_pct` takes no decay within the season (bound) and a league prior of about 300 attempts.
- Rookie or cold rows: the model equals the league rate by construction. Bootstrap "significance" there is floating-point noise (differences below `3e-14`). A true rookie flag is unavailable without a draft or debut registry.
- #31's 2,396 unscored targets are now classified: mostly first-date no-league-reference rows (545 regular, 973 playoff) and zero-exposure history.

## Verification performed

| Check | Actual result |
| --- | --- |
| Real run from a clean tree, code commit `33fd3d0` | Pass. 336,622 regular rows matched #31 exactly, 0 possession fallbacks, 234 fits converged, 110 s wall time, 1.10 GB peak RSS |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Pass |
| `uv run pytest -q` | 187 passed, 2 skipped (before docs) |
| `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` | Pass |
| Independent review | Not run in this session. The lead should arrange it |

## Blockers and remaining risks

- **Interruption.** This session was interrupted by a rate limit before any commit or data run. On resumption the worktree had moved to another agent's branch. The `claude/issue-32-skill-decay` branch (still at `aa33dd7`) was checked out there, and no `issue-32` output existed, so the single run went to `issue-32-v1` as planned. No v2 rerun was needed.
- Doc files were edited while the run was in progress. The evaluated code commit and its clean-tree check were captured at start, and only Markdown changed.
- One season, retrospective, no strict cohort. The bootstrap ignores within-player dependence across games, so intervals are likely too narrow.
- The log-loss clipping inherited from #31 inflates sparse-history baseline losses. MSE is the cleaner group comparison.

## Next actions

- Independent review of `33fd3d0` and the docs commit against the protocol.
- Run the same frozen protocol on the 2023–24 and 2024–25 outer folds once #52's builds are accepted, including the offseason gap where clocks differ most. Do not touch 2025–26.
- Candidate follow-ups for triage: a draft or debut registry for true rookie status, player-clustered or two-way bootstrap, and tying half-lives across clocks or statistics given the flat decay surface.
