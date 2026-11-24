# Agent run: context ablations of the zero-prior RAPM baseline (2022–23)

- **Date:** 2026-11-23
- **Status:** Awaiting review
- **Related issues:** #24, and the first item of #77 (the context-only comparator). Depends on #23 and #59.
- **Branch / commit / PR:** `claude/issue-24-context-ablations`. Protocol `1d6a885`, then solver, runner and tests `9ad75e2`, then report and handoff in the final commit. No push, no PR, no issue edits.

## Objective and authorized scope

The task was to ablate, one at a time against the zero-context #23 fit:
- home court (and neutral court, where the data allow it),
- pre-possession score margin and game time,
- fitted control against an eligible offset,
- exposure and weight scale.

It also required verifying that covariates precede each possession, reporting the regular season, playoffs, late blowouts and neutral-court strata, and recording fit, holdout and coefficient sensitivity, plus the #77 context-only comparator. Scope was 2022–23 only, reusing #23's folds R1–R4 and P1 with $\lambda$ = 4,000. The protocol had to be frozen and committed before a single run from a clean tree.

## Work completed

- `docs/research/rapm-context-protocol.md` (committed before the run): pins, covariate timing rule and audit, column definitions, 12 variants plus 6 context-only comparators, the verdict rule and the run command.
- `src/bil/models/rapm/context.py`: `fit_context_rapm` (unpenalized context columns, or a fixed offset, beside the ridge player blocks; Frisch–Waugh–Lovell projection plus sparse LSQR) and `fit_context_only`. The verified `reference.py` is unchanged.
- `src/bil/models/rapm/context_ablation.py`: CLI `python -m bil.models.rapm.context_ablation <rows> <pilot> <out>`. It verifies the #59 and pilot pins, derives pre-possession covariates with a DuckDB ASOF join on `seq < start_seq`, runs the timing audit, scores every variant with game-clustered bootstraps, and stores per-fit LSQR diagnostics.
- `tests/test_rapm_context.py`: 15 synthetic tests:
  - the k=0 fit equals the #23 solver,
  - agreement with a dense oracle,
  - offset equals fitted control under balanced context,
  - fitted control recovers a confounded effect that the offset misstates,
  - collinearity rejection,
  - weight-scale versus penalty equivalence,
  - covariate timing, a mutation-invariance check and leak detection,
  - features and blowout flags, fold masks, blowout variants, the verdict rule and bootstrap re-indexing,
  - overtime clock boundaries,
  - an end-to-end runner smoke run.
- `docs/research/rapm-context-ablations-2022-23.md`: the aggregate report. `docs/research/epm-uncertainties.md`: EPM-U08 links to it.
- Private output: `data/processed/2022-23/issue-24-v1/` (not committed). The run was not interrupted, so there is no `issue-24-v2`.

## Key decisions and discoveries

- Pooled R1–R4 Δ vs C0, with 95% intervals:
  - Time: T_fit −25.7 (−31.5 to −19.7).
  - Score: S_fit −6.3 (−9.6 to −3.0).
  - All context: HST_fit −32.3 (−39.0 to −25.4).
  - Home: H_fit −0.4 (−1.9 to +1.2), inconclusive.
  - Late-blowout weighting: W_half +0.00 and W_drop +0.17, rejected.
  - Offset variants match their fitted versions within noise.
  - On P1, T and HST stay clearly negative, while H and S are null.
- Context-only comparator against the league mean: HST −30.5 (−37.2 to −23.8) and time −26.9. Both beat zero-context player RAPM (−14.1).
- The time gain is mostly the end-of-period column (≤ 24 s left, about −30 points per 100). That may partly reflect parser handling of period-boundary possessions, which was not audited separately.
- The fitted score slope is −0.30 per point against −0.20 for the context-only offset. Score terms worsen team-game RMSE (about 10.45 to 11.4 points).
- Player totals shift at most RMS 0.27 (W_drop), correlation at least 0.978.
- Neutral court is untestable: `game.neutral_site` is null for every pilot game. Two likely neutral international games (`0022200439`, `0022200678`) are coded by nominal home team. This is Inferred and not verified in the pinned data.
- Bug found before freezing: a draft `period_start_ms` placed overtime periods at the 36:00 mark instead of 48:00. A unit test caught it. It was fixed before the protocol and code commits, and the pre-freeze audit was rerun after the fix.
- Before freezing, only covariates were inspected (audit, strata counts, margin distribution, column means). No outcome-based score was computed for any variant.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run python -m bil.models.rapm.context_ablation <issue-59-v1> <issue-19-v6> <issue-24-v1>` | Ran once at clean tree `9ad75e2`. Manifest `working_tree_clean: true`. 83 fits, all LSQR stop 2, 33.8 s wall, 1,050 MiB peak. Timing audit: 0 leaks, 0 ledger disagreements. Zero-context solver matches the #23 solver to ≤ 9e-14 on every fold. C0 reproduces #23 (pooled MSE 14,095.4). |
| Pilot and row-set digests | Verified by the runner. `event`, `game` and `score_allocation` digests also match the pilot manifest by hand. |
| `uv run pytest -q` | 167 passed, 2 skipped (private archived cases) |
| `uv run ruff check .`, `uv run ruff format --check .` | Clean |
| `uv run mypy src` | Clean (strict, 29 files) |

No independent review was performed. Nothing was pushed.

## Blockers and remaining risks

- Independent review of the diff, protocol-to-run provenance and report is required (AGENTS.md).
- One development season. There are many variants without multiplicity adjustment, and the bootstrap ignores dependence across folds. The verdicts are not reference-spec decisions.
- The end-of-period effect should be audited against possession-parser behavior at period boundaries before it is relied on.

## Next actions

1. Independent review, then a PR when authorized. The PR closes #24 and the first item of #77.
2. Follow-ups to consider:
   - Audit end-of-period and short possessions at period boundaries.
   - Add a neutral-site flag to the pilot or game metadata (needed for later seasons such as the 2020 bubble).
   - Register an outer-fold protocol before adopting any context family into the reference RAPM.
   - Pair the remaining #77 items (split role penalties, random exclusion control) with the HST context.
