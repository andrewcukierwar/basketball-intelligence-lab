# Agent run: safeguarded order repair `order-repair-v2` for 2017–18

- **Date:** 2026-11-24
- **Status:** Awaiting review
- **Related issues:** [#99](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/99), parent [#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53)
- **Branch / commit / PR:** `claude/issue-99-order-repair-v2`, code `d50e7695`, PR linked from #99. Not merged.

## Objective and authorized scope

Implement the ADR-0023 maintainer conditions as a new versioned repair, rebuild 2017–18, decide eligibility under ADR-0022 and diagnose the residual unresolved possessions. The same-clock rule, hard checks and thresholds were not touched.

## Work completed

- `src/bil/data/pilot_order_v2.py` and `build --order-repair-v2`: the nine conditions (immutability, nearest-valid-neighbor clocks, 24 s rejection, replay and timeout separation, corroboration for shots, free throws, turnovers, rebounds and substitutions, full log, lower-trust stratum `datanba_event_order_v2`, failed games only).
- Removed v1's "second use" (`_offer_repair`). v1 `--order-repair` is otherwise unchanged.
- `scripts/order_repair_verification.py` for lineup and possession verification against Bentes, pbpstats.com and data.nba.
- Synthetic and integration tests in `tests/test_pilot_order_v2.py` (24 s reject, replay separation, corroboration decline, accepted games untouched, log completeness, off by default).
- ADR-0029 (Proposed), EXP-0019, the research note, the eligibility-matrix row and the data-pilot note.

## Key findings

- 27 of 172 offered games recovered (v1: 137). 118 declined uncorroborated, 7 incomplete `ord`, 4 over the ceiling, 16 rejected by reconciliation. The largest applied shift is 11 s.
- 2017–18: regular coverage 87.7% and unresolved 0.388%. It stays ineligible under ADR-0022.
- Repaired games match Bentes on 99.979% of lineup seconds and the rest of the season on possession counts.
- Residual unresolved possessions: 884, of which 16 are in repaired games. 80% touch a same-clock group, 38% have a nearby data.nba `ord` descent (in accepted games the repair may not touch), 58% are in technical-free-throw games. Not fixed.
- The same-clock rule applied to 0 games in this season.

## Failed or abandoned approaches

- A first `-b` build collided with a still-running earlier background build and was removed. It was rebuilt alone.
- No tuning of the corroboration tiers against reconciliation results.

## Verification

| Check | Result |
| --- | --- |
| `uv run pytest -q` | 347 passed, 2 skipped, exit 0 |
| `ruff check .`, `ruff format --check .`, `mypy src` | Pass |
| `pilot check` on both v2 builds | 26 of 26 |
| `season_quality.py --run-checks` | 2017–18 `fails_hard_limit` |
| Independent review | Not run. Required before canonical use |

## Blockers and risks

- Corroboration is the maintainer's open call: relaxing it for same-clock substitutions would recover more games but rely on `ord` alone.
- Private outputs are under `data/processed/2017-18/issue-99-*` and `data/quality/issue-99-2017-18-v2a`. Nothing under `data/` is committed.

## Next actions

- Independent review of the diff and a replay of `-a`.
- Maintainer decision on the tiers. The residual unresolved causes may justify a separate same-clock free-throw and substitution issue.
