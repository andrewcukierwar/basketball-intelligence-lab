# #162 near-threshold playoff recovery

- **Objective.** Diagnose four one-game-short playoff cohorts and identify evidence-backed recovery or a separately approved training sensitivity. Branch `codex/issue-162-playoff-recovery`.
- **Result.** [Audit](../research/historical-playoff-recovery-audit.md) enumerates all 12 quarantines. Same-clock, free-throw-miss and control-ownership replay recovered zero. Six V3-derived Bill Mill candidates match official score, minutes and plus-minus across three seasons. The six other candidates fail the final-score or plus-minus check.
- **Verification.** Four selected-game pilot replays retained all twelve quarantines and passed their exported artifact checks. DuckDB compared archived player rotations against official box totals on each game. The audit records eight checked provider partition digests and exact retained game, minutes and player counts.
- **Blocker.** No independently supported decision exists yet for the affected order, lineup or ownership sequences. The regular-season-only sensitivity needs a separate policy decision. No new games or rows are eligible.
