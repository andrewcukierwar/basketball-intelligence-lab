# Architecture and Research Decisions

Maintain append-only decision records. Each entry should identify the date, status, alternatives, justification, implementation link and validation evidence.

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
