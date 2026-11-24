# Issue #51 historical feed coverage audit

- **Date** 2026-11-23
- **Status** Independently reviewed
- **Issue** [#51](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/51)
- **Branch** `codex/issue-51-feed-coverage`, based on `d3d01f3`

## Scope and work

Measured the 2001–02 through 2024–25 regular-season and playoff feeds from Shufinskiy, Bentes and Bill Mill. Recorded 2025–26 and 2026–27 metadata only. The [audit report](../research/nba-feed-coverage.md) links the per-asset revisions and counts, rule coverage matrix, source terms, and batch plan.

The private local capture is in `data/raw/historical-feed-audit/2026-11-23`. It contains 412 source payloads totaling 1,393,644,925 bytes, including reused 2022–23 pinned pilot bytes. Git ignores this directory. The source SHA-256 and available publisher digest were checked locally. The checked-in registers contain aggregate metrics and provenance only.

## Decisions and discoveries

- Used team box logs as the cross-feed denominator. Retained full-file counts and separately scoped IDs to prefixes `002` and `004`. These counts establish availability and do not certify ingestion, lineup correctness or historical point-in-time availability.
- Used local SHA-256 for mutable Bill Mill season partitions and recorded the catalog's dataset-level update stamp as contextual metadata. Bound Shufinskiy files to the pinned Git tree and Bentes files to release asset IDs and published digests.
- Found absent V2 games in 2019–20, absent V3 games in 2012–13, the first data.nba archives missing `ord`, and comparison gaps in both outer folds. The report specifies fallback and quarantine behavior. No change to the existing pilot builder was needed to measure these differences.
- The initial scanner assumed the pilot's data.nba schema. The measured 2016–17 schema exposed the assumption. The scanner now treats missing order columns as unavailable period-score evidence and continues counting offense keys.

## Verification

| Check | Observed result |
| --- | --- |
| Public provider metadata and local asset scan | 48 measured season/type partitions. 460 measured entries, 89 absent entries and 23 inventory-only entries. All listed pre-holdout payloads were available. |
| Local replay from the recorded CSV pins | `PYTHONPATH=src .venv/bin/python scripts/audit_feed_coverage.py <private-capture> <scratch-output> --pins docs/research --jobs 6` regenerated four byte-identical CSVs. |
| 2022–23 reconciliation to issue #2 counts | Checked Bentes events, possessions and stints, V2, V3, pbpstats.com and both box logs. The regular-season and playoff counts match published pilot values. |
| Evidence gaps | Compared scoped game-ID sets directly. Confirmed two shared 2023–24 regular-season omissions across data.nba and pbpstats.com. Confirmed one shared 2024–25 playoff omission across data.nba and all three Bentes files. |
| Holdout isolation | The acquisition queue and scanner excluded payloads for starting years 2025 and 2026. Verified no matching payload files in the capture. |
| Repository checks | `pytest -q`: 43 passed. `ruff check .`, `ruff format --check .`, `mypy src scripts/audit_feed_coverage.py` and `git diff --check` all passed. |

The independent reviewer confirmed the holdout inventory boundary and all 412 measured local assets. A targeted 2016–17 replay reproduced each of the four register slices exactly. No acceptance blockers remained.

## Next actions

Land #51, then use the pinned captures and era-specific coverage gates for [#25](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/25) and [#52](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/52). Split [#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53) into the proposed historical batches before implementation. Any season build must run the game-level checks and record accepted, quarantined, and evidence-limited games. [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42) governs confirmatory outcome access.
