# #170 availability-aware minutes design

- **Objective.** Specify a paired prospective minutes benchmark against the last-ten-game baseline. Branch `codex/issue-170-availability-registration`.
- **Result.** [Draft protocol](../research/availability-minutes-protocol.md) freezes a proposed single status-weight rule, cutoffs, roster and normalization rules, coverage, scoring, intervals and fallback. The design separates the new cohort from the running #44 box-only comparison.
- **Verification.** Inspected the #39 projection and the existing #55 capture receipt and crosswalk interfaces. One captured report date was present. No retrospective forecast outcomes, external sports results, or private availability rows informed the weight rule.
- **Remaining.** Implement and verify a per-player status parser and as-of roster input, then freeze an eligible cohort once the necessary sources and repeated captures exist. No scorer ran.
