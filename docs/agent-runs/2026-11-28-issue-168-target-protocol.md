# #168 expanded RAPM target run design

- **Objective.** Define the first matched target experiment unlocked by #161. Branch `codex/issue-168-target-protocol`.
- **Result.** [Draft protocol](../research/expanded-rapm-target-protocol.md) fixes four cohort arms, #28's joint objective and final penalties, shared chronological origins, paired scorer and reliability diagnostics. #178 implements the pin-checked input step separately.
- **Verification.** Matched the origin calendar, kernel, reference penalties, feature cutoff and ownership mask to #28, #138 and #161. No new fit was executed.
- **Next.** Independently review the protocol and runner, then run a bounded first origin and queue the full rolling experiment after that check.
