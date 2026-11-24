# Issue #54 pilot verification

- **Status:** Implementation verified and independently reviewed.
- **Scope:** [Issue #54](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/54) on `codex/issue-54-pilot-verification`. Pilot rebuild at `8a1edadbcf7fc2964508d85906d2a978ce691e77`, based on `d3d01f3`.
- **Changes:** Added an independent same-offense check on exported possession rows. Adjacent rows in a period with the same offense must both be unresolved, or their earlier possession or its predecessor must contain a flagrant foul confirmed by the pinned V2 archive. Added synthetic acceptance and rejection cases and a real-parser integration fixture for each of starter search and V3-primary retry.
- **Data handling:** Archived tests use two games selected from the existing private snapshot via `BIL_PILOT_SNAPSHOT`. The tests skip without that variable. Source and derived game rows stay outside Git.

## Verification

| Check | Result |
| --- | --- |
| `BIL_PILOT_SNAPSHOT=… python -m pytest -q` | All 46 tests pass, including both archived cases and the flagged/unresolved controls. A first run exposed a mistyped game ID in the synthetic archive test. Corrected it and reran the suite. |
| Ruff lint and format, mypy, diff whitespace | Pass. |
| Full build from pinned `issue-5-v2` and `check` | 26 of 26 checks pass. 1,292 of 1,314 games accepted, with 256,456 counted possessions, 2,756 parser exclusions and 51 unresolved possessions. Across accepted games, 36 same-offense pairs within a period consist of 20 pairs with both members unresolved and 16 covered by the flagrant exception. |
| Comparison against the #19 pilot | Eight tables have identical SHA-256. The remaining two differ only in `ingested_at`. Coverage and disposition counts agree. |
| `evidence` against the pinned comparison inputs | Runs successfully on the rebuilt pilot. |
| Fresh-context review of the four-file implementation | No blockers. The review confirmed the V2 foul codes, period boundaries, exact sequence intervals and real-parser integration paths. |

The pilot alternation check found no unexplained violation to carry forward into the historical RAPM row work in #20.
