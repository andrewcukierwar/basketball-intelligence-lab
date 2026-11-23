# Basketball Intelligence Lab — Project Plan

**Version:** 0.1 (2026-11-22)  
**Status (2026-11-23):** M0 and the initial M1 exit gate are complete. The synthetic M2 reference is merged. The archived-feed pilot upgrade is awaiting integration.

**Initial research program:** R1 — Estimated Plus-Minus (EPM) methodology replication  
**Repository:** andrewcukierwar/basketball-intelligence-lab

## 1. Mission

Basketball Intelligence Lab (BIL) is an independent research and machine-learning project to reconstruct, audit, compare, and improve frontier basketball analytics methodologies.

**Working principle: Reproduce first. Understand second. Improve third.**

Our first goal is to reproduce the *methodology* of Taylor Snarr's Estimated Plus-Minus (EPM) as faithfully as publicly documented and feasible with primarily free NBA data. We aim to recreate the key mechanisms: possession-level RAPM, statistical plus-minus trained on long-term RAPM, dynamic Estimated Skills, and prior-informed RAPM. The objective is an independent, reproducible EPM-like model—not a supervised emulator of Dunks & Threes ratings.

Longer term, replicate DARKO/DPM, LEBRON, and other important approaches; establish uniform historical and prospective comparisons; design an original Basketball Intelligence model; and provide player, lineup, team, and game intelligence through a well-documented platform.

## 2. Non-negotiable research rules

1. **No EPM-label training.** Never train, fine-tune, calibrate, select features, or optimize hyperparameters to minimize errors against EPM outputs. Those outputs, when legitimately accessible for the intended use, can serve as *external diagnostics* only. Do not create a disguised EPM imitation model.
2. **Methodology provenance.** Label every decision **Documented**, **Inferred**, **Experimental**, or **Original**. Preserve exact sources, revision dates, and open questions.
3. **Keep reference replications separate from innovations.** An experiment that changes the methodology for higher accuracy must not silently change the EPM-reference baseline.
4. **Avoid temporal leakage.** Point-in-time forecasts use only information that would have been available at the timestamp, including model training state, features, availability information, and minutes projections.
5. **Measure validity independently.** Agreement with a proprietary metric is *not* evidence of predictive accuracy. Evaluate future player statistics, on-court outcomes, team margins, probability calibration, and stability separately.
6. **Reproducibility.** Record code revision, source snapshots, run configuration, time cutoffs, seeds, coefficients, exclusions, and results. Preserve negative experiments.
7. **Free-first data sourcing.** Prefer free, transparent sources; document usage rights and quality limitations. No redistribution of restricted data. Keep any later paid benchmark data segregated.
8. **No fabricated precision.** Never claim exact EPM fidelity when formulas, private features, or model parameters are unpublished.

## 3. Programs and milestones

| Program | Purpose | Planned milestones |
| --- | --- | --- |
| **R1 — EPM methodology replication** | Build, validate, and operate independent EPM-like impact ratings | M0–M8 |
| **R2 — Frontier replications** | DARKO/DPM, LEBRON, BPM, RAPM variants, selected other methodologies | M9–M10+ |
| **R3 — Comparative research** | Common datasets, point-in-time evaluation, cross-model ablations | M11 |
| **R4 — Original intelligence model** | Novel player and team talent, context, interactions and uncertainty | M12 |
| **R5 — Public intelligence platform** | Daily ratings, forecasts, research dashboards, explainability | M13 |

**Scope guardrail:** Until R1 has a sound RAPM baseline and data quality foundation, do not build a frontend, attempt sports-market optimization, or pursue sophisticated neural models.

## 4. R1 target: modern EPM methodology

Target the documented **2026–27 EPM architecture**, while noting that some published training periods reflect the historical components and some implementation details are proprietary.

### 4.1 RAPM foundation

Build offense/defense adjusted plus-minus from lineup/possession observations. Include proper player signs, contextual controls, regularization, home court, score effects, and multi-season history. Use sparse linear algebra; explore exact equivalence between possession and suitably aggregated stint representations.

A conceptual model is:

\[
\min_\beta (y-X\beta)^T W (y-X\beta)+\lambda\|\beta\|^2
\]

Explicitly define response scales, baseline/identification, defensive sign, normalization, possession grouping, weighting, and garbage-time handling before making player comparisons.

### 4.2 Statistical Plus-Minus (SPM)

Estimate offensive and defensive impact priors from player statistics with **long-term independent RAPM as the training target**.

EPM documents box-score SPM training on 2003–04 through 2022–23 data and a defensive-tracking SPM trained using 2017–18 through 2022–23 data. Reconstruct suitable training panels, reliability weights, available feature families, and chronological validation. Begin with an interpretable linear model; test nonlinear alternatives as *explicitly experimental*, not as undocumented facts about EPM.

