# RAPM training targets for box-score SPM: protocol (issue #28)

**Status:** Frozen before any real-data target fit for [issue #28](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/28). **Classification:** Original BIL design under the maintainer decision of 2026-11-24 ([ADR-0026](../DECISIONS.md#adr-0026--maintainer-decisions-of-2026-11-24-m2-acceptance-informed-rapm-comparators-and-partial-history-spm-targets)). **Reserved records:** ADR-0027 (target specification, written with the results) and EXP-0017 (the single real-data run). Results go in `docs/research/rapm-targets.md`, written after the run. Any change to this document after the run starts is a deviation and is listed in that report.

**Every artifact of this issue is a _partial-history methodology replication_, not a full historical EPM replication.** EPM documents box-score SPM trained on independent RAPM over 2003–04 through 2022–23 ([EPM methodology](epm-methodology.md), Documented). BIL has 10 of those 20 seasons eligible, with a seven-season gap. The runner writes the label `partial-history methodology replication` into every output row, manifest and frozen-target record.

A target is a **retrospective label** for training SPM, not a forecast. It is specified separately from the [ADR-0025](../DECISIONS.md#adr-0025--two-season-unit-weight-window-with-split-penalties-for-the-multi-season-rapm-baseline) two-season predictive configuration: the objective, weighting, penalty choice and reliability analysis below are this issue's own, and nothing here changes ADR-0025.

## 1. What was looked at before freezing

No target, RAPM or SPM model was fitted on real data, and no outcome aggregate (points, rates or residuals) was computed or printed. The following were inspected:

- The row-set manifests of the ten authorized seasons and their SHA-256 values, their contract revision (`rapm-historical-rows-issue-82-v2`), variant (`canonical`) and pilot-manifest digests.
- From `model_row.parquet` and `game_reconciliation.parquet`: row and game counts by season type, date ranges, the `weight` column (1.0 everywhere), overtime row counts, accepted-game strata counts, distinct players, players with more than one team in a season, and player overlap between seasons.
- A loader smoke check through the runner's own loader (`multiseason.load_season` with the #28 pins): every pin, digest and timing audit passes; each season's calendar and the origin schedule below were computed. That check held outcomes in memory to build the context covariates and printed none of them.
- Synthetic data only, for the tests and for runtime of the code paths.

The earlier RAPM results were public before this protocol and informed it: [#23](rapm-baseline-2022-23.md), [#24](rapm-context-ablations-2022-23.md), [#26](rapm-multiseason.md) (offense carries most of the predictive signal; the defense penalty selected at twice the offense penalty; split-half reliability rises with window length and exposure) and the [M2 report](rapm-m2-report.md). No EPM output was read, and none will be.

## 2. Frozen inputs

Canonical row sets (ADR-0013, ADR-0019; contract `rapm-historical-rows-issue-82-v2`), pinned in `bil.models.rapm.targets.TARGET_PINS`. The loader hashes each `manifest.json` against the pin and the row and pilot tables against their manifests before reading a row (the #26 verification, reused).

| Season | Row set | Row-set `manifest.json` SHA-256 | Pilot build (context only) | Pilot `manifest.json` SHA-256 | Model rows | Accepted games (reg. / playoffs) | Verification group |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| 2005–06 | `issue-97-rows-v1` | `0cd0db16dbf6b7819eb5e88449bedccd9577204050b24ce6415429452b06e062` | `issue-97-v1` | `66d2904d79e43321b2a57fbef498f294c1ed3e7333dd7dd6c920ac1395cce8c5` | 205,754 | 1,220 / 88 | `no_livedata`, `no_datanba` |
| 2006–07 | `issue-97-rows-v1` | `4dcd6a00be96da4011f9e9aac56152ec043e15f8a16b3e8f18d58106c8686f5c` | `issue-97-v1` | `1cb82fe3160d9e722d4e86a8b3362c5a900f1f40da756adfe9ece61d4d67bce9` | 204,981 | 1,209 / 78 | `no_livedata`, `no_datanba` |
| 2007–08 | `issue-97-rows-v1` | `8aa10687f33efb950315eb11c11db2dbb50418882d9a86e5a39e43b727012c57` | `issue-97-v1` | `d2e4be9d6bdd53306126252fc527ecb0a88bb77f72175c31aed8a16490809769` | 209,831 | 1,214 / 86 | `no_livedata`, `no_datanba` |
| 2015–16 | `issue-98-rows-v1` | `4214ed84b842a7575848462847d2788867465ff7a09c505479c5cbcc64e29373` | `issue-98-v1` | `fa68579155d6689a36ad733c362caf552394e1bc5939e37b1dd2f84c0807fbea` | 215,087 | 1,208 / 85 | `no_livedata`, `no_datanba` |
| 2016–17 | `issue-96-rows-v1` | `eca05cb8515446a6a61f36685d621b3701b502f621f490bc1280614dac8d1bde` | `issue-96-v1` | `e96ba9042e6463566cd0666f1c4b88d89b07d2484908a4125b8860218ac2e9b2` | 215,884 | 1,209 / 79 | `no_livedata`, data.nba without `ord` |
| 2018–19 | `issue-93-v1` | `c0fa49896b96827ec9ff6864bbcf5d3ddb55e8b6079ed693f4a88ebd4b1e1df1` | `issue-25-v1` | `a5f52e4880666fb8eb887d82eecedf6cf7ebd1e6c5e5ba42e6fea25fdb43ce35` | 223,686 | 1,206 / 80 | `no_livedata` |
| 2019–20 | `issue-93-v1` | `f17dfd1bd9b39cdd022375656be2681cc119c65b5f66b97466f2992bbd6ed777` | `issue-25-v1` | `334daf0237f3f9669d76ca807929802426bf667ad68f0932ffdcdfd0a0a52ac6` | 195,128 | 1,041 / 82 | `no_livedata` |
| 2020–21 | `issue-93-v1` | `231f742dbf7aeeb02e99c5a4b1ff8c2c3eed5e5bfb484390d307ecf0d8c5e756` | `issue-25-v1` | `c3c75d43236a93070fd8fb3dd90200f572894af6aa5f5c05b8f38881ede72a11` | 200,256 | 1,072 / 85 | liveData |
| 2021–22 | `issue-93-v1` | `58fed85cce0822865e7b3bf369e55b5ba5a280f6a1347d19832381df383cc298` | `issue-25-v1` | `49bb4a91c71d2f255a17ba1c52a3ae6e5c2737f1a8c6716c0405980949947075` | 223,043 | 1,219 / 87 | liveData |
| 2022–23 | `issue-93-v1` | `2affb62a8d875963f05e5eb39e2e36d8e8fbab4df43840f1dc0062deb581a1ac` | `issue-19-v6` | `89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570` | 224,039 | 1,208 / 84 | liveData |

The ten seasons hold 2,117,689 rows from 12,640 accepted games. The row sets for the history seasons already existed from #96, #97 and #98, so no row set was built for this issue.

- **Guards.** The runner refuses any season outside the ten above: 2017–18 (excluded, ADR-0022), 2008–09 through 2014–15 and 2001–02 through 2004–05 (unavailable or not built), 2023–24 and 2024–25 (outer seasons, never read by #28) and every season from 2025–26 on (holdout, refused before a path is built). It asserts that every loaded row is played before 2023-07-01.
- **Strata checks.** The runner refuses a season whose accepted games carry the ADR-0023 `datanba_event_order` repair stratum (not approved for canonical use), or whose `no_livedata` and `no_datanba` counts disagree with the verification group in the table.
- **Lineage only.** Quarantined games are not rows. Their counts are carried into the manifest.

## 3. Estimand

For reference $R$, origin $O$, target season $s$ and player $p$, the **offensive label** $o_{p,s}$ and **defensive label** $d_{p,s}$ are the player's effects, in points per 100 possessions, in a season-centred, elapsed-time-weighted, ridge-regularized RAPM fit. The fit uses the rows of $R$ played strictly before $O$ and is adjusted for home court, pre-possession score state, game time and each season-and-season-type scoring level. Positive offense scores more; positive defense prevents points. The total is $o + d$.

The label describes the player's average on-court impact around season $s$, borrowing from neighbouring eligible seasons in proportion to the real time between them. It is defined for every player with at least one offensive and one defensive possession in season $s$. EPM's SPM target is "multi-season RAPM from the same seasons" (Documented); the season-centred weighting is an **Original** BIL choice, made because the eligible seasons span 18 years with a seven-season gap, and a single constant effect per player over that span would ignore aging and the time that elapsed.

**Why not ADR-0025.** ADR-0025 weights the 730 days *before* a cutoff to predict *later* possessions. A label needs the best description of season $s$, so it may use later eligible seasons as well (two-sided), and its penalty is chosen for in-window, not forward, accuracy.

## 4. Objective, weights and penalties

**Weights (the kernel).** Each row has base weight 1 (ADR-0013). For target season $s$ with first and last played dates $[f_s, l_s]$ among the eligible rows, a row of another season played on day $t$ has gap $g = \max(0, f_s - t, t - l_s)$ in calendar days. Its weight is

$$w = 1 \text{ in season } s, \qquad w = 0.5^{\,g/365} \text{ if } 0 < g \le 730, \qquad w = 0 \text{ otherwise.}$$

The kernel is named `K365`. A missing season therefore counts as the time that elapsed. 2007–08 rows reach no 2015–16 label (gap above seven years), and 2016–17 rows reach a 2018–19 label at 0.25 to 0.39 weight. A row of another season inside $[f_s, l_s]$ raises an error. Weights are not renormalized and penalties are not rescaled (ADR-0015). The half-life and cap are fixed here and are not tuned: 365 days gives the adjacent seasons about 0.5 to 0.8 weight and caps the reach at about two seasons on each side. The three nearest #26 candidates (`W2`, `H365`, `H730`) were a predictive near-tie, which gives no reason to prefer a different scale.

**Stage 1, context offset.** Weighted least squares of the response (100 × `model_points`) on an intercept, the #24 `home_score_time` columns (home ±1, clipped pre-possession margin, period 2–4 and overtime indicators, end of period, final two minutes; built and timing-audited exactly as in #24 and #26) and indicator columns for every season-and-season-type level present in the fit rows except the first (`bil.models.rapm.context.fit_context_only`). EPM documents home-court and rubber-band adjustment in the SPM-target RAPM (Documented). The levels carry era differences in scoring and the playoff scoring level, and the offset absorbs each level's average lineup composition as well (Inferred; a joint fit is not implemented).

**Stage 2, players.** On the response minus the offset (without its intercept), the verified zero-prior two-penalty ridge with a free intercept, five positive offensive and five negative defensive indicators, penalties $\lambda_o$ and $\lambda_d$, and each player block centred on its unweighted mean over the fit universe (ADR-0012; `reference._solve_rapm` through `multiseason.fit_players`). Each origin builds its own design from its own eligible rows, so a later row cannot enter a column or change an earlier solve.

**Penalty choice (specified in advance).** For each reference, origin and scenario, one pair $(\lambda_o, \lambda_d)$ shared by all target seasons is chosen by **five-fold game-grouped cross-validation inside the rows eligible at that origin**:

- A game's fold is `int(sha256("issue-28-v1:" + game_id)) mod 5`. It is the same at every origin.
- For fold $k$ and target $s$, both stages are fitted on the kernel rows of games outside fold $k$. The squared error is scored, unweighted, on season $s$'s rows in fold $k$. A player unseen in training contributes zero. The runner asserts that no scored row is a fit row.
- The criterion is the pooled mean over every target and fold.
- The search is the #26 one-pass coordinate search (`multiseason.search_penalties`): a shared grid {1,000, 2,000, 4,000, 8,000, 16,000, 32,000} with up to five twofold extensions off an edge, then $\lambda_d$ and then $\lambda_o$ over the factors {1/4, 1/2, 2, 4} with up to three extensions. Ties go to the smaller penalty.

No outer-season row, EPM value, player-level quantity, SPM result or downstream metric enters the choice. In-window cross-validation selects for interpolation accuracy, which is the retrospective quantity a label describes. It is not a claim that this penalty minimizes label error.

## 5. Units, signs, centring and the label table

- Points per 100 possessions. Offense positive = more points scored by the player's team; defense positive = fewer points allowed. Total = offense + defense.
- **Centring (primary).** Within each target season, `offense` and `defense` are shifted so that their means, weighted by the player's target-season offensive and defensive possessions, are zero over the labelled players: the average possession of season $s$ is 0. `offense_raw` and `defense_raw` keep the ADR-0012 fit-universe centring, and the per-season shift between them is reported.
- **Columns** (private `targets.csv`): version, artifact label, reference, origin, whether the origin is final, target season, verification group, player, `offense`, `defense`, `total`, `offense_raw`, `defense_raw`, target-season offensive and defensive possessions, kernel-weighted offensive and defensive exposure, number of teams in the target season, and the bootstrap standard errors (final origin only).

## 6. References and rolling origins

| Reference | Seasons | Purpose |
| --- | --- | --- |
| `contiguous` | 2018–19 to 2022–23 | The primary-cohort reference with no gap |
| `extended` | 2005–06, 2006–07, 2007–08, 2015–16, 2016–17, 2018–19 to 2022–23 | All currently eligible history (ADR-0026) |

One **origin closes each eligible season**. Its cutoff is the day after the last scheduled game of that season (accepted or quarantined, from `game_reconciliation`). Each origin fits every target season with eligible rows before it, with its own penalty search, and freezes the result. Cutoffs computed in the loader check:

| Closes | 2005–06 | 2006–07 | 2007–08 | 2015–16 | 2016–17 | 2018–19 | 2019–20 | 2020–21 | 2021–22 | 2022–23 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cutoff | 2006-06-21 | 2007-06-15 | 2008-06-18 | 2016-06-20 | 2017-06-13 | 2019-06-14 | 2020-10-12 | 2021-07-21 | 2022-06-17 | 2023-06-13 |

The contiguous reference uses the last five origins; the extended reference uses all ten. The runner refuses an origin that falls after the next eligible season's first game or after 2023-07-01. A fixed 1 July boundary would cut the 2019–20 and 2020–21 playoffs, which is why the cutoffs follow the calendar.

- **Unavailable origins.** No target closes 2008–09 through 2014–15 or 2017–18 in the extended reference. These origins are marked unavailable. A consumer needing a target at such a date uses the latest earlier frozen set (2007–08 or 2016–17 closure) and must say so. In each reference the first season has no earlier target, so an evaluation of that season is unavailable.
- **One-sided labels.** At the origin closing season $s$, the label of $s$ has no later data. It gains later neighbours at later origins. Each label records its kernel seasons and whether it has forward support. How much labels move is measured in §8.

## 7. Freezing, versioning and leakage

- **Version.** `issue-28-v1`. A frozen target record holds the version, reference, kernel, cutoff, closed season, seasons, penalties, row count, scenario, the artifact label, a SHA-256 of every input it read, and a SHA-256 of each season's label table.
- **Input digest.** It covers game ID, possession sequence, season, season type, played date, period, outcome, both lineups, every context covariate, the verification flag and both teams of every eligible row, independent of row order. `verify_frozen` recomputes it from any row collection. A difference raises `FrozenTargetError`.
- **Revisions.** A revised row set, a newly eligible season (for example from #53 or #99) or any other input change produces a new target version (`issue-28-v2` and later) in a new output directory. Existing targets are never silently changed (ADR-0026).
- **Capture-bound availability.** All source revisions were captured in 2026 (`retrospective_capture_bound`). Origins filter by played date only. Revision availability before 2026 is not evidenced, so no target is a strict as-of label in the [evaluation contract's](../validation-strategy.md) sense. Every result is labelled with this evidence tier.
- **Leakage tests** (`tests/test_rapm_targets.py`, synthetic):
  - `test_later_rows_cannot_change_a_frozen_target`: appending later rows with new players and changed outcomes leaves the frozen record and every label bit-identical, and `verify_frozen` passes, including after row reordering.
  - `test_a_revised_earlier_row_is_detected_and_needs_a_new_version`: changing one earlier outcome or covariate fails verification and yields a new input digest.
  - `test_kernel_uses_real_elapsed_time_across_gaps`: weights depend on dates, not season numbering. A seven-year gap gets zero weight, and relabelling seasons as adjacent changes nothing.
  - `test_cross_validation_never_fits_a_held_out_game` and `test_game_folds_are_deterministic_and_whole_games`.
  - `test_chronological_registration_trains_only_on_earlier_target_sets` and the end-to-end check that evaluation labels read no row before their training origin.
  - Guards refusing 2017–18, 2023–24, 2024–25, the gap seasons and the holdout, the strata check, and the refusal to run without the committed protocol on a clean tree.
  - `test_sensitivity_fits_are_never_frozen_targets`.

## 8. Reliability, stability and exposure

All at the final origin of each reference unless stated, offense and defense always separate.

- **Split-half reliability.** The games of every season are alternated in (date, game ID) order into two halves (`multiseason.split_halves`), so the two fits share no possession. Each target is refitted on each half with the frozen penalties. A role's labels are paired for players with at least 250 possessions in that role in the target season in both halves (the #23 rule). The report gives Pearson $r$ and the Spearman–Brown full-sample reliability $2r/(1+r)$, pooled and by season, era (2005–08, 2015–17, 2018–23), verification group, exposure band (target-season on-court possessions, both roles: under 2,000, 2,000–5,000, 5,000–10,000, 10,000 or more), and roster status (one team or more than one in the target season).
- **Bootstrap standard errors.** 100 game-clustered resamples (multinomial game counts over all games eligible at the origin, seed 28 with the target season and reference). Each replicate refits both stages with the frozen penalties and centres with the full-sample exposures. Each label gets a standard error; by band, the report gives the mean standard error and $1 - \overline{SE^2}/\mathrm{Var}(\text{label})$. Ridge shrinkage makes these standard errors describe the shrunken estimator, not the error against a true effect (Inferred).
- **Label revision across origins.** For every season and earlier origin, the label against its final-origin value: correlation and RMS difference by role and band. This measures one-sided labels and how much a newly eligible season moves earlier labels.
- **Reference agreement.** Contiguous against extended at the final origin, for 2018–19 to 2022–23: correlation and RMS difference by role and band.
- **Exposure effects.** By band: label count, standard deviation, mean absolute label, mean bootstrap standard error and bootstrap reliability. Low-exposure labels are expected to be shrunk toward the season average (Inferred).
- **Era and verification.** Per season: label count, the count with at least 250 possessions in each role, players with team changes, label spread overall and for that cohort, the raw-centring shift, and the fitted level effects and context coefficients of every fit.

**Sensitivity scenarios** (final origin; each reruns the whole penalty search and never changes the primary targets):

| Scenario | References | Change |
| --- | --- | --- |
| `K0` | both | Target season only (no borrowing) |
| `K730` | both | Half-life 730 days, cap 1,460 days |
| `regular_only` | both | Playoff rows removed |
| `pooled_window` | contiguous | One unit-weight fit over all five seasons; every season's label is the same window effect (the literal "multi-season RAPM from the same seasons") |
| `exclude_no_livedata` | contiguous | 2018–19 and 2019–20 removed (ADR-0020 stratum), so labels exist for 2020–21 to 2022–23 only |

Each reports its penalties, its cross-validation errors and the label shift against the primary targets by season, role and band.

## 9. Cohorts and the #30 registration

- **Label cohort.** Every labelled player-season: at least one offensive and one defensive possession in the target season.
- **Minimum-exposure cohort.** At least 250 offensive and 250 defensive possessions in the target season. This is the cohort for reliability statements and the default common cohort for #30 comparisons.
- **Common reference cohort.** Player-seasons of 2018–19 to 2022–23 in the minimum-exposure cohort of both references at the final origin.

**Chronological evaluation for #30** (machine-readable in `results.json`, `chronological_registration`). For each reference and each eligible season $e$ after its first:

| Item | Rule |
| --- | --- |
| Training targets | The frozen target set at the origin closing the previous eligible season, which has only seasons before $e$ |
| Evaluation label | The season-$e$ label fitted only on rows played on or after that origin (seasons $e$ and later, up to the final origin), with the final-origin penalties of the reference. It shares no possession with any training label |
| Unavailable | The first season of each reference (2018–19 contiguous, 2005–06 extended) |
| Outer seasons | Any #30 use of 2023–24 or 2024–25 trains on the final-origin targets (closing 2022–23) under #30's own frozen protocol. #28 reads neither season |

A same-window SPM fit on the final-origin targets is a retrospective co-window calibration, as the [evaluation contract](../validation-strategy.md) describes. It is not an out-of-time result. The extended folds for 2015–16 and 2018–19 cross the gaps and must be reported as such.

## 10. Stopping rule

- The run happens **once**, from a clean tree at the commit that contains this protocol and the runner, to a new directory `data/processed/targets/issue-28-v1/`. The runner refuses to start unless it is given this file's SHA-256, the file is committed and unmodified, and the working tree is clean. It records the digest, the commit and `HEAD` in the manifest.
- A rerun is allowed only after a crash before results are written. It is reported as a deviation.
- No result can change anything in this protocol: no kernel, penalty rule, cohort, scenario or centring choice is revisited because of reliability, stability or any downstream outcome. A non-converging fit or a penalty still at a grid edge after its extensions is recorded and kept. If an origin cannot be fitted, it is marked unavailable with the reason, and nothing is substituted.
- Low reliability, for example of defensive labels, is an acceptable finding. It is reported with the targets, which stay provisional.

## 11. Outputs

Private, in the run directory: `targets.csv`, `evaluation_labels.csv`, `sensitivity_labels.csv` and `frozen_targets.json`. Aggregate: `results.json` and `fit_log.json`. `manifest.json` holds the pinned inputs and verified digests, timing audits, coverage, the protocol verification, code commit, library versions, runtime, peak memory and output digests. Committed reports carry aggregates only, with no named players or rankings. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md).

Expected scale, estimated from #26's real fit times (0.2 to 0.7 s per fit of 0.4 to 1.1 million rows) and the 2.4 GB loader peak: about 12,000 sparse fits and two to three hours. This is an estimate, not a measurement.

## 12. Open questions (not decided by the run)

- Whether the season-centred label (`K365`) or a window-constant label (`pooled_window`) better serves SPM. This protocol fixes `K365` as primary and reports `pooled_window` only as a sensitivity. #30 must register which label it trains on before fitting.
- Label reliability weights for SPM (EPM-U03). The targets supply exposures and bootstrap standard errors; #30 registers how to use them.
- The two-stage context offset against a joint fit, and whether the home effect should vary by era (it is common within each fit).
- Neutral sites are uncoded (every pilot has null flags), including the 2019–20 bubble.
- The extended reference crosses a seven-season gap. Its 2005–08 labels describe a different era and box-score environment, so #30 must decide whether to pool them with modern seasons.

| Claim | Label |
| --- | --- |
| Box-score SPM trained on long-window independent RAPM with home and score-state adjustment, playoffs included | **Documented** (EPM methodology) |
| Sparse ridge solver, centring, dated clock | **Documented** in this repository ([#6](rapm-synthetic.md), [#64](rapm-dated-weights.md)) |
| Season-centred elapsed-time kernel, two-stage offset with season levels, in-window CV penalties, origins, centring, reliability design, cohorts | **Original** |
| Every number the run produces | **Experimental**, retrospective (`retrospective_capture_bound`) |
