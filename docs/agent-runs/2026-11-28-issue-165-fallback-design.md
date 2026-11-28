# #165 validated game-level alternate design

- **Objective.** Define a bounded game-level alternate source, using existing normalized contracts and quality checks. Branch `codex/issue-165-fallback-design`.
- **Result.** [Design](../research/game-source-fallback-design.md) records candidate capabilities, source precedence, explicit revision and cutoff rules and a staged validation matrix. The first implementation would name one alternate per approved scope and fail closed on unqualified or conflicting sources.
- **Verification.** Cross-checked the design against the existing source and revision contract, #138 ownership rule, #160 evidence and the historical diagnostics. No adapter, capture job or production selection was changed.
- **Blocker.** #133 still needs a qualified alternate and independent event and lineup evidence before an end-to-end validation or canonical adoption.
