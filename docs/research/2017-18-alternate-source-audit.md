# 2017–18 alternate-source feasibility audit

[#163](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/163), 2026-11-28. A V3-derived reconstruction agrees with the pinned NBA boxes on 154 of 163 regular-season and both playoff quarantines from the experimental #99 build. That supports a bounded alternate-source experiment. The quarantine-only comparison cannot solve the accepted games' existing unresolved possessions, and 2017–18 remains outside the registered target cohort.

## Development inventory

| Result | Regular season | Playoffs |
| --- | ---: | ---: |
| Previously accepted after #99 repair | 1,067/1,230 | 80/82 |
| Remaining quarantines in same build | 163 | 2 |
| Bill archive has events and correct final score | 163 | 2 |
| Every player matches official minutes and plus-minus | 154 | 2 |
| Provider's own rotation flag passes | 162 | 2 |

The quarantines comprise 86 parser errors, 67 unsupported reorders, four player plus-minus mismatches, four missing period starts, two V3 final-score mismatches, one unresolved starter and one period-score mismatch. The previously flagged 15 successful experimental repairs and all previously failed repair verdicts are preserved. The #99 default build, data.nba `ord` corrections, V3 neighbor comparisons and Bentes lineup comparison are prior development evidence. The new evidence is an independently implemented V3 rotation pipeline checked against the same official NBA boxes. The two playoff IDs are `0041700117` and `0041700176`.

There is a difference between the provider flag and the project's stricter recheck. Compare each game's final score by team ID and require a complete one-to-one set of player IDs, exact plus-minus and less than one millisecond absolute error against the pinned NBA.com minutes. This audit found 154 qualifying regular games by that aggregate test. For adoption, each must also pass event order, period scores, exact lineups and control ownership. Public Bentes lineups and data.nba labels help compare sequences with explicit provenance. They share upstream NBA inputs. The #160 ESPN development sample establishes that a different publication can help corroborate a subset of event actors and clocks, but we did not use ESPN on 2017–18 games in this aggregate sweep.

## Separate recovery requirements

1. **Quarantined game coverage.** The regular-season floor is 1,194 accepted games, so 127 more are needed. The 154 provisional box matches exceed that by 27. Register a game-level alternate candidate sourced from archived V3 bytes, with no event splicing and explicit source pins. On development cases, require nondecreasing clocks, stable printed counts, unambiguous substitutions and starters, technically correct score allocations and no decisive ownership contradictions. Test ordering and draw-foul/technical groups separately. Independent row-level evidence is still needed on affected windows. When multiple transformations satisfy the aggregates, retain the quarantine. Publish new source strata and verify that previously accepted games are invariant under the fallback.
2. **Accepted-game unresolved exposure.** The #99 candidate has 875 unresolved of 225,248 canonical possessions (0.388%). There are 80,279 Bill event rows in the 165 remaining quarantines. Even crediting a new, fully resolved possession per event would leave 875 of 305,527 unresolved (0.286%). At least 570 existing unresolved possessions would still need to be resolved to meet the 0.1% limit under that deliberately generous denominator. A second experiment must address boundary and ownership within accepted streams, with the prior #99 clock/actor evidence and a separate corroborator. Start by stratifying by defensive rebounds, final free throws, made shots and turnovers as described in #99's residual analysis. Test the literal #138 negative control and separate administrative free throws from live control. Freeze event-mapping and same-clock rules and compare denials and corrections by period, team, margin, substitution pattern and clock. No automatic promotion follows from either experiment alone.

For success, both thresholds and every hard reconciliation check must pass in independently reviewed, versioned results before generating canonical candidate rows. Only then check the overlap with the tracking source window. A failed qualification retains the current cohort treatment. [#99 residual diagnosis](order-repair-v2-2017-18.md#residual-unresolved-possessions-diagnosis-not-fixed) · [ADR-0022 and ADR-0029](../DECISIONS.md)

## Local inputs

- Original raw and build, `data/raw/2017-18/issue-25-v1` and `data/processed/2017-18/issue-99-order-repair-v2-c`. Filter `game_stream.parquet` to `quality = 'quarantined'` and group `quality_issue.parquet` by quarantine code.
- Bill Mill's archive at inspected revision [`d3941f7`](https://github.com/llimllib/nba_data/tree/d3941f7b3105973ef77bf21409eb6bd9c2b65903), `game_events/season=2018/data.parquet` SHA-256 `0fd877afbc2dffc07e8aea0d7898fe378e97e103cb7b30407d820cd8bad4f453`. Use the final ordered event's home and away team/score and compare by ID.
- `game_rotations/season=2018/data.parquet` SHA-256 `7aa5aea23204abe8d75039ab18a6cb5f0675cb62de846f7aeec4b2db7e993bdd`. Aggregate `out_time - in_time` and `plus_minus` by game/player before a full outer join to the pinned NBA player logs.
