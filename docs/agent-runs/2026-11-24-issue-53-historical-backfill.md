# Historical backfill closeout

[#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53) · `codex/issue-53-historical-backfill` · build base `8eac253`

The [coverage and replay report](../research/historical-backfill-2001-2017.md) reconciles the six historical batches, preserves the original classifications in the pilot guide, and records the current dispositions for all 16 requested seasons. Eleven meet the ADR-0022 hard limits. The selected 2012–13 row set is a candidate for conditional use because its April quarantine and close-margin unresolved concentrations recur. The five failed seasons and experimental 2017–18 have zero modeling exposure under this backfill.

Replayed both accepted opt-in parser rules in 2001–02 through 2003–04. Nine games recovered and none moved a season across the gates. The `time -l` system clock query was denied after its child process succeeded. Replayed the first build and first row extraction with Python's child RSS and a monotonic timer, which also measured subsequent builds.

Built six private `issue-53-rows-v1` row sets totaling 1,251,142 stable-lineup possessions. Used the reviewed same-clock build for 2004–05 and the reviewed two-rule build for the five other seasons. The #28 target pins, #30 inputs and holdout stayed reserved under ADR-0026 and ADR-0027. Corrected #99's archived output paths and recorded its experimental merge status.

## Verification

- `season_quality.py --run-checks` passed 26 of 26 invariants on each of the 17 selected pilot builds, including 2017–18.
- `pilot check-seasons` passed all five checks across 21,959 expected games and roster changes.
- Verified snapshot and evidence artifact hashes, all selected pilot output digests, and actual counts and digests of all six new row-set outputs. Each row set passed the 16 row identities and replayed to the same content-addressed ID and four Parquet digests.
- Compared the 3,712 previously accepted games in the earliest three seasons with both-direction `EXCEPT ALL` across ten tables. Only ingestion timestamps differ. Reran pinned feed comparisons for these seasons and the six row sets.
- `python -m pytest -q` reported 408 passed with both archived fixtures enabled (405 passed and 3 skipped without them). Ruff lint, Ruff format, mypy, Markdown links and `git diff --check` passed.

Independent review is pending. The versioned row sets are available for separately registered cohort experiments. Any attempt to recover the remaining seasons would need a new evidence-backed parser or feed change under the existing gates.
