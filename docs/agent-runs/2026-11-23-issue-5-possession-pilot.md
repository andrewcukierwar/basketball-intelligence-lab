# Issue #5 offline 2022–23 possession pilot

- **Date:** 2026-11-23
- **Status:** First full-season build and code reviewed. Issue #5 remains open for coverage and anomaly resolution.
- **Base and branch:** `9165d24`, `codex/issue-5-possession-pilot`.
- **Commits:** `6a58ee1` (pipeline), `e603698` (review fixes), `19c1bf7` (private spill routing and final dataset build).
- **Issue and PR:** [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) and [PR #12](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/12).

## Results and decisions

- Captured eight pinned 2022–23 input files and built canonical game, event, actor, lineup, stint, possession and score allocation Parquet tables. The [pilot guide](../data-pilot.md) records the commands, scoring rules and observed coverage.
- The final local build accepted 1,131 of 1,314 games and counted 223,995 possessions. The output manifest and per-game quality reports trace the 183 quarantines. All V3 final scores matched the team boxes. Regular-season overtime coverage was lower than regulation coverage.
- GPT‑6.2 Astra independently reviewed GPT‑6.2 Sol's changes from a fresh context. Review caught missing validation for missed-shot actors and comparison counts that combined unattempted checks with outcomes. Focused re-review confirmed fixes. The real run also surfaced spill files from an earlier DuckDB query. The final build uses private staging, and the earlier query and its temporary files were cleared from the checkout.

## Verification

| Check | Observed result |
| --- | --- |
| Pinned source capture and build through `python -m bil.data.pilot build` | Verified exact source sizes and hashes. The full-season build at `19c1bf7` finalized its output under `data/processed/2022-23/issue-5-final-v1/`. |
| Separate DuckDB queries on the final outputs and pinned boxes | Verified Parquet file hashes and row counts, five-player shape, team sides, active shot actors, complete stint timing, disjoint possession intervals, final scores, scoring allocations, exact plus-minus, and per-player minutes within 2,000 ms. The exported checks found zero failures in the accepted subset. |
| Pytest, Ruff lint and formatting, mypy, `git diff --check` | Seven tests passed in the isolated Python 3.12 pilot environment. Static and whitespace checks passed. [CI on the reviewed pipeline](https://github.com/andrewcukierwar/basketball-intelligence-lab/actions/runs/45206361192) |
| Git inventory and independent review | Neither raw nor generated dataset files are tracked. The reviewer confirmed active-shot identity, separate V3 metrics and private staging. |

## Next work

- Test compatible archived event-order evidence and period-starter evidence for the largest unresolved groups. Retain quarantines and measure results by anomaly stratum before accepting the pilot at milestone level.
- The source capture establishes retrospective evidence. Exact historical availability, broader rights, and downstream model fitness remain separate questions. Continue under issue #5 before claiming a training-ready season.
