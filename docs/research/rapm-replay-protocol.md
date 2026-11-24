# Reproducibility replay of the ADR-0025 multi-season RAPM configuration: protocol

**Status:** Frozen before the replay runs. **Classification:** Original BIL design (verification procedure), no new evidence about player quality. **Issue:** [#27](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/27), as required by [ADR-0026](../DECISIONS.md).

This replay re-runs the frozen [ADR-0025](../DECISIONS.md) configuration (`W2`: rows 1 to 730 days before the cutoff, unit weights, $\lambda_o$ = 4,000, $\lambda_d$ = 8,000) with the existing runner and compares the new artifacts with the originals from [#26](rapm-multiseason.md). **It is not model selection.** No other configuration is tried and the selection is not changed. No EPM value is read. The runner reads 2018–19 through 2024–25 only, as it did originally.

## What is run

1. Development phase from a clean tree on the replay branch: `python -m bil.models.rapm.multiseason dev PROCESSED data/processed/multiseason/issue-27-replay-dev-v1`. This reruns the whole eight-candidate selection, the baselines, stability and the four sensitivity scenarios, so it tests that the selection is reproducible, not only the fit.
2. Outer phase from the same clean tree: `... outer PROCESSED data/processed/multiseason/issue-27-replay-outer-v1 --addendum docs/research/rapm-multiseason-outer-addendum.md --addendum-sha256 23a9d3b764fcc319b7008ad74c796f8c395becdd7d5e1275f324bf6e8957420b --dev-manifest <manifest>`.
   - The outer runner refuses unless the supplied development manifest has the SHA-256 the addendum froze (`8cbb4e5e…536a`). A replayed manifest differs by construction (timestamp, runtime, code commit), so its digest can never match. The replay therefore passes the **original** `issue-26-dev-v1/manifest.json`, which is what the guard requires. No guard is changed or bypassed. The replayed development manifest is compared separately, below.
   - `PROCESSED` is the main checkout's `data/processed` by absolute path. All output directories are new.

## Compared items

Every comparison is original (`issue-26-*-v1`) against replay (`issue-27-replay-*-v1`).

| Group | Artifact and fields | Class |
| --- | --- | --- |
| Input lineage | Dev and outer `manifest.json` `inputs`: per season `row_manifest_sha256`, `pilot_manifest_sha256`, `row_set`, `row_set_build_id`, `pilot_build`, `row_set_digests`, `pilot_digests`, `coverage`; outer `outcomes` digests and scored possession counts | Exact |
| Row counts | Dev `results.json` `rows` (possessions, games, players, by season) and `blocks` (cutoff, games, possessions, role); outer `sets` and `per_block` possessions and games; `possessions_with_unseen_player` | Exact |
| Selected configuration | Dev `selected` and `manifest.selected` (temporal, window, penalties, baseline temporals); `scenarios.*.search.selected_temporal` and per-scenario selections; `infeasible` lists; outer `configuration` | Exact |
| Candidate MSEs | Dev `scenarios.*.per_temporal` for all eight candidates (pooled and per-block MSE, baselines, deltas and their 95% bootstrap intervals, penalty-search surface); `baselines` | Tolerance |
| Dev stability and sensitivity | `sensitivity_summary` (rank correlation, final-fit shifts, reduced-minus-full), `oracle_max_abs_diff`, effective scales, stability and volatility sections of the per-temporal entries | Tolerance |
| Outer-validation deltas | Outer `sets` (`comparisons`, `mse`, `calibration`, `team_game_rmse_points`, `mean_points_per_100`) and `per_block`, including all `*_minus_*` deltas with their bootstrap intervals; `refit_volatility` | Tolerance |
| Coefficients (dev) | `player_estimates.csv`: `player_id` set and order (exact), `on_court_possessions` (exact), `offense`, `defense`, `total` | Tolerance |
| Predictions (outer) | `predictions.npz`: key set, shapes, `game_id`, `possession_seq`, `y`, `unseen` (exact); every prediction array (tolerance) | Mixed |
| Fit diagnostics | `fit_log.json` in both phases: same entries in the same order; `label`, `scenario`, `temporal`, `cutoff`, ridge values, `rows`, `iterations` and `stop` (exact); `condition_estimate` and `scaled_residual_norm` (tolerance) | Mixed |
| Provenance | `manifest.versions`; `manifest.protocol` digest; addendum digest and commit; `dev_manifest_sha256`; `frozen_configuration` | Exact (`versions`: reported, see below) |

## Tolerances

- **Exact equality:** all strings, integers, booleans, nulls, lists of those, row counts, digests, cutoffs, labels, the selected configuration, solver iteration counts and stop codes, player ids and the player order.
- **Numerical tolerance for every other float:** pass when `|a − b| ≤ 1e-10 + 1e-8 · max(|a|, |b|)`. The relative 1e-8 covers coefficients, MSEs, deltas, correlations, calibration and the bootstrap bounds. The absolute floor of 1e-10 stops values that are zero up to rounding from failing on relative error. Two NaNs match. NaN against a number fails.
- **Expected numerical behaviour.** The solver is sparse LSQR with a fixed stop rule on a deterministic row order. The data, code and library versions are expected to be identical (original: Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1, DuckDB 2.0.1). I expect bit-identical results, and a deviation above about 1e-12 relative would already be a finding to explain, even though it passes at 1e-8.
- **Bootstrap.** The runner draws all resamples from `numpy.random.default_rng(2023)` (`BOOTSTRAP_SEED`, 2,000 resamples, game and week clusters), a fixed seed with a fixed clustering order, so the intervals are expected to be reproduced with the same tolerance as the point estimates, not statistically. No stochastic tolerance is granted. If an interval differs while every point estimate matches, that is reported as a bootstrap-ordering finding.
- **Reported, not pass/fail:** wall-clock and memory fields (`generated_at`, `runtime_seconds`, `peak_memory_mib`, `seconds`, `fit_seconds`, `_assemble_seconds`, and the solver-summary timings `median_fit_seconds` and `total_fit_seconds`), `code_commit` and the clean-tree flags (the replay's code commit is its own branch head), and the output file digests in `manifest.outputs`. `results.json` and `fit_log.json` embed timings, so their byte digests are expected to differ, so equality of the parsed contents is what counts. `manifest.versions` is compared and a difference is reported with its cause, because a library change is a legitimate explanation of a numerical deviation, but a version difference alone does not fail the replay.
- **Tolerances are not adjusted after seeing the result.** They are fixed in this file, committed before any replay run.

## Pass and fail

- **Per group:** pass when every compared leaf in it meets its class. One failed leaf fails the group.
- **Replay passes** when every group passes and both runs complete with all guards satisfied.
- **Replay fails** otherwise. A failure is not repaired by loosening a tolerance, rerunning with different settings or editing the original artifacts. The cause is investigated (nondeterminism, a change on `main` since #26, an environment change) and reported as a finding, which may be the result.
- **Structural differences** (a key, file, array or fit-log entry present on one side only) fail.
- The script `scripts/compare_rapm_runs.py` implements these rules and prints per-group results, the largest absolute and relative deviation per group and the location of the worst leaf. Its exit status is 0 only if every group passes.

## What the replay does not show

It checks that the code and the pinned inputs regenerate the recorded numbers. It does not validate the modeling choices, the row-set definition (ADR-0013, ADR-0019) or the comparators, and it does not test inputs rebuilt from raw source files. The row sets and pilot builds are reused as pinned by their manifests.

## Amendment (after the development comparison, before the outer comparison)

The first comparison run flagged `median_fit_seconds` and `total_fit_seconds` in the `solver` summary. Both are wall-clock timings, which this protocol already classes as reported, not pass/fail, but the script ignore list did not name them. They were added to the ignore list and to the list above. Only timing keys were added. No tolerance and no other key changed. Every other development group passed with zero deviation before and after the amendment.
