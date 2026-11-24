# Agent run: RAPM baseline controls (split penalties, random-exclusion control, per-fit diagnostics)

- **Date:** 2026-11-24
- **Status:** Awaiting independent review
- **Related issues:** [#77](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/77) (remaining items), parent #20. The context-only comparator came from #24/#83.
- **Branch / commit / PR:** `claude/issue-77-baseline-controls`. Protocol `e2168f3`, runner and tests `b032969`, report and handoff in the final commit. No push, PR or issue edit from this run.

## Objective and authorized scope

Add separate offense and defense penalties selected on folds R1–R4 (P1 scored after selection), a size-matched random-game exclusion control for the 170 adjudication-stratum games, and per-fit solver diagnostics in `results.json`. Protocol committed before the run, one run from a clean tree, canonical row set `issue-82-canonical-v1`, 2022–23 only, no EPM.

## Work completed

- `docs/research/rapm-baseline-controls-protocol.md`: frozen first, SHA-256 `7fb3ce72…8531b2`.
- `src/bil/models/rapm/reference.py`: `fit_split_rapm_diagnostics` (the #61 split-penalty solver plus LSQR diagnostics), exported from the package.
- `src/bil/models/rapm/baseline_controls.py`: 2-D grid selection with edge extension, vectorized held-out scoring (tested equal to `baseline.score`), `FitLog` per-fit diagnostics, the random-set sampler and the control comparison, runner and manifest.
- `tests/test_rapm_baseline_controls.py`: dense-oracle agreement for split penalties, equal-penalty identity, scoring equivalence, grid selection, random-set determinism and matching, tail statistics, exclusion statistics.
- One registered run (976 s, 836 MiB) into `data/processed/2022-23/issue-77-v1` (uncommitted, private). Manifest: code `b032969`, clean tree, protocol hash above, `results.json` SHA-256 `dd3b16f9…3811f`.
- Report `docs/research/rapm-baseline-controls-2022-23.md`, EXP-0014, a pointer in the #23 report. No ADR: nothing here is a lasting design choice.

## Key decisions and discoveries

- Selected (2,000, 8,000), interior to the 7 × 7 grid. Pooled R1–R4 delta against the single penalty −1.57 (−3.11 to −0.06) but P1 +3.57 (−1.61 to +8.75). By the frozen rule the split penalty is not distinguishable, so the single penalty stays the baseline.
- Stratum exclusion shifts estimates like random exclusion of 170 ordinary games (total RMS 0.369 against 0.361 ± 0.015). Its held-out effect is lower than random draws in direction (post hoc lower tail 0.02), but the pre-declared two-sided statistic has no power and is not significant.
- All 3,806 fits converged, iterations 8 to 60, condition at most 106.
- Rejected: per-stratum random controls and a split-penalty stability fit, both out of scope.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Pass |
| `uv run pytest -q` | Pass (253 passed, 2 skipped) |
| `uv run ruff check .`, `uv run ruff format --check .` | Pass |
| `uv run mypy src` | Pass |
| Registered run | Completed; #23 single-penalty numbers reproduced (pooled MSE 14,095.4, P1 14,014.2, final fit condition 34.4) |
| Independent review | Not run |

## Blockers and remaining risks

- The pooled delta is selection-optimistic and P1 is one short block. A split penalty needs the 2023–24 outer season to be judged.
- A 2-draw smoke run on real rows preceded the registered run, and only structural facts were read from it.
- The control's two-sided held-out statistic was uninformative, and the directional lower-tail count is post hoc.

## Next actions

- Independent review of the diff and report (fresh context, ideally a Codex review).
- Maintainer decision on whether to carry the split penalty to 2023–24 under a new frozen protocol.
- Lead to update issue #77 and open a PR when authorized.

## Independent review

A fresh Opus reviewer approved with no blocking findings. With its own script, it reproduced the following:
- the single-λ pooled delta of −14.09, which matches #23;
- the split-penalty delta of −1.566;
- the P1 delta of +3.571;
- the observed exclusion shift of 0.3688.

It confirmed the protocol was frozen before the run, the solver oracle, the matching of the random draws, and that the smoke run did not compromise the registered run.

Nonblocking items for future runners:
- Record `HEAD` and the clean-tree check before fitting, not after.
- Save the drawn game IDs.
- Tighten the loose assertion at `tests/test_rapm_baseline_controls.py:128`.
- `draw_sd` uses ddof=0.
