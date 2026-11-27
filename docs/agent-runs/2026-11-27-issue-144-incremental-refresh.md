# Agent run: checkpointed refresh, warm/cold equality and capacity

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #144 (part of #43), #142, #143, #129
- **Branch / commit / PR:** `claude/issue-144-incremental-refresh`. The run was at `3d645b8`.

## Objective and authorized scope

Make the refresh incremental, with warm and cold builds that agree. Measure capacity against a registered budget. Detect and record late revisions instead of republishing.

## Work completed

- **`src/bil/refresh.py`:**
  - `save_checkpoint`, `load_checkpoint` (exact identity and digest match), `prune_checkpoints` (latest 14 origins) and `Published.checkpoint`;
  - the late-revision guard: `revision_record`, `revisions.jsonl` and `RevisionConflict`, with `accept_revision`;
  - CLI options `--no-checkpoints` and `--accept-revision`;
  - `VERSION` set to `origin-refresh-issue-144-v3`.
- **`src/bil/refresh_capacity.py`.** The registered workload, the cold and warm passes, the cold daily-job subprocess, the late-revision drill and the budget checks.
- **Tests.**
  - `tests/test_refresh_checkpoints.py`, 4 tests: warm, cold and plain builds are identical; reuse happens only on an exact identity and digest match; retention; a late revision is recorded, not republished.
  - The #142 rerun test now expects changed inputs at a published origin to be refused and recorded.
- **Docs.** `docs/refresh.md` (checkpoints, late revisions, budget, results) and ADR-0041.

## Key decisions and discoveries

- **Exact checkpoints only.** "Incremental" is read as exact checkpoints plus idempotent per-origin artifacts. Approximate rolling solver updates cannot give bit-identical artifacts, and a refit is already 0.5 s. The interpretation is stated in the docs and the ADR.
- **The bound is the window.** Checkpoints drop the per-row prior offset, which is recomputed on load, so they are bounded by the window (0.70 MB each).
- **Recaptures are counted separately.** A recapture with unchanged content is counted apart from content changes, so input-pin changes and real corrections are distinguishable.

## Verification performed

| Check | Actual result |
| --- | --- |
| Full `pytest`, `ruff`, `ruff format`, `mypy src` | See PR |
| Registered capacity run, clean tree at `3d645b8` | All 6 checks pass. 65 of 65 origins identical warm and cold. Peak 1.98 GiB. Per-origin maximum 0.56 s. Cold daily job 3.8 s. Checkpoints 9.8 MB at retention. Drill refused and recorded. 45 s total |

## Blockers and remaining risks

- Live freshness (capture latency) cannot be measured in replay.
- The checkpoint store has no file lock. Concurrent refreshes of the same origin are not supported; that is a #145 drill candidate.

## Next actions

Review and merge. Then #145: failure drills and runbook.
