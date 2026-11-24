# Agent run: multi-season RAPM selection, stability, sensitivity and outer validation

- **Date:** 2026-11-24
- **Status:** Awaiting review
- **Related issues:** #26 (depends on #93, #89, #24, #64; #77 not merged)
- **Branch / commit / PR:** `claude/issue-26-multiseason-rapm` from `origin/main` at `c5843ba` (includes #94). Commits in order:
  - `86790ae`: development protocol
  - `ec4f127`: runner, tests and a pre-run protocol clarification
  - `bd86289`: development results
  - `57fe88e`: frozen addendum
  - the final commit: outer results, ADR-0025, EXP-0015 and this handoff

  Nothing is pushed and there is no PR.

## Objective and authorized scope

Fit multi-season zero-prior RAPM, compare windows and exponential decay with separate offense and defense penalties on development folds inside 2018–19 to 2022–23, measure stability and the four maintainer sensitivities, then score only the frozen choice on 2023–24 and 2024–25 against the league-mean and #24 context-only baselines, with uncertainty, coverage and calibration. Two-phase discipline was mandatory. No 2025–26 or later file, no 2017–18 file, no EPM, no edits to `baseline.py`, no push, PR or issue edits.

## Work completed

- `src/bil/models/rapm/multiseason.py`: a new module, with `dev` and `outer` subcommands.
  - It reuses the reference solver (`_solve_rapm`), the dated clock semantics, `select_penalty`, `bootstrap_delta`, and the #24 context SQL, timing audit and feature columns, all by import.
  - It builds one vectorized design in the reference layout and solves on row subsets.
  - A season registry pins 2018–19 to 2024–25 by manifest SHA-256. `check_season` refuses 2025 and later, unpinned seasons, and seasons outside the phase.
  - The outer runner refuses to run unless its addendum checks pass: SHA-256, committed, unmodified and a clean tree. It also checks the development-manifest and protocol digests. It reads the configuration from the addendum's `frozen-config` JSON block.
- `tests/test_rapm_multiseason.py`: 19 synthetic tests, covering:
  - the holdout and phase guards (the guard fires before any path is opened);
  - window and decay weights against `decay_multiplier`;
  - design equality with `build_design`;
  - subset fits equal to `fit_dated_prior_rapm` and `fit_prior_rapm` within 1e-8;
  - fold nesting (no fit row on or after its cutoff, no later-season rows, no shared games);
  - outer refusals (no addendum, wrong digest, uncommitted, modified, dirty tree, development-manifest mismatch), with no output directory created;
  - penalty search and calibration;
  - a synthetic end-to-end run of both phases.
- Documents:
  - `docs/research/rapm-multiseason-protocol.md`
  - `docs/research/rapm-multiseason-outer-addendum.md`
  - `docs/research/rapm-multiseason.md`
  - ADR-0025 in `docs/DECISIONS.md`
  - EXP-0015 in `docs/experiment-log.md`
- Private data (uncommitted): `data/processed/multiseason/issue-26-dev-v1` and `issue-26-outer-v1`.

## Key decisions and discoveries

- **Selected configuration:** `W2` (730 days, unit weight), $\lambda_o$ = 4,000 and $\lambda_d$ = 8,000. Both baselines selected `W1`. The selection is a near-tie: `W3`, `H365` and `H730` are within 0.3 MSE units. Every candidate chose $\lambda_d = 2\lambda_o$.
- **Development:** −16.24 (−19.25 to −13.20) against the league mean and +12.28 (+7.61 to +16.71) against context.
- **Sensitivity:** the same selection in every scenario.
  - `exclude_2018_19` is identical for `W2`, because the window never reaches that season.
  - `exclude_no_livedata` makes the 2021–22 folds 1.40 (+0.68 to +2.13) worse.
  - `exclude_2021_22` makes `W1` infeasible. The final fit shifts by RMS 0.85 (r = 0.81).
  - `exclude_overtime` is negligible.
- **Outer, regular season over both seasons:**
  - `rapm` against the league mean: −23.39 (−26.48 to −20.33), better.
  - `rapm` against context: +8.82 (+4.09 to +13.68), worse.
  - `rapm_context` against context: −24.73 (−27.88 to −21.50), better.
- **Outer playoffs:** inconclusive for `rapm` against both baselines.
- **Calibration:** the `rapm` slope is 1.12 (1.04 to 1.20), so predictions are under-dispersed. All models over-predict playoff scoring by 2 to 4 points per 100.
- **Pre-run clarification:** found by a synthetic test. Candidates with an empty fit window are infeasible in a scenario. It was committed before the development run and is reported as a deviation.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Pass |
| `uv run pytest -q` | 283 passed, 2 skipped |
| `uv run ruff check .`, `uv run ruff format --check .` | Pass |
| `uv run mypy src` (strict) | Pass |
| Design reuse against the dated reference on a real fold | 4.0e-15 maximum difference (`W2`, `H365`) |
| Timing audit, all seven seasons | 0 leaks, 0 ledger disagreements |
| Development run (clean tree, `ec4f127`) | 1,156 s, peak RSS 3.10 GB. 3,970 fits, all converged, median 0.24 s. The largest fit (1.07 M rows) took 0.67 s |
| Outer run (clean tree, `57fe88e`, addendum checks passed) | 11.7 s, peak RSS 2.93 GB, 20 fits |

Independent review has not been run.

## Blockers and remaining risks

- **Interruption.** The rate-limit interruption came after the protocol commit and before the runner commit. No run had started, so no run was repeated.
- **Weak selection evidence.** The selection is a near-tie, and `W5` was truncated in development.
- **Comparator structure.** The context comparator's advantage rests on end-of-period run-outs (#82, ADR-0019).
- **Neutral sites.** They are uncoded (bubble games and the `v2_home_designation` games).
- **Split penalties.** They were selected here, not by #77. Reconcile once #77 lands.

## Next actions

1. Independent review of the diff, preferably by a different model family, and of the outer manifest's addendum lineage.
2. The maintainer decides whether informed RAPM should use the RAPM-with-context-offset model as its comparator, and whether to adopt ADR-0025.
3. Push and open a PR only on authorization. Do not edit #26 without authorization.
