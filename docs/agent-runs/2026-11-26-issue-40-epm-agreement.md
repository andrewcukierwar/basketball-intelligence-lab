# Agent run: #40 external EPM agreement diagnostics

- **Date:** 2026-11-26
- **Status:** PR open
- **Related issues:** #40, #42, #38
- **Branch / commit:** `claude/issue-40-epm-agreement`. The run used `12a225d`.

## Work completed

- **Permission.** The maintainer reported express written permission from Dunks & Threes to obtain and privately store EPM, non-commercial only. It is recorded in the data-sources ledger.
- **Source.**
  - The live free page shows only current (2026–27) values, and its history views are subscriber-only.
  - Internet Archive captures of the free page hold dated values for 2021–22 through 2024–25.
  - Four captures, all before the 2025–26 holdout, were pinned by SHA-256. Values were masked during the structure probe.
- **Protocol and run.** Registered the [protocol](../research/epm-agreement-protocol.md) and `bil.models.epm_agreement`. Embedded JS literals are parsed with a non-evaluating reader. One clean run. [Results](../research/epm-agreement.md)

## Key results

- **Agreement.** Pooled primary-cohort r is 0.862 on offense, 0.699 on defense and 0.825 on total.
- **On-court update.** EI agrees more than its SPM prior alone on every side, by +0.218 r on defense.
- **Level offset.** EI sits +0.75 above EPM on total.
- **Scope.** This is a diagnostic only; nothing was tuned or selected.

## Verification

| Check | Result |
| --- | --- |
| `uv run pytest -q` | 446 passed, 3 skipped |
| `ruff check`, `ruff format --check`, `mypy src` | Pass |
| Run | Clean `12a225d`, manifest `bbebb1a6…ec8c` |

## Next actions

- **#42.** The R1 joint registration is now unblocked on #40, pending maintainer review of ADR-0030, ADR-0031 and ADR-0032 before any 2025–26 holdout capture.
