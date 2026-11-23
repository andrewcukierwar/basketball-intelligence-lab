# Initial GitHub Backlog

**Tracking convention:** BIL-### are *planning identifiers*, not GitHub issue numbers. Create actual issues incrementally rather than dumping all future work into an unmanageable board.

## Priority 0 — M0 (research foundation)

| ID | Task | Depends on | Definition of done |
| --- | --- | --- | --- |
| BIL-001 | Bootstrap Python project, packaging, tests and CI | — | Install, lint, type checks and tests pass on a clean machine |
| BIL-002 | Primary-source EPM methodology audit | — | Per-claim source links, documented/inferred distinction and explicit open questions |
| BIL-003 | Historical data-source coverage and terms audit | — | Versioned table of seasons, fields, rights, access and quality |
| BIL-004 | Canonical data model and point-in-time contracts | BIL-003 | Schema definitions, IDs, timestamp semantics and test fixtures |
| BIL-005 | Experiment/evaluation contract | BIL-002 | Train/val/test policy, run manifest, temporal leakage tests, baseline metrics |
| BIL-006 | Architecture review and first implementation decision gate | BIL-002–005 | Reviewable decisions, risks, staged M1 plan |

## Priority 1 — M1 (NBA data, one season)

| ID | Task | Depends on | Definition of done |
| --- | --- | --- | --- |
| BIL-007 | Ingest 2022–23 raw play-by-play and schedule | BIL-003–004 | Immutable snapshots and row/coverage manifests |
| BIL-008 | Normalize game, event, player and team IDs | BIL-007 | Consistent canonical keys and source mapping |
| BIL-009 | Construct possessions and active lineups | BIL-008 | Explicit parser and reproducible data output |
| BIL-010 | Validate scores, stints, lineups and anomalies | BIL-009 | Passing quality gate and exception report |
| BIL-011 | Independently reconcile another feed | BIL-010 | Stratified agreement/disagreement analysis |
| BIL-012 | Prepare training-ready 2022–23 sample | BIL-011 | Frozen versioned dataset and documented exclusions |

## Priority 2 — M2 (ordinary RAPM)

| ID | Task | Depends on | Definition of done |
| --- | --- | --- | --- |
| BIL-013 | Implement synthetic sparse RAPM fixture | BIL-001, BIL-004 | Known offense/defense effects recovered under test |
| BIL-014 | Implement offensive/defensive sparse design matrix and solver | BIL-012–013 | Numerical properties and sign conventions tested |
| BIL-015 | Add home/score context and exposure weighting | BIL-014 | Controlled ablation and documented specification |
| BIL-016 | Validate against independent open reference | BIL-014 | Same-input solver agreement and methodology differences |
| BIL-017 | Multi-season RAPM with temporal weights | BIL-016 | Stable estimates, runtime/memory profile and held-out results |
| BIL-018 | Publish baseline RAPM research report | BIL-017 | Frozen run manifest, benchmark and limitations |

## Later milestones

- **M3 — SPM:** RAPM target construction; player feature panels; offense/defense priors; out-of-time validation.
- **M4 — Estimated Skills:** Stabilized skill trajectories; stat-specific decay; Differential Evolution; future-game statistical evaluation.
- **M5 — Integrated EPM:** Prior-centered career RAPM; daily expected ratings; model component ablations.
- **M6 — Tracking:** Defensive feature coverage and value-add experiments.
- **M7 — Replication report:** Independent predictive validity; permitted external fidelity comparisons; gaps report.
- **M8 — Operations:** Incremental data ingestion and rated daily model snapshots.
- **R2+ — Further research:** DARKO, LEBRON, cross-method comparisons, original intelligence model and product.

## Issue template / PR quality bar

Every research issue should specify: question, evidence class, dependencies, inputs/outputs, tests, acceptance criteria and what would falsify the proposed improvement.

A model PR is not complete without updated methodology docs, non-leaking evaluation, reproducible metrics and a record of failures/limitations.

**Do not start frontend, odds optimization, or neural extensions during M0–M2.**