# Basketball Intelligence Lab

**Reconstruct frontier NBA analytics. Benchmark them honestly. Build better basketball intelligence.**

Basketball Intelligence Lab (BIL) is an independent, research-first Python project for reproducible basketball player-impact estimation, statistical forecasting, and model comparison.

## Current focus: R1 — EPM methodology replication

Our first objective is to reproduce the published methodology behind Taylor Snarr's [Estimated Plus-Minus (EPM)](https://dunksandthrees.com/about/epm) as faithfully as possible:

1. Historical possession-level, offensive/defensive **regularized adjusted plus-minus (RAPM)**.
2. **Statistical Plus-Minus (SPM)** priors trained on independent multi-season RAPM.
3. **Estimated Skills** derived from dynamically weighted player histories.
4. **Prior-informed RAPM** combining player statistical priors with adjusted on-court evidence.
5. Time-correct evaluation, defensive tracking experiments, and documented fidelity analysis.

**We will not train a model using EPM ratings as labels.** Dunks & Threes ratings, where their use is permitted, serve only as independent external diagnostics—not a loss function, training target, or hyperparameter optimization objective.

The first milestone is a reliable historical NBA data foundation and a mathematically validated RAPM baseline. No production ratings have been implemented yet.

## Long-term research

| Program | Focus |
| --- | --- |
| **R1 EPM** | Methodology-first independent replication |
| **R2 Frontier models** | DARKO/DPM, LEBRON, BPM, and other relevant approaches |
| **R3 Comparison** | Common datasets, temporal benchmarks and ablations |
| **R4 Original model** | Dynamic player talent, context, interactions, uncertainty |
| **R5 Platform** | Daily player/team intelligence, forecasts, simulations, explainable analytics |

## Documentation

- [Full project plan](docs/PROJECT_PLAN.md)
- [Initial issue backlog](docs/INITIAL_BACKLOG.md)
- [Architecture](docs/architecture.md)
- [EPM methodology evidence](docs/research/epm-methodology.md)
- [Methodology uncertainty register](docs/research/epm-uncertainties.md)
- [Data-source audit](docs/data-sources.md)
- [Validation strategy](docs/validation-strategy.md)
- [Research decisions](docs/DECISIONS.md)
- [Experiment log](docs/experiment-log.md)

## Development setup

The repository begins as a lightweight Python research scaffold; modeling and ingestion dependencies will be added based on verified requirements.

Requirements: Python 3.11+ (CI uses 3.12). Recommended: [uv](https://docs.astral.sh/uv/).

    uv sync --extra dev
    uv run pytest
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src

The uv lockfile should be generated and committed when the first dependency resolution is performed.

## Research standards

- Label methodological claims as **documented**, **inferred**, **experimental**, or **original**.
- Preserve source data and historical cutoff provenance; never leak future information into forecasts.
- Evaluate independently against future basketball outcomes—not only existing metrics.
- Record code commits, data versions, configurations, metrics and negative experiments.
- Prefer free data while honoring source terms, licensing and redistribution constraints.
- Keep any proprietary benchmarks separate from published datasets and trained models.

## Status

**M0 — Research foundation (in progress).** See [project milestones](docs/PROJECT_PLAN.md#9-project-management). Contributions should be small, tested and accompanied by methodological evidence.

This is an independent research project and is not affiliated with Dunks & Threes, DARKO, BBall Index or the NBA.