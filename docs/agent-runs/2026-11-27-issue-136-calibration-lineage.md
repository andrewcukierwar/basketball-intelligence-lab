# Agent run: chronological margin-calibration lineage

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #136 (audit A2), #39, #42, #129, #43
- **Branch / commit / PR:** `claude/issue-136-calibration-lineage`. Registration commit `a461ddc`.

## Objective and authorized scope

Register a chronological construction for margin-calibration examples, record and check their lineage at the consumer boundary, prove later outcomes cannot change an earlier calibration, reject late-selected parents, document support, and compare on development data. Frozen #35/#39/#42 results stay reproducible and unrevised.

## Work completed

- **Protocol.** `docs/research/calibration-lineage-protocol.md` registers the post-freeze construction, the parent registry, the eligibility conditions, the fit and the comparison. It was committed before the run.
- **Module.** `src/bil/models/calibration_lineage.py` provides `Parent`, `Example`, `check_example`, an order-independent `fit_post_freeze` with an examples digest, and `load_calibration`, which re-checks parents, examples, digest and coefficients against the origin. It also has a pinned development runner.
- **Tests.** `tests/test_calibration_lineage.py` covers:
  - later-outcome invariance;
  - each lineage condition;
  - refusal of late parents and tampered examples through the normal loader;
  - refusal of #39-style examples.
- **Run.** `data/processed/team_outcomes/issue-136-v1` (private).
- **Docs.** The [report](../research/calibration-lineage.md), ADR-0036 and a note in team-outcomes.

## Key decisions and discoveries

- **Construction.** Post-freeze was chosen because nested selection has no earlier block for the first 2021 origin, and no independently predeclared penalty exists. Parent `outcomes_through` is set conservatively at 2023-06-30 for #35, #36 and #39.
- **Raw inputs.** They come from frozen #39 predictions, inverted through the frozen calibration. Scores under the frozen calibration reproduce the published #39 2024–25 metrics exactly.
- **Support.** No 2021–23 or 2023–24 origin has an eligible calibration. The #42 calibration was not chronologically eligible, and its result stands as recorded.
- **2024–25 result.** Post-freeze changes EI by −0.014 RMSE and −0.0010 log loss, and both intervals span zero. EI minus team stays about +0.13 RMSE.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q` | 474 passed, 3 skipped |
| `ruff`, `mypy src` | Pass |
| Development run from a clean detached worktree at `a461ddc` | `working_tree_clean_at_end: true`. Outputs listed in the report |
| Independent review (Sonnet subagent, fresh context) | No blocker. All numbers and hashes match the private outputs. The non-blocking findings were fixed after the run: test coverage of a forged parents block, tolerance on the coefficient refit, refusal of post-cutoff rows and of parent/source mismatches, staging cleanup, and doc clarifications. None of the fixes changes the fit. `issue-136-v1` loads unchanged |

The main checkout's untracked audit handoff made `verify_protocol` refuse a dirty tree, so the run used a clean detached worktree of the same commit.

## Blockers and remaining risks

- One season supports each calibration. Drift across seasons is not modeled.
- Upstream EI and team-rating parents for 2021–23 origins remain non-chronological. Nested selection would be a separate registration.

## Next actions

#129 and #43 should build calibrations with this module and register their fit cutoffs.
