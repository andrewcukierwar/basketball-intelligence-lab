# Issue #2 historical NBA source validation

- **Date:** 2026-11-23
- **Status:** Audit complete and independently reviewed. Pilot acceptance remains with issue #5.
- **Branch:** `codex/issue-2-source-validation`, based on the merge of PR #8 at `2a76400`.
- **Commits:** `7d4090b` (source and tracking audit), `22e8254` (machine-readable box-score reference).
- **Issues and PR:** [Issue #2](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/2) and [PR #9](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/9).

## Results and decisions

- Changed the leading 2022–23 event candidate from Bentes to pinned Shufinskiy NBA Stats V2. Its stable IDs, explicit substitution participants, and matching game sets support this choice. Bentes's processed stints and possessions remain comparisons. The [source ledger](../data-sources.md) records access, formats, licenses and upstream rights limits. [Decision records](../DECISIONS.md)
- Confirmed a machine-readable box-score candidate covering the full pilot, the V3 final-period score comparison, and an offline two-game `pbpstats` path. Four native CDN requests returned 403 in this environment. Loading V2 events alone worked, and the possession parser required team shot-chart inputs. Both sample games parsed once those were supplied using the matching archive. [Audit methods and results](../research/nba-source-validation.md)
- Measured game-level defensive matchup coverage for all six EPM tracking training seasons. The largest gap was 92 regular-season games in 2019–20. The checks address observed rows and game presence. Coverage within games and other defense metric families still need investigation.

## Verification

| Check | Observed result |
| --- | --- |
| Public archive and box-score files | Verified six Bentes downloads against published SHA-256 and pinned Shufinskiy blobs against the Git tree. Computed local SHA-256 for the two team/player log files. Kept source rows outside the repository. |
| Python 3.12, DuckDB 2.0.1, `tarfile` and `csv.DictReader` | Profiled game sets, event fields, terminal scores, lineup tokens, duration and possession totals, box-score aggregates, and matchup coverage. The audit records the relevant keys, denominators and exceptions. |
| `pbpstats` 1.3.11 with HTTP disabled | Parsed one regular-season game and one playoff game using V2 events and shot charts. Both five-player lineup shape checks passed. Full lineup accuracy and parser coverage remain pilot questions. |
| `pytest -q`, `ruff check .`, `ruff format --check .`, `mypy src`, `git diff --check` and internal Markdown links | Passed locally, including one existing smoke test. [GitHub Actions on the reviewed commits](https://github.com/andrewcukierwar/basketball-intelligence-lab/actions/runs/45178892294) |
| Independent review of `7d4090b` and `22e8254` | Reproduced key source and tracking counts, archived parser smoke tests, box-score snapshot hashes, and reconciliation metrics. No blockers. |

## Next work

- [Issue #3](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/3) can use the observed V2 identity fields, exact duplicate events, score order, game-type boundaries and missing availability timestamps to ground the canonical contracts.
- [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) owns intended-use permissions, snapshot retention, full official box reconciliation, lineup and possession validation, and exception handling. Any wider use of the NBA-derived data needs permission evidence. The audit did not acquire commercial benchmarks or fit models.
