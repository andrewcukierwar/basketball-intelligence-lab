# Agent run: issue #62 box-score feature views

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** #62, parent #29, contract #63
- **Branch / commit / PR:** `claude/issue-62-box-feature-views`, builder commit `00bfd677b2c7425d49f2fe19ce99642a4c5ccb65`, review fixes `3527ec57869fdf206c225729ca268a877d246b92`, no PR (lead integrates)

## Objective and authorized scope

Build same-window (retrospective) and eligible as-of box-score feature views for 2022–23 from the pinned `issue-5-v2` logs under the #63 contract. Verify rates, identity, missingness and chronological joins, reconcile the full pilot, and write a reproducible build and manifest. Nothing was pushed and no GitHub issue was edited.

## Work completed

- `src/bil/features/box.py`: pure feature definitions (13 features), accumulator, window and as-of selection, strict selection through `bil.evaluation.eligibility.resolve_revisions`.
- `src/bil/features/box_build.py`: loader and validator, view builder, DuckDB reconciliation, manifest, CLI (`python -m bil.features.box_build`).
- `tests/test_box_features.py`: replays all five #63 fixture cases, same-day and future exclusion, season-type separation, missing-component isolation, strict boundary cases, and a synthetic end-to-end build.
- `docs/data-pilot.md`: command and output description.
- Review fixes (commit `3527ec5`): reconciliation now reads the written Parquet and checks all 13 features in both as-of and same-window views against independent SQL. Any SQL mismatch, group-versus-row gap, nonempty strict history or profile difference fails the build and removes the output (tests seed a mismatch in each view). The manifest gains per-view, per-season-type `coverage` (rows, cold starts, players, per-feature eligible, covered and null counts), per-view `snapshot_ids` bound to the snapshot digest, cohort mode and history policy, `source_pins_verified`, and window start and end dates.
- Private output (not in Git): `data/processed/2022-23/issue-62-v2/` (supersedes v1) with `appearances`, `same_window_features`, `asof_retrospective_features`, `asof_strict_features` and `manifest.json`.

## Key decisions and discoveries

- As-of history is limited to the target game's season type (regular games see regular history, playoff games see playoff history). The contract says season types must be declared but gives no as-of default, so this follows its rule against pooling types unless registered. Recorded in the manifest as `history_season_type`.
- Dated retrospective rule: `game_date < rating_date`, cutoff `eastern_origin(game_date)` recorded per row. Cold-start rows are kept with null statistics (756 = 539 regular + 217 playoff first appearances).
- The strict view is an explicit unavailable cohort. All 2,190,960 candidate-cutoff exclusions (summed over date and season-type cutoffs) are `available_after_cutoff`, because the capture bound is 2026-11-23.
- Same-window views use full regular-season and playoff windows only. Team splits remain derivable from `appearances`. Mixed windows are not built.
- Source data have no null counts in scope, so missingness is exercised by hand fixtures only.

## Verification performed

| Check | Actual result |
| --- | --- |
| Real build (v2, code commit `3527ec5`) | Pass, exit 0, `failed_checks` and `mismatched_expectations` empty. 27,622 appearances (25,894 regular, 1,728 playoff), 1,314 games, 539 and 217 players, 71 multi-team players, 1,378 / 6,016 / 12,102 zero FGA / 3PA / FTA, 2 zero-minute rows. All equal the #63 profile, zero mismatched expectations. |
| Same-window vs independent SQL, all 13 features, from written Parquet | 9,828 feature rows (756 groups x 13), group count equals row count, 0 mismatches. |
| As-of vs SQL self-join, all 13 features, from written Parquet | 359,086 feature rows checked, 0 mismatches; strict view has 0 rows with history. |
| Coverage in manifest | Retrospective as-of cold-start rows 539 regular + 217 playoff = 756; players with history 530 regular, 202 playoff. |
| Output rows | appearances 27,622; as-of retrospective 359,086; as-of strict 359,086 (max eligible 0); same-window 9,828. |
| `uv run pytest -q` | 102 passed, 2 skipped |
| `ruff check .`, `ruff format --check .`, `mypy src` | Pass |
| Independent review | Not run. |

## Blockers and remaining risks

- Retrospective as-of features carry an unrecorded historical-revision gap; they are not forecast-origin evidence.
- The SQL checks share the scope filter with the loader, so they test aggregation, not source completeness; completeness rests on the #63 profile counts.
- Open SPM decision: because as-of history is per season type, every player's first playoff game has empty history (217 rows). Pooling regular-season history for playoff games needs an explicit registered convention.
- Independent review is required before acceptance.

## Next actions

Review the branch, then decide whether the SPM fit should pool or separate season types in as-of history and add the RAPM-target intersection counts.

## Independent review

A fresh Opus reviewer recomputed all 13 features independently with SQL over the raw logs. The same-window view and the as-of retrospective view both had 0 mismatches. The reviewer requested two changes: gate the build on reconciliation, and record coverage and missingness in the manifest. Both were fixed in 3527ec5.

A focused re-review approved the fixes. Four seeded faults each fail the build and remove the output. The reviewer checked the manifest coverage fields in `issue-62-v2` against its own SQL, and confirmed that `expected=None` cannot be reached from the CLI.
