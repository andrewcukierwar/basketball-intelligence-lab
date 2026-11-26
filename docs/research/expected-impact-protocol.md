# Expected impact v1: prior-centered walk-forward RAPM on inner development folds

**Registration:** [#35](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/35), committed before any real-data fit. **Classification:**
- Original BIL design and Experimental evidence under [ADR-0026](../DECISIONS.md#adr-0026--maintainer-decisions-of-2026-11-24-m2-acceptance-informed-rapm-comparators-and-partial-history-spm-targets) and ADR-0030.
- Every artifact carries `partial-history methodology replication` and `retrospective_capture_bound`.
- EPM combines an SPM prior with prior-informed, decayed RAPM (**Documented**). The window, weights, penalties, prior inputs and refit schedule below are BIL choices (**Original**).
- No EPM output is read.

The estimand is a dated offensive and defensive rating per player in points per 100 possessions. Positive defense means points prevented. Each rating is split into an SPM prior and an on-court residual.

## 1. Scope and inputs

- **Seasons read:** canonical rows (`issue-93-v1`, M2's `SEASON_PINS`) for 2019–20 through 2022–23. NBA.com box logs (#30's `LOG_PINS`) for 2020–21 through 2022–23.
- **Not read:** 2023–24 or later rows or logs. The 2025–26 holdout stays reserved. Outer-fold use belongs to #36 under its own registration.
- **SPM fits:** the private #30 run `data/processed/spm/issue-30-v2`, manifest SHA-256 `376d89ceb41ca8b90b1e36b3c6a6ad5d9ea09c32acd4e78114c16ec73f96786d`. Verify the manifest-listed digest of every file used.
- **SPM fit per season:**
  - 2021–22 uses the `full` candidate of `contiguous-2021/fit.json`, origin `contiguous@2021-07-21`.
  - 2022–23 uses `contiguous-2022/fit.json`, origin `contiguous@2022-06-17`.
  - The final development snapshot (§4) uses `final_contiguous_fit.json`, origin `contiguous@2023-06-13`.
  - These are #30's out-of-fold chronological fits. No fit is retrained here.
- **SPM inputs:** #120 §5's dated prior-only box snapshot. It pools positive-minute appearances from the immediately preceding calendar season and from the current season with official played date `< C`, across regular season and playoffs.
- **Cold fallback:** a player with no such appearance gets the fit's side intercepts. Older seasons do not roll forward.
- **Estimated Skills are not an SPM input in v1 (ADR-0030):**
  - The #32 skill-decay fit used 2022–23 outcomes, so it is ineligible at every inner cutoff.
  - The SPM was trained on raw season box rates.
  - The skill-input path is marked **unavailable** for inner folds and becomes a follow-up.

## 2. Model at a cutoff `C`

Weights and rows follow ADR-0025's `W2`: rows played 1 to 730 days before `C` (`played_date < C`), with unit weight and no renormalization.

1. **Context.** Fit M2's `home_score_time` context-only regression on the window rows (`fit_context`). Columns that are zero in every row get coefficient 0. Its contribution is `Zγ`.
2. **Prior.** Compute the SPM snapshot `m = (m_O, m_D)` as of `C` for every player in the loaded design. Each row's prior offset is `o = Σ_offense m_O − Σ_defense m_D`.
3. **Residual RAPM.** Fit M2's two-penalty zero-prior ridge (`fit_players`, the verified LSQR reference) to `y − Zγ − o` on the window rows with penalties `(λ_O, λ_D)`. The fit has a free intercept `b` and deviations `δ`. Players absent from the window keep `δ = 0`.
4. **Rating.** Rating = `m + δ` per side, and total = offense + defense. Score predictions are `b + Zγ + o + X·δ`.

This equals prior-centered ridge `λ_O‖o − m_O‖² + λ_D‖d − m_D‖²` with a context offset (#61). Any uniform prior shift is absorbed by `b`.

## 3. Refit schedule, selection and comparators

- **Blocks.** Use M2's `season_blocks` for 2021–22 and 2022–23: R1–R4 at 1 October, 1 December, 1 February and 1 April, then P at the first playoff date. Each block fits at its cutoff and scores its whole games.
- **Selection.** Use the pooled possession MSE in (points per 100)² over the eight regular-season blocks. Search with M2's `search_penalties` procedure: the shared grid {1,000 … 32,000} with edge extension, then defense, then offense line search. The two P blocks are scored after selection and never choose anything. Selection scores are optimistic because the same folds choose and score.
- **Comparators.** Each uses the `W2` window and is scored on the same blocks.
  - League mean, context-only, zero-prior RAPM and RAPM plus context offset. The two RAPM comparators use ADR-0025's fixed 4,000/8,000.
  - SPM-only: `b' + Zγ + o`, where `b'` is the window mean of `y − Zγ − o`. This is the prior with no on-court update.
  - EI at the selected penalties with the offense-only and defense-only deviations. These are descriptive part ablations.
- **Uncertainty.** Paired MSE deltas, EI minus each comparator, use M2's `paired_delta` with game-clustered and Monday-start calendar-week-clustered bootstraps (M2's resamples and seed). Regular season and playoffs are reported separately and never pooled.
- **Slices.** Report each block, each season, and the `no_livedata` versus liveData strata.

**Interpretation.** These inner-fold results are development evidence for #35's configuration. Independent validity is #36's outer-fold question.

## 4. Ratings artifacts and eligibility

- **Ratings per cutoff.** For every block cutoff, and for a final development snapshot at `C = 2023-07-01`, write private ratings for every player in the design or the box snapshot. Each row has:
  - `player_id`, `as_of`;
  - prior, deviation and rating for each side, and total;
  - unweighted window exposure;
  - prior-fallback and box-history flags;
  - the SPM fit ID and origin;
  - `(λ_O, λ_D)` and the `W2` window bounds.
- **Final snapshot.** It uses the selected penalties.
- **Eligibility audit.** At each cutoff, the runner checks and records that:
  - every window row, every box row used and the SPM origin cutoff are strictly before `C`;
  - context and RAPM use the same window rows;
  - no scored game is in its own fit window.
  Any violation raises.

## 5. Reproducibility and stopping

- **Run conditions.** A committed, unmodified protocol with this file's SHA-256, a clean tree and a new output directory.
- **Recorded:** input digests, package versions, per-fit solver diagnostics, the penalty search trace, runtime and peak memory.
- **Order of writes.** Frozen predictions are written before scores are joined.
- **Synthetic tests:**
  - prior-centered equivalence against #61's verified `fit_prior_rapm`;
  - rookie or no-history fallback;
  - all-zero context columns;
  - revising or poisoning rows or box logs on or after `C` leaves ratings at `C` byte-identical;
  - changing an earlier input changes the fit ID.
- **Results.** Preserve every result, whatever its direction. Any methodological change requires a registered revision before refitting.
- **Freeze for #36.** The results freeze the selected `(λ_O, λ_D)`, the `W2` window, the refit schedule and the SPM-fit policy as the configuration #36 registers for outer validation. For the outer seasons, that policy is a locked pre-window fit: `final_contiguous_fit.json`, cutoff 2023-06-13.
