# Agent run: Dated RAPM eligibility clock and exponential weights

- **Date:** 2026-11-23
- **Status:** Awaiting review (no independent review run yet)
- **Related issues:** #64, parent #34, dependency #61
- **Branch / commit / PR:** `claude/issue-64-dated-rapm-weights`, not pushed, no PR

## Objective and authorized scope

Define and verify an as-of date and exponential decay on the prior-centered RAPM solver, with a leakage-safe cutoff, missing-date policy and an independent dense oracle. Synthetic only.

## Work completed

- `src/bil/models/rapm/dated.py`: `fit_dated_prior_rapm(possessions, *, as_of, half_life_days, offense_ridge, defense_ridge, offense_prior, defense_prior)` returning `DatedRAPMFit(fit, as_of, included, excluded_same_or_later)`. It filters, applies `base_weight * 0.5 ** (age / half_life)` and delegates to `fit_prior_rapm`.
- `Possession` gained an optional `played_date` field (default `None`, ignored by undated fits).
- `bil.evaluation.eligibility.played_before` extracted from the existing same-or-later rule so there is one cutoff definition.
- Docs: `docs/research/rapm-dated-weights.md`, ADR-0015, link in `docs/DECISIONS.md`, pointer in `rapm-prior-centered.md`.
- Tests: `tests/test_rapm_dated.py` (25 cases).

## Key decisions and discoveries

Strict `<` on Eastern calendar dates, whole-day age, no weight normalization (decay raises the effective penalty), fail closed on missing or non-`date` values even for excluded rows, underflowed weights raise. The repo has no RAPM cache, so cache safety is covered by statelessness tests and a documented keying rule. Alternatives not taken: normalizing weights to mean 1, and dropping rows with missing dates.

## Verification performed


| Check | Actual result |
| --- | --- |
| `uv run pytest -q tests/test_rapm_dated.py -s` | 25 passed. Max coefficient delta 6.5e-11 (no decay) down to 6.8e-14 (half-life 0.5), tolerance 1e-8. Condition numbers 6.99 to 14.66. |
| Full suite and lint/type checks | Full suite: 113 passed, 2 skipped (private archived cases). ruff check, ruff format --check and mypy src (strict) passed. |

## Blockers and remaining risks

No independent review. Half-life and penalty choice are untested on real data. A future cache is a risk if not keyed by `as_of`.

## Next actions

Independent review; then choose half-life and penalties without EPM outputs in a later issue.

## Independent review

A fresh Opus reviewer approved commit 77073d9 with no blocking findings and reran pytest (113 passed, 2 skipped), ruff, ruff format and strict mypy. The lead then added the knowledge-time caveat and qualified the 0.5-day oracle case in the research doc.
