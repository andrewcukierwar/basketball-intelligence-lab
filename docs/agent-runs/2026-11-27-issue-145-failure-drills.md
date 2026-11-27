# Agent run: refresh failure drills and recovery runbook

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #145 (part of #43), #44, #136, #142, #143, #144
- **Branch / commit / PR:** `claude/issue-145-failure-drills`, PR #152. The final drill run was at `339d156`.

## Objective and authorized scope

Exercise quality gates and provenance failures in the local refresh, with auditable outcome records and no partial publication. Document resume, rollback and cold rebuild. Hand off to #44.

## Work completed

- **`src/bil/refresh.py`:**
  - stage-tagged refusals (`stage_of`);
  - `check_parents` (late SPM parent);
  - `calibration_for`, through `load_calibration`, so an eligible calibration becomes a parent;
  - `record_outcome` and `build`, which write one outcome per origin, record the requested inputs on a refused load, and exit nonzero on refusal;
  - `current` and `retire`, with the CLI `retire`;
  - `load_inputs(addendum=, pins=, calibration=)`;
  - `VERSION` set to `origin-refresh-issue-145-v4`.
- **`src/bil/models/rapm/multiseason.py`.** `_prepare` passes `pins` through to `load_season`.
- **`src/bil/refresh_drills.py`.** The real-data drill runner.
- **`tests/test_refresh_drills.py`.** Five tests:
  - a load refusal covers every origin;
  - a late parent is refused;
  - an ineligible calibration is refused, and an eligible one is a parent;
  - an interrupted publish leaves nothing and resumes;
  - rollback restores the current artifact.
- **Docs.** The `docs/refresh.md` outcome log, drill table, runbook and #44 hand-off. ADR-0042.

## Key decisions and discoveries

- **Calibration is an optional parent.** The refresh did not use a calibration before. Making it a parent is the only way to drill `load_calibration` in the refresh, and #44 needs calibrated margins anyway.
- **Load refusals record the requested inputs.** The first drill run recorded `inputs: null` for load refusals. They now record the requested sources, and the drills were rerun as `-v2`.
- **First run failed on a missing directory.** The first drill invocation failed before any drill because a drill root was not created. It produced no outputs and was fixed.

## Verification performed

| Check | Actual result |
| --- | --- |
| Full `pytest`, `ruff`, `ruff format`, `mypy src` | See PR |
| Drills `refresh-drills-issue-145-v3`, clean tree at `339d156` | 9 of 9 pass with strict causes. 7.4 s |

## Review

An independent Haiku review found four blockers, all fixed with tests:

- `retire` could not retire an inconsistent artifact;
- `current` silently skipped inconsistent artifacts (it now fails closed and refuses unrecorded extras);
- interrupts left no outcome record (they are now recorded, with the remaining origins as `skipped`);
- two drills accepted any load failure (their expected causes are now strict).

Optional findings, also fixed:

- the stage of the same-ID check and of the post-publication revision log;
- inputs on publication records;
- the documented `VERSION` identity change and `current` semantics.

The drills were rerun as `-v3`.

## Blockers and remaining risks

- There is no lock, so there is a single writer per root.
- A crash between publication and the revision log leaves an unrecorded accepted artifact. `current` refuses, which is fail-closed.
- Live capture is #44's.

## Next actions

Review and merge. #43 can then close: #142 to #145 are done. #44 needs its own registration and live capture.
