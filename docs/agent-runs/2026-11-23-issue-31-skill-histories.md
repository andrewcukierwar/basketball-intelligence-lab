# Agent run: issue #31 skill histories, exposure denominators and baselines

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** #31, downstream #32 and #33, evidence EPM-U05 and EPM-U06
- **Branch / commit / PR:** `claude/issue-31-skill-histories`, code commit `8e1dc21631c3c3f4807acdfaa4c8fc5f8a4202b9` (docs in the following commit), no PR (lead integrates)

## Objective and authorized scope

Build player-game targets, strictly earlier baselines and exposure-weighted scores on top of the merged #62 box features and the evaluation resolver, for 2022–23 only. Document the numerator, opportunity and eligibility rules, freeze opportunities against source revisions, and record cohort coverage. Do not use 2023–24, 2024–25 or 2025–26. Nothing was pushed and no GitHub issue was edited.

## Work completed

- `src/bil/features/skill_history.py`: pure engine. One-date-at-a-time processing, so same-day games never see each other. Career, season, last-10 (covered games), 30- and 90-day decay and league baselines. Target and history statuses (observed, zero exposure, missing component, no prior, no covered, zero-exposure history). `strict_prior_counts` through `resolve_revisions`. Chronological `Scorer` (weighted MSE, binomial and Poisson log loss).
- `src/bil/features/skill_build.py`: loader reuse from `box_build`, three Parquet tables, manifest with `content_id`, snapshot IDs, opportunity and appearance digests, coverage, and a gated reconciliation (independent DuckDB self-joins over the raw logs for every baseline, target and headline score, plus player-day duplicates, career equals season, no strict history, and #62 appearance equality). `box_build._write_parquet` gained an optional `columns` argument.
- `tests/test_skill_history.py` (15 tests): brute-force reference for every baseline on a synthetic multi-player, two-season set, same-day exclusion, rookie and zero-exposure and missing cases, recency weights by hand, last-N window, season boundary, playoff separation, scorer hand calculation, strict counts against revisions, an end-to-end build, source-revision digest changes, and seeded prediction and target mismatches that fail the build and remove the output.
- Docs: `docs/research/skill-histories.md`, `docs/data-pilot.md` section, ADR-0016.
- Private output (not in Git): `data/processed/2022-23/issue-31-v1/`.

## Key decisions and discoveries

- As-of history stays keyed by season type, as in #62. Every first playoff game (217) is a no-history row. Registering a pooling convention is deferred to #32.
- Rookie means no earlier appearance in the loaded data. With one season this includes veterans in their first game, so it is not true rookie status.
- Baselines are untuned constants (last 10, half-lives 30 and 90 days, day clock). League baseline is per season type and season, so it is empty on the first date.
- The strict cohort is unavailable for this source, so only strict eligibility counts are frozen and no strict baseline exists. Strict eligibility need not be monotone, so a future strict baseline must rebuild state per cutoff.
- Descriptive result: unshrunk player percentages lose to the league baseline on `fg2_pct`, `fg3_pct`, and nearly `ft_pct`. Decay baselines edge out career on most per-36 counts, and last 10 is worst everywhere. These are not tuning decisions.
- First build passed reconciliation. The seeded-mismatch tests confirm the gates fail when a value is altered.

## Verification performed

| Check | Actual result |
| --- | --- |
| Real build, commit `8e1dc21`, `--box-manifest` issue-62-v2 | Pass. 27,622 appearances, 359,086 skill rows, 156 score cells. `baseline_sql_mismatches`, `league_sql_mismatches`, `target_sql_mismatches`, `score_sql_mismatches`, `player_same_day_duplicates`, `career_ne_season_rows`, `strict_rows_with_history` and `box_appearance_mismatches` all 0. `content_id` `167b7954d4a8...` |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Pass |
| `uv run pytest -q` | 155 passed, 2 skipped (before docs) |
| `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` | Pass |
| Independent review | A fresh Opus reviewer approved 69c6465 with no blocking findings. Its own bil-free script reproduced a decay prediction, regular and playoff league predictions (strictly earlier dates; not the full-season mean) and the `fg3_pct` headline MSE and log loss exactly. |

## Blockers and remaining risks

- Retrospective only, with an unrecorded historical-revision gap. Not forecast-origin evidence.
- One season: career equals season-to-date, so those two baselines are untested on real multi-season data (they are tested synthetically).
- The SQL reconciliation shares the loader's scope and identity checks. It tests aggregation and as-of logic, not source completeness.
- Independent review is required before acceptance.

## Next actions

Review the branch. For #32, register the playoff pooling convention and a true rookie flag, and fit decay and shrinkage against these baselines using eligible chronological folds. Append 2023–24 and 2024–25 only as outer folds, and never read 2025–26.
