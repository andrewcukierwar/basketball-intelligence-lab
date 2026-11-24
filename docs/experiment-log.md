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

- **Status:** Run once under a frozen protocol. Independently reviewed (approved; #87).
- **Date:** 2026-11-23.
- **Research question:** Does a fitted pregame context adjustment (home, team rest, opponent allowed rates, own-team rate, league trend) improve the frozen #32 skill forecast on later 2022–23 games, factor by factor, using only evidence available at the prediction origin?
- **Category:** Experimental (retrospective replay, one season).
- **Inputs and configuration:** Pinned `issue-5-v2` logs, frozen `issue-32-v1` fits, [frozen protocol](research/skill-context-protocol.md) (commit `9642a51`), code commit `9483a40`, output `issue-33-v1`. 2,496 penalized likelihood fits, game- and player-clustered bootstrap with 2,000 replicates.
- **Results:** All 194,764 base predictions and 26,481 snapshot rows reproduced #32 exactly, and no context input used a date on or after its game. The matchup-specific forecast lowered log loss in 12 of 13 statistics (10 with game-clustered intervals excluding zero), with MSE changes of −0.02% to −0.88%. Opponent allowed rates carried the gain (retained for 9 statistics). Home, rest and team terms did not beat an intercept-only control. Aging was untestable (no birthdates). Playoffs got worse for 4 statistics. [Full results](research/skill-context-2022-23.md)
- **Scope:** Single-season evidence only. Outer seasons 2023–24 and 2024–25 must be run before any context is adopted.

### EXP-0011 — Run-outs and period-end possessions in the RAPM row set, 2022–23

- **Status:** Sensitivity runs under frozen protocols v1 and v2 (v2 superseded), then one cohort comparison under v3. A focused independent re-review approved the canonical decision at abed529 before PR #91 merged.
- **Date:** 2026-11-23 and 2026-11-24.
- **Research question:** Do possessions that start a period's end, or contain no action, need exclusion from the RAPM row set, and what do the alternatives change?
- **Category:** Experimental (retrospective replay, one season), with an Original row rule.
- **Inputs and configuration:** `issue-19-v6`. Row sets `issue-82-canonical-v1` (equal to `issue-59-v1`), `issue-82-period-end-start-v1` and `issue-82-noaction-v1`, built at `0c6d111`. [Protocol v3](research/rapm-no-action-protocol-v3.md) commit `abf011b`. $\lambda$ = 4,000, bootstrap seed 2023.
- **Results:** All 962 accepted `period_end`-first possessions begin after a change of control with 3 to 24 s left, while the pilot's 1,567 excluded ones all have under 3 s, so the canonical set stays the pilot-eligible set and the #23 and #24 results stand. Sensitivity: RAPM vs league −14.09 canonical, −13.16 `period_end_start`, −13.17 `no_action`. `T_fit` −25.69 against about −5. On canonical held-out rows, fits on the sensitivity rows score 1.74 (1.01 to 2.42) and 1.86 (1.10 to 2.57) MSE better. [Report](research/rapm-no-action-2022-23.md)
- **Limitations / interpretation:** One season. A first audit that used possession-internal duration was invalid and led to a withdrawn v2 protocol. A residual end-of-period effect remains unexplained.
- **Next decision:** Whether game-final possessions need a treatment, and how to read the canonical time effect in later reports.

### EXP-0012 — M1 quality policy revision and season missingness diagnostic, 2017–18 through 2024–25

- **Status:** Completed. Independently reviewed (approved; #92).
- **Date:** 2026-11-24.
- **Research question:** Under the revised M1 policy (ADR-0022), which seasons meet the hard limits, and are quarantined games and unresolved possessions missing systematically by team, date, player, exposure, game state or cause? How much does the primary cohort (2018–19 through 2022–23) depend on the conditionally authorized seasons, overtime periods and weaker-verification strata?
- **Category:** Original (data-quality diagnostic, no model).
- **Code SHA / run ID:** `scripts/season_quality.py` and `bil.data.season_quality` on branch `claude/issue-89-m1-policy`; private output `data/processed/quality/issue-89-v2` (supersedes `v1`, which used 1,000 bootstrap replicates). Seed 20261123, 5,000 permutations, 20,000 bootstrap replicates, `--run-checks`. The unresolved-possession flag rule was revised after the first run (3-event cells gave infinite ratios; now at least 5 events and Bonferroni), and v2 fixes a bootstrap p-value floor that made flags unreachable. Details in the report's revision history.
- **Datasets/checksums and cutoff:** The existing builds `issue-25-v1` (2017–18 to 2021–22), `issue-19-v6` (2022–23, snapshot `issue-5-v2`) and `issue-52-v1` (2023–24, 2024–25), opened read-only. No 2025–26 file was read.
- **Train / validation / test periods:** Not applicable. No model was fitted or scored, and no model result exists for 2023–24 or 2024–25.
- **Baselines:** The original M1 table results in EXP-0007 and EXP-0009, which the script reproduces. Those results are preserved.
- **Results:**
  - Revised classification: 2017–18 fails two hard limits; 2018–19 and 2021–22 meet them with an overtime-stratum warning; 2019–20, 2020–21, 2022–23 and 2023–24 meet; 2024–25 meets with a playoff unresolved-share warning (0.135%). All 26 invariants pass in every build.
  - Five systematic flags among 83 testable tests: 2017–18 early-season quarantines, player minutes and October 2017 unresolved possessions; 2018–19 quarantines concentrated in overtime games (9 of 67 against 15 of 1,163 regulation games) and in November 2018 (11 of 219 games). Four watch flags, including 2021–22 overtime (3 of 58).
  - 2024–25 playoff unresolved possessions (22 in 10 of 84 games) show no testable pattern by team, month, period or score margin, and the interval (0.056–0.228%) includes 0.1%.
  - Cohort sensitivity (baseline 6,164 games, 1,223,735 possessions, 970 players): excluding 2018–19 changes games by −20.9% and players by −107; excluding 2021–22, −21.2% and −46; both, −42.1% and −163; overtime periods, −0.6% of possessions; overtime games, −5.4% of games; weaker-verification games, −39.1% of games. [Full results](research/season-quality-2017-2025.md)
- **Limitations / interpretation:** Quarantined games lack events, so their game state is box and final-score only. The permutation tests have low power at 3 to 25 quarantines a season. Lost exposure is a box-log estimate. Flags describe association, not mechanism.
- **Next decision:** The maintainer decides whether the 2018–19 overtime and November concentration is material for primary training use. The 2021–22 and 2024–25 findings need no action beyond the recorded conditions.

### EXP-0013 — 2017–18 event-order diagnosis and older feed-era builds

- **Status:** Completed. Feasibility only. No independent review yet.
- **Date:** 2026-11-23.
- **Research question:** Why do 2017–18 early-season games fail event order, and do older feed eras build under the unchanged pipeline and hard gates?
- **Category:** Original (data pipeline, not a model).
- **Code SHA / run ID:** Builds `issue-90-v1` for 2005–06, 2010–11, 2014–15 and 2016–17 at `c079ba8`. Scratch builds `issue-90-order-repair-v1` and `-v2` of 2017–18 at `899464b` and `4fc5cba`. 2022–23 rebuild `issue-90-rebuild-v1` at `4fc5cba`. These are the SHAs in the manifests, from before the branch was rebased onto `99d558c`.
- **Datasets/checksums and cutoff:** Snapshots copied from the #51 audit capture and checked against its pins. Retrospective capture, no availability claim. The 2025–26 holdout was not touched.
- **Baselines:** `issue-25-v1` for 2017–18, `issue-19-v6` for 2022–23, and the M1 hard gates under the #89 revision.
- **Results:**
  - 2017–18: 168 of 180 quarantines (166 of 178 in the regular season) are event-order failures. The opt-in repair recovers 137 of them. Coverage 96.6%, unresolved 0.283%, so it still fails.
  - 2016–17 and 2005–06 meet both hard gates. 2014–15 meets them for the regular season and misses 97% in the playoffs by one game. 2010–11 misses regular-season coverage (96.5%) from a same-clock rebound pattern.
  - All builds pass 26 of 26 checks. The 2022–23 rebuild is row-identical to `issue-19-v6` apart from `ingested_at`.
- **Limitations / interpretation:** One season per era. 2001–02 to 2003–04 was not probed. The reason for the early-season rate in 2017–18 is Inferred. Starter verification is weaker without liveData and data.nba.
- **Next decision:** Whether to adopt ADR-0023, and how to split #53 ([recommendation](research/backfill-feasibility.md#part-3-recommended-split-of-53)).


### EXP-0014 — Split penalties, random-exclusion control and per-fit diagnostics for the RAPM baseline, 2022–23

- **Status:** Run once under a frozen protocol. Independently reviewed (approved; #100).
- **Date:** 2026-11-24.
- **Research question:** Do separate offense and defense ridge penalties improve held-out possession scoring over the single #23 penalty, and is the effect of excluding the 170 adjudication-stratum games unusual against excluding the same number of random ordinary games?
- **Category:** Experimental (retrospective replay, one season).
- **Inputs and configuration:** `issue-82-canonical-v1` (manifest SHA-256 `bd25cd0a…56488`), [frozen protocol](research/rapm-baseline-controls-protocol.md) (commit `e2168f3`, SHA-256 `7fb3ce72…8531b2`), code commit `b032969`, clean tree, output `issue-77-v1`. 49-cell grid, folds R1–R4 for selection and P1 after, 300 random draws per matching variant, 3,806 logged fits.
- **Results:** Selected $(\lambda_{off}, \lambda_{def})$ = (2,000, 8,000). Pooled R1–R4 delta against the single penalty is −1.57 (95% −3.11 to −0.06), optimistic. P1 delta is +3.57 (−1.61 to +8.75), so the split penalty is not distinguishable by the frozen rule. Stratum exclusion shifts estimates like random exclusion (total RMS 0.369 against 0.361 ± 0.015). Its held-out effect (−0.79) is lower than 2% of random draws (mean +1.28), which is descriptive only. All fits converged (iterations 8 to 60, condition at most 106).
- **Limitations / interpretation:** One season, one short playoff block, selection and reporting share R1–R4. The single penalty remains the baseline. [Report](research/rapm-baseline-controls-2022-23.md)
- **Next decision:** Whether a split penalty is worth carrying to the 2023–24 outer-validation season.

### EXP-0015 — Multi-season RAPM: temporal weighting, split penalties and outer validation, 2018–19 through 2024–25

- **Status:** Completed. Development and outer runs each ran once. Independently reviewed (approved).
- **Date:** 2026-11-24.
- **Research question:** Which window or exponential decay, with separate offense and defense penalties, best predicts held-out possession scoring in chronological development folds? Does the frozen choice beat the league mean and the #24 context-only comparator in 2023–24 and 2024–25?
- **Category:** Experimental (retrospective replay, realized lineups), Original design.
- **Code SHA / run ID:** Protocol `86790ae`. Runner `ec4f127`. Development run `data/processed/multiseason/issue-26-dev-v1` (manifest `8cbb4e5e…536a`, results committed `bd86289`). Addendum `57fe88e` (SHA-256 `23a9d3b7…420b`). Outer run `data/processed/multiseason/issue-26-outer-v1` at `57fe88e`.
- **Datasets/checksums and cutoff:** Canonical `issue-93-v1` row sets for 2018–19 to 2024–25, each pinned by manifest SHA-256, with pilot builds (`issue-25-v1`, `issue-19-v6`, `issue-52-v1`) for context covariates. No 2017–18 or 2025–26+ file was read.
- **Train / validation / test periods:**
  - Development: R1–R4 and P blocks of 2021–22 and 2022–23, fitting on all earlier rows in the window.
  - Outer: the same blocks in 2023–24 and 2024–25, walk-forward.
  - The confirmatory holdout (2025–26) was untouched.
- **Model and configuration:** Zero-prior two-penalty sparse ridge. Candidates `W1`, `W2`, `W3`, `W5`, `H90`, `H180`, `H365` and `H730`. The search used a shared grid, then the defense penalty, then the offense penalty. Selected: `W2`, $\lambda_o$ = 4,000, $\lambda_d$ = 8,000.
- **Baselines:** League mean and #24 `home_score_time` context-only, each with its own selected window (both `W1`). Secondary model: RAPM with a context offset.
- **Metrics and uncertainty:** Per-possession MSE deltas with game-clustered and week-clustered bootstrap (2,000 resamples, seed 2023). Calibration-in-the-large and slope. Coverage.
- **Results:**
  - Development: `W2` −16.24 (−19.25 to −13.20) against the league mean and +12.28 (+7.61 to +16.71) against context. Selection unchanged in all four sensitivity scenarios.
  - Outer, regular season over both seasons: −23.39 (−26.48 to −20.33) against the league mean (better) and +8.82 (+4.09 to +13.68) against context (worse). RAPM with a context offset beats context by 24.73 (−27.88 to −21.50).
  - Outer playoffs: −14.03 (−30.24 to +1.39) and +15.56 (−6.03 to +36.32), both inconclusive.
  - Calibration slope of RAPM in the regular season is 1.12 (1.04 to 1.20). Every model over-predicts playoff scoring by 2 to 4 points per 100.
  - [Report](research/rapm-multiseason.md)
- **Limitations / interpretation:** Near-tie selection. `W5` was truncated in development. Neutral sites are not coded. The context advantage rests on end-of-period run-outs (#82). Retrospective, not confirmatory.
- **Next decision:** Review, then whether informed RAPM (#30 and later) should take the RAPM-with-context-offset model as its comparator.
