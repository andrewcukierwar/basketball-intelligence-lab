# 2022–23 NBA source validation and historical matchup coverage

**Audit date:** 2026-11-23. NBA game data and official reference results are attributed to NBA.com. This is follow-up evidence for [issue #2][issue] and the [source ledger](../data-sources.md). All archive reads were for a local research audit. The repository contains aggregate quality findings and source identifiers.

## Inputs and access

- Downloaded the six Bentes 2022–23 releases once, using their published asset URLs. All returned HTTP 200 and matched the published byte counts and SHA-256 values. [Source ledger](../data-sources.md#pilot-asset-identifiers-and-observed-metadata)
- Checked Shufinskiy NBA Stats V2 and V3, shot detail and processed `pbpstats` CSVs for 2022–23. Also checked V3 and matchup assets for each regular season and postseason in the six-year tracking window. Each compressed file matched the size and Git blob ID at commit `46488f0f8e1cab58fc1256511ea808166a443a15`. Files use the season's starting year. [Pinned archive][archive]
- Native NBA CDN `static/json/liveData` play-by-play and box-score requests for the regular-season opener and Finals Game 1 returned HTTP 403 for all four requests. This records access from the audit environment for those URLs. NBA.com game summary and box-score pages provide a manual check, and the offline parser used the archived data. [Regular-season opener][opener] [Finals Game 1][finals]
- The NBA Statistics terms specify attribution and restrict permitted purposes and uses. A publisher's download route or repository software license supplies no evidence of upstream rights to republish the game data. BIL's intended wider use, including public datasets or commercial outputs, requires its own permission record. ESPN assets were checked at inventory level only because the rights for the proposed automated comparison remain unverified. [NBA terms][nba-terms] [Shufinskiy license][shuf-license] [Disney terms][disney-terms]

## Pilot game and schema checks

All checked 2022–23 Bentes, V2, V3 and processed `pbpstats` files contained the same set of 1,230 regular-season and 84 playoff game IDs. Those totals agree with the NBA's 82-game regular-season schedule for 30 teams and the sum of games in the 15 playoff series. IDs had regular-season or playoff prefixes only. Treat play-in games as outside this specific pilot inventory. [NBA regular-season announcement][schedule] [NBA playoff series][series] [NBA play-in history][play-in]

| Check | Regular season | Playoffs |
| --- | ---: | ---: |
| Bentes event rows | 591,146 | 39,353 |
| Bentes possession rows | 247,007 | 16,330 |
| Bentes stint rows, both team perspectives | 74,016 | 4,984 |
| Archived NBA Stats V2 event rows | 574,410 | 38,216 |
| Archived NBA Stats V3 action rows | 603,785 | 40,163 |
| Archived `pbpstats` rows, observed granularity | 486,514 | 32,411 |
| V2 substitution rows with distinct positive IDs in both player slots | 57,340 / 57,340 | 3,733 / 3,733 |
| V2 repeated game/event keys | 14, all exact row repeats | 0 |
| Bentes repeated game/`event_num` keys | 1,492 | 92 |
| Bentes games where team possession points fall short of event finals | 208 | 10 |
| Bentes games where home-perspective stint point sums disagree with event finals | 0 | 0 |
| Final-period V3 score disagreements with Bentes event finals | 0 | 0 |
| V2 last scored row by period and event number disagrees with V3 final-period score | 12 | 1 |

The V2 CSV includes `GAME_ID`, `EVENTNUM`, `PERIOD`, `PCTIMESTRING`, the event and action codes, and three player and team ID slots. V2 substitutions (`EVENTMSGTYPE = 8`) occur in every pilot game and carry both player IDs. Bentes events contain `number_event`, local clock fields and names. Their `number_event` was unique within game in the pilot. The three Bentes tables encode lineups as comma-delimited names. Each lineup had five distinct nonblank strings. This establishes field shape only. Player identity, lineup truth, and availability times were outside this check. The newer Bentes `action_type` and absolute `time_actual` columns were entirely null in both pilot event files.

Bentes final scores use `hs` and `vs` at the last `number_event`. Score deltas and home-perspective stint totals matched those finals for every game. Summing `secs_played` by game and team perspective matched 2,880 seconds plus 300 per overtime in every group. There were 86 regular-season and two playoff stint rows with zero or negative duration across both perspectives. Use one perspective when aggregating so that scores and minutes are counted once. The possession key `(game_id, period, team_poss, poss_num_team)` was unique. Its points totaled up to three short for a team in a regular-season game and up to two short in a playoff game. The audit did not determine how unassigned points should be modeled.

In V3, select the last `actionType = period`, `subType = end` row with both scores, ordered by period and action number. The unrestricted highest-action-number score produced 13 regular-season and one playoff discrepancies with Bentes, all resolved by using final-period markers. The NBA.com final agreed in both parser sample games and in a playoff discrepancy spot check. Preserve event ordering evidence and retain the V2 exception counts for the pilot. Complete official score, minutes and plus-minus reconciliation is in [issue #5][pilot]. [Regular-season opener][opener] [Finals Game 1][finals] [Playoff score check][playoff-check]

## Machine-readable box-score comparison

Bill Mill publishes season Parquet files derived from NBA Stats team and player game logs. In the 2022–23 partition, both files returned HTTP 200. The server's Last-Modified timestamp is a snapshot property and supplies no evidence of availability on the game date. [Publisher data dictionary][billmill]

| 2022–23 partition | Bytes | Local SHA-256 | Server Last-Modified (UTC) |
| --- | ---: | --- | --- |
| [Team game logs][team-logs] | 157,942 | `bd3b4a9f745249c970970beffd27813ce2ed7e235a9df20228fde042535a6c43` | 2026-10-30 00:37:59 |
| [Player game logs][player-logs] | 1,608,541 | `5f378f06b35f36bf2aa928d2fb77c4d14ed87a4f43161f43b4e4de30c601638e` | 2026-10-10 12:15:13 |

Filtering prefixes `002` and `004` produced 2,460 regular-season and 168 playoff team rows, and 25,894 regular-season and 1,728 playoff player rows. Both game-ID sets matched the event candidate. Each game had two team rows and one home side. `(game_id, team_id)` and `(game_id, player_id)` were unique in their respective files. Team final scores matched the Bentes and V3 final scores for all 1,314 games. Every team/game player's point and plus-minus sums matched the team points and five times the team margin. The player-minute sums matched 240 minutes plus 25 per overtime to within floating-point rounding. These are consistency checks on the published logs. Use NBA.com boxes to arbitrate player-level disagreements. The publisher recomputes team plus-minus, and the player logs omit DNPs. Record the NBA upstream and publication restrictions for this candidate. [Publisher data dictionary][billmill] [NBA Statistics terms][nba-terms]

## Offline parser check

Python 3.12 with `pbpstats 1.3.11` loaded archived NBA Stats V2 events and matching `shotdetail` rows for the opener and Finals Game 1. For each game the audit wrapped the CSV rows in legacy `resultSets[0]` with `headers` and `rowSet`, using numeric event/player fields and preserving ten-character game IDs and input order. The `StatsNbaPbpFileLoader` read `pbp/stats_<game_id>.json`. The possession loader additionally required `game_details/stats_home_shots_<game_id>.json` and its away counterpart. The shot files used `GAME_EVENT_ID`, `LOC_X`, `LOC_Y` and `SHOT_DISTANCE`, split by the box score's home and away team IDs. HTTP calls raised locally during both tests. Event-only loading passed first, while the possession loader required the shot inputs. With both inputs it returned 193 and 186 possession objects respectively, and every parsed event in both games had five distinct players on each side. No lineup or possession interpretation was validated against ground truth for those games. [pbpstats 1.3.11][pbpstats] [Loader code][pbpstats-code] [Pinned shot and event archives][archive]

The processed `pbpstats` CSVs cover both game sets, but contain no five-player lineup fields or established one-row-per-BIL-possession key. Raw row counts equaled Bentes possession counts in none of the 1,314 games. Use the offline parser as the reference implementation and compare documented possession definitions before judging disagreement. The parser check is independent processing of the archived NBA inputs.

## Defensive matchup coverage

Denominators are distinct game IDs in the pinned V3 event archive, by season and type. The numerator counts games with at least one row in the corresponding matchup CSV. These matched game IDs after padding to ten characters. There were no matchup-only game IDs among the compared files. [Pinned V3 and matchup assets][archive]

| Season | Regular games covered / V3 | Playoff games covered / V3 | Regular matchup rows | Playoff matchup rows |
| --- | ---: | ---: | ---: | ---: |
| 2017–18 | 1,222 / 1,230 | 82 / 82 | 231,888 | 14,555 |
| 2018–19 | 1,223 / 1,230 | 82 / 82 | 232,985 | 14,616 |
| 2019–20 | 967 / 1,059 | 83 / 83 | 181,840 | 14,071 |
| 2020–21 | 1,080 / 1,080 | 85 / 85 | 202,195 | 15,060 |
| 2021–22 | 1,229 / 1,230 | 87 / 87 | 229,901 | 15,312 |
| 2022–23 | 1,230 / 1,230 | 84 / 84 | 229,185 | 13,817 |

Observed grain is one row per ordered `(game_id, person_id, matchups_person_id)`. Neither ID had blanks and that key had no repeats. The five checked fields `partial_possessions`, `matchup_minutes_sort`, `matchup_field_goals_attempted`, `help_field_goals_attempted` and `switches_on` had no blank or NA strings on observed rows. Game absence, especially the 92-game gap in 2019–20, still requires a separate missingness flag. A game with rows can have incomplete player or play coverage. Zero counts, absent rows and absent files have different meanings. Public defend dashboards, closest-defender shooting and hustle coverage remain unverified by season, and these matchup files provide no evidence of the exact EPM feature set. [NBA tracking announcement][tracking] [NBA Stats quick links][quick-links] [EPM uncertainty register](epm-uncertainties.md)

## Reproduction and pilot exit

The profiles used DuckDB 2.0.1 for Parquet, Python 3.12 `tarfile` and `csv.DictReader` for the single CSV member of each verified archive, and `pbpstats 1.3.11` in a temporary environment. Match by zero-padded NBA ID and the specified terminal-score rule. Count distinct game IDs and compare sets before computing rate or provider agreement. For the lineup shape check, split on commas, trim, discard blank fields and count distinct names. For matchup coverage, compare complete game-ID sets by source, then check uniqueness and explicit missing tokens by field.

Advance the V2 event candidate and named reconciliation references to the [canonical contract][contracts] and [one-season pilot][pilot]. Keep the pilot private and attributable under the recorded source constraints. Before accepting training data, verify permissions for the intended use, source publication and correction timing, game completeness, player-level box-score and lineup reconciliation, and explicit treatment of possession points and exclusions. Historical replay and model fitting remain later work.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/2
[contracts]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/3
[pilot]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5
[archive]: https://github.com/shufinskiy/nba_data/tree/46488f0f8e1cab58fc1256511ea808166a443a15/datasets
[shuf-license]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/LICENSE
[nba-terms]: https://www.nba.com/termsofuse
[disney-terms]: https://disneytermsofuse.com/english/
[schedule]: https://pr.nba.com/2022-23-nba-schedule/
[series]: https://www.nba.com/playoffs/2023/series
[play-in]: https://www.nba.com/news/play-in-tournament-history
[opener]: https://www.nba.com/game/0022200001
[finals]: https://www.nba.com/game/0042200401-heat-vs-nuggets-denver-co-06-01-2023
[playoff-check]: https://www.nba.com/game/bos-vs-mia-0042200306
[billmill]: https://github.com/llimllib/nba_data/blob/main/docs/DATA_DICTIONARY.md
[team-logs]: https://basketball-data.billmill.org/nba/stats/team_game_logs/season=2023/data.parquet
[player-logs]: https://basketball-data.billmill.org/nba/stats/player_game_logs/season=2023/data.parquet
[pbpstats]: https://pypi.org/project/pbpstats/1.3.11/
[pbpstats-code]: https://github.com/dblackrun/pbpstats/tree/main/pbpstats/data_loader/stats_nba
[tracking]: https://pr.nba.com/nba-announces-multiyear-partnership-sportradar-second-spectrum/
[quick-links]: https://www.nba.com/stats/quicklinks
