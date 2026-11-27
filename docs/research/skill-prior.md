# As-of Estimated Skills as the SPM prior input: results (#125)

- **Issue:** [#125](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/125). [Registered protocol](skill-prior-protocol.md), SHA-256 `3d3c6c1f…5873`.
- **Decision:** [ADR-0037](../DECISIONS.md#adr-0037--keep-the-raw-box-spm-input-chronological-skills-prior-is-inconclusive).
- **Evidence class:** **Experimental** development evidence.
  - 2021–23 are the #35 development seasons, and 2023–25 were already examined by #36.
  - Nothing here is fit or compared with EPM. No 2025–26 data was read.
- **Run:** `issue-125-v1`, from a clean worktree at commit `0582f7d`.
  - Runtime 464 s, of which 358 s was the four bundle fits. Peak memory 1.88 GiB.
  - Private outputs are under `data/processed/expected_impact/issue-125-v1`.

## Verdict

**Inconclusive. The raw-box SPM input is retained** (protocol §5).

On the outer pooled regular season, Skills-prior EI minus v1 raw-prior EI is **+0.38 [−0.52, +1.23]** possession MSE (game interval). The sign is positive, which favors the raw prior, in both outer seasons: +0.09 in 2023–24 and +0.67 in 2024–25. On the development seasons the difference is +0.09 [−0.54, +0.71].

The EPM-documented chain now runs end to end with chronological lineage, so the R1 Skills link exists. It does not improve on the raw-box prior when the #30 SPM is applied unchanged.

## Reproduction and eligibility

- **Reproduction gate.** The v1 raw-prior refit reproduced the published `issue-35-v1` and `issue-36-v1` EI predictions exactly (maximum gap 0.0 over 447,082 and 445,204 scored possessions).
- **Bundles.** All four were available:

| Season `S` | Fit seasons | Outcomes through | `fit_id` |
| --- | --- | --- | --- |
| 2021–22 | 2018–19 to 2020–21 | 2021-07-20 | `8dfa245f8ea16c05` |
| 2022–23 | 2019–20 to 2021–22 | 2022-06-16 | `5ded2d1d85c17423` |
| 2023–24 | 2020–21 to 2022–23 | 2023-06-12 | `efcce2605c3d629c` |
| 2024–25 | 2021–22 to 2023–24 | 2024-06-17 | `920be8426207cbba` |

- **Solver.** No final fit hit a bound or reported a solver failure.
- **Chosen clocks.** The games clock is chosen most often for per-36 volume statistics. Shooting percentages split across clocks.
- **Shrinkage.** It is stable across seasons: three-point percentage takes 154 to 286 attempts of league prior, two-point percentage 44 to 50, and free-throw percentage 18 to 26. These are close to the #32 single-season values.

## Results

Possession MSE is in squared points per 100 possessions. Each delta is `ei` (Skills prior) minus the comparator, with the 95% game-cluster interval.

| Comparator | Development regular, 2021–23 | Outer regular, 2023–25 | Outer verdict |
| --- | ---: | ---: | --- |
| `ei_raw` (v1, primary) | +0.09 [−0.54, +0.71] | **+0.38 [−0.52, +1.23]** | inconclusive |
| `ei_skills_recent` (ablation) | +0.04 [−0.15, +0.24] | −0.15 [−0.30, −0.01] | skills_better |
| `ei_zero_prior` (matched, 8,000/8,000) | −3.32 [−4.22, −2.51] | −6.04 [−6.96, −5.10] | skills_better |
| `rapm_context` (4,000/8,000) | −2.24 [−3.00, −1.48] | −4.22 [−5.00, −3.47] | skills_better |
| `rapm` (zero-prior, 4,000/8,000) | −31.15 | −37.76 | skills_better |
| `context` | −19.42 | −28.95 | skills_better |
| `league` | −48.01 | −61.15 | skills_better |
| `spm_only` minus `spm_only_raw` (no on-court update) | +0.93 | +2.37 | — |

The `spm_only` minus `spm_only_raw` row is not a contrast with `ei`. It is the difference between the two priors' MSEs without an on-court update.

**Playoffs.** Skills minus raw is −0.89 [−2.13, +0.37] on development playoffs and +0.15 [−0.97, +1.21] on outer playoffs.

**Week-cluster intervals** agree with the game intervals in every row above. For example, the outer primary is [−0.50, +1.25].

### Ablation: history length versus decay and shrinkage

The registered ablation feeds the SPM a Skills snapshot over the same seasons as v1 (`S-1` and `S`):

- **Against the full Skills prior.** Full Skills is better by 0.15 [0.01, 0.30] on the outer regular season. The longer history therefore helps a little.
- **Against the raw prior.** The recent-history Skills prior is about 0.53 worse in MSE, by subtracting the two deltas. This is **Inferred**: no interval was computed for that difference.

So the loss relative to v1 comes from feeding shrunk and decayed estimates to an SPM trained on raw full-season rates.

### Prior compression

At every cutoff, among players with both histories, the applied Skills prior is narrower than the raw-rate prior:

| Prior | Skills SD | Raw SD | Correlation with raw prior |
| --- | --- | --- | --- |
| Offense | 0.77 to 0.86 points per 100 | 1.38 to 1.71 | 0.59 to 0.74 |
| Defense | 0.28 to 0.30 points per 100 | 0.45 to 1.01 | 0.40 to 0.81 |

That is the compression anticipated in protocol §3 and §7. The SPM coefficients were fit on raw rates, so shrinking the inputs toward the league rate shrinks the prior roughly in proportion. The on-court ridge then has less prior signal to center on.

### Coverage

The Skills snapshot reads three earlier seasons, so it rates more players than the raw prior:

| Count | Values |
| --- | --- |
| Players with Skills but no raw history | 82 to 247 per cutoff |
| Players with raw but no Skills history | 0 |
| Outer regular-season possessions with all ten players Skills-rated | 359,994 |
| Same, with all ten raw-rated | 354,184 |

On lineups with any raw-cold player, Skills minus raw is −1.35 [−3.96, +1.24], which favors Skills but is inconclusive. On lineups where all ten have Skills history it is +0.72 [−0.16, +1.61].

## Interpretation

- **The chain works.** The Skills link is now chronological, versioned and enforced at both consumer boundaries. The link itself is reusable.
- **Applying the SPM unchanged does not help.** Skills are a reasonable SPM input only if the SPM is trained on them. A follow-up would register an SPM retrained on as-of Skills inputs at the #28 target cutoffs. That needs chronological calibration rows and is a separate registration. It is a likely way to recover the prior's spread.
- **The cold-start gain is small and uncertain.** The three-season history rates more players, and the slice of lineups with any raw-cold player leans in Skills' favor, but the interval includes zero.

## Limits

These are as registered:

- the SPM is applied unchanged to inputs from a different distribution;
- the league references differ between fit and snapshot;
- the penalties were selected with the raw prior;
- 2019–20 and 2020–21 are irregular seasons in the early bundles;
- the outer seasons were previously examined;
- surrogate-target and team-level outcomes (#137, #39) were not run.

Every label other than the primary contrast is exploratory and uncorrected for multiplicity.
