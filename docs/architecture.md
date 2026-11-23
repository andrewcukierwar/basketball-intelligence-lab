# Technical Architecture

**Status:** Proposed; no live modeling pipeline yet. **Scope:** local-first, auditable, modular NBA research.

## Design goals
- Independent reproducible implementations of RAPM, SPM, Estimated Skills, EPM-style integration and later DARKO/LEBRON.
- Shared canonical data, as-of timestamp semantics and evaluation contracts.
- Sparse, memory-efficient algorithms suitable for development on 16GB Apple Silicon.
- Clear separation between documented reference replication and experimental models.

## Logical pipeline

1. **Raw inputs:** Immutable play-by-play, substitution, lineup, box-score, roster, tracking and game metadata. Record source URL, retrieval/availability time, checksum, season and usage notes.
2. **Canonical datasets:** Stable player/team/game IDs; games, events, possessions and lineup stints with validated scores/participants.
3. **Feature snapshots:** Per-game and career skill history; statistical rates and exposures; tracking coverage; strict as-of cutoffs.
4. **Reference estimators:** Independent RAPM; RAPM-trained SPM; skill forecasts; EPM-style prior-informed RAPM.
5. **Research evaluation:** Rolling-origin forecasts, baseline comparisons, ablations, stability and calibration; isolated permitted external benchmarks.
6. **Publication/production (later):** Versioned daily player/team outputs and monitoring.

## Canonical data and evaluation

The [canonical data contracts](data-contracts.md) specify identities, revisions, as-of availability and schemas for source artifacts, games, events, possessions, stints, observations and feature snapshots. The stream revision ties a game's event order, lineups and scoring allocations together.

The [rolling-origin evaluation and run-manifest issue](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/4) owns forecast origins, training and evaluation partitions, model outputs and run metadata. The [validation strategy](validation-strategy.md) describes the overall evaluation approach.

## Repository boundaries

- src/bil/data — ingestion, schemas, reconciliation and provenance.
- src/bil/features — time-correct skill features and context.
- src/bil/models/rapm — standalone RAPM.
- src/bil/models/epm — SPM, Estimated Skills and integration (later).
- src/bil/models/darko and lebron — independent future reference replications.
- src/bil/evaluation — shared backtests/metrics and baseline evaluation.
- src/bil/experiments — auditable research runs.
- src/bil/pipelines — incremental orchestrations (later).

Avoid coupling ingestion code to any one model. No model may read a future value merely because it exists in a current data table.

## Technology decisions

Python with uv; Parquet as primary immutable/intermediate format, DuckDB and Polars for analysis, NumPy/SciPy/scikit-learn for classical estimation. Add heavier libraries only when needed. Unit/contract tests via pytest; static checks via Ruff and mypy. Use GitHub Actions for fast tests only (not large data jobs).

## Operational guardrails

Raw and restricted data, credentials, cached API results, model binaries and large reports stay out of Git. Data manifests are committed. Pin dependencies using uv.lock once generated. Freeze run metadata and preserve prior published outputs when later data corrections occur.

Do not claim the local Mac mini can run a complete 25-year daily historical rebuild until representative sparse-RAPM, memory and runtime benchmarks have been measured.

## Architectural decision process

Before major changes, add a short decision entry to DECISIONS.md documenting motivation, alternatives, research implication and validation evidence. Reference models must never silently inherit experimental innovations.
