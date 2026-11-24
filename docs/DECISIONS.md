# Architecture and Research Decisions

Maintain append-only decision records. Each entry should identify the date, status, alternatives, justification, implementation link and validation evidence.

Additional record: [ADR-0014, prior-centered RAPM](decisions/0014-prior-centered-rapm.md).

Additional record: [ADR-0015, dated RAPM clock and decay](decisions/0015-dated-rapm-clock-and-decay.md).

## ADR-0001 — Methodology replication rather than output imitation

**Date:** 2026-11-22  
**Status:** Accepted

**Decision:** Recreate EPM-like components using basketball data and independent RAPM; never fit models or tune hyperparameters to Dunks & Threes EPM ratings.

**Why:** This project is research into the methodology, including strengths and weaknesses, rather than reverse-regression to a commercial output.

**Consequence:** Achieving numeric agreement is secondary to method fidelity and generalization. External benchmarks are diagnostic only and subject to usage permissions.

## ADR-0002 — Start with data quality and ordinary RAPM

**Date:** 2026-11-22  
**Status:** Accepted

**Decision:** Complete a reliable one-season possession/lineup dataset and independently validated zero-prior RAPM before implementing SPM/Estimated Skills or applications.

**Why:** Possession reconstruction and regression signs/constraints can silently corrupt advanced models.

**Consequence:** The initial repo contains no speculative production ratings, API or frontend.

## ADR-0003 — Local-first, modular Python

**Date:** 2026-11-22  
**Status:** Provisional

**Decision:** Python 3.11+, uv, Parquet, DuckDB, Polars and SciPy sparse modeling; simple tests and CI first.

**Why:** Broad scientific ecosystem and efficient local experimentation.

**Revisit when:** Benchmarking demonstrates a concrete computational or storage bottleneck.

## ADR-0004 — 2022–23 source and reconciliation candidates

- **Date:** 2026-11-23
- **Status:** Provisional
- **Evidence class:** Original BIL decision based on published source metadata.

**Decision:** Use Bentes event Parquet as the leading source-of-record candidate for the 2022–23 pilot. Use official NBA box scores as the score and minutes reference. Compare lineup and possession reconstruction with `pbpstats` on permitted, compatible per-game NBA JSON. Compare events separately with the pinned Shufinskiy NBA Stats V3 CSVs. Consider ESPN-derived events for a separate feed comparison if use is permitted.

**Evidence:** Regular-season and playoff assets exist for the Bentes event, stint and possession tables. GitHub supplies release asset IDs, sizes and digests. A pinned Shufinskiy revision contains separate NBA variants for the same season. Bentes's full field dictionary and exact upstream endpoint lineage are unavailable in its documentation. [Source audit](data-sources.md)

**Alternatives:** A Shufinskiy event archive supplies clearer feed-specific provenance and is the fallback candidate. Direct `nba_api` access requires endpoint-by-endpoint validation and repeatable capture. The Bentes companion tables can measure agreement with its own processing.

