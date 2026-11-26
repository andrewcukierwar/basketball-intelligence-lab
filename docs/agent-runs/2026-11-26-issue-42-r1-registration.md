# Agent run: #42 R1 joint confirmatory registration (draft)

- **Date:** 2026-11-26
- **Status:** Draft registration in PR, awaiting maintainer review. **No 2025–26 data captured or read.**
- **Related issues:** #42, #36, #39, #40, #38, #41, #55
- **Branch:** `claude/issue-42-r1-registration`

## Work completed

- **ADRs.** ADR-0030, ADR-0031 and ADR-0032 are marked Accepted on maintainer approval.
- **Draft.** The [registration draft](../research/r1-confirmatory-protocol.md) covers:
  - **P1 (primary):** EI vs context-offset RAPM, possession MSE.
  - **P2:** other comparators and ablations.
  - **T1 and T2:** team margin and win probability.
  - **S:** rating stability.
  - **D1:** EPM agreement, after scoring.
  - **Freeze:** two stages, with the code frozen and reproduced on 2024–25 before any holdout byte is fetched.
  - **Run rules:** a single capture, the unchanged quality gate with no discretion, explicit cutoffs, ordered pre-score freezing and a committed access log.
- **Review.** An independent pre-freeze review (Sonnet subagent) found 8 blockers, all addressed in the draft:
  - row seasons for `W2`;
  - unfrozen code and a circular digest guard;
  - an unregistered playoff cutoff;
  - discretion in the gate and capture rules;
  - an unimplementable order of operations;
  - a retrospective access log;
  - a verdict-rule inconsistency with #39;
  - discretionary D1 capture selection.

## Next actions

1. **Maintainer review** of the draft (PR).
2. **Implement §4.0:** parametrized runners, verdict rule and the code-constant guard. Reproduce #36's and #39's 2024–25 predictions exactly. Independent code review.
3. **Freeze commit (stage B).**
4. **Capture, gate, fit and freeze, score, D1, report,** each logged.
