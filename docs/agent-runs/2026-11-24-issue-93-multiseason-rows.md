# Agent run: canonical RAPM row sets for 2018–19 through 2024–25

- **Date:** 2026-11-24
- **Status:** Awaiting review
- **Related issues:** #93 (parent #26), #91, #89
- **Branch / commit / PR:** `claude/issue-93-multiseason-rows`, not pushed, no PR

## Objective and authorized scope

Generalize `bil.data.rapm_rows` to any pinned pilot build and build canonical (ADR-0019) row sets for 2018–19 to 2024–25. Data only: no model fitted or scored, no outcome statistics for 2023–24 or 2024–25 beyond ledger reconciliation, no 2025–26 or later files, no network, nothing under `data/` committed.

## Work completed

- `src/bil/data/rapm_rows.py`: the season now comes from the pinned manifest's `season_start_year` and is validated by `pinned_season()` (holdout and unpinned seasons refused, a missing or non-integer season refused). The hard-coded 2022 in the `stream_status_matches_review` check became the manifest season. The output manifest records `season_start_year`. It is not part of the `build_id` identity, so 2022–23 keeps its existing `build_id`.
- `tests/test_rapm_rows.py`: synthetic tests for builds in 2018, 2021, 2023 and 2024, a manifest/ledger season mismatch, holdout and unpinned refusal, and a missing or malformed season. The quarantined fixture game now has null home and away teams.
- `docs/data-pilot.md`: command and per-season reconciliation tables (aggregates only).
- Data (private, uncommitted): `data/processed/<season>/issue-93-v1/` for all seven seasons, built from `issue-25-v1` (2018–19 to 2021–22), `issue-19-v6` (2022–23) and `issue-52-v1` (2023–24, 2024–25), each pinned by manifest SHA-256.

## Key decisions and discoveries

- Season-specific handling needed no code beyond the season parameter. `no_livedata`, `v2_home_designation` and null-team quarantined games already flow through the strata tally and the identity checks.
- 2022–23 reproduction: the new build equals `issue-82-canonical-v1` byte for byte in all four tables, with an identical `build_id`. Against `issue-59-v1`, `model_row` and `score_reconciliation` have 0 rows in `EXCEPT ALL` both ways and identical file digests. `issue-59-v1`'s disposition and game reconciliation tables have the pre-#74 column set, so they were not compared.
- Each build took 3 to 4 seconds.

## Verification performed

| Check | Actual result |
| --- | --- |
| Seven builds, 16 identity checks each | 0 violations in every season |
| Pilot snapshot digest vs pilot manifest | Equal for every season |
| 2022–23 reproduction | As above |
| `uv run pytest -q`, `ruff check`, `ruff format --check`, `mypy src` | See the final report of this run |

Independent review has not been run.

## Blockers and remaining risks

- 2018–19 and 2019–20 are `no_livedata` throughout (ADR-0020). 2018–19 still has the quarantine concentration in overtime and November 2018 noted in the season-quality report.
- Retrospective capture-bound availability only.

## Next actions

Independent review of the diff, then push and PR on the lead's authorization. The row sets are the input for the #26 fits, which remain unauthorized here.

## Independent review

A fresh Opus reviewer approved with no blocking findings. It checked the following:
- **2022–23:** byte-identical reproduction.
- **2021–22:** its own interval-overlap query gave 223,043 eligible and 32,974 multiple-lineup possessions, matching the build.
- **`build_id`:** all seven are distinct.
- **Snapshots and inputs:** the raw snapshot and archive digests and all pinned inputs match for every season.

Non-blocking follow-ups:
- The builder copies the snapshot digest rather than re-hashing it. The docs now say so.
- No real season contains a null-team quarantined game, so only the synthetic fixture covers that path.
