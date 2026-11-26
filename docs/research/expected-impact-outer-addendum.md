# Expected impact v1: frozen outer-validation addendum (2023–24 and 2024–25)

**Status:** Frozen. Committed after the [#35 development run](expected-impact-v1.md) and before any code read a 2023–24 or 2024–25 row or box log for this model. **Issue:** [#36](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/36).

**Classification:**
- Original BIL design and Experimental evidence.
- Partial-history methodology replication, retrospective capture bound.

**Runner rules.** The runner (`python -m bil.models.expected_impact_outer`):
- refuses to start unless this file matches its SHA-256, is committed unchanged, and the tree is clean;
- checks the development manifest and protocol digests named below;
- reads every choice from the frozen block;
- runs once.

No outer result can change anything here. A rerun for any reason other than a crash before results are written is a deviation and is reported. The 2025–26 holdout is never read. The final snapshot at 2025-07-01 uses only rows and box lines dated before that day.

**Prior exposure of these seasons.** M2's [outer run](rapm-multiseason.md) already scored zero-prior RAPM, context and league on these seasons (ADR-0025). The EI penalties were chosen on the 2021–23 inner folds only. However, the decision to build on `W2` and M2's schedule was made with M2's outer results known. This evidence is therefore outer-fold development evidence, not confirmatory evidence.

## Frozen configuration

| Name | Role | Definition |
| --- | --- | --- |
| `ei` | **Model** | #35 v1. `W2` with the context offset fitted on the same rows. Residual ridge on `y − Zγ − prior offset` with λ_O = λ_D = 8,000. Rating = prior + deviation |
| SPM prior | Input | Locked pre-window fit `final_contiguous_fit.json` (origin `contiguous@2023-06-13`), applied unchanged in both outer seasons to #120 §5's dated prior-only box snapshots: preceding calendar season plus current season before the cutoff |
| `rapm_context` | **Primary comparator** (ADR-0026) | M2's frozen secondary model: `W2`, 4,000/8,000, `W2` context offset |
| `rapm` | Comparator | M2's frozen primary: zero-prior `W2`, 4,000/8,000 |
| `context`, `league` | Comparators | M2's frozen `W1` baselines. #35's development table used `W2` for these two, which is a definitional difference, not a re-tune |
| `ei_zero_prior` | Ablation | `rapm_context` at EI's 8,000/8,000. It isolates the prior at equal penalties |
| `spm_only` | Ablation | Context + prior, intercept = window mean residual, no on-court update |
| `ei_offense_only`, `ei_defense_only` | Ablations | EI with the other side's deviations zeroed |

<!-- frozen-config -->
```json
{
  "issue": 36,
  "outer_seasons": [2023, 2024],
  "dev_run": "data/processed/expected_impact/issue-35-v1",
  "dev_manifest_sha256": "db254b8c450034a0142255c40301e74cd6ddc59d505ab6d7aef983f846fce5d1",
  "dev_code_commit": "0b605c76",
  "protocol_sha256": "28869a50993ce93e598997b3dd56cce246c5a3915c1205cff30975ccaf64889d",
  "spm_fit": "final_contiguous_fit.json",
  "spm_fit_sha256": "1025774a8d327cbb25f6c284b49b9cbd80406e88a0406108a0877bf77b1edd90",
  "primary_comparator": "rapm_context",
  "models": {
    "ei": {"window": "W2", "offense_ridge": 8000.0, "defense_ridge": 8000.0},
    "ei_zero_prior": {"window": "W2", "offense_ridge": 8000.0, "defense_ridge": 8000.0},
    "rapm": {"window": "W2", "offense_ridge": 4000.0, "defense_ridge": 8000.0},
    "rapm_context": {"window": "W2", "offense_ridge": 4000.0, "defense_ridge": 8000.0},
    "league": {"window": "W1"},
    "context": {"window": "W1"}
  },
  "box_logs": {
    "2022": {"snapshot": "issue-5-v2", "sha256": "348eb8a072534659956082fd64cf3106c2d07092c87b5aca6f9d0ca056ae6611"},
    "2023": {"snapshot": "issue-52-v1", "sha256": "acf17139f5494cb38550530d345d167c8f58dc8e0cfc30966d0f63868cc9a57e"},
    "2024": {"snapshot": "issue-52-v1", "sha256": "e34398e754233203759f1e6ab8866dc6b61a11afcc3166b6ac9c099feca8b9bd"}
  }
}
```

The 2023 and 2024 box snapshot records were hashed, but their logs were not read, before this commit. Canonical rows are M2's `issue-93-v1` pins for 2021–22 through 2024–25.

## Update policy

- **Refits.** Walk-forward in each outer season with M2's blocks: R1 to R4 at 1 October, 1 December, 1 February and 1 April, and P at the first playoff date. Each fit uses every eligible row its window admits, including earlier 2023–24 games when fitting in 2024–25.
- **Box snapshots** update at every cutoff. SPM coefficients, penalties and windows stay frozen.
- **Unseen players.** A player absent from a fit window keeps deviation 0. A player with no box history gets the SPM intercepts.

## Metrics, uncertainty and verdict

- **Scores.** Possession MSE in (points per 100)², with paired deltas of EI minus each comparator. The intervals are game-clustered and calendar-week-clustered bootstraps (M2's 2,000 resamples, seed 2023). Report regular season and playoffs separately and never pool them. Report each outer season and both pooled.
- **Team-level.** Team-game RMSE in points of summed predictions (ADR-0026).
- **Slices:**
  - season;
  - `no_livedata` versus liveData;
  - lineups whose ten players all have at least 1,000 window possessions, versus lineups with any player below that;
  - lineups whose ten players all have box history, versus lineups with any prior fallback.
- **Stability.** The correlation and RMS change of total ratings between consecutive cutoffs, and year over year between 2023-10-01 and 2024-10-01. Both use players with at least 1,000 window possessions at both dates.
- **Verdict per comparator, regular season:**
  - `ei_better` requires a pooled delta below 0 with the game-clustered interval excluding 0, and a negative delta in both outer seasons.
  - `ei_worse` is the mirror image.
  - Anything else is `inconclusive`.
  The primary claim is the verdict against `rapm_context`. Playoff results are reported, not adjudicated.

## Freeze for release evaluation

Whatever the verdict, these frozen configurations are the reference set for the R1 confirmatory protocol of [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42): `ei`, the four ADR-0026 comparators and the ablations above. #42 registers that protocol separately before any 2025–26 access. Unsuccessful ablations are preserved.
