# Chronological margin-calibration lineage: registered protocol (#136)

- **Issue:** [#136](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/136), from Astra audit finding A2.
- **Status:** Registered before any run of `bil.models.calibration_lineage`. The registration is the commit that adds this file.
- **Evidence class:** **Original** (construction and lineage contract). The comparison in §5 is development evidence on seasons already examined by #36, #39 and #42.
- **Unchanged:** the #35 selection, the #39 calibration, and the #39 and #42 results are reproducible and are not revised.

## 1. Problem

#35 chose its penalty pair on all 2021–23 development blocks and exported snapshots at the starts of those blocks. #39 fit its margin calibrator on 2021–23 regular-season games scored with those snapshots, and #42 loaded that calibration. A later 2021–23 outcome could therefore change an earlier calibration example. In the audit fixture, an October 2021 rating moved by up to 50.59 points per 100.

## 2. Registered construction: post-freeze calibration

Of the three constructions #136 allows, this protocol registers **calibration examples collected after upstream selection froze**:

- **Not nested selection.** It would rerun the #35 search at every origin, and the first 2021 origin has no earlier block to select on.
- **Not a new fixed penalty.** A predeclared fixed penalty would need an independent prior choice, and none exists.

**Parents.** Each parent records the latest outcome date that any of its fits or selections read (`outcomes_through`, inclusive):

| Parent | Run (manifest) | Selection | Outcomes through |
| --- | --- | --- | --- |
| `ei:issue-36-v1` | #36 outer EI snapshots | #35 W2 penalties, offense 8000 and defense 8000. SPM origin `contiguous@2023-06-13` | 2023-06-30 |
| `ei:issue-35-v1` | #35 development snapshots | same | 2023-06-30 |
| `team_rating:issue-39-v1` | #39 daily ridge team rating | half-life 60, ridge 4, chosen on 2021–23 regular season | 2023-06-30 |

**Example eligibility.** A calibration fit with cutoff `F` may use an example only if all three conditions hold:

1. `parent.outcomes_through < snapshot_as_of`. The parent froze before the snapshot used for the game.
2. `snapshot_as_of <= game_day`.
3. `game_day < F`, so the label is final before the fit cutoff.

A forecast made at origin `O` may load the calibration only if `F <= O`.

**Recorded lineage.** Each example records its source (`ei` or `team_rating`), game, raw model input, realized margin, parent ID, snapshot date and ID, and source view, which is the digest of the file the raw input came from. The calibration records its construction, fit cutoff, the parent registrations it used, the per-source coefficients and support, and the SHA-256 of its sorted examples.

**Consumer boundary.** `load_calibration(directory, origin)` refuses the artifact in four cases:

- a recorded parent differs from its registration;
- an example fails conditions 1–3;
- the examples do not reproduce the recorded digest and coefficients;
- the fit cutoff follows the origin.

## 3. Consequence for the existing calibration

Every #39 calibration example is a 2021–23 game scored with an `ei:issue-35-v1` snapshot taken before 2023-06-30, so all of them fail condition 1. Under this construction, origins before the first post-freeze fit cutoff have **no eligible calibration**. Those origins are every 2021–23 development origin and the 2023–24 season. That is reported as unavailable support, not repaired.

## 4. Fit

The first eligible fit uses 2023–24 regular-season games with a home flag. Its cutoff is `F = 2024-07-01`.

- **Sources.** The EI examples use #36 snapshots and the team-rating examples use the #39 daily fit.
- **Models.** Each source gets the #39 model `margin = a + b · raw` with `σ` the in-sample RMS residual. The home-court baseline is the mean and standard deviation of the same games' margins.
- **Inputs.** Raw inputs are read from the frozen #39 `predictions.csv`, pinned by the #39 manifest. Each model's six-decimal calibrated margin is inverted through its frozen #39 calibration, giving recovery error below 1e-5. Realized margins come from the pinned 2023–24 team log of the #36 addendum.

## 5. Development comparison

The comparison scores 2024–25 regular-season games with the frozen #39 calibration and with the post-freeze calibration. The scoring uses the same raw inputs, metrics and game/week cluster bootstrap as #39.

- **Within each calibration:** EI minus team rating.
- **Across calibrations:** post-freeze minus frozen, for each source.

The comparison is descriptive development evidence with no adoption threshold. It measures how much the chronological construction changes the calibrated scores on already-examined data. It does not revise #39 or #42. No 2025–26 data is read.

## 6. Limits

- **Support.** One season of examples supports a two-parameter fit per source. Season-to-season drift in `a` (home advantage) and `b` is not modeled.
- **Upstream parents.** The construction makes calibration examples chronological. It does not make the upstream EI or team-rating parents chronological for 2021–23 origins.
- **Later use.** #129 and #43 should load calibrations through `load_calibration` and register their own fit cutoffs.
