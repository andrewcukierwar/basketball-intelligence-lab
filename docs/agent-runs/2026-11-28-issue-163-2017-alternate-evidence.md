# #163 2017–18 alternate-source audit

- **Objective.** Check new, V3-derived evidence for #99's remaining quarantines. Branch `codex/issue-163-2017-alternate-evidence`.
- **Result.** [Audit](../research/2017-18-alternate-source-audit.md) finds 154 regular-season and two playoff quarantines with exact official score, player minutes and plus-minus in Bill Mill. Separates alternate-source coverage from the unresolved burden in earlier accepted games. Taking every additional event as a resolved possession would still leave a 0.286% unresolved share, above the 0.1% limit.
- **Verification.** DuckDB checked all 165 quarantines against the pinned official logs and counted 80,279 alternate events. The comparison used the current 2017–18 development build and archived provider bytes, with no parser modifications or new modeling rows.
- **Blocker.** Event-level source qualification and a resolution for the existing accepted-game unresolved possessions are both required. The 2017–18 gap stays open.
