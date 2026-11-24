# Agent run: issue #33 context for game-agnostic and game-optimized skill forecasts

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** #33, inputs from #31 and #32, consumer #30 (SPM prior), evidence EPM-U07
- **Branch / commit / PR:** `claude/issue-33-skill-context`. Protocol `9642a51` (committed before any real-data run), code `9483a40` (the evaluated revision), docs in the following commit. No push, no PR, no issue edits.

## Objective and authorized scope

Freeze and compare the game-agnostic and matchup-specific skill forecasts with the #32 split and losses. Ablate aging, league trend, home, rest, opponent and team context one at a time, record missing inputs, validate cold starts and cutoffs, and expose an as-of skill snapshot for the SPM prior. 2022–23 only. Never read 2023–24 or later.

## Work completed

- `docs/research/skill-context-protocol.md`: frozen protocol, committed first.
- `src/bil/features/skill_context.py`: schedule inputs (home, back-to-back, rest), as-of opponent, own-team and league-trend inputs with a per-row latest-source date, the link-scale ridge adjustment (L-BFGS-B, analytic gradient) and the variant tables.
- `src/bil/features/skill_context_build.py`: CLI. Loads the pinned logs and the private #32 build (digests verified), reads the frozen fits and clock selections, fits the adjustment on earlier blocks only, scores all variants with game and player bootstraps, reconciles with #32 predictions and snapshots, writes Parquet and a manifest with the code commit and protocol SHA-256. Refuses a dirty tree and removes its output on any failed gate.
- `src/bil/features/skill_snapshot.py`: `skill_snapshot(rows, params, as_of)` for the SPM prior.
- `tests/test_skill_context.py` (14 tests): rest and back-to-back by hand, opponent and own-team allowed rates by hand, later games and rewritten later box lines cannot move earlier inputs, cutoff-violation detection, planted-effect recovery for both links, fold isolation of coefficients, end-to-end variants with a Parquet write, snapshot alignment with the #62 feature codes and aggregate rates, snapshot cutoff and equality with the #32 next-game state.
- Docs: `docs/research/skill-context-2022-23.md`, ADR-0021, EXP-0010, EPM-U07 evidence note.
- Private output: `data/processed/2022-23/issue-33-v1/` (`content_id` `e0ed313d9180...`).

## Key decisions and discoveries

- The base is the unchanged #32 model of record, and the adjustment is fitted on blocks before the scored one, with the block's own frozen parameters. All 194,764 base predictions and 26,481 snapshot rows matched #32.
- `full` (matchup-specific) lowers log loss in 12 of 13 statistics (10 with game-clustered intervals excluding zero, 9 under player clustering). MSE falls 0.02% to 0.88%. The gain shrinks from M3 (13 of 13 statistics) to M5 (10 of 13).
- Opponent allowed rates carry the gain: retained (beats agnostic and `recal`, both clusterings, all three blocks) for 9 statistics. Home, rest and team terms only match what the intercept-only control already gets, and `recal` shows level drift in the frozen base for `pf`, `tov` and `fga`.
- Aging cannot be tested: no birthdates in the pinned sources. Other missing inputs (injury reports, starters, expected minutes, rosters, travel, lines) are listed in the results.
- Regular-season context does not transfer to the playoffs: `full` is worse in 4 statistics there.
- Cold and post-layoff groups show no benefit (inconclusive, 15–50 and 181–573 rows).

## Verification performed

| Check | Actual result |
| --- | --- |
| Real run from a clean tree, code commit `9483a40` | Pass. 0 cutoff violations, 0 prediction mismatches, 0 snapshot mismatches, 2,496 fits converged, 18.5 s wall time, 1.05 GB peak RSS |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Pass |
| `uv run pytest -q` | 224 passed, 2 skipped (includes the 14 new tests) |
| `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` | Pass |
| Independent review | Not run in this session. The lead should arrange it |

## Blockers and remaining risks

- A first real-data launch (code `b6bb243`) aborted at the output step on a schema mismatch (level and delta score rows had different fields) after the reconciliation gates. `context_inputs.parquet` and `predictions.parquet` were written briefly and deleted on the exception, before any scores table or manifest existed. The fix changed only the output schema. No result from that launch was read.
- One season, retrospective. Intervals ignore serial dependence across a player's games. No multiplicity correction across 13 statistics and 11 variants.
- Opponent and team inputs are unadjusted for opposing rosters, so opponent quality and schedule are mixed.

## Next actions

- Independent review of `9483a40` and the docs commit against the protocol.
- Run the frozen protocol on 2023–24 and 2024–25 once #52's builds are accepted. Do not touch 2025–26.
- #30 can consume `skill_snapshot` (game-agnostic skill, strictly earlier appearances) as its as-of skill feature. A draft or debut registry would give birthdates and true rookie status. Candidates for triage: opponent inputs adjusted for opposing rosters, and an expected-minutes input.

## Independent review

A fresh Opus reviewer approved with no blocking findings. It checked:
- Every context input uses only strictly earlier dates, and fit rows stop before each outer block.
- The `recal` comparison is apples-to-apples. The reviewer recounted the 9 retained opponent statistics.
- The manifest provenance: protocol SHA-256 and a clean evaluated commit.
- The aborted launch, which it judged not to be a second run in substance.

It recomputed `tov_per_36` independently: full − agnostic is −7.43 ×10⁻³ (95% interval −10.69 to −4.08).

Nonblocking items:
- #30 callers must not pass `SkillParams` fitted on data after `as_of`. There is no public loader keyed by block yet.
- The `team` input includes the target player's own earlier games.

