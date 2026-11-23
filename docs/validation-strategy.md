# Research Validation Strategy

## Separate questions

1. **Implementation correctness:** Is the code mathematically correct? Synthetic data, unit tests, invariants, solver equivalence.
2. **Methodological fidelity:** Did we implement the published idea faithfully? Evidence register and documented assumptions.
3. **External rating agreement:** Are the resulting numbers like EPM, if benchmarking is permitted? Diagnostic only; never a training or tuning objective.
4. **Predictive validity:** Do ratings and skill estimates forecast genuinely unseen outcomes?
5. **Operational integrity:** Could a historical or daily result be reproduced, with correct cutoff and data versions?

## Required test tiers

- **Unit:** Feature denominators, signs, timestamp cutoffs, shrinkage, recency weights, lineup matrix indices and statistical identities.
- **Property/synthetic:** Create toy leagues with known offensive/defensive effects; recover coefficients to tolerance, including collinear and low-sample cases.
- **Integration:** Possession reconstruction with substitutions, technical fouls, end periods, overtime, ambiguous free throws and known feed inconsistencies.
- **Reconciliation:** Official score and team totals; player minutes and plus-minus; missing/invalid lineup rate; source-to-source differences.
- **Model evaluation:** Frozen split manifests; baseline comparison; off-by-one time leakage tests; ablation tests; reproducible runs.

## Chronological protocols

- **Retrospective fit:** Uses data available at model-building time; can analyze past players, but not labeled a live historical forecast.
- **Rolling-origin backtest:** Re-estimate only from past data at each cutoff. Hyperparameters chosen in earlier inner validation windows.
- **Prospective paper trail:** Freeze predictions before game results. Record cutoff, feature availability and minutes model.

Do not randomly split possessions from the same game across train and test and call it independent. Account for repeated players, games, teams and dates.

## Baselines

For skill forecasts: career average, season average, rolling weighted average and simple empirical Bayes.

For impact: zero-prior RAPM, SPM alone, prior-informed RAPM, alternative decay choices.

For team/game: opponent-adjusted net ratings and simple schedule-aware models. Use predicted minutes in true pregame forecasts; if using future observed minutes, label as an oracle-minutes isolation experiment.

## Primary metrics

- Skills: appropriate future-outcome likelihood, binomial/log loss where relevant, count/rate errors with opportunity-weighting and calibration.
- Player impact: holdout on-court likelihood/error, temporal stability, ranking reliability, offense/defense slices and model ablations.
- Team/game: scoring margin MAE/RMSE, win accuracy, probability log loss/Brier, calibration and matchup/season slices.
- External EPM (permission-dependent): Pearson/Spearman, mean signed error, offense/defense/total MAE/RMSE, top-N overlap, role/age/minutes residuals.

## Evidence quality gates

Record per-experiment data checksums, train/validation/test ranges, model config, code SHA, seed, run ID and exclusions. Confidence intervals, uncertainty or repeated temporal folds are preferred over ranking models by tiny single-split differences.

The first production-quality model may be less numerically similar to EPM than an output imitator; methodology correctness and independent validation take priority.