# Experiment Log

Do not overwrite negative or unexpected results. New experiments should be append-only, with links to generated [run manifests](run-manifest.md) and any linked scoring runs.

## Template

### EXP-XXXX — Descriptive title
- **Status:** Proposed / Running / Completed / Invalidated
- **Date:** YYYY-MM-DD
- **Research question/hypothesis:**
- **Category:** Reference replication / Experimental / Original
- **Code SHA / run ID:**
- **Datasets/checksums and cutoff:**
- **Train / validation / test periods:**
- **Model and configuration:**
- **Baselines:**
- **Metrics and uncertainty:**
- **Results:**
- **Limitations / interpretation:**
- **Next decision:**

## Log

### EXP-0001 — V3 action order for unresolved 2022–23 pilot games
- **Status:** Completed
- **Date:** 2026-11-23
- **Research question/hypothesis:** Can the pinned V3 action order replace the parser's live data.nba.com reorder, and would V3 order also help when used as the primary order?
- **Category:** Original (data pipeline, not a model)
- **Code SHA / run ID:** Fallback at `e098dca`. Exploratory V3-first runs used an unmerged scratch patch on the same commit.
- **Datasets/checksums and cutoff:** Pinned issue #5 snapshot. Retrospective capture with no historical availability claim.
- **Train / validation / test periods:** Not applicable.
- **Model and configuration:** pbpstats 1.3.11 offline. Parser version `pbpstats-1.3.11-bil-v2`.
- **Baselines:** Build `issue-5-final-v1` at `19c1bf7`.
- **Metrics and uncertainty:** Games accepted under the unchanged reconciliation checks.
- **Results:**
  - As a fallback, V3 order made 70 of the 79 `unresolved_event_order` games acceptable. The other nine remain quarantined for plus-minus (3), parser errors (3), score allocation (2) and a substitution conflict (1).
  - Used as the primary order, V3 recovered 4 of 22 `parser_error` games and 2 of 4 `unsupported_reorder` games. Not adopted.
- **Limitations / interpretation:** V3 order is a stand-in for data.nba.com order. Same-clock ties that change no reconciled quantity cannot be verified.
- **Next decision:** Keep the fallback (ADR-0008). Next, investigate period-starter evidence for the 33 `unresolved_starters` games.

### EXP-0002 — Narrow-scope resolution of the remaining 2022–23 pilot quarantines
- **Status:** Completed
- **Date:** 2026-11-23
- **Research question/hypothesis:** Can local anomalies be resolved at event, possession or credit level without relaxing whole-game lineup, score and box checks?
- **Category:** Original (data pipeline, not a model)
- **Code SHA / run ID:** Branch `claude/issue-5-remaining-quarantines`. Steps were measured on targeted builds of the quarantined games.
- **Datasets/checksums and cutoff:** Pinned issue #5 snapshot. Retrospective capture.
- **Train / validation / test periods:** Not applicable.
- **Model and configuration:** pbpstats 1.3.11 offline. Parser version `pbpstats-1.3.11-bil-v5`.
- **Baselines:** Build `issue-5-v3-order-v2` with 1,201 accepted games and 113 quarantined.
- **Metrics and uncertainty:** Recovered games under unchanged whole-game checks, and violations from the independent output check.
- **Results:** Cumulative recovery of the 113 quarantined games, in the order applied:
  1. Starter search: 29 of 33 `unresolved_starters` games. Two more were "immaterial", because the parser discarded the early choice.
  2. Unresolved possessions: 60 of 113 cumulative. This also recovered the two remaining starter games and every back-to-back parser error except one.
  3. Same-clock credit search: 78 cumulative. Eighteen games used it, and four plus-minus games stayed ambiguous or unsolved.
  4. V3-primary retry: 85 cumulative.
  5. Truncation-aware minutes tolerance: 89 cumulative.
  6. Negative result: treating V3 substitution disagreements as non-blocking recovered none of the 8 games, because their V2 reconstruction also failed. It was reverted.
