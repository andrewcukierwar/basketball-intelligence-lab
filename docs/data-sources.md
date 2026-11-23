# Historical NBA Data Sources — Audit

**Status:** Candidate inventory; no source is yet accepted as canonical.

Data strategy is free-first, auditable and license-aware. Verify the current coverage, access requirements and usage terms before ingesting or redistributing anything.

| Candidate | Potential data | Use | Verification required |
| --- | --- | --- | --- |
| [Ramiro Bentes NBA Data](https://github.com/ramirobentes/nba_data) | Historical play-by-play / lineup stints / possessions | Candidate bulk historical foundation | Seasons, field definitions, score accuracy, license |
| [nba_api](https://github.com/swar/nba_api) | NBA stats endpoints, player logs, tracking summaries | Box score, features and incremental updates | Endpoint stability, missing seasons, request limits and use terms |
| [pbpstats](https://pbpstats.readthedocs.io/) | Possession parsing and on-court lineups | Independent parser / reconciliation | Event edge cases and source dependency |
| [Shufinskiy NBA data](https://github.com/shufinskiy/nba_data) | Historical NBA feed archives | Cross-check / alternative feed | Coverage, quality and reuse rights |
| [SportsDataverse/hoopR](https://hoopr.sportsdataverse.org/) | NBA historical analytics tools/datasets | Secondary validation/reference | Available files and supported schema |
| [Basketball-Reference](https://www.basketball-reference.com/) | Historical player/team summary statistics | Human validation and box-score baselines | License, automation and redistribution limits |

## Required source ledger fields

Source, provider, exact URL/version, season range, dataset type, retrieved_at, earliest_known_available_at (if known), checksum, row count, coverage/completeness, quality flags, refresh process, allowed uses, attribution, redistribution permissions and restrictions.

## Primary ingestion requirements

1. Preserve immutable raw snapshots before normalization.
2. Store data availability and game-finalization timestamps separately from game dates.
3. Canonicalize IDs and season/playoff boundaries.
4. Reconcile games, events, scores, minute totals, five-player lineups and possessions.
5. Compare at least one independent source on stratified representative samples.
6. Record source-specific edge cases and exclusion reasons.
7. Do not blindly combine different possession-count conventions; document chosen outcome definition.
8. Never include API credentials, raw restricted files or enormous parquet datasets in Git.

## Tracking considerations

Publicly accessible defensive metrics may include defended shots, nearest-defender shooting summaries, contested rebounds, matchup aggregates and hustle stats. These are **not** equivalent to full optical player-coordinate tracking and have unequal historical coverage. Model missingness and selection bias explicitly.

## Initial source-acceptance gate

A 2022–23 sample with immutable manifests, comprehensive schema, score/lineup reconciliation, independent checks, and a source-permissions review. Expand beyond one season only when quality thresholds are met.