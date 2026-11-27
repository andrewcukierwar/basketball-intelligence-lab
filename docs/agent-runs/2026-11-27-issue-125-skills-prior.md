# Agent run: chronological Estimated Skills as the SPM prior input

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #125 (audit A3), ADR-0030
- **Branch / commit / PR:** `claude/issue-125-skills-prior`. Registration at `6d5cc8e`, then the final registration with review changes at `0582f7d`, which is the run commit.

## Objective and authorized scope

Complete the Skills → SPM → informed-RAPM chain with chronologically fitted, versioned Skills parents, enforce their eligibility at the consumers, and compare against v1's raw-box prior on matched folds with the ADR-0026 comparators.

## Work completed

- **`bil.features.skill_bundle`.**
  - Per-season bundles fit on `S-3` to `S-1`, with inner clock choice on `S-1`. They use the #32 DE settings with unique seeds.
  - Lineage recorded in each bundle: source view, box-log pins, outcomes date, fit cutoff, and a `fit_id` over every field.
  - `check_bundle` and `bundle_values` enforce eligibility. The rules cover late, wrong-season or shifted-history bundles, source-view mismatch, rows strictly before the as-of date, and the v1 cold definition.
- **`skill_decay.fit_rows`.** Extracted from `fit`. Behavior is identical, and the #32 tests pass.
- **`bil.models.expected_impact_skills`.** Matched runner on the #35 development and #36 outer blocks. Each block computes four EI variants:
  - Skills-prior EI;
  - the v1 raw-prior refit, gated to reproduce the published predictions;
  - a recent-history ablation;
  - all comparators.
- **Tests.** `tests/test_skill_bundle.py` has 7 tests.
- **Docs.** The [protocol](../research/skill-prior-protocol.md), the [results](../research/skill-prior.md) and ADR-0037.

## Key decisions and discoveries

- **SPM applied, not retrained.** This isolates the input change. Context is not used, so the stacked-context criterion does not apply.
- **Result.** Inconclusive, and the raw-box input is retained. The applied Skills prior is compressed to about half the raw spread. The ablation attributes the loss to the input distribution shift rather than to the longer history.
- **Pre-run review** (Sonnet, fresh context). No blockers. All seven suggestions were folded into the registration before the run:
  - seed uniqueness;
  - `fit_id` coverage and pins;
  - the source-view check;
  - the cold definition;
  - the support floor;
  - the recent-history ablation and the multiplicity and confound limits;
  - consumer tests.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q` | 481 passed, 3 skipped |
| `ruff check`, `ruff format --check`, `mypy src` | Pass |
| Pre-registration plumbing check (one block, reduced DE settings) | v1 reproduction gap 0.0. No scores computed |
| Registered run `issue-125-v1` | Clean tree at `0582f7d`, 463 s, 1.84 GiB. v1 reproduction gap 0.0 in both folds |

## Blockers and remaining risks

- The SPM input-distribution shift is unresolved. Retraining the SPM on as-of Skills needs its own registration.
- Surrogate-target (#137) and team-level outcomes were not run for the Skills prior.

## Next actions

Independent review of the PR, then merge. A follow-up issue for an SPM retrained on as-of Skills inputs.
