# Agent run: issue #62 box-score feature views

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** #62, parent #29, contract #63
- **Branch / commit / PR:** `claude/issue-62-box-feature-views`, builder commit `00bfd677b2c7425d49f2fe19ce99642a4c5ccb65`, no PR (lead integrates)

## Objective and authorized scope

Build same-window (retrospective) and eligible as-of box-score feature views for 2022–23 from the pinned `issue-5-v2` logs under the #63 contract. Verify rates, identity, missingness and chronological joins, reconcile the full pilot, and write a reproducible build and manifest. Nothing was pushed and no GitHub issue was edited.

## Work completed

- `src/bil/features/box.py`: pure feature definitions (13 features), accumulator, window and as-of selection, strict selection through `bil.evaluation.eligibility.resolve_revisions`.
- `src/bil/features/box_build.py`: loader and validator, view builder, DuckDB reconciliation, manifest, CLI (`python -m bil.features.box_build`).
- `tests/test_box_features.py`: replays all five #63 fixture cases, same-day and future exclusion, season-type separation, missing-component isolation, strict boundary cases, and a synthetic end-to-end build.
- `docs/data-pilot.md`: command and output description.
- Private output (not in Git): `data/processed/2022-23/issue-62-v1/` with `appearances`, `same_window_features`, `asof_retrospective_features`, `asof_strict_features` and `manifest.json`.

## Key decisions and discoveries

- As-of history is limited to the target game's season type (regular games see regular history, playoff games see playoff history). The contract says season types must be declared but gives no as-of default, so this follows its rule against pooling types unless registered. Recorded in the manifest as `history_season_type`.
- Dated retrospective rule: `game_date < rating_date`, cutoff `eastern_origin(game_date)` recorded per row. Cold-start rows are kept with null statistics (756 = 539 regular + 217 playoff first appearances).
- The strict view is an explicit unavailable cohort. All 2,190,960 candidate-cutoff exclusions (summed over date and season-type cutoffs) are `available_after_cutoff`, because the capture bound is 2026-11-23.
- Same-window views use full regular-season and playoff windows only. Team splits remain derivable from `appearances`. Mixed windows are not built.
- Source data have no null counts in scope, so missingness is exercised by hand fixtures only.

## Verification performed

| Check | Actual result |
| --- | --- |
| Real build | Pass. 27,622 appearances (25,894 regular, 1,728 playoff), 1,314 games, 539 and 217 players, 71 multi-team players, 1,378 / 6,016 / 12,102 zero FGA / 3PA / FTA, 2 zero-minute rows. All equal the #63 profile, zero mismatched expectations. |
| Same-window vs independent SQL totals | 756 player and season-type groups, 0 mismatches (minutes, points, 2P, 3P, FT, assists). |
| As-of prior-appearance counts vs SQL self-join | 27,622 rows, 0 mismatches. |
| Output rows | appearances 27,622; as-of retrospective 359,086; as-of strict 359,086 (max eligible 0); same-window 9,828. |
| `uv run pytest -q` | 100 passed, 2 skipped (before the handoff commit) |
| `ruff check .`, `ruff format --check .`, `mypy src` | Pass (format run before commit; `format --check` rerun below) |
| Independent review | Not run. |

## Blockers and remaining risks

- Retrospective as-of features carry an unrecorded historical-revision gap; they are not forecast-origin evidence.
- `reconcile` and the SQL checks share the scope filter with the loader, so they test the aggregation, not source completeness; completeness rests on the #63 profile counts.
- Independent review is required before acceptance.

## Next actions

Review the branch, then decide whether the SPM fit should pool or separate season types in as-of history and add the RAPM-target intersection counts.
