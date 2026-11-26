# Agent run: #38 defensive tracking against box-only SPM

- **Date:** 2026-11-26
- **Status:** PR open
- **Related issues:** #38, #37, #30, #40, #42
- **Branch / commit:** `claude/issue-38-tracking-spm`. Registration `11cb9df`, pre-run review fixes `38718f9`, and the run used `38718f9`.

## Work completed

- **Protocol.** Registered the [protocol](../research/tracking-spm-protocol.md) and `bil.models.tracking_spm`. It:
  - reuses #30's contiguous `K365` chain and box-only Full;
  - adds three SportsDataverse matchup rates to defense, with a Full-defense fallback;
  - scores K0 agreement and the realized-lineup diagnostic;
  - checks that it reproduces #30 exactly.
- **`spm.py` change.** `fit_prior` accepts extra columns, and `LinearPrior.record` takes the code names. Nothing changes for #30.
- **Review and run.** An independent pre-run review (Sonnet subagent) found no blockers, and its non-blocking items were fixed before the run. One clean run. [Results](../research/tracking-spm.md)

## Key results

- **On court:** tracking meets the criterion, at −0.000247 [−0.000311, −0.000185].
- **K0:** it fails, and is worse, at +0.089 [+0.047, +0.145] on defense. The deterioration is driven by players under 15 minutes per game.
- **Coverage:** no pinned tracking after 2022–23, so there is no M7 comparison. ADR-0032 (Proposed) keeps EI v1 box-only.

## Verification

| Check | Result |
| --- | --- |
| `uv run pytest -q` | Pass |
| `ruff check`, `ruff format --check`, `mypy src` | Pass |
| #30 reproduction | Fold coefficients and pooled MSE 1.4091153 matched |
| Run | Clean `38718f9`, manifest `236795ae…5962` |

## Next actions

- **Maintainer review:** ADR-0030, ADR-0031 and ADR-0032.
- **Possible follow-up:** an exposure-shrunk tracking specification, which needs later-season captures to matter for M7.
- **#40:** EPM agreement diagnostics are now unblocked. Then **#42**.
