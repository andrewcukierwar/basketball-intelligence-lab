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
- **Status:** **Accepted** (maintainer decision 2026-11-24) as the initial stable-lineup RAPM convention. The excluded multiple-lineup possessions are materially nonrandom. Alternative representations, such as stint-level or fractional exposure, are a bounded future research question ([#110](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/110)), and it does not block current work.
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

## ADR-0019 — Keep run-outs in RAPM model rows and exclude only verified pseudo-possessions

- **Date:** 2026-11-23
- **Status:** **Accepted. Maintainer decision 2026-11-23, principle B:** exclude only verified pseudo-possessions that offer no live-ball opportunity, keep run-outs, and never condition eligibility on later actions or realized outcomes. Applies to the historical RAPM row set ([#82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82)). **Departure from the literal option:** the maintainer selected option (b), excluding the 962 possessions that start on `period_end`, conditional on verifying that the start event is sufficient evidence and that no legitimate live-ball possession is removed. Verification failed, because all 962 had 3–24 s of live-ball clock after a change of control. Applying the maintainer's stated principle, the canonical set therefore departs from literal option (b) and adds no exclusion beyond the pilot's under-3 s rule. Literal (b) is kept as the `period_end_start` sensitivity variant. A focused independent re-review approved this canonical revision (abed529) before PR #91 merged. **Maintainer confirmation 2026-11-24:** the maintainer explicitly approved the departure from literal option (b). The original authorization was conditional, and the evidence shows those possessions are legitimate playing opportunities. Keep the current canonical row set, retain genuine run-outs and held balls, and preserve both alternative exclusion definitions as sensitivity variants. The pilot's under-3 s pseudo-possession convention stays for now, with its limitations documented. Eligibility rules are never chosen by which one gives the most favorable model comparison.
- **Evidence class:** Original BIL design.
- **Context:** The review of #24 found that possessions starting near a period's end drive most of the measured time-of-period effect. Many are run-outs that score 0. The first implementation excluded every possession with no action event. Independent review judged that a material change, because it filters rows by how each possession turned out.
- **Decision:**
  - The canonical row set adds no exclusion beyond the pilot's. The pilot already marks genuine pseudo-possessions as `excluded`. The canonical rows are the pilot-eligible set (accepted, stable lineup), identical to `issue-59-v1`. The registered #23 and #24 results stand.
  - Two sensitivity alternatives are versioned and selectable with `--variant`: `period_end_start` drops accepted possessions whose first event is `period_end`, and `no_action` drops accepted possessions with no shot, free throw, turnover, foul or violation event.
  - The rule was not chosen by whether player RAPM beats the context-only comparator.
- **Verification (2022–23, `scripts/audit_period_end_possessions.py`):** The condition that a `period_end` start shows no live-ball opportunity fails.
  - All 962 accepted `period_end`-first possessions begin after a change of control (312 defensive rebounds, 297 made shots, 260 turnovers and 93 final free throws) with 3 to 24 s on the clock (median 9 s). 729 are in the final period.
  - The first audit measured duration over the possession's own events, which is zero for a one-event possession, so it showed nothing about the clock.
  - The pilot's 1,567 excluded `period_end` starts all have under 3 s left, and 1 unresolved start has 1 s. The pilot rule covers the real pseudo-possessions.
- **Consequences:** The baseline keeps run-outs. Sensitivity runs show small differences: RAPM versus league −14.09 (canonical), −13.16 (`period_end_start`) and −13.17 (`no_action`), but a larger fall in the time-block gain (−25.7 against about −5). A model fit on canonical rows scores 1.7 to 1.9 MSE worse than fits on the sensitivity rows on canonical held-out rows. These describe the sample and do not select the rule.
- **Links:** [Row contract](research/rapm-historical-rows.md), [Report](research/rapm-no-action-2022-23.md), [Protocol v3](research/rapm-no-action-protocol-v3.md)

## ADR-0020 — Build without liveData where the archive lacks it, as a weaker-verification stratum

- **Date:** 2026-11-23
- **Status:** Accepted for the 2017–18 through 2021–22 builds ([#25](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/25)).
- **Evidence class:** Original BIL design.
- **Context:** The #51 register records NBA liveData (`cdnnba`) as absent from the pinned Shufinskiy inventory for 2017–18, 2018–19 and 2019–20. The pilot read liveData as a required build input under ADR-0011, so those seasons could not be built.
- **Decision:**
  - Pin every other feed for these seasons. The snapshot omits liveData, and the build passes no liveData to the cross-feed reader.
  - Without liveData, ADR-0011's starter rule falls back to the box-guided search. Its V3 period-defect rule cannot be met, so those games stay quarantined. The data.nba relabel rule still applies.
  - Label every game without liveData evidence `no_livedata`, a lower-trust stratum in `evidence`.
  - `evidence` stages an empty liveData table for such a season and adds a V3 versus data.nba period comparison.
  - Acceptance thresholds do not change.
- **Evidence:** 2019–20 meets every M1 threshold without liveData. Its lineups agree with Bentes on 99.97% of court time, and all 20 box-inferred starter team-periods match Bentes. Its 3 V3 period-score quarantines are exactly the 3 games where V3 and data.nba disagree. The 2022–23 rebuild is row-identical to `issue-19-v6` apart from `ingested_at`.
- **Consequences:**
  - Seasons before 2020–21 have weaker verification for starters and period scores. Downstream fits should treat `no_livedata` as a sensitivity stratum.
  - Any other missing feed is still an error.
- **Links:** [Development seasons](data-pilot.md#development-seasons-201718-through-202122), [Feed coverage audit](research/nba-feed-coverage.md)

## ADR-0021 — Pregame context as a fitted link-scale adjustment of the frozen skill forecast

- **Date:** 2026-11-23
- **Status:** Proposed for the #33 context experiment. Nothing is adopted as a default.
- **Context:** EPM describes context families and a game-agnostic versus game-optimized split but not their forms, covariates or inputs ([EPM-U07](research/epm-uncertainties.md)). #32 froze the game-agnostic skill.
- **Decision:** Keep the #32 forecast frozen as the game-agnostic skill, including for the SPM prior (#30) through `bil.features.skill_snapshot.skill_snapshot`. Test context only as a link-scale adjustment (log for per-36 rates, logit for fractions) with an intercept and ridge-penalized standardized terms for home, team rest, opponent allowed rates, own-team rate and league trend, fitted only on earlier blocks. Every input must come from the schedule or from strictly earlier games, with the source date audited. Aging is untested because the pinned sources have no birthdates. Retain a factor only when it beats both the agnostic forecast and an intercept-only control under game and player clustering and in every outer block.
- **Evidence:** Frozen [protocol](research/skill-context-protocol.md) and [2022–23 results](research/skill-context-2022-23.md). Opponent allowed rates passed the rule for 9 of 13 statistics. Home, rest, team and trend terms did not beat recalibration. Context did not transfer to the playoffs.
- **Consequences:** Gains are small (median 0.29% MSE) and single-season. The snapshot excludes context by design. Outer seasons must confirm before any context is adopted.
- **Links:** [Issue #33](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/33), [ADR-0018](#adr-0018--league-shrunk-exponential-skill-decay-with-inner-fold-clock-choice)

## ADR-0022 — Revise the M1 quality policy: hard correctness, dataset eligibility and representativeness

- **Date:** 2026-11-24
- **Status:** Accepted (maintainer decision of 2026-11-23, [#89](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/89)). Supersedes the stratum and season-type reading of the M1 table in [data-pilot.md](data-pilot.md#m1-acceptance-for-the-202223-pilot). Does not change any check in code.
- **Evidence class:** Original BIL design.
- **Context:** The M1 table was written after 2022–23 was observed and treated every row as a pass/fail gate for the whole season. The 2017–18 through 2021–22 builds ([#25](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/25)) and the outer-validation builds ([#52](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/52)) showed what that reading does in practice. Two seasons (2018–19 and 2021–22) were recorded unavailable only because the regular-season overtime stratum, with 67 and 58 games, fell below 95%. 2021–22 missed by part of one game. The 2024–25 playoffs have an unresolved-possession share of 0.135% while the season is at 0.070%. The revision follows those observed data-quality findings. It is not a way to rescue a result, and it was decided after the original results were recorded.
- **Decision:** Separate three questions that the original table mixed.
  - **Hard correctness (unchanged, never relaxed to raise coverage).** Every `check` invariant (structural, identity, chronology, scoring, lineup, minutes, plus-minus reconciliation) must pass for every accepted game. A violation cannot be waived by this policy.
  - **Dataset eligibility (hard limits kept).** At least 97% of expected games accepted for each season type, and at most 0.1% unresolved possessions over the full season. A season that misses either is not eligible as built.
  - **Representativeness (target and warning, not a gate).**
    - The 95% stratum coverage target (overtime, technical free throw, same-clock substitution) is kept as a target. A miss is a quality warning that needs investigation and sensitivity analysis, not automatic rejection of the season.
    - Unresolved-possession shares are reported separately for each season type. A season type above 0.1% while the full season is within the limit is a warning to document.
    - Material systematic missingness or demonstrated bias can still disqualify a dataset for a particular use. The diagnostic `scripts/season_quality.py` ([report](research/season-quality-2017-2025.md)) tests for it with a documented rule.
  - **Application.** The policy applies to every season in the same way, retroactively as a classification. The original pass/fail results stay in `data-pilot.md` and the experiment log next to the revised ones.
- **Season decisions (maintainer):**
  - 2018–19 and 2021–22: conditionally authorized for primary retrospective training, subject to the missingness analysis.
  - All individual game quarantines are retained.
  - 2017–18: stays outside the primary cohort pending remediation ([#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53) feasibility). It fails two hard limits.
  - 2024–25: accepted as an outer-validation season, playoffs included, with the elevated playoff unresolved rate documented.
- **Evidence:** [Season quality report](research/season-quality-2017-2025.md) and [EXP-0012](experiment-log.md). Data-level only: no model was fitted or scored.
- **Revision note:** The diagnostic's unresolved-possession flag rule was revised after its first run, because cells with 3 events gave infinite rate ratios: it now needs at least 5 events per cell and a Bonferroni adjustment. A later review found the 1,000-replicate bootstrap could not reach its own flag thresholds, so the run uses 20,000 replicates and refuses a floor above 1%. Neither revision touches any eligibility threshold, and the conclusions on 2018–19, 2021–22 and the 2024–25 playoffs did not change. Details are in the report's revision history.
- **Consequences:** Eligibility is now a per-use judgment backed by the diagnostic, so a later change in a build or snapshot needs the diagnostic rerun. A conditionally authorized season whose analysis shows material bias for its use would be reported to the maintainer, who decides. The thresholds themselves were not changed.
- **Links:** [Issue #89](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/89), [ADR-0020](#adr-0020--build-without-livedata-where-the-archive-lacks-it-as-a-weaker-verification-stratum), [ADR-0017](#adr-0017--season-pinned-builds-and-v2-home-designation-for-unflagged-box-games), [Development seasons](data-pilot.md#development-seasons-201718-through-202122)

## ADR-0023 — Repair late-entered event order from data.nba entry order (opt-in)

- **Date:** 2026-11-23
- **Status:** Proposed for [#90](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/90). Implemented behind `build --order-repair`, off by default. No default build changes. **Maintainer decision 2026-11-24:** further development and evaluation are authorized under the conditions below ([#99](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/99)). Canonical use is approved only after an independent review validates these safeguards. Until then, repaired outputs are experimental.
- **Maintainer conditions (2026-11-24):**
  - Raw source records and original timestamps stay immutable.
  - Ordering must be supported by evidence. Corrected clocks are constrained to valid neighboring clocks where justified.
  - Substantive events may shift by at most 24 s at first. A larger correction is rejected, never silently truncated. Staying under the ceiling does not by itself make a correction valid.
  - Instant replays and non-substantive metadata are handled separately and must not distort basketball event chronology.
  - Changes to shots, free throws, turnovers, rebounds and substitutions need stronger corroboration, especially where possession attribution or lineup exposure could change.
  - Every modification is recorded: original and corrected clock, signed shift, event type, justification and source evidence.
  - The hard reconciliation checks stay unchanged, with added verification of possession and lineup attribution. The report must say which checks become less informative because repaired clocks are monotone by construction.
  - Repaired games form a separately identifiable lower-trust stratum.
  - The repair applies to failed games first. It never replaces an accepted game merely because it leaves fewer unresolved possessions, which withdraws the "second use" above. It is not applied to seasons that already pass by default.
  - 2017–18 stays outside the primary cohort unless it meets every ADR-0022 hard requirement.
- **Evidence class:** Original BIL design, applying ADR-0010's rule that evidence feeds may adjudicate only narrow, checkable decisions.
- **Context:** V2 sorts events by clock. A late stat correction keeps its original clock, so V2 can place it before an event that preceded it. 168 of 180 2017–18 quarantines are event-order failures (166 of 178 in the regular season), and their rate follows the rate of such events, which is highest from October to mid-November. V3 order equals V2 order in 37% of them. data.nba `ord` records entry order and is present from 2017–18.
- **Decision (proposed):** After the V2 attempt and the V3-primary retry both fail, retry in data.nba entry order. Require `ord` for every event, distinct and period-monotone. Within each period keep the longest non-increasing run of clocks (earliest-entered on ties) and give every other event its predecessor's clock. Never re-clock period boundaries. Run every unchanged check on the new stream, label it `datanba_event_order` (lower trust), and record the largest shift. A second use offers the repair to accepted games with unresolved possessions and keeps it only when it leaves fewer. That selection optimizes the hard-gate metric (unresolved possessions), so a reduction in 2017–18's 0.283% is partly selected, not independently found.
- **What the repair changes:** it gives each displaced event its predecessor's clock, so repaired clocks are monotone by construction. `unsupported_reorder` and `unresolved_clock_reset` cannot fire on those events. No check is relaxed, but those two lose discriminating power on repaired games. In the 225 games of scratch build `-v2`, 384 events were re-clocked, 160 (42%) of them earlier in game time. They include 44 made field goals, 8 free throws and 21 substitutions. Shifts range from -47 s to +518 s: a dunk at -41 s, free throws at +47 s, a turnover at +156 s, a jump ball at +208 s. The largest are replays (+518, +498, +289 s). 41 events moved more than 24 s and 17 games have a shift above 60 s.
- **Safeguard options for the maintainer (none implemented):**
  - (i) clamp each displaced event to its nearest kept neighbor's clock, not only its predecessor's;
  - (ii) cap the shift at about 24 s for events with actors and refuse the repair above that;
  - (iii) handle replays (type 18) separately, since they carry the largest shifts and no lineup or score effect;
  - (iv) report signed shifts in the per-game warning and the manifest. `scripts/event_order_diagnostics.py --shifts` already reports them for any repaired build.
- **Not decided:** which of those safeguards to adopt, and whether to apply the repair to seasons that already pass.
- **Evidence:** [Backfill feasibility](research/backfill-feasibility.md). On 2017–18, 137 of 168 order-class quarantines recover, `check` passes 26 of 26, and Bentes agreement stays at 99.97%. Coverage reaches 96.6% (5 games short) and unresolved possessions fall from 0.391% to 0.283%, so 2017–18 still fails the hard limits.
- **Consequences:** data.nba shares upstream lineage with V2 and V3, so the box and Bentes reconciliation carries the verification burden. Not adopting it leaves 2017–18 outside the primary cohort.
- **Links:** [Issue #90](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/90), [ADR-0010](#adr-0010--pinned-evidence-feeds-verify-builds-but-do-not-feed-them), [ADR-0011](#adr-0011--use-archived-livedata-and-datanba-evidence-for-three-narrow-decisions), [ADR-0020](#adr-0020--build-without-livedata-where-the-archive-lacks-it-as-a-weaker-verification-stratum)

## ADR-0025 — Two-season unit-weight window with split penalties for the multi-season RAPM baseline

- **Date:** 2026-11-24
- **Status:** **Accepted** (maintainer decision 2026-11-24) as the frozen multi-season zero-prior RAPM reference ([#26](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/26)). Independently reviewed (approved). The near-tie findings and alternative configurations are preserved. No further resources go to distinguishing near-identical candidates without a concrete research hypothesis.
- **Evidence class:** Original BIL design, Experimental evidence.
- **Context:** Multi-season RAPM needs a temporal weighting and penalties chosen without outer-season or EPM information. #77's split penalties are not merged. ADR-0015 leaves the half-life free and the weights unnormalized.
- **Decision:**
  - The multi-season zero-prior baseline uses `W2`: rows played 1 to 730 days before the cutoff, unit weight, with $\lambda_o$ = 4,000 and $\lambda_d$ = 8,000.
  - It refits on a fixed calendar schedule (1 October, 1 December, 1 February, 1 April and the first playoff date).
  - The choice was made on 2021–22 and 2022–23 development folds, by a two-phase procedure. The development protocol was committed before any fit. A frozen addendum was committed before any outer read. The outer runner refuses to run without that committed addendum on a clean tree.
- **Evidence:**
  - Development: lowest pooled MSE of eight candidates (windows of 1, 2, 3 and 5 seasons; decays with 90- to 730-day half-lives). Four candidates are within 0.3 units. The choice is unchanged when 2018–19, 2021–22, overtime or `no_livedata` games are excluded.
  - Outer seasons: −23.4 (−26.5 to −20.3) against the league mean and +8.8 (+4.1 to +13.7) against the context-only comparator, regular season. Player RAPM with a context offset beats context by 24.7. [Report](research/rapm-multiseason.md)
- **Consequences:**
  - The defense penalty is twice the offense penalty, and defense-only predictions still do not beat the league mean.
  - Player RAPM alone is not better than context-only possession scoring on the canonical rows. Proposal, informed by outer-validation evidence: later informed-RAPM work could compare against the context offset model rather than plain RAPM.
  - The selection is a near-tie, so `W3`, `H365` and `H730` are acceptable alternatives on this evidence.
- **Links:** [Protocol](research/rapm-multiseason-protocol.md), [Addendum](research/rapm-multiseason-outer-addendum.md), [ADR-0015](decisions/0015-dated-rapm-clock-and-decay.md), [ADR-0019](#adr-0019--keep-run-outs-in-rapm-model-rows-and-exclude-only-verified-pseudo-possessions)

## ADR-0026 — Maintainer decisions of 2026-11-24: M2 acceptance, informed-RAPM comparators and partial-history SPM targets

- **Date:** 2026-11-24
- **Status:** Accepted (maintainer decision).
- **Evidence class:** Maintainer decision on Experimental evidence ([M2 report](research/rapm-m2-report.md)).
- **Decisions:**
  - **M2.** M2 is accepted as sufficient for downstream model development, and its empirical limitations are documented. [#27](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/27) closes after an independent reproducibility replay of the ADR-0025 configuration. The replay compares output artifacts and aggregate results under documented tolerances and is not used for further model selection. The record keeps numerical correctness, demonstrated predictive validity and unresolved limitations distinct.
  - **Comparators for informed RAPM.** Context-adjusted zero-prior RAPM (RAPM with the context offset) becomes an additional primary comparator. Standalone RAPM, context-only and league-average comparators are kept. Evaluation covers both possession-level and team-level performance, and the same configuration is not assumed to win every objective.
  - **SPM targets ([#28](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/28)).** Provisional independent long-window RAPM training targets are authorized on the currently eligible seasons: 2005–06 through 2007–08, 2015–16, 2016–17, and 2018–19 through 2022–23. Two references are evaluated: a contiguous 2018–19 through 2022–23 reference and an extended eligible-history reference.
    - The target objective, weighting, regularization and reliability are specified separately from ADR-0025's two-season predictive configuration.
    - Historical gaps, real elapsed time, player exposure, era differences, roster changes and verification strata are handled explicitly. A missing season never counts as time not elapsed.
    - Earlier targets never use future games or revisions.
    - Offensive and defensive targets stay separate.
    - Every artifact is labelled a **partial-history methodology replication**, not a full historical EPM replication.
  - **#53.** SPM development does not wait for #53. Newly eligible seasons enter through versioned datasets and controlled incremental experiments, and existing targets are never silently changed.
  - **Holdout.** The 2025–26 confirmatory holdout is not accessed or scored. It stays reserved for the registered R1 release protocol.
  - **Autonomy.** Agents may make reversible, bounded engineering and experimental decisions within the existing research standards. They escalate changes to:
    - hard correctness requirements;
    - material model estimands;
    - confirmatory holdout boundaries;
    - source authorization;
    - irreversible or inadequately validated methodology.
    A negative experimental result is an acceptable outcome.
- **Links:** [ADR-0013](#adr-0013--limit-the-first-historical-rapm-fit-to-stable-lineup-possessions), [ADR-0019](#adr-0019--keep-run-outs-in-rapm-model-rows-and-exclude-only-verified-pseudo-possessions), [ADR-0023](#adr-0023--repair-late-entered-event-order-from-datanba-entry-order-opt-in), [ADR-0025](#adr-0025--two-season-unit-weight-window-with-split-penalties-for-the-multi-season-rapm-baseline), [#110](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/110), [#111](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/111)

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
