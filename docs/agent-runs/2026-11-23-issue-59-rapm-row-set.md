# Agent run: build and reconcile the 2022–23 RAPM row set

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** [#59](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/59), parent [#20](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/20), contract [#58](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/58)
- **Branch / commit / PR:** `claude/issue-59-rapm-row-set` from `26ac177`. Code commit `075babf`. No PR or push.

## Objective and authorized scope

Implement the [row contract](../research/rapm-historical-rows.md): a reproducible command that emits eligible rows, a possession disposition for every canonical possession, a score-allocation classification, per-game reconciliation and a content-addressed manifest. Reconcile to the pinned pilot (`issue-19-v6`) ledgers by game, season type and stratum. Keep per-possession rows. No model fitting.

## Work completed

- `src/bil/data/rapm_rows.py`: DuckDB builder and CLI (`python -m bil.data.rapm_rows`). It verifies the pinned pilot manifest digest and every table digest, then derives dispositions from half-open same-period stint overlap, model rows with numerically sorted player IDs, score classification and game reconciliation. Fifteen identity checks run against the pilot ledgers; any violation raises and removes the output directory.
- `tests/test_rapm_rows.py`: 13 tests. They exercise the #58 hand-adjudicated fixture (dispositions, model rows, per-team totals), a quarantined game, manifest content, rebuild determinism, the digest pins and eight ledger corruptions, each blocking on its intended check.
- Docs: build section in `docs/data-pilot.md`; pointer from the contract's exposure profile.

## Key decisions and discoveries

- Aggregation is not applied, so no equivalence argument is needed (**Original**, per the contract).
- `build_id` hashes the contract revision, pinned inputs and output digests, not the timestamp or code commit. Two builds (one at an earlier dev commit) gave identical Parquet digests.
- A control allocation scored by the possession's defense is an invalid input and blocks the build. The pilot has none.
- Evidence tier stays `retrospective_capture_bound`. No rolling-origin availability claim.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Pass |
| `uv run pytest -q` | 101 passed, 2 skipped (archived-feed tests without `BIL_PILOT_SNAPSHOT`) |
| `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` | Pass |
| Real build, `issue-19-v6` (manifest SHA-256 `89cb2e82…1570`) to `issue-59-v1`, about 3 s | All 15 identity checks report 0 violations. Build id `bc7b0174a2277146aba4eedef5bae7dbfd90462e03b6db14f46f63bc3af45b68`. |

Real reconciliation (1,314 expected games; 1,292 accepted, 22 quarantined with zero rows):

| Scope | Possessions: eligible / multiple-lineup / pilot-excluded / unresolved | Modeled pts | Other control pts | Dead-ball pts | Unresolved pts | Final pts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Regular (1,208 accepted) | 209,942 / 30,338 / 2,590 / 51 | 233,592 | 41,963 | 1,437 | 47 | 277,039 |
| Playoffs (84) | 14,097 / 2,079 / 166 / 0 | 15,499 | 2,838 | 74 | 0 | 18,411 |
| Total | 224,039 / 32,417 / 2,756 / 51 | 249,091 | 44,801 | 1,511 | 47 | 295,450 |

These reproduce the #58 profile exactly (224,039 and 32,417 of 256,456 accepted; 138.20 against 111.18 control points per 100). Per-stratum cells for all 12 strata, overall and by season type, are in the private manifest. Outputs: 224,039 model rows, 259,263 dispositions (equal to the possession ledger), 155,440 score classifications (equal to the allocation ledger), 1,314 game rows. Per-game score identities hold on each side against the final score.

## Blockers and remaining risks

- Not independently reviewed. The reconciliation checks were written by the implementer, though the tests show each fails on a seeded corruption.
- Row-level quarantine of 22 games means the cohort is the accepted 1,292, as the contract states.

## Next actions

- Independent fresh-context review of the diff and a re-run of the real build against the pinned manifest.
- Then #20 can feed `model_row` into the #6 estimator, converting player IDs to integers at that boundary.
