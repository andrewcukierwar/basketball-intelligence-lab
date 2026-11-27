# Agent run: replayable origin refresh

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #142 (part of #43), #135, #129
- **Branch / commit / PR:** `claude/issue-142-origin-refresh`

## Objective and authorized scope

Build one origin's EI snapshot from pinned inputs, with cutoff enforcement, content-addressed idempotent artifacts, atomic publication and a frozen-rebuild check. Scope is replay only: no live capture and no 2025–26 date.

## Work completed

- **`src/bil/refresh.py`:**
  - `Inputs`, `artifact_id`, `check_origin` (replay seasons, holdout guard), `existing` (consistency check), `publish` (staging plus rename) and `refresh_origin`;
  - `load_inputs`, using the pinned #36 inputs;
  - `verify_frozen`;
  - the `build` and `verify-frozen` CLI.
- **`tests/test_refresh.py`.** Four synthetic tests:
  - later rows and box lines cannot change the published bytes;
  - a rerun is a no-op and changed inputs get a new artifact;
  - an interrupted publish leaves nothing;
  - tampered or incomplete artifacts and out-of-scope origins are refused.
- **Docs.** `docs/refresh.md` and ADR-0039.

## Key decisions and discoveries

- **Identity.** The artifact identity excludes the code commit, which is recorded only. Identity is the inputs, parents and configuration. This is what lets warm and cold rebuilds (#144) be compared by ID.
- **Inconsistent artifacts.** An existing directory that fails its own manifest check is refused, not repaired.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q tests/test_refresh.py` | 4 passed |
| Full `pytest`, `ruff`, `ruff format`, `mypy src` | 479 passed, 3 skipped. All clean |
| `verify-frozen` on real pins (enforced 1e-6 gate) | 10 of 10 #36 block snapshots reproduced: roster gap 0.0, no refreshed player missing from the export, and 2,077 off-roster player-cutoffs equal to the cold prior (gap 0.0). 6.7 s, 1.9 GiB peak |
| Rerun `build --origin 2023-12-01` | `created: false`, same ID, nothing rewritten |

## Review

An independent Haiku review flagged one blocker: `verify-frozen` reported the gap without enforcing it. It also made optional findings:

- non-`RefreshError` failures on malformed manifests;
- no fsync;
- overclaims about kill and power-loss cleanup;
- a code-version identity that was not stated.

All were fixed. A focused re-review then found that NaN gaps were masked by `max`. Every gap is now checked, with NaN tests added. The macOS `F_FULLFSYNC` limit is documented and not fixed. Enforcing the gate showed that the legacy export lists every indexed player, so the check now also verifies the off-roster players against the cold prior.

## Blockers and remaining risks

- The row-set pins cover whole seasons, so the identity changes if a pinned row set is re-versioned, even for rows after the origin. Per-origin revision resolution is #143.
- The refresh fits from scratch. Checkpoints and warm/cold comparison are #144.

## Next actions

Review and merge. Then #143.
