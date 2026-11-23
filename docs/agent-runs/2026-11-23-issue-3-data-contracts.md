# Issue #3 canonical NBA data contracts

- **Date:** 2026-11-23
- **Status:** Design and synthetic fixture independently reviewed. Ready for maintainer review.
- **Branch:** `codex/issue-3-data-contracts`, based on merged source audit `892be51`.
- **Commits:** `905fd40` (contract and fixture), `5c7f590` (clock and schedule review corrections).
- **Issue and PR:** [Issue #3](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/3) and [PR #10](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/10).

## Results and decisions

- The [contract](../data-contracts.md) defines typed keys and provider crosswalks, immutable game stream revisions, event/stint/possession boundaries, scoring allocations, box and tracking observations, coverage, and feature snapshots. The [decision record](../DECISIONS.md) explains why an audited source clock, score ledger and evidenced availability are separate concerns.
- Strict views select evidenced revisions at the cutoff and apply retractions and final status. The daily game-agnostic EPM convention uses the Eastern NBA played date. Current archive snapshots with later capture evidence remain useful for retrospective work.
- Independent review found gaps in clock restoration and replacement game IDs. The corrected contract separates displayed time from reconciled elapsed time, and the as-of schedule hides superseded IDs only when a verified relation becomes visible. Re-review confirmed both corrections.

## Verification

| Check | Observed result |
| --- | --- |
| Ad hoc fixture and contract assertions using `.venv/bin/python` | Checked the synthetic game's keys and provenance, dense sequence, restored clock, pre- and post-substitution lineups, 48-minute stint totals, and score reconciliation across assigned and retained-ball points. |
| Ad hoc cutoff assertions | Checked publication equality, corrected and retracted revisions, unknown availability, archive capture, NBA Eastern midnight in winter and summer, schedule replacement, cancellation, relation retraction and cycle rejection. These checks exercise examples. Production normalization tests are planned in the contract. |
| `.venv/bin/pytest -q`, `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, `.venv/bin/mypy src`, Markdown links and `git diff --check` | Passed. Pytest ran the existing smoke test. [CI on the reviewed correction](https://github.com/andrewcukierwar/basketball-intelligence-lab/actions/runs/45191531459) |
| Independent review | Examined exact diffs `892be51..905fd40` and `905fd40..5c7f590`. Reproduced fixture arithmetic, attribution and cutoff checks. No remaining blockers. |

## Next work

- [Issue #4](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/4) should apply the cutoff and revision rules when defining train and holdout periods, input manifests and output freeze requirements.
- [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) should use authorized snapshots to implement the mappings and run the anomaly plan. Full per-player and possession reconciliation, score attribution choices and real source availability remain pilot verification work.
