# Refresh recovery and Skills SPM retraining

## Delivery

- Reconciled the live tracker with Claude's handoff. [PR #152](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/152) merged at `dd5f411` and closed #145 and #43. Both issues are labeled `state: done`. Re-review caught invalid rollback targets, unrecorded revisions after retirement, and interrupts after atomic rename. The corrections preserve the original directory, fail closed on an unrecorded revision and record post-publication uncertainty with the artifact ID. [Runbook](../refresh.md#failure-outcomes-drills-and-recovery-runbook-145)
- Marked [#44](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/44) blocked. Its remaining requirements are an authorized live final-game capture source, independent receipts and a prospective registration. #55 and #133 retain their existing blockers.
- Claimed [#148](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/148) and completed the registered retraining and comparisons in [PR #153](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/153). Five frozen fit origins matched the #28 clock. Offense passed the K0 diagnostic. Retraining improved on the applied-Skills comparator in the retrospective regular seasons and was inconclusive against raw-box EI. [Results](../research/skills-spm-retraining.md) · ADR-0043
- Claimed [#137](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/137) and published the disjoint schedule-block design and runner in [PR #154](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/154). That experiment has its own results and tracking record.

## Verification

- #145 reviewed fix `958dd320` has the same tree as remote head `a4ece05e`. Both PR CI runs and main CI passed. Locally, 518 tests passed and three archived-input tests skipped. Ruff, strict mypy and `git diff --check` passed. All nine pinned drills passed in 8.11 s. Independent re-review exercised legacy #144 and mixed-version recovery alongside the new regressions.
- #148 preregistered run `8fe3528`, same tree as remote `a8c6f16`, passed all alignment and provenance checks. Ran `bil.models.spm_skills` using the registered protocol digest from a clean checkout. Peak memory was 2,742.6 MiB. Focused SPM and bundle tests passed 17/17. Strict mypy and Ruff passed. Independent pre-run review kept the K0 shot-volume slice on observed FGA/36 and added explicit opening lineage before any outcome scoring.
- The shell could not resolve GitHub. Remote branches used the GitHub connector with fast-forward leases and compared local and remote tree hashes before integration. The project checkout's pre-existing untracked handoff remained in its own worktree.

## Next gated work

#41 remains the separate retrospective Actual-impact experiment. The roadmap feasibility milestones are downstream of their independent review and authorization gates. The live run awaits resolution of the source and receipt requirements documented on #44.
