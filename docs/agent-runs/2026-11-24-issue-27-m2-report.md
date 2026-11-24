# Agent run: M2 RAPM research report and gate assessment

- **Date:** 2026-11-24
- **Status:** Awaiting maintainer review
- **Related issues:** #27 (depends on #26)
- **Branch / commit / PR:** `claude/issue-27-m2-report` from `origin/main` at `7f9b85e`. One commit. Not pushed, no PR, no issue edits.

## Objective and authorized scope

Synthesize the M2 evidence into one report, update the EPM uncertainty register, and propose a gate assessment without closing the gate. Documentation only: no model code, no new fits, no private data read.

## Work completed

- `docs/research/rapm-m2-report.md`: frozen fit pins and commands, numerical verification, runtime, benchmark results with intervals, negative and failed results, exclusions, accepted target definitions, remaining EPM uncertainties, coverage limits for #28 and #30, a seven-row gate assessment and nine open maintainer items.
- `docs/research/epm-uncertainties.md`: added an "M2 status" note to EPM-U01, U08, U09, U10, U12, U13 and U14. IDs and original text unchanged.
- `README.md`: one documentation link.

## Key decisions and discoveries

- Proposed assessment: numerical correctness met. The multi-season ratings and holdout reports are partially met (development evidence, one run each, ADR-0025 unaccepted, no confirmatory 2025–26 run, playoffs inconclusive). The gate is not declared closed.
- Gaps noticed in the repository records: ADR-0013 (stable-lineup restriction) is still marked Proposed. #23 and #24 have no EXP entries in `experiment-log.md`. There is no ADR-0024 on `main`. The independent re-review of the ADR-0019 canonical decision is recorded as pending (EXP-0011, #74/#82 handoff) and I found no later record of it.
- Every number was copied from a source report or ADR. I did not recompute anything.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv sync --locked --extra dev --extra pilot --extra rapm` | Done (a first run before sync failed to spawn pytest and ruff) |
| `uv run pytest -q` | Exit 0: 304 passed, 2 skipped |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 160 files already formatted |
| `uv run mypy src` | Not run (no source changes) |
| Number check | Read against the source reports during drafting. No independent re-derivation |
| Independent review of this report | Not run |

## Blockers and remaining risks

- The report relies on the source documents' accuracy. It cannot re-run private-data fits.
- The gate recommendation needs the maintainer decisions listed in section 7 of the report.

## Next actions

1. Independent review of the report (fresh context), then a PR when authorized.
2. Maintainer: decide ADR-0025, ADR-0019 departure, ADR-0013, ADR-0023, the #53 remainder, the informed-RAPM comparator and the 2025–26 registration.
3. Optional follow-up: add EXP entries for #23 and #24.

## Independent review

A fresh Opus fact-checker approved after checking about 75 claims, with no blocking errors. It found that the repository still recorded the ADR-0019 re-review as pending. The re-review had in fact approved abed529 before PR #91 merged, so the lead recorded it in ADR-0019, EXP-0011 and the #74/#82 handoff. The lead also applied the reviewer's eight minor corrections:
- the fitted-rate delta;
- the development seasons count;
- the 2010–11 probe;
- the warning labels;
- the scope of the ADR status;
- the EPM-U labels;
- the Bentes coverage;
- the residual end-of-period effect as an open item.
