# Agent run: checkpointed refresh, warm/cold equality and capacity

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #144 (part of #43), #142, #143, #129
- **Branch / commit / PR:** `claude/issue-144-incremental-refresh`, PR #151. The final run was at `9494ce7`.

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
| Registered capacity run `-v2`, clean tree at `9494ce7` | All 7 checks pass. 65 of 65 origins identical warm and cold, with every warm origin reusing its checkpoint. Peak 2.08 GiB. Per-origin maximum 0.58 s. Cold daily job 3.9 s. Checkpoints 9.9 MB measured at retention 14. Drill refused and recorded |
| Full `pytest` | 508 passed, 3 skipped |

## Review

An independent Haiku review found one blocker: an accepted revision was logged as "published" before publication, so a failed publish left a false record. It is now logged only after publication succeeds, with a test.

Optional findings, all fixed:

- the record now includes config, parent and version changes;
- an inconsistent sibling is recorded and refused;
- pruning never removes the checkpoint just written, and drops orphans and superseded identities;
- a stray `allow_pickle` array is gone;
- the runner asserts warm reuse and measures the retained store;
- the ADR wording is qualified as compute-only.

The capacity run was repeated as `-v2` after the fixes.

## Blockers and remaining risks

- Live freshness (capture latency) cannot be measured in replay.
- The checkpoint store has no file lock. Concurrent refreshes of the same origin are not supported; that is a #145 drill candidate.

## Next actions

Review and merge. Then #145: failure drills and runbook.
