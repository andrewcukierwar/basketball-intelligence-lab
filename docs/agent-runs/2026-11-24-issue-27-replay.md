# Agent run: ADR-0025 reproducibility replay (#27)

- **Date:** 2026-11-24
- **Status:** Awaiting review
- **Related issues:** #27 (ADR-0026 closing condition), #26
- **Branch / commit / PR:** `claude/issue-27-replay`, PR referencing #27 (not merged)

## Objective and authorized scope

Replay the frozen ADR-0025 configuration (`W2`, 730 days, unit weights, 4,000 / 8,000) with the existing runner and compare artifacts and aggregates with the #26 runs under tolerances documented in advance. No selection, no new configuration, no EPM, no 2025-26 data.

## Work completed

- `docs/research/rapm-replay-protocol.md` committed before any run.
- `scripts/compare_rapm_runs.py` and `tests/test_compare_rapm_runs.py` (9 tests).
- Dev run to `issue-27-replay-dev-v1` (1,149 s) and outer run to `issue-27-replay-outer-v1` (11.1 s), from a clean tree. The dev run completed without interruption.
- EXP-0016, a section in the M2 report, this handoff.

## Key decisions and discoveries

- Everything numerical reproduces with maximum deviation exactly 0, with identical library versions. Seeds are fixed (2023).
- The outer guard needs the dev manifest whose digest the addendum froze, so the replay passed the original `issue-26-dev-v1/manifest.json`. No guard was changed.
- Two comparator findings. (1) The ignore list missed two solver-timing keys, which the protocol already classed as reported. Added by a documented protocol amendment, with no tolerance change. (2) `addendum.addendum_commit` differs because the #26 PR was squash-merged (`57fe88e` not in main). The addendum SHA-256 matches. Left as a recorded failed leaf, not special-cased.

## Verification performed

| Check | Actual result |
| --- | --- |
| compare dev | PASS, all groups, max deviation 0 |
| compare outer | Formal FAIL under the protocol on 1 provenance leaf (addendum commit hash, changed by the squash merge). Every output and aggregate is identical. The lead judged the ADR-0026 requirement met; this was not a protocol or maintainer waiver. |
| `uv run pytest -q` | exit 0, 313 passed, 2 skipped |
| `ruff check`, `ruff format --check`, `mypy src` | all clean |
| Independent review | Fresh-context reviewer (Sonnet): APPROVE. Rehashed the estimates, walked the outer JSON (2,474 leaves, only timings and one NaN pair differ), reran the script, and confirmed the addendum SHA-256 matches. |

## Blockers and remaining risks

Same-machine, same-version reproduction only. Maintainer decides whether the addendum-commit leaf is acceptable for closing #27.

## Next actions

Maintainer review, then close #27.