- **Limitations / interpretation:** Box values were selection evidence for 49 games. The unresolved possessions are concentrated around held-ball jump balls and flagrant fouls.
- **Next decision:** Accept the pilot at M1 level with the remaining 24 quarantines documented (ADR-0009).

### EXP-0003 — External verification of the 2022–23 M1 build
- **Status:** Completed
- **Date:** 2026-11-23
- **Research question/hypothesis:** Do independent feeds and reconstructions confirm BIL's lineups, possession labels, event order and inferred starters, and do they explain the remaining quarantines?
- **Category:** Original (data verification)
- **Code SHA / run ID:** `32d1303`, `python -m bil.data.pilot evidence` on build `issue-5-v5` built at `92011a7`.
- **Datasets/checksums and cutoff:** Pilot snapshot `issue-5-v1` and evidence snapshot `issue-5-evidence-v1`. Hashes are in the source ledger.
- **Train / validation / test periods:** Not applicable.
- **Model and configuration:** Not applicable.
- **Baselines:** Not applicable.
- **Metrics and uncertainty:** Time-weighted lineup agreement, live-ball offense agreement, adjacent order reversals, starter matches and period-score matches.
- **Results:**
  - Lineups agree on 99.97% of court time, and the lowest game is 99.75%.
  - Live-ball offense agrees on 99.99% of events in accepted possessions.
  - Counted possessions equal pbpstats.com's in 1,257 of 1,290 games.
  - All 87 V3-ordered games match data.nba order exactly.
  - All 35 inferred starter sets match Bentes, and all 33 after period 1 match liveData.
  - Two quarantines are V3 period-score defects.
  - Ten are play-by-play substitution defects that V2 and liveData share and that the box contradicts.
  - Using liveData's tenth-second clocks cut the mean player-minutes error from 146 ms to 29 ms and reconciled two of the four games that rely on the truncation allowance exactly. Some liveData event clocks are missing or disagree with V2, so mixing clock sources gave larger errors for 74 player-games. V2 clocks therefore remain the build basis.
- **Limitations / interpretation:** Every feed derives from the NBA's event log. data.nba and liveData share upstream order numbers, and data.nba mislabels periods in one game. Bentes appears box-calibrated, which makes it strong evidence for BIL's lineups but not for the box.
- **Next decision:** The ADR-0010 proposals.

### EXP-0004 — Archived-feed adjudication of starters, period scores and possession labels
- **Status:** Completed
- **Date:** 2026-11-23
- **Research question/hypothesis:** Can liveData and data.nba evidence replace box-based starter selection, recover the V3 period-score defects and resolve unresolved possessions, without changing verified lineups?
- **Category:** Original (data pipeline)
- **Code SHA / run ID:** `b1a43ed` (rules in `9b4f24d`, review fixes in `b1a43ed`), build `issue-5-v6`.
- **Datasets/checksums and cutoff:** Snapshot `issue-5-v2`, which is `issue-5-v1` plus four pinned liveData and data.nba archives.
- **Train / validation / test periods:** Not applicable.
- **Model and configuration:** Parser version `pbpstats-1.3.11-bil-v6`.
- **Baselines:** Build `issue-5-v5` with 1,290 accepted games.
- **Metrics and uncertainty:** Accepted games, changes to previously accepted rows, the `check` and `evidence` results, and the number of games where the box chose the reconstruction.
- **Results:**
  - 1,292 games accepted.
  - liveData starters settled 33 team-periods in 29 games, with identical lineups, all matching Bentes. Box-chosen games fell from 49 to 20.
  - Two V3 defect games were accepted.
  - Only 3 of 54 unresolved possessions were relabeled, against an estimate of 28. Unanimous labels usually repeat a neighbor's offense, which means a missing boundary rather than a wrong label.
  - No previously accepted lineup or event changed.
  - All 79 regular-season overtime games are accepted.
