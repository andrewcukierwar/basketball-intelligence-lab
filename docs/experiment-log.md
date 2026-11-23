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
