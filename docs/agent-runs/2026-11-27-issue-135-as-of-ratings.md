# Agent run: as-of Expected Impact rating roster and explicit cold priors

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #135 (audit A1), #39, #42, #43
- **Branch / commit / PR:** `claude/issue-135-asof-roster`

## Objective and authorized scope

Make each Expected Impact snapshot's roster, coverage, metadata and digest invariant to players who first appear after its cutoff. Persist explicit per-side cold priors and consume them through the normal loader and team scorer. The frozen #35/#36/#39/#42 artifacts must stay reproducible.

## Work completed

- **`expected_impact.py`.**
  - `as_of_ratings()` writes `ei-ratings-as-of-v2`, restricted to players with completed box history before the cutoff or fit-window exposure, sorted by ID.
  - `cold_prior()` gives the per-side SPM intercepts. The snapshot also records coverage counts.
  - `snapshot_id` covers the values at their exported 6-decimal precision.
  - `write_ratings()` adds `artifact_version`, `cold_offense` and `cold_defense` columns for v2 and refuses mixed versions. `ratings()` and the v1 columns are unchanged.
- **`team_outcomes.load_ratings()`.** It uses the explicit cold priors when present and checks that they agree within a snapshot. It keeps the legacy inference for v1 files.
- **Tests.** The regressions append a later on-court ID and a later box-only ID and compare the earlier roster, ratings, coverage, cold priors, digest and unknown-player team score. They also compare keyed realized-lineup predictions. Snapshots with and without no-history roster members are covered, and the legacy dependency is pinned.
- **Docs.** The [EI v1 note](../research/expected-impact-v1.md#as-of-rating-artifact-135), a team-outcomes caveat and [ADR-0035](../DECISIONS.md#adr-0035--versioned-as-of-expected-impact-rating-artifact-with-explicit-cold-priors).

## Key decisions and discoveries

- **Frozen runners.** They keep v1. Switching them would change frozen artifact bytes and digests.
- **Digest.** It cannot be over raw float bytes. A design that indexes later players solves a larger system, which moves the same fit by about 1e-15.
- **Frozen artifacts.** In `issue-35-v1` and `issue-36-v1`, every snapshot exports 96 to 265 non-eligible players. All of them carry exactly the inferred cold total, so #39/#42 margins equal the v2 result. The #39 claim of no cold minutes is understated coverage, not a scoring error. This is inferred from the artifacts; #39 was not rerun.

## Verification performed

| Check | Actual result |
| --- | --- |
| `pytest -q` (worktree, `PYTHONPATH=src`) | 464 passed, 3 skipped |
| Independent review (Sonnet subagent, fresh context) | No blockers. Fixed: the sign of a rounded zero could move the digest. Docs now note the 1e-6 cold-total precision |
| `ruff check`, `ruff format`, `mypy src` | Pass |
| `load_ratings` on frozen `issue-35-v1` and `issue-36-v1` | 11 snapshots each. Cold totals are unchanged (−0.356921, −0.369487 and −0.375704). A v2 cold total is the sum of two 6-decimal priors, so it can differ from a v1 inferred total by up to 1e-6 |

## Blockers and remaining risks

- No production runner writes v2 yet. #43 and #129 are its first consumers.
- At 6 decimals, a fit near a rounding boundary could still flip one digit across design sizes. The probability is low but not zero.

## Next actions

#43 should write v2 snapshots, and its team scorer should read them through `load_ratings`.
