# #178 experimental expanded RAPM inputs

- **Objective.** Make the #161 input registration executable for #168. Branch `codex/issue-168-expanded-target-inputs`, based on `e0c85b3`.
- **Result.** The opt-in loader pins the registration bytes, audits archived row, pilot and box lineage, and removes the registered #138 contradiction keys by full game, stream revision and possession identity. The existing historical loader exposes the stream revision only when requested. The new selector verifies the date boundary and per-season, game-type and cohort counts before the dry run reports success.
- **Verification.** The CLI verified all 16 private archive inputs and reported 3,368,797 eligible rows. Focused expanded, targets and multi-season RAPM suites passed 54 tests. Ruff formatting/lint and mypy passed. Synthetic fixtures check scoreless reversal, a same-clock ambiguous turnover and refusal of changed registration bytes.
- **Next.** #168 still owns the target run registration, matched fits and separate score replay. This checkpoint produces no target fits or new rating data.
