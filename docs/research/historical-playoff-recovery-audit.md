# Near-threshold playoff recovery audit

[#162](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/162), 2026-11-28. These four seasons are one playoff game short under ADR-0022. The replay recovered zero games. A separate V3 rotation reconstruction passed the box checks on six games, giving concrete recovery leads for three seasons. No season entered the training cohort.

## Development evidence

We selected all 12 playoff quarantines from #53's pinned builds and used the NBA game ID as the only cross-source key. The rerun uses the existing same-clock, free-throw-miss and #138 ownership checks, without changing any parser rule. Each game remains quarantined. Bill Mill's separately implemented V3 build was checked against the pinned official team and player logs. Minutes match exactly for every player in all 12 games. This V3-derived comparison uses the same upstream league data, so it qualifies candidates for development.

| Season | Game ID | Original quarantine | Bill score | Bill players with correct plus-minus |
| --- | --- | --- | --- | ---: |
| 2002–03 | `0040200141` | Unresolved starters, including missing period ends | Pass | 17/19 |
| 2002–03 | `0040200232` | Player plus-minus | Pass | 22/24 |
| 2002–03 | `0040200234` | Player plus-minus | Pass | 18/20 |
| 2003–04 | `0040300111` | Player plus-minus | Pass | 21/23 |
| 2003–04 | `0040300211` | Unsupported cross-clock reorder | Pass | 24/24 |
| 2003–04 | `0040300226` | Player plus-minus | Pass | 17/19 |
| 2011–12 | `0041100104` | Unsupported cross-clock reorder | Pass | 19/19 |
| 2011–12 | `0041100167` | Ambiguous rebound candidates and rejected free-throw retry | Away score +1 | 8/18 |
| 2011–12 | `0041100201` | Unsupported cross-clock reorder | Pass | 19/19 |
| 2013–14 | `0041300171` | Unknown possession offense | Pass | 18/18 |
| 2013–14 | `0041300173` | Unresolved starters after unsupported reorder | Pass | 17/17 |
| 2013–14 | `0041300224` | Unsupported cross-clock reorder | Pass | 22/22 |

The six candidates all pass score, player minutes and player plus-minus. Their possession assignments, period boundary checks, clock ordering and independent evidence still need qualification. The 2002–03 alternatives fail at least two player plus-minuses each, and 2011–12 `0041100167` also fails the official final score. A game that fails those checks stays quarantined.

## Registered recovery and training-only designs

1. **Ordering and starter evidence.** Qualify exact event clocks, same-clock order, starters and ten-player lineups on the five box-reconciled order/starter candidates. Start with `0040300211`, `0041100104` and `0041300224`, one per recoverable season. A trusted independent event/lineup record or separately documented evidence for every affected sequence is required before recovery. Use another untouched quarantine in a verified family for the generalization check if available. Test the unsupported cross-clock transition as a synthetic regression. Preserve raw clocks, stop when several event sequences fit the same aggregates, and reconcile each period's scoring and the game's full possession ledger.
2. **Unknown offense and score/plus-minus failures.** Investigate `0041300171` separately at the possession level. Resolve a missing owner only with corroborated, unanimous decisive events and legal adjacent boundaries. No actor, clock or score may be inferred solely to obtain acceptance. For the six failed aggregate reconstructions, require newer primary evidence before another repair attempt. Stop on any unresolved aggregate mismatch, ambiguous owner, or unsupported event movement. For any accepted repair, re-run every selected-season game at the new revision. Verify previously accepted tables are unchanged (apart from ingestion timestamp) and compare all recovered row and disposition keys, unit exposure, score allocations, date bounds and game splits. Require independent review of the exact repair and results.
3. **Regular-season-only sensitivity.** Pending policy approval, compare the #161 matched reference with a separately versioned training branch that adds only fully reconciled regular-season games from these four seasons. Keep the 97% floor for the admitted regular season and the 0.1% unresolved limit within it. Carry the missing playoff denominator and outcomes in coverage rather than implicitly adding any playoff rows. Restrict 2002–03 to final RAPM history. Keep identical evaluation games, years, weighting and context across arms. Report player-team minutes, trade intervals, exposure by role and seeds, body of season, score margin, overtime, and the held-out playoff behavior separately. Missing history remains a gap. The sensitivity can be preregistered for later comparison without changing canonical season eligibility.

| Season | Accepted regular | Accepted playoffs | Playoffs needed | Regular box minutes retained | Playoff box minutes retained | Players with playoff minutes retained / expected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2002–03 | 1,172/1,189 | 85/88 | 86 | 98.57% | 96.51% | 187/187 |
| 2003–04 | 1,170/1,189 | 79/82 | 80 | 98.40% | 96.37% | 188/189 |
| 2011–12 | 979/990 | 81/84 | 82 | 98.85% | 96.45% | 204/204 |
| 2013–14 | 1,218/1,230 | 86/89 | 87 | 99.02% | 96.43% | 204/204 |

All players with regular-season box minutes have at least one observed game in the accepted set in each season. The corresponding regular unresolved counts are 80/218,660, 51/215,947, 59/182,283 and 64/233,111. The missing playoffs remove 63, 66, 56 and 57 positive-minute appearances, respectively. This is a coverage audit. The sensitivity still needs a hash-pinned fit cohort, approval and independent review before application.

## Reproduction

Use #53's [pinned builds and snapshots](historical-backfill-2001-2017.md), and the current pilot builder at `7386d22`. For each season pass the three listed `--game-id` arguments together with `--same-clock-rule --free-throw-miss-rule --control-ownership`. Compare the resulting review with the original. Compute retained box minutes and player coverage using `bil.data.season_quality.load_season`. Use the [Bill Mill v2 archive](https://github.com/llimllib/nba_data/tree/d3941f7b3105973ef77bf21409eb6bd9c2b65903). The Parquet inputs are `game_events/season=<end year>/data.parquet` and `game_rotations/season=<end year>/data.parquet`. Match final points by NBA team ID, aggregate rotation seconds and signed plus-minus by player, and compare to the same archived official logs by player key.

| End year | Events SHA-256 | Rotations SHA-256 |
| --- | --- | --- |
| 2003 | `5af833b9a09a85279c64aa76dce0048d1c09ff6db05c3729ec40ff8c3a5e74ef` | `15347cd124e78f304d45ffcfba6b4afd6f85b5ebbcb25eee16697f9b4777f4b9` |
| 2004 | `a8d79eaaa689f2a53912f962d7ec482d502128a99cde1b0316f7ca9d67147cb0` | `fb06ed33873e14b9d0925a87b80c43e1f994324201790aa9a3eb0a16d9573d7e` |
| 2012 | `a86451f466798abece897c4c548f5cff38bfaa8a7e8e6f095be7cab811774c1f` | `12b6f891192729cb54bc32f1c26314a85108cf626788af4353b468ad441b36ad` |
| 2014 | `cb332d0483ce162f20f81a3c29177e2974cec7be37cff7330f77363e3bd38743` | `3fa95c63f398ab588862ed859cd24907027d475bce8a1ac6db9051700348570b` |
