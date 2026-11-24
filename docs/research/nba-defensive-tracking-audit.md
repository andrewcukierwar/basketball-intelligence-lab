# Public defensive tracking for the 2017–18 through 2022–23 window

**Audit date** 2026-11-23. NBA game data are attributed to NBA.com. This extends the [original matchup inventory](nba-source-validation.md#defensive-matchup-coverage) for [issue #37][issue]. It measured both season types, including the 2019–20 gap, without accessing confirmatory outcomes.

The per-game matchup archive supports a **private retrospective paired candidate**. The pinned SportsDataverse mirror covers **7,542 of 7,562 games** in the positive-minute NBA box universe, including all 503 playoff games. It provides **159,691 of 160,241** positive-minute defender-game rows with linked matchup evidence and positive partial-possession exposure. A strict historical paired cohort is **unavailable on the recorded revisions**. The season-total hustle and rim archives can describe coverage retrospectively, with no game-level history or evidenced cutoff eligibility. [Aggregate counts](nba-tracking-audit-counts.json) · [Source pins](nba-tracking-audit-assets.csv)

The EPM author describes a six-season defensive tracking SPM fit to a multi-season RAPM. It gives the window and approximate possession count but does not identify the feature set or state whether playoffs enter the tracking model. The NBA announced leaguewide Second Spectrum tracking for 2017–18 onward. Neither statement establishes access to the underlying observations, the provider's adjustment and role logic, or its exact point-in-time feed. Those are **methodology and source gaps**. An absent game, absent player, null metric, or zero recorded opportunity in the public archives is a separate **statistical coverage** issue. [EPM methodology][epm] · [NBA tracking announcement][nba-tracking]

## Provider, grain, opportunities and use

| Source | Measured scope and linkage | Opportunities and decision |
| --- | --- | --- |
| NBA `BoxScoreMatchupsV3`, Shufinskiy and SportsDataverse mirrors | Both mirrors measured for all six seasons and both types. Each row identifies an ordered offensive and defensive NBA person pair and a game. SportsDataverse names both IDs and teams. Matching directed keys and compared numeric fields verified that Shufinskiy's outer `person_id` maps to offense and its nested `matchups_person_id` maps to defense in the compared archives. | A `partial_possessions` value allocates fractional matchup exposure. The provider does not expose the frame-level assignment algorithm. `matchup_field_goals_attempted` counts shots attributed to the matchup and denominates its made-shot rate. Compare these fields in the paired retrospective cohort below. [SportsDataverse schema][sdv-matchups-schema] · [Shufinskiy extraction][shuf-code] |
| NBA `LeagueHustleStatsPlayer`, SportsDataverse totals | A verified file per season and type, linked by NBA person ID to the positive-minute box population. Its game and minute counters are aggregate exposures. There is no game ID in the archived rows. | Hustle contests count actions before release and deflections count disruptions of the ball on non-shots. Use measured season totals for descriptive checks. A count per played minute is an exposure rate, and the archive supplies no at-risk contest or deflection denominator for a probability. Keep season totals out of the dated matchup cohort. [NBA glossary][glossary] · [Hustle archive][sdv-hustle] |
| NBA `LeagueDashPtStats` Defense, SportsDataverse `player_tracking_defense` | Each verified season file contains regular-season and playoff totals. Link by NBA player ID and season type. There are no defender-game or shooter keys. | `def_rim_fgm / def_rim_fga` on positive rim attempts measures shooting on NBA-attributed rim defenses. These totals do not quantify shot deterrence or team help. Keep season totals out of the dated matchup cohort. [NBA glossary][glossary] · [Tracking archive][sdv-tracking] |
| NBA `LeagueDashPTDefend` overall and distance categories | NBA documents a defender-based player dashboard. Historical per-season payloads, within-game opportunities and publication revisions were not verified in this audit. The dated website query did not return inspectable historical rows in the audit tool. | Defended attempts and makes are defined by the dashboard's attribution; distance-to-hoop categories can overlap. Hold this family out of the candidate feature set until there is a pinned historical game-level path. [NBA defense dashboard][nba-defense] · [NBA glossary][glossary] |
| NBA closest-defender shooting dashboard and shot detail | NBA documents shooting by closest-defender distance. The dated dashboard query did not return inspectable historical rows. Shufinskiy's shot-detail archive links shooter, game and shot event with court coordinates. | A distance bucket describes a shooting opportunity and does not identify the responsible defender. Shot coordinates locate the attempt and do not measure defender distance. No defender-level feature is derivable from the verified shot-detail fields. [NBA shooting dashboard][nba-shots] · [Shot-detail fields][shuf-fields] |

The three public tracking and hustle archives use NBA Stats inputs. Their same-source agreement checks transcription and revision stability. SportsDataverse and Shufinskiy are distribution channels for NBA data. The Bill Mill positive-minute player game logs used for linkage also derive from NBA records. [Source ledger](../data-sources.md)

## What was measured

The first table counts positive-minute box appearances by unique `(game_id, player_id)`. Both matchup mirrors were compared on directed pair identity, offensive and defensive teams, partial possessions, matchup FGA, FGM and turnovers. The SportsDataverse counts below require all represented pair rows for that defender-game to join to positive-minute box appearances on the indicated opposite teams and to have finite, nonnegative candidate quantities with makes no greater than attempts.

| Season | Type | Shufinskiy games | SportsDataverse games / box games | SportsDataverse pair rows | Linked defender-games with positive exposure / positive-minute box appearances | With positive matchup FGA |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2017–18 | Regular | 1,222 | 1,222 / 1,230 | 231,888 | 25,923 / 26,104 | 25,129 |
| 2017–18 | Playoffs | 82 | 82 / 82 | 14,555 | 1,722 / 1,729 | 1,642 |
| 2018–19 | Regular | 1,223 | 1,223 / 1,230 | 232,983 | 25,930 / 26,098 | 25,258 |
| 2018–19 | Playoffs | 82 | 82 / 82 | 14,616 | 1,756 / 1,761 | 1,669 |
| 2019–20 | Regular | 967 | 1,055 / 1,059 | 198,908 | 22,289 / 22,392 | 21,655 |
| 2019–20 | Playoffs | 83 | 83 / 83 | 14,071 | 1,686 / 1,692 | 1,625 |
| 2020–21 | Regular | 1,080 | 1,080 / 1,080 | 202,196 | 23,036 / 23,054 | 22,233 |
| 2020–21 | Playoffs | 85 | 85 / 85 | 15,060 | 1,861 / 1,864 | 1,711 |
| 2021–22 | Regular | 1,229 | 1,229 / 1,230 | 229,901 | 26,003 / 26,036 | 25,115 |
| 2021–22 | Playoffs | 87 | 87 / 87 | 15,312 | 1,889 / 1,891 | 1,747 |
| 2022–23 | Regular | 1,230 | 1,230 / 1,230 | 229,185 | 25,875 / 25,892 | 25,056 |
| 2022–23 | Playoffs | 84 | 84 / 84 | 13,817 | 1,721 / 1,728 | 1,615 |

- The SportsDataverse archive supplies 88 additional 2019–20 regular-season games, taking the matchup comparison from 967 to 1,055 of 1,059. The two archives otherwise have the same game sets. The broader revision still omits 8 regular-season games in 2017–18, 7 in 2018–19, 4 in 2019–20 and 1 in 2021–22.
- Among 1,395,420 shared directed keys, 453 rows differ in at least one compared field. In addition to rows in the 88 extra games, SportsDataverse has four additional pair rows in overlapping games and Shufinskiy has none. The sources share lineage and differ by capture or processing revision. Freeze one revision for modeling and keep the other for sensitivity comparisons.
- All 1,412,492 SportsDataverse matchup rows had valid numeric candidate quantities and unique directed keys. Sixty-two rows did not pass the positive-minute, opposite-team box linkage. There were 1,172 zero partial-possession rows and 692,395 zero-FGA rows. These are supplied values. An absent row or game remains an unknown opportunity.
- Positive box FGA exactly matched the sum across tracked defender pairings for 62,662 of 152,182 linked shooter-games with positive FGA. Matchup shot attribution has a smaller or different scope than the complete box outcomes. This rules out treating matchup counts as an exhaustive shot ledger, regardless of game coverage.
- The rim archive linked all 4,594 positive-minute box player-season-type combinations, with one additional playoff player in 2019–20 without a positive-minute box match. It had no null rim counts and includes zero-attempt rows. The hustle archive linked 4,524 of those 4,594 player-season-types. Its observed rows contain no nulls among the audited contests, deflections, charges or defensive box-out counts. Three of the 4,524 rows had zero total minutes and are ineligible for per-minute rates. Per-season row and zero counts are in the [audit output](nba-tracking-audit-counts.json).

## Publication timing and rights

The [asset register](nba-tracking-audit-assets.csv) pins the Shufinskiy Git tree and blob IDs, the SportsDataverse releases and asset IDs, and every inspected file's SHA-256. The SportsDataverse historical assets show publication or update metadata in August 2026 (rim), September 2026 (hustle) and October 2026 (matchup). These are archive timestamps. Shufinskiy documents adding matchup history in February 2025 and does not provide a dated, per-game history of the exact revisions used here. Bill Mill's recorded timestamp is dataset-level metadata. The official game date and the NBA's general stats update guidance do not establish first publication or correction cutoff for the measured fields. Classify these revisions as capture-bound with the audit observation date. A strict origin before capture requires independent proof of its exact eligible revision. [Shufinskiy archive announcement][shuf-readme] · [NBA Stats FAQ][nba-faq] · [Evaluation contract](../validation-strategy.md)

The audit follows the project's private noncommercial research scope, with NBA.com attribution. NBA terms restrict redistribution and commercial, gambling, fantasy and certain statistics product uses. Neither a mirror's repository license nor the public availability of a download grants broader upstream rights. Store captures and derived row-level data privately. The committed artifacts contain aggregate audit counts and provenance. Research uses requiring broader rights need their own permission record. No purchased, private-player-tracking, or EPM rating data were used. [NBA Statistics terms][nba-terms] · [Project rights ledger](../data-sources.md#schema-access-and-permissions-ledger)

## Paired evaluation cohort for #38

Use the six SportsDataverse matchup revisions as the candidate source because they name both roles and add 88 previously missing games. Keep season and type as separate strata and report regular-only and playoff-included sensitivities. The box appearance counts above provide a measured coverage ceiling before independent target reconciliation and the #29 feature join.

1. For each qualifying defender-game, sum `partial_possessions`, opponent `matchup_turnovers`, `matchup_field_goals_attempted` and `matchup_field_goals_made` over directed rows. Preserve numerators and denominators when combining games. Candidate features are opponent turnovers and attributed attempts per 100 matchup partial possessions, and attributed makes per attempt. These are rates among credited matchups. They do not measure every team defensive possession or assign causal defensive credit.
2. Use positive partial possessions for exposure-based rates and positive FGA for the made-shot rate. The fully exposed candidates number **154,455 defender-games** before the target and #29 joins. Model the missing-FGA stratum or use the box fallback under a registered policy. Leave out failed participant links and preserve source omissions separately from finite zeros. Keep minutes and rates checked by season type and exposure thresholds.
3. In a private **retrospective** comparison, intersect the candidate rows with accepted independent RAPM target scope and #29 box eligibility. Fit the frozen box-only reference on the same inputs, compare on the same paired scored rows with chronological outcome boundaries, and report lost coverage against the full box-only cohort. Freeze opportunity and missing-feature policy before scoring. Use the six-series window as the historical calibration scope, with all rows outside the window requiring separate eligibility evidence.
4. Withhold strict historic evaluation on the measured assets. A whole-season chart or revised matchup snapshot cannot enter a historical prediction origin if the exact revision was unavailable then. Treat empty strict eligibility as an observed limitation for #38. Revisit only with evidenced dated revisions or a separately authorized prospective plan. Preserve the confirmatory holdout.

## Reproduce the audit

Fetch the pinned asset basenames into private local directories under the recorded access scope. Use the six player-game box files captured in the [season-feed audit][season-audit], with exact digests as recorded here. Run the offline profiler using the pilot DuckDB dependency. It verifies every pin before loading the historical payloads and emits aggregate rows only.

```sh
.venv/bin/python scripts/audit_defensive_tracking.py \
  /path/to/private/tracking /path/to/private/box-logs \
  docs/research/nba-tracking-audit-assets.csv /path/to/new-counts.json
```

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/37
[season-audit]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/51
[epm]: https://dunksandthrees.com/about/epm
[nba-tracking]: https://pr.nba.com/nba-announces-multiyear-partnership-sportradar-second-spectrum/
[nba-defense]: https://www.nba.com/stats/players/defense-dash-overall
[nba-shots]: https://www.nba.com/stats/players/shots-closest-defender
[glossary]: https://www.nba.com/stats/help/glossary
[nba-faq]: https://www.nba.com/stats/help/faq
[nba-terms]: https://www.nba.com/termsofuse
[shuf-code]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/loading/utils.R#L623
[shuf-fields]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/description_fields.md
[shuf-readme]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/README.md
[sdv-matchups-schema]: https://hoopr.sportsdataverse.org/reference/load_nba_stats_game_matchups.html
[sdv-hustle]: https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_hustle
[sdv-tracking]: https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_leaguedash
