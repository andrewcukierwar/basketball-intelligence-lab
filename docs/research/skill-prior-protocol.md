# As-of Estimated Skills as the SPM prior input: registered protocol (#125)

- **Issue:** [#125](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/125), with Astra audit finding A3.
- **Status:** Registered before any scored run of `bil.models.expected_impact_skills`. The registration is the commit that adds this file.
  - **Pre-registration check.** One plumbing check ran on block `2021-R1`, using reduced Differential Evolution settings. It confirmed that the v1 raw-prior refit reproduces the published #35 EI predictions (maximum gap 0.0), and it counted prior coverage.
  - **Nothing scored.** No error, delta or interval was computed.
- **Evidence class:** **Original**, covering the chronological Skills bundle, the consumer checks and the matched design. Results are **Experimental** development evidence.
  - **Seasons.** 2021–22 and 2022–23 are the #35 development seasons. 2023–24 and 2024–25 were already examined by #36.
  - **Exclusions.** No 2025–26 data is read. Nothing is fit or compared with EPM.
- **Unchanged:** #32, #33, #35, #36, #39 and #42 and their artifacts.

## 1. Question

EPM's documented chain is Estimated Skills → SPM prior → prior-informed RAPM. #35 v1 skipped the first link (ADR-0030). It applied the #30 SPM to raw dated box rates: the preceding calendar season plus the current season before the cutoff.

This protocol asks one question. With everything else in v1 held fixed, does applying the same SPM to chronologically fitted, as-of skill estimates change on-court prediction?

## 2. Chronological Skills bundles

`bil.features.skill_bundle` fits one bundle per scoring season `S` ∈ {2021, 2022, 2023, 2024}.

**Model.** The #32 model and frozen Differential Evolution settings (ADR-0018) apply unchanged:

- exponential decay on one of three clocks (day, games, possessions);
- league shrinkage strength `k`;
- the #31 target engine on a stream that pools playoffs with the regular season.

**Fit stream.** The fit stream is the pinned box logs of seasons `S-3`, `S-2` and `S-1`. These are the `spm_build.LOG_PINS` snapshots for 2018–19 to 2022–23 and the #36 addendum pins for 2023–24. All three seasons must be present.

**Clock choice.** For each of the 13 #62 statistics and each clock:

1. Fit on regular-season targets of `S-2`.
2. Score the mean loss on regular-season targets of `S-1`.
3. The clock with the lowest validation loss wins. Ties go to the earlier clock in (day, games, possessions).

**Final fit.** Refit the chosen clock on regular-season targets of `S-2` and `S-1`.

**Seeds.** `125000 + 1000 × (S mod 100) + 100 × stat_index + 10 × clock_index + stage`. Stage 0 is the inner fit and stage 1 is the final fit.

**Lineage.** Each bundle records the following:

- version `skills-bundle-issue-125-v1`;
- the scoring season, history seasons and validation season;
- `outcomes_through`, the last appearance date in the fit stream;
- `fit_cutoff`, the day after `outcomes_through`;
- the order-independent digest of the fit stream (`source_view`);
- per-statistic parameters and clock-selection losses;
- every fit's seed, objective, evaluations and bound hits;
- a `fit_id` that hashes the version, season, source view, outcomes date and parameters.

Every bundle's `fit_cutoff` falls in July of `S`. The first EI cutoff of `S` is 1 October, and the 2020–21 playoffs ended in July 2021. Label maturity therefore holds by dates.

**Consumer boundary.** `check_bundle(bundle, origin, S)` refuses a bundle in five cases:

- the bundle has another version;
- it serves another scoring season;
- its fit cutoff does not follow its outcomes;
- its fit cutoff follows the origin;
- its `fit_id` does not reproduce its recorded contents.

`bundle_values` and the SPM consumer `skill_prepared` both call it. `bundle_values` builds the as-of snapshot as follows:

- **Input rows.** It uses the #33 `skill_snapshot` function on appearances from seasons `S-3` to `S` dated strictly before the cutoff, so a later game cannot move an earlier feature.
- **Players without history.** A player with no such appearance gets NaN inputs. The SPM maps NaN inputs to its intercepts, which is the v1 cold prior.

Tests cover the following:

- a bundle whose fit read outcomes up to the origin is refused, with identical pre-origin rows;
- the bundle is unchanged when scoring-season games are dropped;
- a snapshot is unchanged when later games are added;
- tampered, misdated and wrong-season bundles are refused;
- the skill estimate with no decay and no shrinkage equals the v1 raw rate, so the SPM receives inputs in its own units.

**Context.** The #33 context model is not used. Skills enter only as game-agnostic snapshots, so the stacked-context acceptance criterion does not apply.

**League reference.** The #31 engine shrinks each fit target toward the within-season league rate to date. The snapshot shrinks toward the pooled league rate of all stream appearances before the cutoff, which is the `skill_snapshot` convention. The two references agree within a season but differ across seasons. This is a limit (§7), not a tuned choice.

## 3. SPM: applied, not retrained

The #30 SPM is **applied** to the skill snapshot. It is not retrained on as-of skill inputs.

- **Development seasons.** These use the per-season `contiguous-2021` and `contiguous-2022` fits that #35 used.
- **Outer seasons.** These use `final_contiguous_fit.json`, pinned by the #36 addendum.
- **Unchanged.** The coefficients, imputation and scaling are unchanged.

Retraining would need new chronological SPM calibration rows built from as-of skills at each #28 target cutoff. That is a separate registration. Applying the fits isolates the input change and keeps the comparison matched. Shrunk inputs have smaller spread than raw rates, so the applied prior is expected to be compressed. The run reports the standard deviation of priors and their correlation with the v1 priors for players with both histories.

## 4. Expected impact

Everything except the prior input is #35 v1:

- **Model.** `W2` window, context offset fitted on the same rows, and the two-penalty residual ridge.
- **Penalties.** Offense and defense penalties are fixed at 8,000 each. This is the #35 selection, used unchanged in both fold groups. It was chosen on the development blocks with the raw prior, and the comparison does not reselect it.
- **Development blocks.** #35 R1–R4 and P blocks in 2021–22 and 2022–23, scored on the #35 row sets.
- **Outer blocks.** #36 blocks in 2023–24 and 2024–25, scored on the #36 row sets.

Every block refits both variants on identical rows:

- **`ei`.** Skills prior.
- **`ei_raw`.** v1 raw prior.

**Reproduction gate.** The `ei_raw` predictions must reproduce the published `issue-35-v1` and `issue-36-v1` EI predictions to 1e-6 on the same scored rows, or the run stops.

## 5. Comparisons and decision rule

Each block also predicts the following:

| Prediction | Role |
| --- | --- |
| `ei_offense_only`, `ei_defense_only` | Skills EI with one side's deviation zeroed |
| `spm_only`, `spm_only_raw` | Context plus each prior with the window mean residual, no on-court update |
| `ei_zero_prior` | `rapm_context` at 8,000/8,000. This is the matched zero-prior comparator |
| `rapm`, `rapm_context` | Zero-prior RAPM and context RAPM at 4,000/8,000, `W2` (ADR-0026) |
| `league`, `context` | The window mean and context-only model. Development seasons use `W2` as in #35. Outer seasons use `W1` as in the #36 addendum |

**Metrics.** Scoring follows #35/#36: possession MSE and paired deltas `ei − comparator`, with game- and week-cluster bootstrap intervals. These are pooled by role and fold group, by season and by block.

**Coverage slices** for the scored lineups:

- all ten players with at least 1,000 window possessions, or not;
- all ten with skill history, or any skill-cold player;
- all ten with raw history, or any raw-cold player.

**Primary contrast.** `ei − ei_raw` on the **outer** pooled regular season, under the #36 rule:

- **`skills_better`.** The game interval lies below 0 and the delta is negative in both outer seasons.
- **`skills_worse`.** The mirror case.
- **`inconclusive`.** Anything else.

The same rule labels every other comparator. Development-fold verdicts are descriptive, because the penalties were chosen there with the raw prior.

**Decision.**

- **`skills_better`.** The Skills chain becomes the candidate prior input for a later EI v2. Adopting it, and any downstream rerun such as #39, #42 or #43, needs its own registration.
- **Otherwise.** The published raw-box baseline is retained and the negative or inconclusive result is reported.
- **Unavailable support.** Any block without an eligible bundle would be reported as unavailable. None is expected, since all four bundles have full three-season history.

## 6. Outputs and reproducibility

Private outputs go to a new directory under `data/processed/expected_impact/`:

- `results.json`, containing the bundles with their full lineage, per-block eligibility audits, fold results, verdicts and the reproduction gaps;
- the per-fold `predictions_*.npz` files;
- `fit_log.json`;
- a manifest recording the protocol digest, code commit, clean-tree flag, row-set, box-log and SPM inputs, package versions, runtime and peak memory.

The run happens once, from a clean tree at a committed revision.

## 7. Limits

- **Inputs and SPM.** The SPM was trained on full-season raw rates. It is applied unchanged to shrunk as-of estimates, with no recalibration.
- **League references.** They differ between fit and snapshot (§2).
- **Penalties.** The penalties favor the raw prior on the development folds.
- **Irregular seasons.** 2019–20 (bubble) and 2020–21 (shortened) enter the 2021 and 2022 bundles. Their clocks and gaps are not modeled specially.
- **Outer seasons.** They were already examined by #36, so outer results are development evidence, not confirmatory.
- **Not covered.** Surrogate-target and team-level results (#137, #39-style) are not part of this run.