**Consequences:** Confirm acquisition and intended use, then verify file contents and reconcile the pilot before accepting a source of record. Score agreement and parser agreement measure different failure modes. Independent parser agreement can still share upstream data defects. [Issue #2](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/2) [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5)

## ADR-0005 — Use archived player IDs for the 2022–23 event pilot

- **Date:** 2026-11-23
- **Status:** Provisional pilot selection. Supersedes ADR-0004's choice of leading event source.
- **Evidence class:** Original BIL decision based on file-level checks and observed parser behavior.

**Decision:** Use the pinned Shufinskiy NBA Stats V2 event archive for the 2022–23 pilot when permitted for the intended use. Reconcile to NBA.com box scores with Bill Mill's game logs as the machine-readable candidate and archived NBA Stats V3 final-period scores as a separate event-feed check. Cross-check BIL parsing with `pbpstats` using locally wrapped V2 events and matching shot charts. Use Bentes's processed data to investigate disagreements.

**Evidence:** The V2 archive covers the observed 1,230 regular-season and 84 playoff games and carries both participant IDs on substitution rows. Bentes lineups contain names and its possession scores fall short of event totals in 218 games. V3 final-period scores agree with Bentes event finals across the pilot. The offline stats parser loaded game samples for both season types after native CDN requests returned 403 in this environment. [Source validation](research/nba-source-validation.md)

**Consequences:** Define stable identity, chronology and duplicate handling in [issue #3](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/3). Official box-score and lineup reconciliation, ambiguous events, full parser coverage and intended-use permissions remain pilot acceptance work in [issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5).

## ADR-0006 — Versioned game streams and evidenced availability

- **Date:** 2026-11-23
- **Status:** Proposed with the canonical data contract.
- **Evidence class:** Original BIL design.

**Decision:** Build stable provider-independent keys around verified NBA identities and use immutable game stream revisions for event, lineup and possession facts. Keep a scoring allocation ledger that can preserve accepted points outside possession totals. Use timestamped evidence for as-of availability and use NBA Eastern played dates for the daily game-agnostic EPM input boundary.

**Evidence:** The source audit found repeated event identifiers, differences in terminal score selection, Bentes possession totals below final scores, and recent archive timestamps that do not establish historical availability. [Source validation](research/nba-source-validation.md) [Canonical data contracts](data-contracts.md)

**Consequences:** The pilot must validate corrections and provenance before accepting a coherent game stream. Data used for historical reconstruction can be checked independently of a claim that an output was published at that time. [Issue #3](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/3) [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5)

## ADR-0007 — Freeze R1 evaluation windows and score immutable forecasts

- **Date:** 2026-11-23
- **Status:** Proposed with the evaluation contract.
- **Evidence class:** Original BIL design.

**Decision:** Develop on history through 2022–23, validate on 2023–24 and 2024–25, and reserve 2025–26 for a registered historical holdout. Predict at the Eastern midnight origin using eligible revisions and transitive fit cutoffs. Freeze the update policy for the holdout and record separately timestamped prediction receipts for prospective claims. Scoring runs reference immutable forecast manifests by digest.

**Evidence:** The published EPM SPM windows end in 2022–23. The pilot uses recent archive snapshots whose timestamps do not establish historical publication of earlier revisions. The canonical contract provides explicit source visibility rules. [EPM methodology](research/epm-methodology.md) [Source validation](research/nba-source-validation.md) [Canonical data contracts](data-contracts.md)

**Consequences:** A strict rolling-origin result depends on dated source evidence. Retrospective replays state their availability limits, and registration protects holdout scores from model selection. Independent basketball outcomes, method fidelity and external EPM agreement remain separate claims. [Validation contract](validation-strategy.md) [Run manifest](run-manifest.md) [Issue #4](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/4)

## ADR-0008 — Archived V3 action order as the offline event-order fallback

- **Date:** 2026-11-23
- **Status:** Provisional pilot decision.
- **Evidence class:** Original BIL decision. The fallback point is documented parser behavior. The substitution of V3 order for data.nba.com order is inferred to be equivalent evidence, not documented as such.

**Decision:** When pbpstats 1.3.11 cannot repair rebound order and would request data.nba.com event order, use the pinned NBA Stats V3 action order of the same game. V3 `actionNumber` equals the V2 `EVENTNUM`. Order by `actionId` and keep the first occurrence of each event number. Apply it only when the V3 and V2 event-number sets are identical, recheck rebound order, and record a warning and a stratum for the game. Keep V2 file order as the primary order.

**Evidence:** The 79 games quarantined as `unresolved_event_order` all reached the parser's live fallback. With V3 order, 70 passed every existing check, including exact player plus-minus and minutes within 2,000 ms against the pinned boxes and V3 period scores. Nine stayed quarantined for other reasons. The 1,131 previously accepted games were unchanged in every output table. Using V3 order from the start instead of V2 recovered only 4 of 22 parser errors and 2 of 4 unsupported reorders, so it was not adopted. [Pilot guide](data-pilot.md) [Experiment log](experiment-log.md)

**Alternatives:** Keep the games quarantined. Request live data.nba.com order, which is unavailable in this environment and would break the offline, pinned build. Hand-edit event order, which the pilot does not allow.

**Consequences:** V3 and data.nba.com order may differ on same-clock ties. Cross-clock moves still quarantine the game, and reconciliation catches errors that change minutes, plus-minus or scores. An ordering error that changes none of those cannot be ruled out, so analyses should be able to report the `v3_event_order` stratum separately. [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5)

## ADR-0009 — Resolve pilot anomalies at the narrowest evidenced scope

- **Date:** 2026-11-23
- **Status:** Provisional pilot decision.
- **Evidence class:** Original BIL design. The parser behaviors these rules replace are documented in pbpstats 1.3.11, and the clock truncation is observed in the pinned feeds.

**Context:** After ADR-0008, 113 of 1,314 games were quarantined. Most of those games had one local anomaly in an otherwise reconcilable game, and quarantining the whole game removed the most anomaly-prone games: overtime (53 of 79 regular-season games accepted), technical free throws, and same-clock substitutions. A whole-game quarantine was needed only when lineups, scores or minutes could not be established.

**Decision:** Keep every whole-game check, and resolve each anomaly only as far as the evidence allows:
1. **Period starters.** When events do not give five starters, try every candidate set and accept only one that alone passes all checks, or a set of candidates that all give an identical reconstruction. This replaces the parser's live box-score request.
2. **Possession labels.** Back-to-back possessions for one team, or a score that contradicts the recorded offense, mark those possessions `unresolved`. They leave the counted possessions, and their points stay in the ledger with the `unresolved` reason. This uses the contract's existing statuses.
3. **Credited lineups.** When only plus-minus fails, choose among the lineup states at the scoring event's clock. Accept the unique smallest set of up to three changes that reproduces the official box, or several that are indistinguishable at that clock. Actual lineups and minutes do not change.
4. **Clock precision.** The minutes tolerance adds 1,000 ms per player substitution at a truncated final-minute clock to the 2,000 ms base.
5. **Last-resort order.** Parse a failed game in archived V3 action order, keeping the cross-clock guard against V2.

**Evidence:**
- The accepted games rose from 1,201 to 1,290. All 84 playoff games are accepted, as are 78 of 79 regular-season overtime games.
- The 1,201 games accepted before are row-for-row unchanged.
- The independent output check passes.
- Marking a V3 substitution disagreement non-blocking, when V2 otherwise reconciles, recovered no games, so it was not adopted. [EXP-0002](experiment-log.md)

**Consequences:**
- Box minutes or plus-minus served as selection evidence in 49 accepted games: 31 starter inferences and 18 credit changes. For those games, the box checks confirm uniqueness rather than independent agreement. V3 period scores, the substitution signature and the structural invariants still apply.
- 54 possessions are unresolved.
- Every rule leaves a warning and a stratum, so analyses can exclude or compare these games.
- The remaining 24 quarantines are source conflicts that only manual adjudication could settle, which the pilot does not allow. [Pilot guide](data-pilot.md) [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5)

## ADR-0010 — Pinned evidence feeds verify builds but do not feed them

- **Date:** 2026-11-23
- **Status:** Accepted for the pilot. The adjudication rules listed below are proposals.
- **Evidence class:** Original BIL design.

**Decision:** Pin archived data.nba.com, NBA liveData and pbpstats.com play-by-play, together with Bentes lineup stints, as a separate evidence snapshot, and compare every build with them. None of them changes acceptance or output.

**Evidence:**
- Lineups agree with Bentes on 99.97% of court time. The two disagreements longer than 2 seconds favor BIL against the official box.
- Possession offense agrees with data.nba on 99.99% of live-ball events in accepted possessions.
- Counted possessions equal pbpstats.com's in 1,257 of 1,290 games.
- V3 order equals data.nba order in all 87 games that used it.
- Every inferred starter set matches both Bentes and liveData's between-period substitutions.
- liveData and data.nba identify two games where V3's period score, and not V2, is wrong.

[External verification](data-pilot.md#external-verification)

**Caveat:** All the feeds derive from the NBA's event log, so agreement shows consistent archiving and parsing rather than external truth.

**Alternatives:** Use the feeds as build inputs immediately. That would turn independent checks into dependencies before their own defects were measured. data.nba and liveData share order numbers and so do not form two independent votes, and Bentes appears to correct lineups with box-derived data.

**Proposals for a later decision:**
1. Accept a V2 reconstruction when V3 alone disagrees on period scores and liveData and data.nba agree with V2. This recovers 2 games.
2. Label unresolved possessions from data.nba when every live-ball event in them agrees. This resolves 28 of the 54 possessions.
3. Derive period starters from liveData's between-period substitutions rather than inferring them from box minutes. That would restore the box as an independent check in the 31 inferred-starter games.

The 10 play-by-play substitution defects are not recoverable without a box-consistent source of record.

**Consequences:** The verification itself can be reproduced. A change to build acceptance needs its own decision and must report the evidence comparison again.

## ADR-0011 — Use archived liveData and data.nba evidence for three narrow decisions

- **Date:** 2026-11-23
- **Status:** Accepted for the pilot. Adopts the three ADR-0010 proposals.
- **Evidence class:** Original BIL design based on the measured agreement in ADR-0010.

**Decision:** The pinned liveData and data.nba archives become build inputs (snapshot `issue-5-v2`), but only for these decisions:
1. **Period starters after the first period.** When events do not give five starters, carry the previous period's closing lineup through liveData's between-period substitutions. Accept the result only when it is consistent with the event-derived starters. The box-value search remains the fallback.
2. **V3 period-score defects.** Accept V2 when V3 alone disputes period scores and both feeds agree with V2 on every disputed period.
3. **Unresolved possession labels.** Label an unresolved possession from data.nba when its offense is unanimous over the possession's live-ball events and does not repeat an adjacent possession's offense.

V2 remains the event source of record.

**Evidence:** See EXP-0004 for the full build.
- liveData settled 33 starter team-periods in 29 games. Their lineups are identical to the box-selected ones, and all 33 match Bentes. Box values now choose the reconstruction in 20 games rather than 49.
- Two V3 period-score defect games are accepted.
- Only 3 of the 54 unresolved possessions could be relabeled. Where data.nba is unanimous, it usually agrees with the parser's label, which already repeats a neighbor's offense, so that possession needs a boundary, not a label. ADR-0010 estimated 28 by counting unanimity alone, which overstated the effect.

**Consequences:**
- For the affected games, the evidence comparisons with liveData and data.nba are no longer independent: starters in `livedata_starters` games, the relabeled possessions, and period scores in `v3_period_defect` games. Bentes and pbpstats.com remain verification-only.
- Earlier builds stay reproducible from snapshot `issue-5-v1` at their recorded commits.

## ADR-0012 — Center the zero-prior RAPM player blocks separately

- **Date:** 2026-11-23
- **Status:** Accepted for the synthetic reference.
- **Context:** Fixed five-player lineups allow uniform shifts in either player block to be absorbed by the intercept. The public EPM methodology leaves player centering and the penalty scale open.
- **Decision:** Regress scaled offensive points on an intercept, five positive offense indicators and five negative defense indicators. Penalize both player blocks equally toward zero and leave the intercept free. Center each block on the unweighted mean over the fitted player universe. Keep observation weights unnormalized and specify the penalty explicitly for each run.
- **Evidence:** The two block-level shifts preserve every prediction. The ridge penalty is minimized within that equivalence class by setting each block mean to zero. The synthetic fixture verifies signs, intercept, recovery and dense agreement.
- **Consequences:** The intercept is the expected rate for zero-effect lineups. Ratings depend on the fitted player universe and the weight-to-penalty scale. Ridge assigns a unique numerical solution even when individual contributions are weakly identified by the lineups.
- **Links:** [Synthetic RAPM specification](research/rapm-synthetic.md), [EPM uncertainty register](research/epm-uncertainties.md), [Issue #6](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/6)

## ADR-0013 — Limit the first historical RAPM fit to stable-lineup possessions

- **Date:** 2026-11-23
- **Status:** Proposed for the M2 baseline.
- **Decision:** Use one unit-weight row per pilot-accepted possession with a single actual lineup pair. Take offensive points from the canonical control ledger. Preserve multiple-lineup intervals and unassigned scores in the reconciliation artifacts.
- **Evidence:** The #19 pilot has 224,039 stable-lineup and 32,417 multiple-lineup accepted possessions. Control scoring rates differ materially between those groups. The contract fixture checks same-clock lineup changes, official score credit and retained-ball allocations.
- **Consequences:** All fitted opportunities have exactly one five-on-five design vector. The cohort excludes 12.64% of accepted possessions. The baseline estimates stable-lineup scoring, and future comparisons can test broader representations.
- **Links:** [Historical row contract](research/rapm-historical-rows.md), [Issue #20](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/20)

## ADR-0016 — Fixed-constant baselines and season-type-keyed history for skill targets

- **Date:** 2026-11-23
- **Status:** Accepted for the #31 baselines.
- **Context:** Estimated Skills needs next-game targets and reference forecasters before any decay or shrinkage is fitted ([EPM-U05](research/epm-uncertainties.md)).
- **Decision:** Target is each player-game's own observed rate. Predictors use only appearances dated strictly before the game, keyed by player and season type. Baselines are career, season, last 10 covered games, 30- and 90-day decay and a league reference, all untuned. Scoring is exposure-weighted MSE and likelihood loss in chronological order on a common cohort.
- **Evidence:** 2022–23 build reconciles against independent SQL. Unshrunk player percentages lose to the league baseline on several shooting statistics.
- **Consequences:** Playoff debuts have no player history until a pooling convention is registered. Career equals season-to-date while one season is loaded. Strict baselines are unavailable with this source.
- **Links:** [Skill histories](research/skill-histories.md), [Issue #31](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/31)

## ADR-0017 — Season-pinned builds and V2 home designation for unflagged box games

- **Date:** 2026-11-23
- **Status:** Accepted for the 2023–24 and 2024–25 outer-validation builds ([#52](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/52)).
- **Evidence class:** Original BIL design.
- **Context:** The pilot pipeline named 2022–23 inputs directly. The 2024–25 Bill Mill team log leaves `home` null for both teams in five neutral-site regular-season games, which stopped the build.
- **Decision:**
  - Pin each season's build and evidence inputs in code from the #51 audit register. Read the season from the snapshot or manifest. Refuse the 2025–26 holdout and any unpinned season. `capture --from-local` may copy verified audit bytes instead of downloading them.
  - When both box home flags are null, take the home team from V2. Every event with a PLAYER1 team and only one of the home or visitor descriptions must place each team on a single, opposite side. The existing V3 terminal-score check must then match the box points under that designation. Mark accepted games `v2_home_designation`. Otherwise quarantine them as `unresolved_home_designation`.
- **Evidence:** V2 designated all five games unanimously, with 173 to 236 attributed events per team. V3 confirmed all five finals. All five games are accepted, and their lineups agree with Bentes on at least 99.93% of court time. The 2022–23 rebuild is unchanged.
- **Consequences:** `neutral_site` stays null because a missing flag does not establish a neutral site. For these games, V2 and V3 set the home/away orientation and the box confirms it. `v2_home_designation` is a lower-trust stratum in `evidence`.
- **Links:** [Outer-validation seasons](data-pilot.md#outer-validation-seasons-202324-and-202425), [Feed coverage audit](research/nba-feed-coverage.md)

## ADR-0018 — League-shrunk exponential skill decay with inner-fold clock choice

- **Date:** 2026-11-23
- **Status:** Proposed for the #32 Estimated Skills reference.
- **Context:** EPM documents per-stat exponential decay tuned by Differential Evolution with day or possession ages, but not the loss, bounds, shrinkage, cold start or playoff handling ([EPM-U05, EPM-U06](research/epm-uncertainties.md)).
- **Decision:** Predict `(N + k m) / (D + k)` from exponentially discounted earlier counts and exposures, shrunk toward the league-to-date rate with per-statistic strength `k`. Fit `(log10 h, log10 k)` per statistic and clock by DE on the #31 likelihood with frozen bounds and seeds. Choose day, games or estimated-possession clock per statistic in inner folds only. Pool regular-season and earlier playoff history (and the league reference) for playoff targets, never fitting on playoffs.
- **Evidence:** Frozen [protocol](research/skill-decay-protocol.md) and [2022–23 results](research/skill-decay-2022-23.md). Synthetic tests check the recursion against a brute-force oracle and fold isolation.
- **Consequences:** Players with no history get the league rate. Single-season retrospective evidence; outer seasons must confirm before any default is fixed.
- **Links:** [Issue #32](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/32), [ADR-0016](#adr-0016--fixed-constant-baselines-and-season-type-keyed-history-for-skill-targets)

## Decision template

### ADR-XXXX — Title

**Date:** YYYY-MM-DD  
**Status:** Proposed / Accepted / Superseded  
**Context:** Why needed  
**Options:** Alternatives considered  
**Decision:** Selected approach  
**Evidence:** Primary source, tests, ablation and evaluation  
**Consequences:** Tradeoffs and limitations  
**Links:** Relevant issues, PRs and research reports

## ADR-0019 — Exclude no-action possessions from RAPM model rows

- **Date:** 2026-11-23
- **Status:** **Proposed, awaiting maintainer sign-off.** It applies to the historical RAPM row set (`issue-82-v1`, [#82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82)). Independent review judged it a material methodology change: it redefines the canonical RAPM sample and reverses the #24 finding that the context-only comparator beats zero-context player RAPM. Until it is accepted, `issue-59-v1` remains the default pin for the #23 and #24 runners.
- **Open alternatives for sign-off:**
  - (a) Exclude all no-action possessions. This is the current implementation: 1,039 possessions, of which 1,003 are eligible.
  - (b) Exclude only possessions that start on `period_end`, a rule known before the possession (962 of the 1,039).
  - (c) Keep all of them in the model rows, as in `issue-59-v1`.
  - Seven mid-period held-ball (`jump_ball`) possessions are classed as no-action under (a). A held ball is arguably a player-attributable outcome, but the effect is immaterial in size.
- **Evidence class:** Original BIL design.
- **Context:** The review of #24 found that possessions starting near a period's end drive most of the measured time-of-period effect. Many are run-outs that contain no shot, free throw, turnover, foul or violation and score 0.
- **Decision:** Give an accepted possession the disposition `no_action` when no `shot`, `free_throw`, `turnover`, `foul` or `violation` event lies inside its own sequence interval. Use only events inside the possession. Do not use its end reason, outcome or score. Exclude these from model rows (exposure 0) but keep them in the disposition and reconciliation ledgers. The check applies after the pilot-status check and before the lineup rule.
- **Evidence:** In 2022–23, 996 of the 6,028 possessions starting with 24 s or less left contain no action, and 962 start on `period_end`. Across the whole pilot, 1,039 accepted possessions have no action event (1,003 eligible and 36 multiple-lineup). All score 0, so the points reconcile unchanged. The #24 review measured an in-sample end-of-period gain of 26.5 that falls to 5.6 without them.
- **Consequences:** The baseline estimates scoring when a possession has a player-attributable outcome, so held-out MSE and the time effect are no longer inflated by a possession-definition artifact. Whole-game total use must add back the zero-point run-outs separately. Whether the exclusion helps or changes RAPM is measured under a frozen addendum protocol, not assumed.
- **Links:** [Row contract](research/rapm-historical-rows.md), [Addendum protocol](research/rapm-no-action-protocol.md)