### 4.3 Estimated Skills

Forecast the player's underlying statistical skills rather than directly using noisy season-to-date box-score values. Implement statistic-specific historical shrinkage, exponential recency weighting, and Differential Evolution for optimizing decay parameters against subsequent statistical outcomes. Extend with aging, team/opponent strength, home/rest, seasonality, league trends and other documented context. Keep game-agnostic versus game-specific predictions distinct.

Evaluate every skill forecast against appropriate next-game losses and simple historical baselines.

### 4.4 Prior-informed RAPM

Generate the offensive/defensive SPM priors from Estimated Skills, then regularize career-weighted RAPM toward them.

A useful *conceptual* objective—not asserted to be the exact private EPM formulation—is:

\[
\hat\beta=\arg\min_\beta\left[(y-X\beta)^T W(y-X\beta)+(\beta-\mu)^T\Lambda(\beta-\mu)\right]
\]

Here \(\mu\) is the SPM prior and \(\Lambda\) controls regularization toward it. Support dated histories, age-of-observation weighting, and explicit calibration/centering conventions. Examine differences between statistical prior and on-court residual contributions.

### 4.5 Output families

- **Expected impact:** Daily, forward-looking offensive, defensive, and total points per 100 possessions, with data cutoff, model version, prior, and residual diagnostics.
- **Actual impact:** Season-specific retrospective evaluation with preseason prior and within-season evidence, treated as a separate later milestone.
- **Scope:** Expand toward all supported regular-season and playoff observations since 2001–02, preserving gaps and exclusions rather than masking them.

## 5. R1 execution phases

Each phase has a practical deliverable and **exit gate**. Exact calendar deadlines will be assigned after profiling the data.

### M0 — Research and repository foundation

- Establish Python package, testing, formatting, typing, CI and architecture documentation.
- Maintain source registry, data rights ledger, methodology evidence matrix, and unknowns register.
- Define source-independent schemas for game, player, team, play, possession, stint and as-of timestamps.
- Establish configuration/run identification, reproducibility conventions, and decision records.
- Review primary EPM documentation, capture uncertain features/weights/formulas, and identify testable hypotheses.

**Exit gate:** Repo tooling passes; a reviewable EPM technical specification and source/data audit exist. No model assumptions are presented as sourced facts.

### M1 — Historical NBA dataset

- Choose canonical raw historical feed(s); preserve immutable source snapshots and hashes.
- Start with one season (candidate 2022–23) before historical expansion.
- Reconstruct possessions and five-player on-court lineups; reconcile substitution edge cases and technical free throws.
- Resolve stable player IDs across sources, team changes and playoff games.
- Validate score reconciliation, minutes/plus-minus totals, on-court identities, duplicate events, and chronology against independent source(s).
- Build reproducible Parquet/DuckDB/Polars data pipeline and coverage report.

**Exit gate:** A training-ready one-season dataset passes documented invariants, reconciliation tolerances, coverage thresholds and exception reporting.

### M2 — Independent offensive/defensive RAPM

- Implement sparse design matrices and ridge estimators; benchmark against independent reference implementations.
- Add synthetic known-coefficient simulations, sensitivity checks, and solver-equivalence tests.
- Introduce home, score-state, temporal and regularization choices separately.
- Fit multi-season RAPM and test coefficient stability by sample/window.

**Exit gate:** Numerical correctness demonstrated on controlled cases; multi-season impact ratings and holdout reports reproducible.

### M3 — RAPM-trained Statistical Plus-Minus

- Construct long-term RAPM training targets with explicit exposure/reliability treatment.
- Define offensive, defensive and context feature families.
- Train separate offensive and defensive box-score priors.
- Use time-aware/out-of-fold prior construction to prevent leakage; report age/role/minutes slices.
- Compare interpretable baseline with experimental nonlinear choices.

**Exit gate:** A documented, independent SPM prior with holdout evaluation and ablations.

### M4 — Estimated Skills engine

- Generate player-game timelines, rate denominators, shrinkage and stat-specific recency.
- Fit decay/stabilization parameters using Differential Evolution and strictly future targets.
- Add aging and context, one controlled factor at a time.
- Build as-of-date predictions and next-game statistical backtests.

**Exit gate:** Reproducible skill forecasts evaluated against career, season, and simple recency baselines.

### M5 — EPM-style integration v1

- Combine predicted skills → SPM prior → prior-informed, decayed RAPM.
- Produce offense, defense, total impact and intermediate decomposition.
- Implement dated snapshots, sparse solvers, hyperparameter selection via chronological folds.
- Validate outputs and improve runtime within measured resource constraints.