- **Limitations / interpretation:** The liveData and data.nba comparisons are no longer independent for the affected games.
- **Next decision:** Possession boundaries for the remaining 51 unresolved possessions would need a different method, for example data.nba possession changes. That is not proposed.

### EXP-0005 — Synthetic offensive/defensive RAPM

- **Status:** Completed.
- **Date:** 2026-11-23.
- **Research question:** Can the sparse solver recover known offensive and defensive effects? How do sample size, ridge strength and paired lineups affect recovery?
- **Category:** Experimental (synthetic).
- **Code SHA / command:** `51b00c6`, `uv run --locked --extra rapm python -m bil.models.rapm.synthetic` with Python 3.12.13, NumPy 2.5.5 and SciPy 1.18.1.
- **Inputs and split:** The committed generator produces all observations. Seed 6014 supplies the 800-row rotating and paired noiseless training sets. Seeds 6440 and 6441 supply the 4,000 rotating noisy rows and the scoring draws; a 48-row prefix tests low exposure. Seed 6992 supplies 1,200 separately drawn evaluation lineups with exact expectations. There are no historical inputs or cutoffs.
- **Model and baselines:** Zero-prior RAPM with unit observation weights and ridge $10^{-4}$ for noiseless recovery. The noisy cases use ridge 0.01, 100 and 1,000. The intercept-only fit uses the sample mean for each training set. A separately assembled dense solution checks the weighted objective in a distinct test fixture.
- **Results:** Noiseless rotation recovers all 24 effects within $2\times10^{-5}$ points per 100 possessions, with effect RMSE $5.501\times10^{-6}$. Identical lineup columns split effects equally and produce 3.079 held-out expected-rate RMSE. At ridge 0.01, the expected-rate RMSE is 76.031 with 48 rows and 6.899 with 4,000. The 48-row intercept-only model returns 9.366. [Full results and tolerances](research/rapm-synthetic.md#verification-and-sensitivity)
- **Limitations:** One fixed seed, additive effects and independent possession outcomes. The test set scores the generated conditional expectation. The sensitivity grid sets no NBA penalty or minimum exposure threshold.
- **Next decision:** Specify how the private possession pilot becomes a RAPM row set and preserve reconciliation and chronology in the subsequent M2 design.

### EXP-0006 — OpenRAPM solver agreement

- **Status:** All four benchmark fixtures passed.
- **Date:** 2026-11-23.
- **Research question:** Do sparse LSQR and OpenRAPM's weighted normal equations agree when both solve the same two-role ridge objective?
- **Category:** Experimental (synthetic).
- **Inputs and configuration:** Pinned OpenRAPM commit `8cfb3df786ceb1cd362a67c4683c37a473ee9c2b`, shared generated rows and unpenalized intercept. The four cases cover unequal weights, common rescaling of weights and penalty, and paired players under weak and strong regularization.
- **Results:** Maximum differences were `3.429e-10` for player coefficients, `1.695e-10` for the intercept and `6.790e-10` for fitted rates, in points per 100 possessions. The absolute limit was `1e-8`.
- **Scope:** Numerical agreement for a shared objective. NBA row construction, model calibration and published ratings require separate evidence. [Full results and command](research/rapm-open-benchmark.md)

### EXP-0007 — 2023–24 and 2024–25 outer-validation season builds

- **Status:** Completed.
- **Date:** 2026-11-23.
- **Research question:** Do the unchanged pilot rules and M1 thresholds hold for the two outer folds, at verification strength comparable to 2022–23?
- **Category:** Original (data pipeline, not a model).
- **Code SHA / run ID:** `9395ce1`, builds `issue-52-v1` for each season and `issue-52-rebuild-v1` for 2022–23.
- **Datasets/checksums and cutoff:** Snapshots `issue-52-v1` and `issue-52-evidence-v1` for each season, copied from the #51 audit capture and checked against its register pins. Retrospective capture with no availability claim. The 2025–26 holdout was not built.
- **Train / validation / test periods:** Not applicable.
- **Baselines:** 2022–23 build `issue-19-v6` and the M1 thresholds.
- **Results:**
  - 2023–24 accepted 1,218 of 1,230 regular-season and 81 of 82 playoff games.
  - 2024–25 accepted 1,205 of 1,230 regular-season and 84 of 84 playoff games.
  - Both pass 26 of 26 checks and every M1 threshold.
  - Bentes lineup agreement is 99.97% for both seasons.
  - Five 2024–25 games needed ADR-0017's V2 home designation.
  - The 2022–23 rebuild is row-identical.
  - The unresolved-possession share rose to 0.039% and 0.070%. The 2024–25 playoffs alone reach 0.135%.
  - 14 of 25 quarantines in 2024–25 trace to box-log minute totals that do not sum to the game length. [Full results](data-pilot.md#outer-validation-seasons-202324-and-202425)
- **Limitations / interpretation:** The box log remains the reference, so box defects quarantine games rather than being corrected. Thresholds were set after 2022–23 was observed and were not changed here.
- **Next decision:** The maintainer decides whether the 0.1% unresolved-possession limit should also apply to each season type. Unresolved-possession boundaries are the main remaining verification gap before #26.

### EXP-0008 — Stat-specific skill decay and league shrinkage, 2022–23

- **Status:** Run once under a frozen protocol. Independently reviewed (approved).
- **Date:** 2026-11-23.
- **Research question:** Does per-statistic exponential decay with league shrinkage, fitted by Differential Evolution in nested chronological folds, beat the fixed #31 baselines on later 2022–23 games, and which age clock works best?
- **Category:** Experimental (retrospective replay, one season).
- **Inputs and configuration:** Pinned `issue-5-v2` logs, #31 build `issue-31-v1`, [frozen protocol](research/skill-decay-protocol.md) (commit `4e25451`), code commit `33fd3d0`, output `issue-32-v1`. 234 DE fits, game-clustered bootstrap with 2,000 replicates.
- **Results:** In regular-season outer blocks, the model beat every #31 baseline on all 13 statistics in log loss and MSE, with intervals excluding zero. MSE gains were 0.6–3.7% over the best player or league baseline. Playoff gains were smaller and mostly within intervals against the 90-day decay. Clocks are indistinguishable for 11–12 of 13 statistics. A pure day clock is worse for free-throw rate. 33 of 234 fits hit the no-decay half-life bound. [Full results](research/skill-decay-2022-23.md)
- **Scope:** Single-season evidence only. Outer seasons 2023–24 and 2024–25 must be run before any clock or parameter is fixed.

### EXP-0009 — 2017–18 through 2021–22 development season builds

- **Status:** Completed.
- **Date:** 2026-11-23.
- **Research question:** Do the unchanged pilot rules and M1 thresholds hold for the five seasons before 2022–23? Three of them lack archived liveData.
- **Category:** Original (data pipeline, not a model).
- **Code SHA / run ID:** `4b72175`, builds `issue-25-v1` for each season and `issue-25-rebuild-v1` for 2022–23.
- **Datasets/checksums and cutoff:** Snapshots `issue-25-v1` and `issue-25-evidence-v1` for each season. They were copied from the #51 audit capture and checked against its register pins. Retrospective capture with no availability claim. The 2025–26 holdout was not built.
- **Train / validation / test periods:** Not applicable.
- **Baselines:** 2022–23 build `issue-19-v6` and the M1 thresholds.
- **Results:**
  - **Meet M1:** 2019–20 (1,041 of 1,059 regular-season and 82 of 83 playoff games) and 2020–21 (1,072 of 1,080 and 85 of 85).
  - **Recorded unavailable:**
    - 2017–18 has 85.5% regular-season coverage and 0.391% unresolved possessions. Early-season event-order failures dominate.
    - 2018–19 accepts 58 of 67 overtime games (86.6%).
    - 2021–22 accepts 55 of 58 overtime games (94.8%).
  - Every build passes 26 of 26 checks, and `check-seasons` finds no identity or chronology violations.
  - Bentes lineup agreement is 99.97% in every season.
  - 2017–18 through 2019–20 carry the `no_livedata` stratum (ADR-0020).
  - The 2022–23 rebuild is row-identical.
  - Builds take 56 to 73 s and peak at 0.76 to 0.85 GB each. [Full results](data-pilot.md#development-seasons-201718-through-202122)
- **Limitations / interpretation:** Thresholds were set after 2022–23 was observed and were not changed. Two of the three failures turn on small overtime denominators. The 2017–18 diagnosis is Inferred and was not investigated at the event level.
- **Next decision:** The maintainer decides whether a stratum floor alone should make a season unavailable, and reassesses the #26 window. Under the current thresholds, the M1 seasons from 2017–18 to 2022–23 are 2019–20, 2020–21 and 2022–23.

### EXP-0010 — Context for game-agnostic and game-optimized skill forecasts, 2022–23

- **Status:** Run once under a frozen protocol. Independent review not yet run.
- **Date:** 2026-11-23.
- **Research question:** Does a fitted pregame context adjustment (home, team rest, opponent allowed rates, own-team rate, league trend) improve the frozen #32 skill forecast on later 2022–23 games, factor by factor, using only evidence available at the prediction origin?
- **Category:** Experimental (retrospective replay, one season).
- **Inputs and configuration:** Pinned `issue-5-v2` logs, frozen `issue-32-v1` fits, [frozen protocol](research/skill-context-protocol.md) (commit `9642a51`), code commit `9483a40`, output `issue-33-v1`. 2,496 penalized likelihood fits, game- and player-clustered bootstrap with 2,000 replicates.
- **Results:** All 194,764 base predictions and 26,481 snapshot rows reproduced #32 exactly, and no context input used a date on or after its game. The matchup-specific forecast lowered log loss in 12 of 13 statistics (10 with game-clustered intervals excluding zero), with MSE changes of −0.02% to −0.88%. Opponent allowed rates carried the gain (retained for 9 statistics). Home, rest and team terms did not beat an intercept-only control. Aging was untestable (no birthdates). Playoffs got worse for 4 statistics. [Full results](research/skill-context-2022-23.md)
- **Scope:** Single-season evidence only. Outer seasons 2023–24 and 2024–25 must be run before any context is adopted.

### EXP-0011 — Period-end pseudo-possession exclusion in the RAPM row set, 2022–23

- **Status:** Run once under frozen protocols (v1 for variant A, v2 for B and the common cohort). Independent review of the B change not yet run.
- **Date:** 2026-11-23.
- **Research question:** Does excluding possessions with no live-ball opportunity change the #23 baseline and #24 context results, and which rows should be eligible?
- **Category:** Experimental (retrospective replay, one season), with an Original row rule.
- **Inputs and configuration:** `issue-19-v6`. Row sets `issue-59-v1` (C), `issue-82-v1` (A) and `issue-82-B-v1` (B, build id `7b8c6449…eac3`). [Protocol v2](research/rapm-no-action-protocol-v2.md) commit `3863286`. $\lambda$ = 4,000, bootstrap seed 2023.
- **Results:** 962 accepted `period_end` first-event possessions with no exceptions in the audit. RAPM vs league −13.16 (B) against −14.09 (C). `T_fit` −5.20 (−8.16 to −2.06) against −25.69. `HST_fit` −11.26 against −32.25. On the common A cohort, B − C RAPM MSE −2.46 (−3.15 to −1.74), A − B −0.15 (−0.21 to −0.09). [Report](research/rapm-no-action-2022-23.md)
- **Limitations / interpretation:** One season. The residual end-of-period effect (about −16) is unexplained, and a game-final explanation is Inferred only.
- **Next decision:** Whether game-final possessions need a treatment, and whether B transfers to outer seasons.
