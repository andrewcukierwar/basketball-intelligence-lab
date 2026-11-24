# Agent run: harden season-build holdout checks and home-designation tests

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** #80 (from reviews of #52 and #25)
- **Branch / commit / PR:** `claude/issue-80-pipeline-hardening`, not pushed

## Objective and authorized scope

Apply the six nonblocking review findings in #80 without changing behaviour on real builds. No rebuilds, network or 2025-26 files.

## Work completed

- `check_build` and `check_seasons` validate the manifest season through `pinned_season()`, so the holdout allow-list applies to `check` itself.
- Removed unused `snapshot_season` from `pilot_sources.py`.
- `_build_game` nulls `home_team_id`, `away_team_id`, `home_final` and `away_final` on a game still undesignated after V2 designation (always quarantined). The cross-season playoff check ignores null team IDs. Documented in `docs/data-pilot.md`.
- Tests for `_build_game`: accepted `v2_home_designation`, and a V3-contradicted designation that fails with `v3_box_final_mismatch`.
- `starter_agreement` takes the season and raises when a pinned-liveData season lacks liveData for a game, instead of counting it unavailable. Seasons without liveData still count it.
- `check_seasons` compares each manifest's `source_snapshot_sha256` with the SHA-256 of its `snapshot.json`.

## Key decisions and discoveries

- No current build has an `unresolved_home_designation` game (checked `game_review` for all eight builds), so nulling changes no existing output. 2024-25 has five `v2_home_designation` games, which keep their designated orientation.
- The liveData assertion is not exercised against real evidence directories here (not rerun); a real game missing liveData would now fail `evidence` rather than be skipped.

## Verification performed

| Check | Actual result |
| --- | --- |
| `check` on 2017-18 to 2021-22 (issue-25-v1), 2023-24, 2024-25 (issue-52-v1) | 26 of 26 each |
| `check` on 2022-23 issue-19-v6 with raw issue-5-v2 and issue-5-v1 | 26 of 26 each |
| `check-seasons` on 2017-18 to 2021-22, 2023-24, 2024-25 | all ok, digests match |
| `uv run pytest -q`, `ruff check`, `ruff format --check`, `mypy src` | Pass (219 passed, 2 skipped) |
| `evidence` on real builds | Not run |

## Blockers and remaining risks

Independent review not yet done.