**Exit gate:** Full end-to-end independent EPM-style results; all model choices documented; zero EPM-label training.

### M6 — Defensive tracking and difficult cases

- Audit historical public tracking coverage; integrate available defense/shot-contest/matchup/hustle features.
- Test tracking-informed SPM against box-only prior; analyze low-minute players, rookies, defensive specialists, missingness and season shifts.
- Record remaining gaps from EPM's private feature set.

**Exit gate:** Clear incremental impact and limitations documented—not assumed.

### M7 — Reproduction and external comparison

- Publish methodological evidence matrix, replication assumptions, full ablations, uncertainty, performance and data coverage.
- On appropriately permitted benchmark samples, compare EPM offense/defense/total ratings using Pearson/Spearman, MAE/RMSE, signed bias, top-N overlap and stratified residuals.
- Keep fidelity diagnostics separate from independent future-outcome validation and never fit to Dunks & Threes outputs.
- Clearly distinguish retroactively reconstructed ratings from genuine as-of-date model predictions.

**Exit gate:** Auditable EPM replication report and reproducible public research artifacts where permissions allow.

### M8 — Reliable daily pipeline

- Incremental ingestion, quality gates, stat/impact refresh, versioned historical snapshots, alerts, backups and recoverable scheduling.
- Measure runtime, memory, data freshness and model drift; avoid heavy rebuilds when unnecessary.
- Defer frontend until data and rating reliability are demonstrated.

**Exit gate:** Daily forecasts/ratings with correct cutoff times, rollback/recovery and monitoring.

## 6. Evaluation contracts

Establish a single framework usable by all future models.

**Fidelity to EPM (external only):** Pearson, Spearman, offense/defense/total MAE/RMSE, mean signed error, top-20 overlap, rank stability and segment-specific residuals; only if benchmark use is permitted.

**Independent validity:** Next-game stat predictive likelihood/error; held-out lineup/possession and future player-on-court performance; team margins with clearly documented minutes assumptions; eventual win probabilities and calibrated uncertainty.

**Historical experiment types:**
- *Retrospective reconstruction:* Model may have been trained with later historical data; cannot be called live-equivalent.
- *Rolling-origin backtest:* Refits and features respect each historical cutoff.
- *Prospective paper forecast:* Forecast snapshot frozen before result and reviewed after outcome.

Never leak realized minutes into a supposed pregame forecast. An *oracle-minutes* evaluation may be used only as an explicitly labeled diagnostic to isolate player-impact quality.

Track train/validation/untouched test boundaries, multiple testing, stability over time, and no-future-information checks. Benchmark against simple models before advanced techniques.

## 7. Technical design and compute

Default: Python (uv), Parquet, DuckDB, Polars, SciPy sparse linear algebra, scikit-learn/statsmodels, pytest, Ruff, mypy, GitHub Actions. Use XGBoost/LightGBM, Optuna, MLflow, API/frontend and scheduling only when a validated requirement appears.

Target local-first computation, including a 16-GB Apple Silicon Mac mini. Benchmark representative matrices, use chunking and sparse solvers, and avoid promising full-daily 25-season fits until measured.

Core module boundaries: data ingestion → canonical datasets → as-of skill features → independent SPM/RAPM implementations → EPM integration → evaluation → reporting → scheduled production.

Each run should contain: code commit, config hash, source data/version hashes, feature cutoffs, training/validation periods, seeds, model parameters, outputs, metrics and provenance.

## 8. Future programs

### R2 — Methodology replication

**DARKO / Daily Plus-Minus:** Reconstruct dynamically updated underlying skills, temporal/Bayesian filtering, career trajectories, and on-court-informed impact. Model the differences in aging assumptions, responsiveness and variance, as far as independently documented.

**LEBRON:** Reconstruct published luck-adjusted plus-minus and box-score-informed priors, including player archetype/role components where described. Analyze what luck adjustment and role-based priors change.

**Additional:** BPM, standard/multi-year RAPM, selected historical RPM/RAPTOR/PIPM concepts and other well-documented frontier models. Prioritize documented technical value and feasibility rather than brand recognition.

Every replication gets a written methodological specification, versioned code, strict point-in-time validity, independent outcome benchmarks and gaps report. Do not train one proprietary metric onto another.

### R3 — Comparative research

Use identical snapshots, split definitions and metrics to study where EPM, DARKO, LEBRON and simpler models agree and diverge. Investigate offensive vs defensive stability, player age/role, uncertainty, lineup interactions, tracking value, model responsiveness and transport to game forecasts.

### R4 — Original Basketball Intelligence model

