# Historical NBA data-source audit

**Ledger revision:** 2026-11-23. Scope is the 2022–23 NBA pilot and historical inputs for the 2026–27 EPM methodology. [Issue #2][issue]

**Provisional source of record:** Ramiro Bentes's 2022–23 event Parquet files are the leading candidate for the regular season and playoffs. The possession and stint files are useful derived comparisons. Each comes from the same provider and has the same declared upstream family. Use independent lineup reconstruction before accepting any derived rows.

**Reconciliation references:** Use official NBA box scores for final score, team totals, player minutes and plus-minus where available. Use `pbpstats` on a pinned Shufinskiy NBA archive asset to compare with BIL's independent lineup and possession reconstruction. ESPN via hoopR is the candidate for an independently distributed event feed, subject to permissions and game ID crosswalk validation. NBA archives, NBA box scores and `pbpstats` can detect independent processing errors while sharing upstream NBA data. Bentes does not identify the exact endpoint per season, so independence at collection level has yet to be established. [Bentes][bentes] [NBA box-score history][nba-box] [pbpstats][pbpstats] [Shufinskiy archive][shuf-tree] [hoopR play-by-play][hoopr]

## Coverage by season and evidence level

Ranges are inclusive. For the asset rows below, every season in each range had a matching published filename at the audit date. This verifies the file inventory only. Game counts, row counts, data inside each file, missing games and fields, and historical availability times remain unverified. The 2026–27 season is in progress. Older archive endpoints may also have partial coverage despite a matching filename.

| Source and dataset | Regular season | Playoffs | Evidence and known limitations |
| --- | --- | --- | --- |
| Bentes NBA event play-by-play, derived possessions and lineup stints | 1996–97 to 2026–27 for each table | 1996–97 to 2025–26 for each table | Checked GitHub release asset inventories. Bentes describes column changes at 2016–17 and 2025–26. The archive has a documented 2020–21 playoff exception using the older schema after a feed gap. Box-score and defensive tracking tables are outside the advertised inventory. [Provider coverage notes][bentes-coverage] [Play-by-play release][bentes-pbp] [Possession release][bentes-pos] [Stint release][bentes-stints] |
| Shufinskiy `nbastats` and `nbastatsv3` play-by-play | 1996–97 to 2024–25 (V2), 1996–97 to 2025–26 (V3) | Same filename coverage as regular season | Pinned Git tree. These are archived endpoint variants. Archived V2 availability does not imply the live V2 endpoint remains usable. [Archive index][shuf-tree] [Loading notes][shuf-loading] |
| Shufinskiy `datanba`, `cdnnba` and `pbpstats` play-by-play | 2016–17 to 2024–25, 2020–21 to 2025–26, and 2000–01 to 2024–25 respectively | Same filename coverage as regular season | Pinned Git tree. The `pbpstats` archive is processed play-by-play, with possession-related fields. Identically named game events or possession counts across feeds require reconciliation. [Archive index][shuf-tree] [Published field descriptions][shuf-fields] |
| Shufinskiy `shotdetail` and `matchups` | 1996–97 to 2025–26 and 2017–18 to 2025–26 respectively | Same filename coverage as regular season | Pinned Git tree. The matchup series overlaps all six EPM tracking-SPM seasons at file level. Shot locations describe events and do not provide optical player trajectories. Coverage denominators and exact season definitions still need verification. [Archive index][shuf-tree] [Published field descriptions][shuf-fields] |
| SportsDataverse ESPN play-by-play and player box scores | Combined annual asset inventory, play-by-play 2001–02 to 2026–27, player box scores 1993–94 to 2026–27 | Separate postseason coverage unverified | GitHub release asset inventories. Test season type and game completeness before relying on combined files. [ESPN play-by-play release][espn-pbp] [ESPN player box-score release][espn-box] [hoopR play-by-play][hoopr] |
| NBA official box scores and `nba_api` endpoint access | NBA reports digitized box scores since 1946–47 and advanced box-score stats since 1996–97 | Endpoint-by-season and field completeness unverified | The NBA statement covers site data availability. The community client provides separate endpoints for scoreboard, box scores, logs, play-by-play and tracking, with individual schema and access behavior. [NBA box-score history][nba-box] [NBA advanced box scores][nba-advanced-box] [nba_api v1.12.0][nba-api] |
| NBA public defensive tracking and hustle dashboards | NBA reports all-game tracking since 2013, with Second Spectrum from 2017–18. Dashboard and category coverage by season remains unverified. | Unverified | Provider eras establish that tracking was collected. They do not establish the public availability of a given metric, game exposure, definitions across eras or raw trajectories. [NBA tracking announcement][nba-tracking] [Defense dashboard][nba-defense] [Hustle dashboard][nba-hustle] |

## Schema, access and permissions ledger

| Candidate | Format, grain and pilot role | Access and rights finding |
| --- | --- | --- |
| Bentes NBA Data | Season/type Parquet for event rows with lineups and possession triggers, possession rows, and lineup stints. The uniform columns can contain era-specific nulls. The maintainer has yet to publish the full dictionary. [Provider schema and release notes][bentes] | Public GitHub releases with no account requirement according to the maintainer. Published GitHub metadata identifies the six pilot assets below. Applicable data license, redistribution permission and exact per-season upstream lineage are unverified. The maintainer advertises daily current-season refreshes. Preserve the exact asset digest even for completed seasons. [Provider README][bentes] [NBA terms][nba-terms] |
| Shufinskiy NBA Data | Compressed CSV per feed, season and season type. Fields depend on the upstream feed. The published dictionary and extraction scripts help identify event ordering, clock, participants and scores. Use the archived V3 feed for a parser/lineage comparison and matchups for a later tracking audit. [Field descriptions][shuf-fields] [Loading notes][shuf-loading] | GitHub tree and maintainer list provide snapshots without per-game API requests. GitHub lists Apache-2.0 for the repository. The status of upstream NBA or pbpstats data rights and redistribution remains to be confirmed. [Repository license][shuf-license] [NBA terms][nba-terms] |
| pbpstats | Python toolkit. Loads game data from NBA endpoints or locally saved source files. Adds possession boundaries, lineup IDs, score margins and event-order corrections. It documents overrides and a rule for excluding certain scoreless end-of-period possessions. Compare definitions before comparing counts. [Documentation][pbpstats] [Event rules][pbpstats-events] | Parser software has an MIT license. The source data's terms still apply, including when obtained as a third-party archive. Prefer a pinned parser with known input feed and snapshot. [Parser repository][pbpstats-code] [NBA terms][nba-terms] |
| NBA.com and nba_api | NBA website for official box-score reference. Community Python wrappers for stats and live JSON endpoints. `LeagueDashPTDefend` exposes grouped player defended-shot counts and percentages for season/type and other filters. Candidate data for defense features require matchup and hustle definition checks, game coverage and opportunities. [Client][nba-api] [Endpoint schema][nba-api-defense] | The client is MIT-licensed. The NBA's terms describe allowed use and attribution for its statistics and restrict specified uses including archived play-by-play services and comprehensive regularly updated public statistics products. The NBA Stats FAQ describes stats as for viewing on its site. Live endpoints can change and availability for a single call would establish neither stable access nor permission. [Client license][nba-api-license] [NBA Statistics terms][nba-terms] [NBA Stats FAQ][nba-faq] |
| hoopR and SportsDataverse | ESPN-derived play-by-play and box-score datasets served as annual release assets. hoopR documents ESPN game IDs and character play IDs from Parquet, and an RDS alternative. Preserve identifiers as strings and validate game and participant crosswalks before comparing rows. [hoopR schema][hoopr] [ESPN play-by-play release][espn-pbp] | Files have a public release inventory. Public assets and software licenses do not establish rights to use the underlying data for automated reconciliation. Disney's terms cover ESPN and limit automated extraction and model-related use of its products. Confirm permitted use of the archive for the proposed check before accessing it for that purpose. [Disney terms, §§1–2][disney-terms] |
| Basketball-Reference | Web tables provide a secondary manual check on player and team summaries. Season-grain data cannot establish event or lineup accuracy. | Kept as a manual reference candidate. Review Sports Reference's policy before automation, publication or reuse. [Sports Reference data use][sports-ref] |
| Dunks & Threes | Creator documentation supports methodology research. Published EPM, downloadable CSVs and API ratings are outside the input ledger. | Premium CSV and API terms restrict storage and downstream use in different ways. Any proposed external diagnostics require a permitted access route and use. [Dunks & Threes subscriber and API terms][epm-terms] |

## Pilot asset identifiers and observed metadata

Bentes uses the season's **ending** year, so `2023` is 2022–23. Shufinskiy uses the **starting** year, so use `2022`. The SportsDataverse releases use the ending year. The byte counts and SHA-256 values below came from GitHub's public release metadata on the ledger date. The Git tree supplies the Shufinskiy archive size and blob ID. These are provider metadata. BIL has not downloaded these files or independently checked their hashes.

| Published 2022–23 asset | Bytes | Upstream identifier |
| --- | ---: | --- |
| [Bentes regular-season events](https://github.com/ramirobentes/nba_data/releases/download/pbp/pbp_regular_2023.parquet) | 15,764,034 | GitHub asset 582062454, SHA-256 `02237973edf38cf121c7b2ad6e9e1a310f10dc27bc1b872ae68cacb2d4cf5640` |
| [Bentes playoff events](https://github.com/ramirobentes/nba_data/releases/download/pbp/pbp_playoffs_2023.parquet) | 1,005,826 | GitHub asset 582060586, SHA-256 `d32f87c090a38264458b6eaae217a503f7b80d54bcf50767d5495a69594e9723` |
| [Bentes regular-season possessions](https://github.com/ramirobentes/nba_data/releases/download/possessions/possessions_regular_2023.parquet) | 5,571,959 | GitHub asset 663237109, SHA-256 `bd19116fab12d77bed1b110b96b3cc1a38d78c0a594fed5fe399c8291d6ef9d5` |
| [Bentes playoff possessions](https://github.com/ramirobentes/nba_data/releases/download/possessions/possessions_playoffs_2023.parquet) | 335,692 | GitHub asset 663233936, SHA-256 `f8231db3fd7e48bf4ef7ba9c61156e07abc491162dedef6816a8fc469b2bc76f` |
| [Bentes regular-season stints](https://github.com/ramirobentes/nba_data/releases/download/lineup_stats/lineup_stats_regular_2023.parquet) | 1,469,829 | GitHub asset 582067188, SHA-256 `e99075847d7748db1ea414b888fc00cfb9ee7bb9727e58794ef2e7fccbe2efb7` |
| [Bentes playoff stints](https://github.com/ramirobentes/nba_data/releases/download/lineup_stats/lineup_stats_playoffs_2023.parquet) | 88,694 | GitHub asset 582066033, SHA-256 `441759669ae9f7afbf39f4e40dc82dc4fe2378148d3e7036ad3f10b89d390260` |
| [Shufinskiy regular-season NBA Stats V3](https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/datasets/nbastatsv3_2022.tar.xz) | 8,640,724 | Git blob `c57ba117f3fdde49649282682d7b3e669629c8a2` |
| [Shufinskiy playoff NBA Stats V3](https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/datasets/nbastatsv3_po_2022.tar.xz) | 573,940 | Git blob `dc8546865c51d964bc9595069c998b17608c073e` |
| [SportsDataverse ESPN events](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_pbp/play_by_play_2023.parquet) | 20,987,371 | SHA-256 `f3fac3a58cf1be8813f1f4332edb7fc8d83936df703892a700095d62f71da886` |
| [SportsDataverse ESPN player boxes](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_boxscores/player_box_2023.parquet) | 595,949 | SHA-256 `968d835cd04b10533c5b5af8c0e41bf0154a73782e9446c76f765109223e8679` |

## Pilot acceptance and outstanding evidence

2022–23 is the most recent season in both documented SPM training windows. Its published files span several event feeds and include matching regular-season and playoff assets. This makes it a useful data-quality pilot. Treat 2022–23 as overlapping reference-model training when evaluating historical fidelity. It can serve as an independent BIL holdout only under a separate, earlier BIL model-fit cutoff. [EPM methodology](https://dunksandthrees.com/about/epm)

1. **Confirm usage and lineage.** Determine whether the intended internal research acquisition and any future publication are permitted for each exact feed and asset. Identify Bentes's upstream 2022–23 endpoints if possible. Use only permitted inputs in the pilot. Document alternatives if a candidate is blocked.
2. **Freeze input snapshots.** Record provider, URL and revision, upstream feed, season and type, retrieval time, earliest evidenced availability and later correction times, locally computed SHA-256, row count, schema, coverage, exclusions, refresh behavior, permitted use, attribution and redistribution limits. Current file timestamps are insufficient to establish historical availability. Keep input data outside Git.
3. **Specify normalization in issue #3.** Cover season-type and ID crosswalks, event order at identical clocks, scoring deltas, substitutions, and possession boundaries. Keep source and normalized values traceable, including unassigned points and source corrections. Track play-in classification and exclusions explicitly.
4. **Validate in issue #5.** Compare accepted games with the official game list and official final scores. Reconcile the player-minute budget, per-player minutes and plus-minus with documented tolerances for rounding. On a stratified set of regular-season and playoff games, compare lineup changes, possessions and scores with `pbpstats` and an alternate event source where permitted. Include overtime, same-clock substitutions, technical and retained-possession free throws, replay and end-period events. Record independent-source coverage and gaps in the exception report.
5. **Profile tracking separately.** For each season and type from 2017–18 through 2022–23, verify availability, entity grain, player/game denominators, definition changes and missingness for defended shots, matchup, hustle and related shot categories. Label absent features separately from zero counts. The exact EPM tracking feature set and access to underlying trajectories remain open. [EPM uncertainty register](research/epm-uncertainties.md)

The audit establishes published asset availability. A one-season canonical dataset requires permitted snapshots, content inspection and successful reconciliation. [Issue #3][contracts] [Issue #5][pilot]

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/2
[contracts]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/3
[pilot]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5
[bentes]: https://github.com/ramirobentes/nba_data
[bentes-coverage]: https://github.com/ramirobentes/nba_data#important-notes-on-coverage
[bentes-pbp]: https://github.com/ramirobentes/nba_data/releases/tag/pbp
[bentes-pos]: https://github.com/ramirobentes/nba_data/releases/tag/possessions
[bentes-stints]: https://github.com/ramirobentes/nba_data/releases/tag/lineup_stats
[shuf-tree]: https://github.com/shufinskiy/nba_data/tree/46488f0f8e1cab58fc1256511ea808166a443a15/datasets
[shuf-loading]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/loading/README.md
[shuf-fields]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/description_fields.md
[shuf-license]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/LICENSE
[pbpstats]: https://pbpstats.readthedocs.io/en/latest/
[pbpstats-events]: https://pbpstats.readthedocs.io/en/latest/pbpstats.resources.enhanced_pbp.html
[pbpstats-code]: https://github.com/dblackrun/pbpstats
[hoopr]: https://hoopr.sportsdataverse.org/reference/load_nba_pbp.html
[espn-pbp]: https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_pbp
[espn-box]: https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_player_boxscores
[nba-box]: https://pr.nba.com/nba-stats-sap/
[nba-advanced-box]: https://www.nba.com/stats/teams/boxscores-traditional
[nba-tracking]: https://pr.nba.com/nba-announces-multiyear-partnership-sportradar-second-spectrum/
[nba-defense]: https://www.nba.com/stats/players/defense-dash-overall
[nba-hustle]: https://www.nba.com/stats/players/hustle
[nba-api]: https://github.com/swar/nba_api/tree/v1.12.0
[nba-api-license]: https://github.com/swar/nba_api/blob/v1.12.0/LICENSE
[nba-api-defense]: https://github.com/swar/nba_api/blob/v1.12.0/docs/nba_api/stats/endpoints/leaguedashptdefend.md
[nba-faq]: https://www.nba.com/stats/help/faq
[nba-terms]: https://www.nba.com/termsofuse
[disney-terms]: https://disneytermsofuse.com/english/
[sports-ref]: https://www.sports-reference.com/data_use.html
[epm-terms]: https://dunksandthrees.com/terms
