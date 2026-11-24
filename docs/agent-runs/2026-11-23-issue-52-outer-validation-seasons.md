# Agent run: build the 2023–24 and 2024–25 outer-validation seasons

- **Date:** 2026-11-23
- **Status:** Awaiting review. Not pushed, no PR, and the issue has not been edited.
- **Related issues:** [#52](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/52), building on [#51](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/51) and [#19](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/19). The [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42) holdout was not touched.
- **Branch / commits:** `claude/issue-52-outer-validation-seasons` from `5ed99fb`:
  - `42be8ca` parameterizes the pipeline by season;
  - `9395ce1` adds V2 home designation;
  - a following commit adds the documentation.

## Objective and authorized scope

Build and reconcile both outer folds with the validated pilot pipeline, generalized minimally:
- pin snapshots and manifests;
- run `check` and `evidence`;
- report accepted, quarantined and unresolved counts by season type, with quarantine causes;
- record any pipeline change, and show that 2022–23 rebuilds identically.

Constraints:
- no network downloads;
- do not build or read 2025–26 or later;
- do not loosen thresholds;
- stop if coverage or verification falls well below 2022–23.

## Work completed

- **`pilot_sources.py`:** Per-season pins for 2022–2024 build and evidence inputs. The digests and sizes come from the #51 register CSVs. 2022 pins and names are byte-for-byte unchanged, which was checked against the previous module. Seasons from 2025 are refused. `capture`/`capture-evidence` take `--season` and `--from-local DIR`. A local copy is verified before and after copying. Its `retrieved_at` is the audit file's mtime, and the snapshot gains a `local_capture` field.
- **`pilot.py`, `pilot_check.py`, `pilot_evidence.py`:** Season-specific file names are read from the snapshot or manifest year. `game.season_start_year` follows the snapshot.
- **`pilot_inputs.py` and `pilot.py`:** The 2024–25 Bill Mill team log has `home = null` for both teams in five regular-season games, and without a rule the build stopped with a `ValueError`. Those games now keep a provisional order. V2 description columns must designate the home team unanimously, and the V3 final must then match the box points. Accepted games carry the `v2_home_designation` warning and stratum. Otherwise the game is quarantined as `unresolved_home_designation`. See ADR-0014.
- **Tests:** Six new synthetic test functions (eight cases) in `tests/test_pilot.py`. They cover:
  - provider-year naming;
  - holdout and unpinned-season refusal;
  - offline local capture, including changed and missing bytes;
  - season-specific check and evidence readers;
  - null-flag box loading and V2 designation;
  - the quarantine path.

  Three existing tests were updated for the new signatures.
- **Docs:**
  - outer-season section in `docs/data-pilot.md`;
  - ADR-0014;
  - EXP-0007;
  - README status line.

## Key decisions and discoveries

- **Box minutes.** 14 of the 19 2024–25 `player_minutes_mismatch` quarantines are games where a team's box minutes sum to 15 to 120 s away from 240 min. Every 2022–23 and 2023–24 regulation team-game is within 2 s. This points to a box-log defect (Inferred). The quarantines stand because the box remains the reference.
- **`0022301202` (2023–24).** V2 and V3 both have a final of 119–112. liveData, data.nba and the box show 122–112. The quarantine is correct.
- **Unresolved possessions.** The share rose from 0.02% to 0.039% and then 0.070%. All are within the season-level 0.1% M1 limit, but the 2024–25 playoffs alone are at 0.135%. This is reported and not acted on.
- **pbpstats.com.** Exact count agreement fell to 1,205 of 1,289 in 2024–25. In games without unresolved possessions it is 99.7%, so the decline comes from those games.
- **Run hygiene.** The first test run after the source refactor let `test_snapshot_checks_bytes_and_never_overwrites` download the public pinned 2022–23 archives into a pytest temp directory. The test still patched the old `SOURCES` global. The files were deleted, and the test now patches `season_sources`. No other network access occurred.
- **Intermediate build.** A first 2023–24 build at `42be8ca` was kept as `data/processed/2023-24/issue-52-pre-42be8ca`. The final build at `9395ce1` is row-identical to it.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Pass (Python 3.14.3 local venv) |
| `uv run pytest -q` | 121 passed, 2 skipped (archived-snapshot tests need `BIL_PILOT_SNAPSHOT`) |
| `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` | Pass |
| `capture` and `capture-evidence --from-local`, both seasons | 12 inputs and 8 evidence files verified per season |
| `build` 2023–24 | 1,218/1,230 regular and 81/82 playoffs. 61.4 s, max RSS 816 MB |
| `build` 2024–25 | 1,205/1,230 regular and 84/84 playoffs. 63.7 s, 805 MB |
| `build` 2022–23 rebuild (`issue-52-rebuild-v1`) | 1,208/1,230 and 84/84. 65.6 s, 802 MB. The `check` and `evidence` runs for 2023–24 overlapped part of the 2024–25 and 2022–23 build times |
| Rebuild vs `issue-19-v6` | 8 tables have identical SHA-256. In `game` and `game_stream`, only `ingested_at` differs (0 differing rows otherwise) |
| `check`, all three builds | 26 of 26 pass each |
| `evidence`, all three builds | Runs. Results are in the pilot guide. The 2022–23 rebuild reproduces the recorded values |
| Independent review | Not run in this session. Required before merge |

## Blockers and remaining risks

- **Bill Mill box log.** It is the reference for minutes and plus-minus, and its 2024–25 partition has internally inconsistent minute totals in at least 14 games.
- **Unresolved possessions.** Growth across seasons and the 2024–25 playoff rate (0.135%) may matter for outer-fold RAPM.
- **V3 order.** A few V3-ordered games show data.nba order reversals: 3 in 2023–24 and 3 in 2024–25, against none in 2022–23.
- **Holdout boundary.** No 2025–26 or 2026–27 payload was opened. The only listing of the audit directory was filtered to names containing 2023 or 2024.

## Next actions

- Run an independent review of the diff from `5ed99fb`, then decide on push and PR.
- Ask the maintainer whether the 0.1% unresolved-possession limit applies per season type.
- Consider a follow-up issue on box-log minute-total defects and on unresolved-possession boundaries before #26.