Investigate an uncertainty-aware, dynamically updated framework for individual skill, offensive and defensive impact, player context, lineup complementarity, availability, coaching and game-level effects. Try hierarchical/Bayesian, state-space, tree, neural or graph-based methods only when a falsifiable hypothesis and proper baseline exist.

Promotion into the original model requires reproducible evidence of better generalization and/or calibration on untouched or prospective outcomes—not merely agreement with EPM.

### R5 — Product and applications

Potential outputs: public player-impact dashboards; skill histories and comparisons; lineup and trade scenarios; team-rating and minutes forecasts; game and season simulations; explainable model outputs; research reports; eventual sports-market predictive evaluation using timestamp-correct odds and realistic costs.

**No deployment of a market-optimized product until independent predictive validation and relevant data-use review.**

## 9. Project management

| Milestone | Deliverable |
| --- | --- |
| M0 | Research foundation |
| M1 | Validated historical data |
| M2 | RAPM baseline |
| M3 | SPM prior |
| M4 | Estimated Skills |
| M5 | Integrated EPM-style v1 |
| M6 | Tracking-enhanced replication |
| M7 | Fidelity and validity research release |
| M8 | Daily model |
| M9 | DARKO replication |
| M10 | LEBRON replication |
| M11 | Cross-model benchmark |
| M12 | Original Basketball Intelligence v1 |
| M13 | Public platform |

Initial engineering work should be small, reviewable PRs with hypothesis, evidence tag, test results, measured performance and documented assumptions. Maintain a decisions log and negative experiment log.

The [GitHub milestones][live-milestones] and [issues][live-issues] track execution. The [initial backlog](INITIAL_BACKLOG.md) retains the original planning IDs. As of the 2026-11-23 reconciliation, [#1–#6][closed-foundation] are closed. The 1,290-game pilot and its external verification are on `main`. The [1,292-game adjudication][pilot-adjudication] was merged into a feature branch. [Issue #19][pilot-merge] tracks bringing it to `main` and verifying the resulting build before constructing the historical RAPM input.

- Use GitHub’s **Blocked by** relationships for direct prerequisites. Start a task once those prerequisites are complete. If an issue closed without delivering its prerequisite, update the affected dependencies before starting that work.
- Apply one **complexity** label. Low is a bounded task with a straightforward verification path. Medium involves meaningful integration or multiple components. High carries substantial research, data or cross-component uncertainty.
- Apply one **state** label and update it as work moves from **not yet started** to **in progress**, **in review** or **done**. Dependency readiness is visible separately from progress.
- **Scope: optional** marks a tracked extension outside the core exit gate. **Scope: roadmap** marks a future-program deliverable that needs separate authorization. Decompose those deliverables further after the relevant feasibility review.

[live-milestones]: https://github.com/andrewcukierwar/basketball-intelligence-lab/milestones
[live-issues]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues
[closed-foundation]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues?q=is%3Aissue+is%3Aclosed+label%3A%22state%3A+done%22
[pilot-adjudication]: https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/17
[pilot-merge]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/19

## 10. Definition of success

**R1 minimum:** Independently reconstructed RAPM + SPM + Estimated Skills + informed-prior RAPM, with reproducible expected offense/defense/total estimates, historical cutoffs, data quality tests and predictive evaluation. No EPM-label training.

**R1 strong:** Broad historical coverage, defensive tracking, Actual EPM analogue, daily snapshots, meaningful external fidelity checks (if permitted), extensive ablations and published replication report.

**Long term:** Credible independent replications of EPM/DARKO/LEBRON; reproducible shared benchmarks; a demonstrably improved original model; a useful continuously updated basketball intelligence platform.

## 11. Primary references

- [Dunks & Threes: EPM methodology](https://dunksandthrees.com/about/epm)
- [Dunks & Threes: EPM](https://dunksandthrees.com/epm)
- [Dunks & Threes: metric comparison](https://dunksandthrees.com/blog/metric-comparison)
- [DARKO](https://www.darko.app/about)
- [LEBRON introduction](https://www.bball-index.com/lebron-introduction/)
- [Basketball-Reference BPM](https://www.basketball-reference.com/about/bpm2.html)
- [NBA Data (Ramiro Bentes)](https://github.com/ramirobentes/nba_data)
- [pbpstats](https://pbpstats.readthedocs.io/)
- [nba_api](https://github.com/swar/nba_api)
- [Engelmann RAPM](https://github.com/jerryengelmann/RAPM)
- [OpenRAPM](https://github.com/bbstats/openrapm)

**First implementation priority:** M0, then one-season validated data, then a correct RAPM baseline. Everything else follows from reliable evidence.
