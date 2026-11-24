# Agent run: revise the M1 quality policy and assess season missingness

- **Date:** 2026-11-24
- **Status:** Awaiting review
- **Related issues:** #89 (depends on #25, #52; informs #53)
- **Branch / commit / PR:** `claude/issue-89-m1-policy`, one commit on `origin/main` at `4191d04`. Not pushed, no PR.

## Objective and authorized scope

Implement the maintainer's 2026-11-23 policy: hard correctness unchanged, 97% game coverage and 0.1% season unresolved share kept as hard limits, 95% stratum coverage a target, unresolved shares reported by season type. Back the conditional season decisions with a reusable missingness diagnostic. Data-level only: no model fitted or scored, nothing on 2023–24 or 2024–25 beyond data quality, no 2025–26 file read, no network, no `data/` commit.

## Work completed

- `src/bil/data/season_quality.py` and the thin `scripts/season_quality.py`: M1 classification (original and revised), quarantine missingness by team, month, overtime, final margin, cause, player minutes and appearances, exposure; unresolved-possession missingness by month, offense team, period and score margin, with concentration measures; the primary-cohort sensitivity; aggregate CSV and JSON output. No `pilot_check` code changed (`--run-checks` calls it).
- `tests/test_season_quality.py`: eight synthetic tests (flag rule, permutation test, classification, concentration, rate ratios, sensitivity arithmetic, deterministic output).
- ADR-0022 in `docs/DECISIONS.md`; revised-policy section, revised classification column and eligibility matrix in `docs/data-pilot.md`; `docs/research/season-quality-2017-2025.md`; EXP-0012.
- Ran the script read-only on all eight builds into `data/processed/quality/issue-89-v2` (not committed). Rerun after review; `v1` is superseded.

## Key decisions and discoveries

- Strata coverage is applied per season type, which reproduces the originally recorded 2017–18, 2018–19 and 2021–22 failures exactly. The unresolved-share denominator is all possessions in the table (accepted, excluded and unresolved), as in the recorded M1 values.
- Quarantine tests use a game-label permutation chi-square; unresolved tests use a game-clustered bootstrap with Bonferroni over cells. The unresolved flag rule was revised after the first run (3-event cells gave infinite ratios; now at least 5 events with Bonferroni). Review then found that 1,000 bootstrap replicates could not reach the flag thresholds for 5 or more cells. The default is now 20,000 replicates, the script refuses when the p floor reaches 0.01, and the run was redone as `issue-89-v2`. Both are disclosed in the report's revision history, ADR-0022 and EXP-0012. The only flag change from v1 to v2 is 2017–18 unresolved October 2017, from watch to systematic.
- Findings: 2018–19 has systematic quarantine concentration in overtime games and in November 2018 (small effect: 2.1% of possessions lost). 2021–22 has none beyond a watch on 3 overtime games. 2024–25 playoff unresolved possessions show no testable pattern. 2017–18 is concentrated in the first months. Eligibility decisions are left to the maintainer.
- The first agent worktree was removed during an earlier rate-limit interruption before any file was written, so the work restarted on a fresh worktree from `origin/main`; only the output directory from the final run exists.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q` | 243 passed, 2 skipped |
| `uv run ruff check .` / `ruff format --check .` | Pass / 131 files formatted |
| `uv run mypy src` and `mypy scripts/season_quality.py` | Success, 38 source files |
| `season_quality.py --run-checks` on 8 builds | 0 invariant failures in every build; deterministic |

## Blockers and remaining risks

No independent review has been run. Low power at small quarantine counts, and the box-log exposure estimate, are documented limits. The 2018–19 finding needs a maintainer decision on materiality.

## Next actions

Independent review of the diff; maintainer decision on 2018–19 materiality; run the diagnostic again on any rebuilt season (including a #53 remediation of 2017–18) into a new output directory.
