# Agent run: verify the 2022–23 M1 build with external evidence

- **Date:** 2026-11-23
- **Status:** Awaiting review.
- **Related issues:** [#5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) (closed by #15)
- **Branch / commit / PR:** `claude/issue-5-external-verification` from `94ad909`. The code is in `e5020b6` and `32d1303`.

## Objective and authorized scope

The user asked to verify the rest of the pilot, including with external data sources. The user approved downloading eight public archives, about 50 MB, into private storage and pinning them by hash. Build acceptance was left unchanged.

## Work completed

- `pilot_sources.EVIDENCE_SOURCES` and `python -m bil.data.pilot capture-evidence` pin the data.nba.com, liveData and pbpstats.com archives from the already pinned Shufinskiy revision, plus the Bentes stints from the source audit.
- `pilot_evidence.py` and `python -m bil.data.pilot evidence` compare a build with them: lineups, possession offense, possession counts, event order, inferred starters and period scores. The command refuses a build that was not made from the given snapshot. One synthetic test was added, for 17 tests in total.
- The pilot guide has a new external-verification section, and the source ledger lists the evidence assets. Added ADR-0010 and EXP-0003.

## Key decisions and discoveries

- **Feed independence.** Every feed derives from the NBA's event log. data.nba and liveData share order numbers, so they count as one path separate from V2 and V3. Bentes appears box-calibrated.
- **Starter evidence.** liveData records between-period substitutions, which V2 never logs. That is direct evidence for period starters.
- **Substitution defects.** All 10 minutes-swap and V3-substitution quarantines share a single fault: V2 and liveData agree with each other and the box contradicts them for one window.
- **V3 period scores.** In two games V3 alone disagrees with three other feeds, so those quarantines are wrong.
- **Not adopted.** Precise liveData clocks and the three proposals in ADR-0010 were left out of the build.

## Verification performed

| Check | Actual result |
| --- | --- |
| Download integrity | Six Shufinskiy files matched the pinned tree's Git blob IDs. Two Bentes files matched their published SHA-256 values. `capture-evidence` re-downloaded and verified all eight. |
| `uv run --extra dev --extra pilot pytest -q`, Ruff lint and format, `mypy src` | Pass, 17 tests |
| `evidence` on `issue-5-v5` | Results as listed in the [pilot guide](../data-pilot.md#external-verification). Takes about 10 seconds. |
| Independent review (fresh-context Claude Sonnet subagent) of `e5020b6` | No blockers. Fixed in `32d1303`:<br>• per-period score comparison, which also surfaced a data.nba period-keying defect<br>• strict, single-match starter checks<br>• build coverage and snapshot pairing<br>• a pbpstats.com possession-count comparison<br>• idempotent staging<br>• liveData and period-score tests<br>• wording that calls the feeds separately archived rather than independent |

## Blockers and remaining risks

- 24 quarantines remain, all classified by cause in the guide.
- Usage rights for the evidence feeds follow the same private, noncommercial posture as the pilot inputs.

## Next actions

- Decide on the three ADR-0010 proposals. The third would restore the box as an independent check for the inferred-starter games.
- Start issue #6.
