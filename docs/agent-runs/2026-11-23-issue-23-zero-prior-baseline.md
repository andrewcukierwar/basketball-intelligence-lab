# Agent run: first historical zero-prior RAPM baseline (2022–23)

- **Date:** 2026-11-23
- **Status:** Awaiting review (independent review not yet run)
- **Related issues:** #23 (depends on #22, #59, #6, #64, #65)
- **Branch / commit / PR:** `claude/issue-23-zero-prior-baseline`; protocol `26cb127`, runner and tests `82b3452`, report and handoff in the final commit. No push, no PR.

## Objective and authorized scope

Reproduce offense, defense and total estimates on the pinned #59 row set with an exposure report, a baseline comparison, chronological game-grouped development checks, penalty sensitivity, optimizer diagnostics, runtime and memory, and the effect of excluding adjudication strata. 2022–23 only. No EPM, no 2023–24 or later data. The protocol was committed before the run.

## Work completed

- `docs/research/rapm-baseline-protocol.md`: frozen pins (build id, SHA-256 of manifest, model rows and game reconciliation), folds, metrics, penalty grid and selection rule, exclusion design.
- `src/bil/models/rapm/baseline.py`: CLI `python -m bil.models.rapm.baseline`, which verifies the pins and writes `results.json`, `manifest.json` and a private `player_estimates.csv` to a new directory.
- `src/bil/models/rapm/reference.py`: additive `fit_rapm_diagnostics` returning LSQR stop code, iterations, residual norm and condition estimate. `fit_rapm` behavior is unchanged.
- `tests/test_rapm_baseline.py`: 12 synthetic tests (strict chronological and game-grouped split, no dependence on scored outcomes, unseen-player scoring, model beats league on clean signal, exclusion, penalty-grid extension, bootstrap, pooling, halves and exposure, pin rejection).
- `docs/research/rapm-baseline-2022-23.md`: aggregate report. Private output: `data/processed/2022-23/issue-23-v1/` (not committed).

## Key decisions and discoveries

- Chosen $\lambda^\*$ = 4,000 (interior minimum of 250 to 32,000 on pooled R1–R4 MSE), role-symmetric.
- Pooled R1–R4 delta vs league −14.1 (95% −18.3 to −9.8) on a 14,109 base. Playoff check −8.0 (−24.0 to +7.5). Defense-only is not better than league. Gains are small because possession noise dominates.
- Split-half total correlation 0.38. Excluding the 170 non-routine-stratum games (13.2%) shifts totals by RMS 0.37 (correlation 0.958) and changes held-out MSE by about 1 unit, below the paired noise.
- Rejected: rerunning OpenRAPM on these rows (the #65 synthetic benchmark covers solver agreement). A context-only team model was not built.
- Deviation: adding LSQR diagnostics touched the verified `reference.py`. The full suite passes.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run python -m bil.models.rapm.baseline <issue-59-v1> <issue-23-v1>` | Ran once at clean tree `82b3452`. 53 fits, all LSQR stop 2, 19.1 s wall, 898 MiB peak. |
| `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` | 138 passed, 2 skipped (private archived cases); ruff check and format clean; mypy strict clean on 25 files. |

No independent review was performed. Nothing was pushed.

## Blockers and remaining risks

- Independent review of the diff and report is needed (AGENTS.md requires it for material changes).
- The R1–R4 scores that picked $\lambda^\*$ are optimistic. The only independent score is the playoff fold, which is inconclusive.
- No size-matched random-game control for the exclusion shifts, no separate offense and defense penalties, no context-only comparator.

## Next actions

1. Independent review, then PR when authorized.
2. Follow-ups to consider as issues: a size-matched random exclusion control; separate role penalties chosen on the same chronological folds; a context-only baseline; use of this fold design as the shared development check for the informed-prior models (#61, #64).
3. Outer folds (2023–24, 2024–25) and the 2025–26 holdout remain untouched and need their own registered protocol.
