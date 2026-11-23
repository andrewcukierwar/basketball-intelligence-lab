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
