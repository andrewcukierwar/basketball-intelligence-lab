# 2022–23 NBA possession pilot

This is the first implementation for [issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5). It covers the eligible 2022–23 regular season and playoffs. Play-in, preseason and All-Star games are outside this pilot. NBA game data are attributed to **NBA.com**. Work is scoped to private, noncommercial research. Keep input and output data outside Git and establish separate permissions before any publication or broader use. [NBA Statistics terms](https://www.nba.com/termsofuse) [Source ledger](data-sources.md)

## Reproduce locally

Install the pinned optional dependencies and capture the audited source bytes once.

```sh
uv sync --locked --extra pilot --extra dev
.venv/bin/python -m bil.data.pilot capture data/raw/2022-23/issue-5-v2
```

Capture writes a new private directory and verifies the exact size and SHA-256 of every source file. Snapshot `issue-5-v2` adds the archived NBA liveData and data.nba.com feeds to the eight inputs of `issue-5-v1`. Earlier builds were made from `issue-5-v1`. Reuse that directory for later builds. Capture fails on publisher changes instead of assigning changed bytes to the audited release. The source snapshot records URLs, artifact IDs, rights references and UTC retrieval times.

Run a build from a clean checkout, with a new output directory for each run. Omit `--game-id` for the full season or repeat it for a targeted run.

```sh
.venv/bin/python -m bil.data.pilot build \
  data/raw/2022-23/issue-5-v2 \
  data/processed/2022-23/issue-5-v6 \
  --code-commit "$(git rev-parse HEAD)"
```

Then check the exported tables independently. The check reads the output tables, the manifest and the pinned player box and V2 event inputs. It exits nonzero on any violation.

```sh
.venv/bin/python -m bil.data.pilot check \
  data/processed/2022-23/issue-5-v6 \
  data/raw/2022-23/issue-5-v2
```

The same commands build other pinned seasons. Seasons are keyed by starting year, and `build`, `check` and `evidence` read the season recorded in the snapshot or manifest. `capture` and `capture-evidence` take `--season` (default `2022`). `--from-local DIR` copies already captured bytes instead of downloading them and checks every pin. Pins exist for 2004–05 through 2007–08, 2010–11, 2014–15, 2016–17 and 2017–18 through 2024–25 only. Seasons before 2016–17 have no data.nba archive and are labeled `no_datanba`. 2016–17 has data.nba without `ord`. The [backfill feasibility study](research/backfill-feasibility.md) records the older-era builds. `build --order-repair` is an experimental, off-by-default retry in data.nba entry order (ADR-0023, proposed). The 2025–26 holdout and later seasons are refused under [#42](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42). The pinned archive has no NBA liveData before 2020–21, so those snapshots omit it (ADR-0020). See [the outer-validation seasons](#outer-validation-seasons-202324-and-202425) and [the development seasons](#development-seasons-201718-through-202122).

`check` and `check-seasons` refuse a manifest whose season is the holdout or unpinned, and `check-seasons` also requires each build's `source_snapshot_sha256` to equal the SHA-256 of its snapshot's `snapshot.json`. A game whose box log has no home flag and whose home side V2 cannot designate is quarantined with null `home_team_id`, `away_team_id`, `home_final` and `away_final`, because the team-ID order is only provisional. `evidence` fails if a season with pinned liveData lacks liveData rows for an inferred-starter game.

The possession check examines consecutive possession rows within each period, including parser-excluded rows. If they share an offense, both rows must be unresolved unless a flagrant foul occurred in the earlier possession or the possession immediately before it. The check looks up flagrant fouls in the pinned V2 archive by game and source event ID. This is the same within-period exception used by the pinned parser.

To run the real parser integration tests for the starter search and V3-primary retry, point pytest at your existing private snapshot. The fixtures select two archived games and keep the underlying source rows outside Git.

```sh
BIL_PILOT_SNAPSHOT=data/raw/2022-23/issue-5-v2 \
  .venv/bin/python -m pytest -q tests/test_pilot_archived.py
```

The manifest records output file digests, row counts, the snapshot digest, code commit, parser version, reconciliation tolerances and coverage. Its ingestion timestamps identify this build. Availability for a canonical stream is the latest captured time of the pinned evidence used by that stream. The box feeds have no actual tip or finalization instant in this pilot. These are retrospective snapshots and carry no claim of availability at a 2022–23 forecast origin. DuckDB spills and intermediate rows stay under the private build staging directory and are removed when the build exits. [Canonical availability rules](data-contracts.md#provenance-and-time)

## Reconstruction and acceptance

| Check | Implementation |
| --- | --- |
| Game inventory and identity | Use Bill Mill's pinned team and player game logs for expected games, official dates, teams and player IDs. Use NBA IDs as strings in output. Compare the V3 final-period marker with the team boxes. When the box leaves the home flag null for both teams, V2 designates the home team. Every event with a team and only one of the home or visitor descriptions must agree. The V3 final check then confirms the designation against the box points (`v2_home_designation`, ADR-0017). Otherwise the game is quarantined as `unresolved_home_designation`. |
| Source order | Read V2 file order and retain raw CSV record locators. Collapse exact repeats with all their locators. Quarantine conflicting duplicate keys, parser event loss or parser moves across clocks. Record supported same-clock parser reorders. When the parser's own rebound-order repairs fail, it would request data.nba.com event order. The pilot substitutes the pinned V3 action order: V3 `actionNumber` is the V2 `EVENTNUM`, rows are taken in `actionId` order and the first occurrence of each event number is kept. It is used only if V3 covers exactly the V2 events. Rebound order is checked again afterward. Every such game carries a `v3_event_order_applied` warning and a `v3_event_order` stratum, and the existing cross-clock and reconciliation checks still apply. As a last resort, a game that fails acceptance in V2 order is parsed again with its events written in V3 action order (`v3_primary_order`). The cross-clock guard still compares against V2 order. If that also fails, the game keeps its V2 failure. |
| Lineup state and timing | Run the pinned `pbpstats` parser offline on locally wrapped V2 events and team shot charts. Verify each side has five distinct players in that team's box, that outgoing and incoming IDs explain each state change, and that stints cover every period. A substitution changes the following event's lineup. When period events do not give five starters, the parser would request a live box score. After the first period, the pilot instead carries the previous period's closing lineup through the archived liveData substitutions logged at the period's starting clock. It accepts that lineup only if it is consistent with the starters the events identify (`livedata_starters`). Otherwise, and in the first period, the pilot tries every candidate: it extends a short set with team players who logged minutes, or trims a set of six to five, and runs each through all acceptance checks. The game is accepted only if exactly one candidate passes (`inferred_starters`), or if every passing candidate gives an identical reconstruction (`immaterial_starters`). Unresolved clock restorations, ambiguous starters and unresolved event order stay quarantined. |
| Score and credited lineups | Compute scoring deltas from parsed makes and reconcile every period against the archived V3 end marker. If V3 alone disputes some periods, and both liveData and data.nba agree with V2 on every one of them, accept the game and record the V3 comparison as a mismatch (`v3_period_defect`). Verify the shooter is on court on the correct team for every field goal or free-throw attempt. Each known scoring delta has a ledger row. For a free throw tied to a same-clock foul, use the foul lineup when it contains the shooter. Credit other made shots to the scoring-event lineup. The credited stint is explicit. Compare player plus-minus exactly and minutes to the pinned box log. The minutes tolerance is 2,000 ms per player plus 1,000 ms for each of that player's substitutions at a clock inside a period's final minute. V2 truncates tenths there, while the V3 clocks keep them. This allows for clock precision without changing a source clock or a box value. The official box sometimes credits a score to the lineup on the other side of a substitution logged at the same clock. When only plus-minus differs, the pilot searches the lineup states at that clock with the shooter on court. It accepts the unique smallest set of up to three credit changes that matches every player, or several that differ only between scores at one clock. Such allocations use `same_clock_box_credit`. Actual lineups, stints and minutes do not change. |
| Possessions | Use the pinned parser's possession segments and countability flag. Check that intervals are ordered, disjoint, within a period and have known offense and defense IDs. A possession can span multiple stints. Technical and flagrant free-throw points are recorded outside the control-possession total and still count for final scoring. The parser rejects games where consecutive possessions share an offense, which usually comes from a held-ball jump ball whose recorded tip contradicts the next action. A score can also contradict its possession's offense, typically when the fouled team keeps the ball after a flagrant. In both cases, mark the affected possessions `unresolved`, exclude them from counted possessions, and allocate their points with the `unresolved` reason and no possession (`unresolved_possessions`). An unresolved possession is counted again only under two conditions. data.nba must give one offense team for all its shots, free throws and turnovers, and that team must differ from the offense of both neighboring possessions in the period. A relabeled possession that a score contradicts stays unresolved (`datanba_possession_labels`). A score outside every possession quarantines the game. |
| Second-feed checks | Compare each expected game's V2 and V3 substitution multisets by period, team and outgoing player ID. In the pinned V3 sample the substitution `personId` identifies the outgoing player. Compare reconstructed period scores as soon as the parser produces them. Report matched, mismatched and unattempted checks separately from acceptance, by season type and for overtime, technical free throws, same-clock free-throw substitutions and exact source repeats. Both feeds describe NBA events. The checks provide separate feed evidence for outcomes and substitution identity. |

The typed Parquet tables follow the [canonical contract](data-contracts.md) for games, game streams, events, actors, lineups, stints, possessions and scoring allocations. Quarantined games retain a game row, a quarantined stream and a quality issue. Their normalized event, lineup and possession records are excluded from the accepted tables. `game_review.parquet` supplies one row per expected or requested game and points to each game's disposition and comparison strata. Player box rows serve as reconciliation evidence in the pinned inputs.

The pilot quarantines unresolved games without live fallback requests or manual overrides. Full-season reports are generated in the local manifest. [Source validation](research/nba-source-validation.md) [pbpstats 1.3.11](https://pypi.org/project/pbpstats/1.3.11/)

## First reviewed full-season build

The build at `19c1bf7` on 2026-11-23 wrote its private manifest and tables under `data/processed/2022-23/issue-5-final-v1/`. The accepted subset contains 223,995 counted possessions and preserves 2,402 additional parser-excluded intervals. Score allocations reconcile independently of possession totals, including 1,290 points recorded outside control possessions.

| Season type | Expected games | Accepted games | Quarantined games | Full V3 period-score checks matched / attempted | V3 substitution checks matched / attempted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Regular season | 1,230 | 1,055 | 175 | 1,093 / 1,095 | 1,222 / 1,230 |
| Playoffs | 84 | 76 | 8 | 77 / 77 | 84 / 84 |
| Total | 1,314 | 1,131 | 183 | 1,170 / 1,172 | 1,306 / 1,314 |

All 1,314 V3 final scores agreed with the team boxes. Local verification of the exported accepted tables found no violations of the five-player, shot actor, period duration, possession sequence, final scoring, score allocation, player minutes or player plus-minus checks. Game-level period comparisons can succeed even when a different check quarantines the game. The manifest records checks that could not be attempted separately from disagreement.

Regular-season overtime coverage was 51 of 79 games, compared with 1,004 of 1,151 regulation games. Playoff overtime coverage was 3 of 4 games. Accepted technical-free-throw game counts were 676 of 800 in the regular season and 34 of 39 in the playoffs. These differences matter when using the subset for analysis.

The largest quarantine groups are unresolved event order (79 games), unresolved starters (33), other parser errors (22), and player plus-minus mismatches (18). Prioritize a pinned alternate event-order reference and independent period-starter evidence. The build establishes an audited subset. [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) remains open for coverage and anomaly resolution before milestone acceptance.

## Second full-season build: archived V3 event order

The build at `4bbf68e` on 2026-11-23 wrote its private manifest and tables under `data/processed/2022-23/issue-5-v3-order-v2/`, with parser version `pbpstats-1.3.11-bil-v2`. It applies the V3 order fallback described under source order and leaves every reconciliation rule unchanged. [ADR-0008](DECISIONS.md) [EXP-0001](experiment-log.md)

| Season type | Expected games | Accepted games | Quarantined games | Full V3 period-score checks matched / attempted | V3 substitution checks matched / attempted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Regular season | 1,230 | 1,121 | 109 | 1,164 / 1,166 | 1,222 / 1,230 |
| Playoffs | 84 | 80 | 4 | 82 / 82 | 84 / 84 |
| Total | 1,314 | 1,201 | 113 | 1,246 / 1,248 | 1,306 / 1,314 |

- **Recovered games.** The accepted subset grew by 70 games to 237,923 counted possessions, with 2,541 parser-excluded intervals and 1,387 points recorded outside control possessions. Of the 79 earlier `unresolved_event_order` games, 76 reached the V3 fallback: 70 were accepted and six failed a later check. The other three failed with parser errors before the fallback.
- **No regressions.** The 1,131 games accepted in the first build have identical event, actor, lineup, stint, possession and allocation rows, and no game was newly quarantined.
- **Independent checks.** A separate check of the exported tables found no violations. It covered manifest digests, lineups, stint and possession intervals, scores, shooters, minutes and plus-minus.
- **Overtime and technical free throws.** Regular-season overtime coverage is now 53 of 79 games, against 1,068 of 1,151 regulation games, and playoff overtime coverage is 3 of 4. Accepted technical-free-throw game counts are 724 of 800 in the regular season and 37 of 39 in the playoffs.
- **Remaining quarantines.** The remaining groups are unresolved starters (33), parser errors (25), player plus-minus mismatches (21), unresolved score allocation (10), V3 substitution mismatches (8), player minutes mismatches (7), unsupported reorders (4), V3 period-score mismatches (2), and one each for missing period start, shooter outside lineup and unresolved substitution.
- **Next priority.** Period-starter evidence is next. Report the `v3_event_order` stratum separately when it could affect an analysis. [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) remains open.

## Third full-season build: narrow-scope anomaly resolution

The build at `92011a7` on 2026-11-23 wrote its private manifest and tables under `data/processed/2022-23/issue-5-v5/`, with parser version `pbpstats-1.3.11-bil-v5`. It applies the starter search, unresolved possessions, same-clock credit, truncation-aware tolerance and V3-primary retry described above. [ADR-0009](DECISIONS.md) [EXP-0002](experiment-log.md)

| Season type | Expected games | Accepted games | Quarantined games | Full V3 period-score checks matched / attempted | V3 substitution checks matched / attempted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Regular season | 1,230 | 1,206 | 24 | 1,206 / 1,209 | 1,222 / 1,230 |
| Playoffs | 84 | 84 | 0 | 84 / 84 | 84 / 84 |
| Total | 1,314 | 1,290 | 24 | 1,290 / 1,293 | 1,306 / 1,314 |

The accepted subset has 256,042 counted possessions, 2,750 parser-excluded intervals and 54 unresolved possessions. The ledger records 1,510 points outside control possessions and 48 points in unresolved possessions. The 1,201 games accepted in the second build have identical rows. `python -m bil.data.pilot check` passed all 25 checks.

Accepted games by stratum:

| Stratum | Regular season | Playoffs |
| --- | ---: | ---: |
| Overtime | 78 / 79 | 4 / 4 |
| Regulation | 1,128 / 1,151 | 80 / 80 |
| Technical free throw | 783 / 800 | 39 / 39 |
| Same-clock free-throw substitution | 1,205 / 1,229 | 84 / 84 |

Games resolved by each rule, all accepted:

| Rule | Games |
| --- | ---: |
| V3 event order fallback (`v3_event_order`) | 80 |
| V3-primary retry (`v3_primary_order`) | 7 |
| Inferred starters (`inferred_starters`) | 31 |
| Starter choice immaterial (`immaterial_starters`) | 2 |
| Unresolved possessions (`unresolved_possessions`) | 30 |
| Same-clock box credit (`same_clock_box_credit`) | 18 |

Box minutes or plus-minus chose the reconstruction in 49 of these games: inferred starters and same-clock credit. In those games the box checks confirm uniqueness rather than independent agreement.

Notes for modeling:
- **Trust tiers.** Treat the strata as trust tiers. Run sensitivity analyses that drop `inferred_starters`, `same_clock_box_credit` and `v3_primary_order` games.
- **Credited lineups.** `credited_stint_seq` is the lineup credited for official plus-minus, not necessarily the lineup on court. Use stints and possessions for on-court exposure.
- **Unresolved possessions.** Only possessions with a contradicting score or a back-to-back neighbor become unresolved. Within those 30 games, dropped possessions are therefore slightly more likely to contain points than misses. The effect is tiny: 54 of about 259,000 possessions.

The 24 remaining quarantines are:
- V2 and V3 substitution disagreements (8)
- plus-minus mismatches with no unique same-clock credit (4)
- player-minutes swaps of 17 to 85 seconds (3)
- unsupported cross-clock parser reorders (3)
- V3 period-score mismatches (3)
- one each of missing period start, substitution conflict and parser error

Each is a source conflict that only manual adjudication could settle, which the pilot does not allow.

## M1 acceptance for the 2022–23 pilot

The M1 exit gate asks for documented invariants, reconciliation tolerances, coverage thresholds and exception reporting.

The thresholds below were set at this milestone after the results were observed. They are a floor for future seasons and rebuilds, not a claim that was tested in advance.

| Criterion | Threshold | 2022–23 result |
| --- | --- | --- |
| Invariants | Every `check` passes | 25 of 25 |
| Final scores | Event and ledger totals equal the box for every accepted game | Pass |
| Lineups | Five distinct box players per side, with substitutions explaining every change | Pass |
| Minutes and plus-minus | Tolerance above, and exact plus-minus | Pass |
| Game coverage | At least 97% of expected games for each season type | 98.0% regular season, 100% playoffs |
| Stratum coverage | At least 95% for overtime, technical-free-throw and same-clock-substitution games | Lowest is 97.9% |
| Unresolved possessions | At most 0.1% of possessions | 0.02% |
| Second feed | V3 period-score and substitution comparisons reported by season type and stratum | In manifest |
| Exceptions | Every quarantine and resolution rule has a reason, warning or stratum | `quality_issue` and `game_review` |

The dataset is fit for private RAPM development under the recorded strata. It makes no claim of historical point-in-time availability or of broader usage rights.

### Revised M1 policy (ADR-0022, 2026-11-24)

The table above is the original M1 result and is kept as recorded. [ADR-0022](DECISIONS.md#adr-0022--revise-the-m1-quality-policy-hard-correctness-dataset-eligibility-and-representativeness) revises how its rows are used, after the 2017–18 through 2024–25 builds ([#25](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/25), [#52](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/52)) showed that one small stratum could reject a whole season. No check in code and no threshold value changed.

| Class | Rows | Rule |
| --- | --- | --- |
| Hard correctness | Invariants, final scores, lineups, minutes and plus-minus | Never relaxed. Every `check` passes for every accepted game. |
| Dataset eligibility | Game coverage; unresolved possessions | Hard limits. At least 97% of expected games for each season type. At most 0.1% unresolved possessions over the full season. |
| Representativeness | Stratum coverage; unresolved possessions by season type; systematic missingness | The 95% stratum figure is a target. A miss, or a season type above 0.1%, is a warning that needs investigation and sensitivity analysis, not rejection. Material systematic missingness or demonstrated bias can still disqualify a dataset for a particular use. |

`scripts/season_quality.py` applies the revised policy and assesses missingness for any built season (see [the report](research/season-quality-2017-2025.md)):

```sh
uv run python scripts/season_quality.py data/processed/quality/<new-dir> \
  --build data/processed/2018-19/issue-25-v1 data/raw/2018-19/issue-25-v1 \
  --build data/processed/2019-20/issue-25-v1 data/raw/2019-20/issue-25-v1 --run-checks
```

It takes one `--build BUILD SNAPSHOT` pair per season, refuses an existing output directory, opens everything read-only and writes aggregate CSV and JSON files. `--run-checks` also runs the unchanged `check` invariants. It fits and scores no model. The flag rule (permutation chi-square for quarantines, game-clustered bootstrap for unresolved possessions) is in the report.

## Fourth full-season build: archived-feed adjudication

The build at `b1a43ed` on 2026-11-23 used snapshot `issue-5-v2` and parser version `pbpstats-1.3.11-bil-v6`, and wrote to `data/processed/2022-23/issue-5-v6/`. [ADR-0011](DECISIONS.md) [EXP-0004](experiment-log.md)

| Season type | Expected games | Accepted games | Quarantined games | Full V3 period-score checks matched / attempted | V3 substitution checks matched / attempted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Regular season | 1,230 | 1,208 | 22 | 1,206 / 1,209 | 1,222 / 1,230 |
| Playoffs | 84 | 84 | 0 | 84 / 84 | 84 / 84 |
| Total | 1,314 | 1,292 | 22 | 1,290 / 1,293 | 1,306 / 1,314 |

- **Possessions.** There are 256,456 counted possessions, 2,756 parser-excluded intervals and 51 unresolved possessions.
- **Stratum coverage.** Regular-season overtime coverage is 79 of 79 and regulation is 1,129 of 1,151. Technical-free-throw games are 784 of 800 in the regular season and 39 of 39 in the playoffs. Same-clock substitution games are 1,207 of 1,229 and 84 of 84.
- **Rules applied.**
  - `livedata_starters` settled 33 team-periods in 29 games, replacing all but two of the box-chosen starter sets.
  - `v3_period_defect` accepted two games.
  - `datanba_possession_labels` relabeled three possessions in two games.
- **Box as selector.** Box values now choose the reconstruction in 20 games, down from 49: two first-period starter inferences and 18 same-clock credits.
- **Lower-trust strata.** Add `livedata_starters`, `v3_period_defect` and `datanba_possession_labels` to the strata to drop in sensitivity analyses. For `livedata_starters`, the Bentes comparison is the remaining independent check on the starters, and box minutes and plus-minus are independent checks on the whole game. A `v3_period_defect` game keeps `v3_periods_match = false` in `game_review` even though it is accepted. Relabeled possessions keep no row-level marker; the game's stratum identifies them.
- **No other changes.** Compared with `issue-5-v5`, every game accepted there has identical event, actor, lineup and stint rows. Only the three relabeled possessions and their two allocation rows differ.
- **Verification.** `check` passes 25 of 25. `evidence` reports:
  - lineups agree with Bentes on 99.97% of court time in all 1,292 games;
  - all 35 starter team-periods chosen from liveData or the box match Bentes;
  - counted possessions equal pbpstats.com's in 1,260 games.

The 22 remaining quarantines are those described above, less the two V3 period-score defects. This build meets every threshold in the M1 acceptance table.

## External verification

A separate, pinned evidence snapshot holds four further sources. None of them are build inputs.
- Archived **data.nba.com** play-by-play. It has event order (`ord`) and offense team (`oftid`).
- Archived **NBA liveData** (cdn.nba.com) play-by-play. It has the possession team, tenth-second clocks and between-period substitutions.
- **pbpstats.com** possessions, which count possessions with the parser's online fallbacks and override files.
- **Bentes** lineup stints, a separate lineup reconstruction.

The NBA feeds come from the Shufinskiy revision the pilot already pins. Bentes comes from the release assets in the [source audit](data-sources.md). Every one of these sources derives from the NBA's own event log. Agreement therefore shows consistent archiving and parsing, not external truth, and an error in the official log would be shared by all of them. The data.nba and liveData feeds share order numbers, so treat them as one publication path that is separate from V2 and V3. Bentes reproduces the official box minutes almost everywhere, which suggests it corrects lineups with box-derived data. Its agreement is evidence for BIL's lineups, not for the box.

```sh
.venv/bin/python -m bil.data.pilot capture-evidence data/raw/2022-23/issue-5-evidence-v1
.venv/bin/python -m bil.data.pilot evidence \
  data/processed/2022-23/issue-5-v5 \
  data/raw/2022-23/issue-5-v1 \
  data/raw/2022-23/issue-5-evidence-v1
```

This example and the table below are for the M1 build `issue-5-v5`, made from snapshot `issue-5-v1`. For the current build, pass `issue-5-v6` and `issue-5-v2` instead. Its evidence results are in the archived-feed adjudication section above.

Results for the M1 build `issue-5-v5`:

| Comparison | Result |
| --- | --- |
| Lineups against Bentes, time-weighted over all 1,290 accepted games (all covered) | 99.97% of court time agrees, and the lowest game is 99.75%. Only two disagreements last more than 2 seconds. Both are substitutions logged late with an earlier clock, where the official box minutes match BIL to the second and not Bentes. The rest are boundary rounding of 2 s or less. |
| Lineups in lower-trust strata | The lowest game share is at least 99.75% in every stratum: 99.89% for `inferred_starters`, 99.90% for `same_clock_box_credit`, and 99.75% for `v3_primary_order`. |
| Inferred starters | All 35 inferred team-periods match the single Bentes stint for that team at the period start. All 33 after period 1 also match BIL's last stint of the previous period plus liveData's between-period substitutions. That second check is conditional on BIL's lineup at the end of the period. |
| Possession offense on live-ball events (shots, free throws, turnovers) in accepted possessions | 323,324 of 323,358 events agree with data.nba, and liveData gives the same result. 254,954 of 254,979 possessions agree on every such event. These events mostly name the acting team, so this check confirms event attribution and joining more than possession boundaries. Whole-possession comparisons differ only where dead-ball substitutions after a final free throw sit on different sides of the boundary. |
| Counted possessions against pbpstats.com | Equal in 1,257 of 1,290 games and within two in 1,283. The totals are 256,042 here and 256,062 for pbpstats.com. |
| Unresolved possessions | Of the 49 with live-ball events, data.nba agrees with the parser's label on 28 and contradicts it on 11. The feed can therefore settle most of them. |
| Event order against data.nba | All 87 games parsed in V3 order match data.nba's order exactly, which is the order pbpstats would have requested online. This confirms ADR-0008 directly. The 1,203 games parsed in V2 file order have 578 adjacent reversals in 408 games. |
| Period-end scores, compared per period | liveData and data.nba agree on 5,346 of 5,349 periods. V3 alone differs from the other two in games `0022200107` and `0022200466`. data.nba alone differs in `0022201098`, where its period keys are shifted, so data.nba period labels are not fully reliable. |

### What the evidence says about the 24 quarantines

| Group | Games | Evidence |
| --- | ---: | --- |
| V3 period-score defect | 2 | V2, liveData and data.nba agree on every period score, so the V3 check rejected a correct V2 reconstruction. |
| V2 scoring defect | 1 | V2 carries four phantom away points (`0022201076`). V3, liveData, data.nba and the box agree with each other. |
| Play-by-play substitution defect | 10 | Seven V3-substitution and three minutes-swap games. V2 and liveData agree on every substitution group and on the between-period substitutions. The official box and Bentes instead place a different player on court for one window of 13 to 127 seconds. |
| Event coverage | 1 | V3 lacks some V2 events (`0022200704`). |
| Plus-minus without a unique credit | 4 | Bentes matches the box plus-minus in two of these games and misses it by two players in the other two. |
| Parser limitations | 6 | Unsupported cross-clock reorders (3), a missing period start, a parser error and a substitution conflict. Bentes reproduces the box minutes and plus-minus in all six, so the data can be reconciled, but not by the pinned parser path. |

The quarantine of the 10 substitution-defect games is correct. Recovering them would make a box-consistent third reconstruction a source of record, which needs a separate decision. The two V3 period-score defects and the 11 resolvable unresolved possessions could be recovered by an explicit three-feed adjudication rule. These are proposals and are not applied. [ADR-0010](DECISIONS.md)

## Build the historical RAPM row set

[Issue #59](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/59) turns an exported pilot build into the per-possession input to the [synthetic RAPM estimator](research/rapm-synthetic.md), following the [row contract](research/rapm-historical-rows.md). Pin the pilot manifest by its SHA-256 and write to a new directory under `data/`. The builder verifies every pilot table against the digests the manifest lists, and no private row enters Git.

```sh
uv run python -m bil.data.rapm_rows \
  data/processed/2022-23/issue-19-v6 \
  data/processed/2022-23/issue-59-v1 \
  --pilot-manifest-sha256 "$(shasum -a 256 data/processed/2022-23/issue-19-v6/manifest.json | cut -d' ' -f1)" \
  --code-commit "$(git rev-parse HEAD)"
```

The output directory holds `model_row`, `possession_disposition`, `score_reconciliation` and `game_reconciliation` Parquet tables plus `manifest.json`. The manifest records the pilot manifest and snapshot digests, the SHA-256 and row count of each output, the reconciliation by season type and adjudication stratum (`<season type>|<stratum>`, with `all` as the unfiltered scope) and a content-addressed `build_id`. The id hashes the contract revision, the pinned inputs and the output digests, so a rebuild from the same pilot gives the same id. DuckDB spills go to a staging directory inside the output that is removed on exit. The build fails and removes its output directory if any identity check finds a gap or a duplicate versus the pinned possession and scoring ledgers. Rows stay per possession: no aggregation is applied. Strata overlap, so stratum cells do not sum to a season type.

The current builder (issues #74 and #82) also reads the pilot `event` table. By default (`--variant canonical`) it keeps every accepted stable-lineup possession and reproduces the `issue-59-v1` model rows. `--variant period_end_start` and `--variant no_action` build sensitivity row sets that drop accepted possessions with a `period_end` first event or with no action event, with no exposure. See the [report](research/rapm-no-action-2022-23.md) and ADR-0019. `scripts/audit_period_end_possessions.py <pilot_dir>` reports the clock at the start of period-end possessions by pilot status.

### Multi-season row sets (issue #93)

The builder reads `season_start_year` from the pinned pilot manifest and validates it through `pinned_season()`. The confirmatory holdout (2025 and later) and unpinned seasons are refused before any table is read. The identity check also requires every game row to carry the manifest's season. Builds for seasons without liveData carry the `no_livedata` stratum on every game, `v2_home_designation` games are ordinary strata, and quarantined games may have no home or away team (ADR-0017). The reconciliation handles all three without special cases. Build each season into a new directory with its own pin:

```sh
for pair in 2018-19:issue-25-v1 2019-20:issue-25-v1 2020-21:issue-25-v1 2021-22:issue-25-v1 \
            2022-23:issue-19-v6 2023-24:issue-52-v1 2024-25:issue-52-v1; do
  season=${pair%%:*}; pilot=data/processed/$season/${pair##*:}
  uv run python -m bil.data.rapm_rows "$pilot" data/processed/$season/issue-93-v1 \
    --pilot-manifest-sha256 "$(shasum -a 256 $pilot/manifest.json | cut -d' ' -f1)" \
    --code-commit "$(git rev-parse HEAD)"
done
```

Each build took 3 to 4 seconds. Rebuilding 2022–23 from `issue-19-v6` reproduces the `issue-82-canonical-v1` tables byte for byte (identical file digests and `build_id`). It reproduces the `issue-59-v1` `model_row` and `score_reconciliation` tables exactly (`EXCEPT ALL` both ways returns 0 rows, identical file digests). The older `issue-59-v1` disposition and game reconciliation tables predate the #74 columns. All seven builds report 0 violations across the 16 identity checks, and each output manifest carries the pilot manifest's source snapshot digest. The builder copies that digest rather than re-hashing the snapshot. Independent review re-hashed each raw `snapshot.json` and its archives for all seven seasons, and all matched. This is ledger reconciliation only. No model was fitted or scored.

| Season | Games (expected / accepted / quarantined) | Possessions | Accepted | Eligible | Multiple lineups | Pilot excluded | Unresolved | Eligible share of accepted | Ledger points (modeled / not modeled) | Strata |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2018–19 | 1,312 / 1,286 / 26 | 259,789 | 256,845 | 223,686 | 33,159 | 2,769 | 175 | 87.09% | 239,862 / 45,336 | `no_livedata` all games |
| 2019–20 | 1,142 / 1,123 / 19 | 227,690 | 225,227 | 195,128 | 30,099 | 2,377 | 86 | 86.64% | 209,469 / 41,291 | `no_livedata` all games |
| 2020–21 | 1,165 / 1,157 / 8 | 231,750 | 229,190 | 200,256 | 28,934 | 2,499 | 61 | 87.38% | 219,138 / 40,034 | none |
| 2021–22 | 1,317 / 1,306 / 11 | 258,831 | 256,017 | 223,043 | 32,974 | 2,746 | 68 | 87.12% | 242,685 / 45,430 | none |
| 2022–23 | 1,314 / 1,292 / 22 | 259,263 | 256,456 | 224,039 | 32,417 | 2,756 | 51 | 87.36% | 249,091 / 46,359 | none |
| 2023–24 | 1,312 / 1,299 / 13 | 258,099 | 255,337 | 223,264 | 32,073 | 2,662 | 100 | 87.44% | 250,340 / 44,952 | none |
| 2024–25 | 1,314 / 1,289 / 25 | 257,543 | 254,727 | 221,940 | 32,787 | 2,636 | 180 | 87.13% | 247,063 / 45,442 | `v2_home_designation` 5 games (886 eligible) |

By season type (eligible possessions, then the eligible share of accepted possessions):

| Season | Regular eligible | Regular share | Playoff eligible | Playoff share |
| --- | ---: | ---: | ---: | ---: |
| 2018–19 | 210,210 | 87.15% | 13,476 | 86.11% |
| 2019–20 | 181,335 | 86.69% | 13,793 | 85.96% |
| 2020–21 | 186,134 | 87.45% | 14,122 | 86.44% |
| 2021–22 | 208,789 | 87.18% | 14,254 | 86.30% |
| 2022–23 | 209,942 | 87.37% | 14,097 | 87.15% |
| 2023–24 | 210,324 | 87.52% | 12,940 | 86.11% |
| 2024–25 | 208,155 | 87.22% | 13,785 | 85.78% |

The per-stratum counts, points and exposure for every season are in each build's `manifest.json` under `reconciliation`. The 2023–24 and 2024–25 figures are ledger counts only. They are not outcome statistics and are not used for fitting.

## Box-score feature views (issue #62)

The builder turns the pinned `issue-5-v2` player and team game logs into the [box-score features](research/box-score-feature-contract.md). It reads only those two logs, verifies the pinned snapshot, and writes a new private directory. It never reads EPM or any model target.

```sh
uv run python -m bil.features.box_build \
  data/raw/2022-23/issue-5-v2 \
  data/processed/2022-23/issue-62-v1 \
  --code-commit "$(git rev-parse HEAD)"
```

Outputs, all Parquet except the manifest: `appearances` (validated observation grain, `(game_id, player_id)`), `same_window_features` (retrospective regular-season and playoff windows, which include every game in the window), `asof_retrospective_features` (per game and player, history from strictly earlier played dates of the same season type, with the New York cutoff recorded), `asof_strict_features` (same grain, built with the evaluation resolver in strict mode) and `manifest.json`. Feature rows are long: numerator, denominator, value, covered and eligible appearance counts and coverage per `(snapshot_id, feature_code, player_id)`.

The pinned logs have only a 2026 capture bound and no finalization instants, so the strict view is an explicit unavailable cohort: every row has zero eligible appearances and null statistics. Do not use the retrospective as-of view as strict history. The manifest records source digests, the snapshot ID, feature version, cutoff rules, output digests and row counts, and a reconciliation of the Python views against independent DuckDB aggregates of the raw parquet. The build reads the written Parquet back, checks all 13 features in the same-window and as-of views against independent SQL over the raw logs, and requires the strict view to have no history. Any SQL mismatch, a group-versus-row count gap or a difference from the #63 profile counts fails the build, removes the output directory and exits nonzero. The manifest also records per-view, per-season-type coverage: rows, cold-start rows, players, and per-feature eligible, covered and null counts.

## Skill histories and baselines

The skill-history builder ([#31](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/31), [rules and results](research/skill-histories.md)) reuses the #62 loader on the same pinned logs. It writes a new private directory and never reads EPM or any model target. Use a new output directory for each build, and pass the #62 manifest so the build also checks that its appearances equal that table.

```sh
uv run python -m bil.features.skill_build \
  data/raw/2022-23/issue-5-v2 \
  data/processed/2022-23/issue-31-v1 \
  --code-commit "$(git rev-parse HEAD)" \
  --box-manifest data/processed/2022-23/issue-62-v2/manifest.json
```

Outputs: `appearance_opportunities` (per appearance: source row digest, earlier-appearance counts, New York cutoff, strict-cohort count and status), `skill_baselines` (per player-game and statistic: realized target, target and history status, covered-game counts and career or season sums, and the career, season, last-10, 30- and 90-day decay and league predictions from strictly earlier dates), `baseline_scores` (exposure-weighted MSE and log loss by season type, cohort, month and history bucket) and `manifest.json` with a `content_id`, snapshot IDs, opportunity and appearance digests, coverage and reconciliation. The build recomputes every baseline, target and headline score with independent DuckDB SQL over the raw logs. Any mismatch, a nonempty strict history, a player-day duplicate, career differing from season while one season is loaded, or a #62 mismatch fails the build, removes the output and exits nonzero. The run takes about 20 seconds.

## Outer-validation seasons: 2023–24 and 2024–25

[Issue #52](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/52) builds the two outer folds of the [evaluation contract](validation-strategy.md) with the pilot rules and acceptance thresholds unchanged. All three builds used commit `9395ce1` and parser version `pbpstats-1.3.11-bil-v6` on 2026-11-23. The 2025–26 holdout was not built, and its payloads were not read.

### Snapshots and commands

Each season's inputs and evidence feeds were copied from the [#51 audit](research/nba-feed-coverage.md) capture with no network requests. The copies were verified against the size and SHA-256 recorded in the audit registers, and those pins are now in `pilot_sources.py`. A copied artifact's `retrieved_at` is the modification time of the audit file, which is when it was downloaded. The snapshot's `local_capture` field names the source directory.

```sh
A=data/raw/historical-feed-audit/2026-11-23
.venv/bin/python -m bil.data.pilot capture data/raw/2023-24/issue-52-v1 --season 2023 --from-local "$A"
.venv/bin/python -m bil.data.pilot capture-evidence data/raw/2023-24/issue-52-evidence-v1 --season 2023 --from-local "$A"
.venv/bin/python -m bil.data.pilot build data/raw/2023-24/issue-52-v1 \
  data/processed/2023-24/issue-52-v1 --code-commit "$(git rev-parse HEAD)"
.venv/bin/python -m bil.data.pilot check data/processed/2023-24/issue-52-v1 data/raw/2023-24/issue-52-v1
.venv/bin/python -m bil.data.pilot evidence data/processed/2023-24/issue-52-v1 \
  data/raw/2023-24/issue-52-v1 data/raw/2023-24/issue-52-evidence-v1
```

2024–25 uses `--season 2024` and the `2024-25` directories. Each build took 61 to 66 seconds, with a peak resident set of 0.80 to 0.82 GB on the maintainer's Apple-silicon Mac.

### Coverage

| Season and type | Expected | Accepted | Quarantined | V3 period scores matched / checked | V3 substitutions matched / checked | V3 final matches box |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022–23 regular (reference) | 1,230 | 1,208 (98.2%) | 22 | 1,206 / 1,209 | 1,222 / 1,230 | 1,230 / 1,230 |
| 2022–23 playoffs (reference) | 84 | 84 (100%) | 0 | 84 / 84 | 84 / 84 | 84 / 84 |
| 2023–24 regular | 1,230 | 1,218 (99.0%) | 12 | 1,217 / 1,218 | 1,226 / 1,229 | 1,229 / 1,230 |
| 2023–24 playoffs | 82 | 81 (98.8%) | 1 | 81 / 81 | 82 / 82 | 82 / 82 |
| 2024–25 regular | 1,230 | 1,205 (98.0%) | 25 | 1,205 / 1,205 | 1,230 / 1,230 | 1,230 / 1,230 |
| 2024–25 playoffs | 84 | 84 (100%) | 0 | 84 / 84 | 84 / 84 | 84 / 84 |

| Season | Counted possessions | Parser-excluded | Unresolved possessions: regular / playoffs (share of possessions) | Points outside control / in unresolved possessions |
| --- | ---: | ---: | --- | ---: |
| 2022–23 | 256,456 | 2,756 | 51 in 30 games (0.021%) / 0 | 1,511 / 47 |
| 2023–24 | 255,337 | 2,662 | 86 in 42 games (0.035%) / 14 in 6 games (0.092%) | 1,474 / 44 |
| 2024–25 | 254,727 | 2,636 | 158 in 76 games (0.065%) / 22 in 10 games (0.135%) | 1,154 / 41 |

Accepted games by stratum:

| Stratum | 2023–24 regular | 2023–24 playoffs | 2024–25 regular | 2024–25 playoffs |
| --- | ---: | ---: | ---: | ---: |
| Overtime | 57 / 59 | 3 / 3 | 58 / 60 | 5 / 5 |
| Regulation | 1,161 / 1,171 | 78 / 79 | 1,147 / 1,170 | 79 / 79 |
| Technical free throw | 784 / 794 | 45 / 45 | 644 / 660 | 36 / 36 |
| Same-clock free-throw substitution | 1,218 / 1,230 | 81 / 82 | 1,205 / 1,230 | 84 / 84 |

Games accepted under each rule. Every game in these strata was accepted.

| Rule | 2023–24 | 2024–25 |
| --- | ---: | ---: |
| `v3_event_order` | 61 | 92 |
| `v3_primary_order` | 10 | 7 |
| `inferred_starters` / `immaterial_starters` | 0 / 0 | 3 / 0 |
| `livedata_starters` (team-periods) | 17 (20) | 15 (17) |
| `v3_period_defect` | 1 | 0 |
| `datanba_possession_labels` | 1 | 3 |
| `unresolved_possessions` | 48 | 86 |
| `same_clock_box_credit` | 20 | 18 |
| `v2_home_designation` | 0 | 5 |

Against the [M1 thresholds](#m1-acceptance-for-the-202223-pilot), both seasons pass all 26 `check` invariants and the game coverage floor of 97% for each season type. Stratum coverage is at least 96.6% for every stratum against the 95% floor. The unresolved-possession share is 0.039% for 2023–24 and 0.070% for 2024–25, inside the 0.1% season limit. The 2024–25 playoffs alone are at 0.135%. The original M1 table sets that limit for the whole season, so this was reported here and not treated as a failure. Under ADR-0022 it is a documented warning (bootstrap 95% interval 0.056% to 0.228% over 22 possessions in 10 of 84 games, with no systematic pattern; see the [season quality report](research/season-quality-2017-2025.md)). The share of unresolved possessions has risen from 0.02% in 2022–23. The thresholds were not changed.

### Quarantines

| Season and type | Games | Cause |
| --- | ---: | --- |
| 2023–24 regular | 3 | V2 and V3 substitution signatures differ. |
| 2023–24 regular | 3 | Player plus-minus differs from the box. In two games several same-clock credit sets match, so no credit is unique. In the third, 6 players differ. |
| 2023–24 regular | 2 | Period start not established. |
| 2023–24 regular | 2 | Parser error (`EventOrderError`). |
| 2023–24 regular | 1 | Parser moved events across clocks. |
| 2023–24 regular | 1 | V3 final differs from the box (`0022301202`). V2 and V3 both end 119–112. liveData, data.nba and the box agree on 122–112, so the two primary feeds share a missing home score. |
| 2023–24 playoffs | 1 | A parser possession has an offense outside the two teams (`unknown_possession_offense`). |
| 2024–25 regular | 14 | Player minutes differ from the box. In each game, at least one team's box minutes sum to 15 to 120 seconds away from 240. Every other regulation team-game in the three seasons is within 20 seconds of 240. Every 2022–23 and 2023–24 regulation team-game is within 2 seconds. This points to a box-log defect (Inferred). |
| 2024–25 regular | 5 | Player minutes differ by 74 to 106 seconds for 2 to 4 players, with consistent box totals. This is the substitution-window pattern seen in 2022–23. |
| 2024–25 regular | 4 | Player plus-minus differs from the box. Two games have several matching same-clock credit sets. The other two differ for 4 and 8 players. |
| 2024–25 regular | 1 | A lineup player is absent from the team box. |
| 2024–25 regular | 1 | Parser error (`EventOrderError`). |

### Pipeline change for these seasons

The 2024–25 Bill Mill team log leaves `home` null for both teams in five regular-season games. By date and teams these are the neutral-site games: Mexico City, two in Paris, and the two Las Vegas NBA Cup semifinals (Inferred). The 2022–23 and 2023–24 logs have no such rows. Without a rule, the build stops. With ADR-0017, V2 designated all five unanimously, and V3 confirmed each against the box final. All five were accepted. `game.neutral_site` stays null because the box flag does not establish it.

The 2022–23 rebuild at `9395ce1` (`data/processed/2022-23/issue-52-rebuild-v1`) matches build `issue-19-v6`. Event, actor, lineup, stint, possession, score-allocation, quality-issue and game-review tables are byte-identical. In `game` and `game_stream`, only `ingested_at` differs. In the manifest, only `code_commit`, `generated_at` and the output digests of those two tables differ. `check` passes 26 of 26, and `evidence` reproduces the recorded results.

### External verification

| Comparison | 2022–23 (rebuild) | 2023–24 | 2024–25 |
| --- | --- | --- | --- |
| Lineups vs Bentes, time-weighted | 99.97% over 1,292 of 1,292 games; lowest 99.75% | 99.97% over 1,299 of 1,299; lowest 99.83%; no disagreement over 2 s | 99.97% over 1,288 of 1,289 (Bentes omits one playoff game); lowest 99.83%; none over 2 s |
| Starters set from liveData or the box, vs Bentes | 35 of 35 team-periods | 20 of 20 | 20 of 20 (17 liveData, 3 box) |
| Live-ball offense vs data.nba, accepted possessions | 323,336 / 323,370 events | 319,818 / 319,829 | 320,352 / 320,379 |
| Counted possessions vs pbpstats.com, games equal / within two | 1,260 / 1,286 of 1,292 | 1,249 / 1,292 of 1,299 (1,298 in pbpstats.com) | 1,205 / 1,285 of 1,289 |
| The same, games without unresolved possessions | 1,249 of 1,262 equal | 1,248 of 1,251 | 1,199 of 1,203 |
| Period-end scores, liveData vs data.nba | 5,346 / 5,349 | 5,303 / 5,307 | 5,319 / 5,321 |
| V3 alone differs / data.nba alone differs (games) | 2 / 1 | 2 / 4 | 0 / 0 |
| V3-ordered games with any data.nba order reversal: `v3_event_order` / `v3_primary_order` | 0 of 80 / 0 of 7 | 1 of 61 / 2 of 10 | 0 of 92 / 3 of 7 |

Verification strength is at least as high as for 2022–23 on lineups, starters, offense and period scores. Lower exact agreement with pbpstats.com is concentrated in games with unresolved possessions, whose boundaries are uncertain. Those games are within two possessions in 47 of 47 and 85 of 86 cases. In games without them, exact agreement is 99.8% and 99.7%. Unlike 2022–23, a few V3-ordered games are not exactly in data.nba's order. They still pass every reconciliation check.

Both 2023–24 V3-alone games are explained. `0022300353` is the accepted `v3_period_defect`, and `0022301202` is the quarantine above. In four late-season 2023–24 games, data.nba alone differs. Three were accepted on V2/V3 evidence, and one is a substitution quarantine. These were not investigated further. data.nba period labels were already known to be unreliable in 2022–23.

The #51 audit expected the evidence gaps: two 2023–24 regular-season games lack data.nba and pbpstats.com, and one 2024–25 playoff game lacks data.nba and Bentes. These games go through the normal build. Their comparisons and any data.nba-based adjudication are unavailable.

Neither fold falls materially below 2022–23 in coverage or verification, so the falsification condition in #52 is not met.

## Skill decay and shrinkage evaluation

The [#32](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/32) evaluation follows the [frozen protocol](research/skill-decay-protocol.md) and reports in [skill decay results](research/skill-decay-2022-23.md). It reruns the #31 engine on the pooled regular-season and playoff stream, requires the regular-season rows to equal the #31 build exactly, fits per-statistic decay and league shrinkage with Differential Evolution in nested chronological folds, and scores later blocks against the #31 baselines. It refuses any appearance outside 2022–23 and must run from a clean tree, recording `HEAD` in the manifest. Use a new output directory for each run.

```sh
uv run python -m bil.features.skill_decay_build \
  data/raw/2022-23/issue-5-v2 \
  data/processed/2022-23/issue-31-v1/manifest.json \
  data/processed/2022-23/issue-32-v1
```

Outputs, all Parquet except the manifest: `fits` (statistic, clock, fit window and cutoff, seed, parameters, objective, evaluations, bound hits), `clock_selection` (inner-fold losses per clock and the selected clock per outer block), `predictions` (outer-block targets with every clock's and baseline's prediction and pregame group fields), `scores` (log loss and weighted MSE levels, plus model-minus-baseline and clock deltas with game-clustered bootstrap intervals for the pooled blocks), `exclusions` (reason counts for every outer-block target), `snapshots` (date-specific skill estimates at each outer block's start) and `manifest.json` (inputs, frozen settings, #31 reconciliation, #31 unscored-target reasons, runtime and peak memory).

## Development seasons: 2017–18 through 2021–22

[Issue #25](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/25) builds the five seasons before 2022–23 with the pilot rules and the [M1 thresholds](#m1-acceptance-for-the-202223-pilot) unchanged. All five builds used commit `4b72175` and parser version `pbpstats-1.3.11-bil-v6` on 2026-11-23. The 2025–26 holdout was not built, and none of its payloads were read.

### Result

Under the original M1 table, two seasons meet every threshold and the other three were recorded **unavailable** for the #26 window under the falsification rule in #25. That original result is kept below. The maintainer then revised the policy ([ADR-0022](DECISIONS.md#adr-0022--revise-the-m1-quality-policy-hard-correctness-dataset-eligibility-and-representativeness)), and the last column gives the revised classification from `scripts/season_quality.py`. Their builds remain private evidence, and the thresholds were not changed.

| Season | Original M1 status (as recorded) | Threshold missed | Revised classification (ADR-0022) |
| --- | --- | --- | --- |
| 2017–18 | Unavailable | Regular-season game coverage is 85.5%, against a 97% floor. Unresolved possessions are 0.391%, against a 0.1% limit. The overtime (90.2%), technical-free-throw (84.6%) and same-clock-substitution (85.5%) regular-season strata are all below the 95% floor. | Fails two hard limits (game coverage and full-season unresolved share), plus three stratum warnings. |
| 2018–19 | Unavailable | Regular-season overtime stratum is 58 of 67 (86.6%), against the 95% floor. Every other threshold passes. | Meets all hard limits. One warning, the overtime stratum, with a systematic missingness finding (below). |
| 2019–20 | Meets M1 | None. This is a weaker-verification season with no liveData. | Meets, no warnings. |
| 2020–21 | Meets M1 | None. | Meets, no warnings. |
| 2021–22 | Unavailable | Regular-season overtime stratum is 55 of 58 (94.8%), against the 95% floor. It misses by part of one game. Every other threshold passes. | Meets all hard limits. One warning, the overtime stratum. |

Every build passes 26 of 26 `check` invariants. The 2018–19 and 2021–22 failures rest on small overtime denominators. Whether a stratum floor should make a whole season unavailable was a maintainer decision, now settled by ADR-0022 as described above.

### Snapshots and commands

Inputs and evidence were copied from the #51 audit capture with no network requests. Each copy was verified against the size and SHA-256 in the audit registers, and those pins are now in `pilot_sources.py`.

```sh
A=data/raw/historical-feed-audit/2026-11-23
.venv/bin/python -m bil.data.pilot capture data/raw/2019-20/issue-25-v1 --season 2019 --from-local "$A"
.venv/bin/python -m bil.data.pilot capture-evidence data/raw/2019-20/issue-25-evidence-v1 --season 2019 --from-local "$A"
.venv/bin/python -m bil.data.pilot build data/raw/2019-20/issue-25-v1 \
  data/processed/2019-20/issue-25-v1 --code-commit "$(git rev-parse HEAD)"
.venv/bin/python -m bil.data.pilot check data/processed/2019-20/issue-25-v1 data/raw/2019-20/issue-25-v1
.venv/bin/python -m bil.data.pilot evidence data/processed/2019-20/issue-25-v1 \
  data/raw/2019-20/issue-25-v1 data/raw/2019-20/issue-25-evidence-v1
```

The other seasons use their own `--season` and directories. For 2017–18 through 2019–20, `capture` verifies 10 inputs and `capture-evidence` verifies 6 files. For 2020–21 and 2021–22, the counts are 12 and 8.

`check-seasons` takes each build directory followed by its snapshot. It checks identity and chronology across seasons:
- game IDs are unique, and each encodes its season and season type;
- seasons do not overlap in date;
- each team's playoff games follow its last regular-season game;
- every on-court player belongs to that game's box team, so traded players are checked game by game.

Run over these five builds and the 2022–23 rebuild, it found zero violations in 7,562 games. 452 player-seasons appear for more than one team in the box. The same 452 appear on court for more than one team, and 769 players appear in more than one season.

### Weaker-verification stratum: no liveData before 2020–21

The pinned archive has no NBA liveData (`cdnnba`) for 2017–18, 2018–19 or 2019–20. The #51 register already records this. These builds read data.nba alone, and every game carries the `no_livedata` stratum (ADR-0020). Without liveData:
- starters after the first period always come from the box-guided search;
- V3 period-score defects cannot be adjudicated, so those games stay quarantined;
- the liveData evidence comparisons are empty.

data.nba offense relabels, V3 order retries, Bentes and pbpstats.com remain available. `evidence` adds a V3 versus data.nba period comparison for these seasons.

### Coverage

| Season and type | Expected | Accepted | Quarantined | V3 period scores matched / checked | V3 substitutions matched / checked | V3 final matches box |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2017–18 regular | 1,230 | 1,052 (85.5%) | 178 | 1,052 / 1,053 | 1,228 / 1,228 | 1,228 / 1,230 |
| 2017–18 playoffs | 82 | 80 (97.6%) | 2 | 80 / 80 | 82 / 82 | 82 / 82 |
| 2018–19 regular | 1,230 | 1,206 (98.0%) | 24 | 1,206 / 1,206 | 1,230 / 1,230 | 1,230 / 1,230 |
| 2018–19 playoffs | 82 | 80 (97.6%) | 2 | 80 / 80 | 82 / 82 | 82 / 82 |
| 2019–20 regular | 1,059 | 1,041 (98.3%) | 18 | 1,041 / 1,044 | 1,056 / 1,056 | 1,059 / 1,059 |
| 2019–20 playoffs | 83 | 82 (98.8%) | 1 | 82 / 82 | 83 / 83 | 83 / 83 |
| 2020–21 regular | 1,080 | 1,072 (99.3%) | 8 | 1,071 / 1,072 | 1,080 / 1,080 | 1,080 / 1,080 |
| 2020–21 playoffs | 85 | 85 (100%) | 0 | 85 / 85 | 85 / 85 | 85 / 85 |
| 2021–22 regular | 1,230 | 1,219 (99.1%) | 11 | 1,216 / 1,219 | 1,228 / 1,228 | 1,228 / 1,230 |
| 2021–22 playoffs | 87 | 87 (100%) | 0 | 87 / 87 | 87 / 87 | 87 / 87 |

The 2019–20 and 2020–21 schedules were shortened by COVID-19, with 1,059 and 1,080 regular-season games. The 2019–20 restart games were played at one site. The box log flags a home team for all of them, so no game needed V2 home designation. Play-in games (prefix `005`) are outside scope, as before.

| Season | Counted possessions | Parser-excluded | Unresolved possessions: regular / playoffs (share) | Season share | Points outside control / in unresolved possessions |
| --- | ---: | ---: | --- | ---: | ---: |
| 2017–18 | 218,906 | 2,481 | 865 in 260 games (0.418%) / 3 in 2 games (0.019%) | 0.391% | 1,047 / 946 |
| 2018–19 | 256,845 | 2,769 | 165 in 81 games (0.068%) / 10 in 5 games (0.063%) | 0.067% | 1,356 / 194 |
| 2019–20 | 225,227 | 2,377 | 77 in 41 games (0.036%) / 9 in 6 games (0.055%) | 0.038% | 1,247 / 90 |
| 2020–21 | 229,190 | 2,499 | 57 in 33 games (0.026%) / 4 in 3 games (0.024%) | 0.026% | 1,219 / 49 |
| 2021–22 | 256,017 | 2,746 | 64 in 40 games (0.026%) / 4 in 3 games (0.024%) | 0.026% | 1,533 / 77 |

Accepted games by stratum, as accepted / total. Bold marks a value below the 95% floor.

| Stratum | 2017–18 reg / po | 2018–19 reg / po | 2019–20 reg / po | 2020–21 reg / po | 2021–22 reg / po |
| --- | --- | --- | --- | --- | --- |
| Overtime | **55 / 61** · 4 / 4 | **58 / 67** · 4 / 4 | 68 / 69 · 6 / 6 | 56 / 56 · 3 / 3 | **55 / 58** · 1 / 1 |
| Regulation | 997 / 1,169 · 76 / 78 | 1,148 / 1,163 · 76 / 78 | 973 / 990 · 76 / 77 | 1,016 / 1,024 · 82 / 82 | 1,164 / 1,172 · 86 / 86 |
| Technical free throw | **622 / 735** · 38 / 40 | 759 / 776 · 43 / 45 | 663 / 674 · 47 / 47 | 630 / 635 · 43 / 43 | 784 / 794 · 47 / 47 |
| Same-clock free-throw substitution | **1,052 / 1,230** · 80 / 82 | 1,206 / 1,230 · 80 / 82 | 1,041 / 1,056 · 82 / 83 | 1,072 / 1,080 · 85 / 85 | 1,218 / 1,229 · 87 / 87 |

Games accepted under each rule, regular season plus playoffs. Every game in these strata was accepted.

| Rule | 2017–18 | 2018–19 | 2019–20 | 2020–21 | 2021–22 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `no_livedata` (all games) | 1,132 | 1,286 | 1,123 | 0 | 0 |
| `v3_event_order` | 119 | 208 | 61 | 71 | 109 |
| `v3_primary_order` | 33 | 25 | 3 | 10 | 8 |
| `inferred_starters` / `immaterial_starters` | 12 / 2 | 11 / 1 | 19 / 0 | 5 / 0 | 4 / 0 |
| `livedata_starters` (team-periods) | — | — | — | 14 (15) | 10 (12) |
| `v3_period_defect` | — | — | — | 1 | 3 |
| `datanba_possession_labels` | 1 | 1 | 1 | 1 | 0 |
| `unresolved_possessions` | 262 | 86 | 47 | 36 | 43 |
| `same_clock_box_credit` | 29 | 18 | 26 | 15 | 22 |

### Quarantines

| Season and type | Games | Cause |
| --- | ---: | --- |
| 2017–18 regular | 99 | Parser error (`EventOrderError`). |
| 2017–18 regular | 65 | Parser moved events across clocks. |
| 2017–18 regular | 14 | Period start not established (4), player plus-minus differs from the box (4), parser `AttributeError` (2), V3 final differs from the box (2), no candidate starters reconcile (1), and V3 period scores differ (1). |
| 2017–18 playoffs | 2 | Parser moved events across clocks. |
| 2018–19 regular | 24 | Parser moved events across clocks (10), period start not established (4), `EventOrderError` (4), plus-minus differs (3, two with several matching credit sets), no candidate starters reconcile because every candidate moves events across clocks (2), and a missing period end (1). |
| 2018–19 playoffs | 2 | Plus-minus differs for 4 players (1) and parser moved events across clocks (1). |
| 2019–20 regular | 18 | Plus-minus differs (5), parser moved events across clocks (5), game absent from V2 (3, `0021901316` to `0021901318`, as the #51 audit found), V3 period scores differ (3), `EventOrderError` (1), and no candidate starters reconcile (1). |
| 2019–20 playoffs | 1 | Parser moved events across clocks. |
| 2020–21 regular | 8 | Parser moved events across clocks (5), `EventOrderError` (1), plus-minus differs (1), and a substitution that conflicts with active IDs (1). |
| 2021–22 regular | 11 | Parser moved events across clocks (4), `EventOrderError` (3), V3 final differs from the box (2), and plus-minus with several matching credit sets (2). |

**2017–18.** 158 of the 178 regular-season quarantines are from October to December 2017. In those months, 57 of 104, 81 of 213 and 20 of 227 games were quarantined. From January the rate is at most 5% a month. 773 of the 868 unresolved possessions are also from October 2017 to January 2018. Almost all of these failures are event-order failures that the V3 retries could not repair. External agreement is also weakest in this season. Counted possessions equal pbpstats.com's in only 871 of 1,132 games. 31 of the 119 `v3_event_order` games show data.nba order reversals. This points to a defect in the early-season V2 event order (Inferred). It was not investigated further, and no new rule was added for it.

**Period scores without liveData.** The 3 games that 2019–20 quarantines for V3 period scores are exactly the 3 where V3 and data.nba disagree on a period. This fits a V3 defect that ADR-0011 could recover if liveData were archived (Inferred). In 2021–22, the two games where the V3 final differs from the box are also games where V3 alone disagrees with liveData and data.nba. This resembles `0022301202` in 2023–24, but the box was not compared with those feeds here. Both stay quarantined.

### External verification

| Comparison | 2017–18 | 2018–19 | 2019–20 | 2020–21 | 2021–22 |
| --- | --- | --- | --- | --- | --- |
| Lineups vs Bentes, time-weighted; all accepted games covered | 99.97%; lowest 99.85% | 99.97%; lowest 99.84% | 99.97%; lowest 99.82% | 99.97%; lowest 99.86% | 99.97%; lowest 99.83% |
| Disagreements over 2 s | 0 | 0 | 0 | 0 | 0 |
| Starter team-periods matching Bentes (liveData-set / box-inferred) | — / 13 of 13 | — / 13 of 13 | — / 20 of 20 | 15 of 15 / 5 of 5 | 12 of 12 / 4 of 4 |
| Live-ball offense vs data.nba, accepted possessions | 273,072 / 273,124 | 322,801 / 322,861 | 282,121 / 282,175 | 285,045 / 285,155 | 321,446 / 321,537 |
| Counted possessions vs pbpstats.com, games equal / within two | 871 / 942 of 1,132 | 1,185 / 1,227 of 1,286 | 1,060 / 1,104 of 1,123 | 1,111 / 1,153 of 1,157 | 1,257 / 1,301 of 1,306 |
| Period-end scores, liveData vs data.nba | — | — | — | 4,716 / 4,723 | 5,336 / 5,336 |
| Period-end scores, V3 vs data.nba | 5,288 / 5,321 | 5,337 / 5,337 | 4,634 / 4,637 | 4,715 / 4,723 | 5,327 / 5,336 |
| V3-ordered games with any data.nba order reversal: `v3_event_order` / `v3_primary_order` | 31 of 119 / 16 of 33 | 11 of 208 / 3 of 25 | 0 of 61 / 0 of 3 | 1 of 71 / 3 of 10 | 4 of 109 / 0 of 8 |

For 2020–21 and 2021–22, live-ball offense against liveData gives 285,462 / 285,520 and 321,358 / 321,449 events. In 2020–21, data.nba alone differs on period scores in four games, three of them playoff games. V3 alone differs in `0022000750`, which is the accepted `v3_period_defect`. Bentes documents an older process for the 2020–21 playoffs. BIL's lineups still agree with it on 99.97% of court time over the season.

Lineup and offense agreement in 2018–19 through 2021–22 is as strong as in 2022–23. In 2017–18, agreement on accepted games is also high. The low game coverage and weak pbpstats.com agreement come from the excluded early-season games and the unresolved possessions.

### Runtime and memory

Builds ran one at a time on the maintainer's Apple-silicon Mac. Times are wall-clock, and the peak resident set comes from `/usr/bin/time -l`.

| Build | Time | Peak RSS |
| --- | ---: | ---: |
| 2017–18 | 62.4 s | 0.82 GB |
| 2018–19 | 61.1 s | 0.85 GB |
| 2019–20 | 55.9 s | 0.82 GB |
| 2020–21 | 57.3 s | 0.76 GB |
| 2021–22 (run first) | 73.4 s | 0.81 GB |
| 2022–23 rebuild | 62.8 s | 0.77 GB |

The five seasons took 310 s in total, run in sequence, with peak memory below 0.9 GB per season. Parallel runs were not benchmarked.

### Pipeline change and 2022–23 equivalence

ADR-0020 makes liveData an optional build input for seasons where the provider archive lacks it. It changes nothing for seasons that have it. The 2022–23 rebuild at `4b72175` (`data/processed/2022-23/issue-25-rebuild-v1`) matches build `issue-19-v6`:
- the event, actor, lineup, stint, possession, score-allocation, quality-issue and game-review tables are byte-identical;
- in `game` and `game_stream`, only `ingested_at` differs, and no row differs once it is excluded (EXCEPT ALL in both directions).

`check` passes 26 of 26 on the rebuild. `evidence` reproduces the recorded values: 99.97% Bentes agreement, 1,260 / 1,286 games against pbpstats.com, 5,346 / 5,349 liveData versus data.nba periods, and 35 of 35 starter team-periods.

## Backfill batch 1: 2016–17

[Issue #96](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/96), under [#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53), builds 2016–17 with the default path at `8401bc7` and parser `pbpstats-1.3.11-bil-v6`. The order repair of ADR-0023 (proposed) was not used. The pin from [#90](research/backfill-feasibility.md) was reused: `capture --from-local` and `capture-evidence --from-local` verified 10 inputs and 6 evidence files by size and SHA-256, with no download. Private outputs: `data/raw/2016-17/issue-96-v1`, `issue-96-evidence-v1`, `data/processed/2016-17/issue-96-v1`, `issue-96-rows-v1` and `data/processed/quality/issue-96-v1`.

```sh
M=/path/to/repo; A=$M/data/raw/historical-feed-audit/2026-11-23
uv run python -m bil.data.pilot capture $M/data/raw/2016-17/issue-96-v1 --season 2016 --from-local "$A"
uv run python -m bil.data.pilot capture-evidence $M/data/raw/2016-17/issue-96-evidence-v1 --season 2016 --from-local "$A"
uv run python -m bil.data.pilot build $M/data/raw/2016-17/issue-96-v1 $M/data/processed/2016-17/issue-96-v1 --code-commit <sha>
uv run python -m bil.data.pilot check $M/data/processed/2016-17/issue-96-v1 $M/data/raw/2016-17/issue-96-v1
uv run python -m bil.data.pilot evidence $M/data/processed/2016-17/issue-96-v1 $M/data/raw/2016-17/issue-96-v1 $M/data/raw/2016-17/issue-96-evidence-v1
uv run python scripts/season_quality.py $M/data/processed/quality/issue-96-v1 \
  --build $M/data/processed/2016-17/issue-96-v1 $M/data/raw/2016-17/issue-96-v1
uv run python -m bil.data.rapm_rows $M/data/processed/2016-17/issue-96-v1 $M/data/processed/2016-17/issue-96-rows-v1 \
  --pilot-manifest-sha256 "$(shasum -a 256 $M/data/processed/2016-17/issue-96-v1/manifest.json | cut -d' ' -f1)" --code-commit <sha>
```

Results are aggregates only. `check` passes 26 of 26. `check-seasons` over 2016–17, 2017–18 to 2022–23 and 2023–24 and 2024–25 (11,497 games) reports zero violations.

| Season type | Expected | Accepted | Quarantined | Possessions | Excluded | Unresolved | Unresolved share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Regular | 1,230 | 1,209 (98.3%) | 21 | 236,228 | 2,664 | 71 | 0.030% |
| Playoffs | 79 | 79 (100%) | 0 | 15,116 | 178 | 61 | 0.404% |
| Season | 1,309 | 1,288 | 21 | 251,344 | 2,842 | 132 | 0.053% |

Both coverage floors (97%) and the full-season unresolved limit (0.1%) pass. Quarantine causes, all regular season: 14 `parser_error`, 4 `unresolved_event_order`, 2 `player_plus_minus_mismatch`, 1 `unresolved_starters`. The `season_quality.py` diagnostic gives original M1 status fail and revised status **meets with warnings**. The warnings are the regular-season overtime stratum (66 of 70, 94.3%, below the 95% target) and the playoff unresolved share (0.404%), which is a stratum-level warning under ADR-0022 and not the full-season gate. The only missingness flag is `watch` for overtime (21 quarantines in 2 cells, chi-square p = 0.031, lift 3.3 on 4 events).

Evidence (**Documented**, from `evidence`): no liveData and no data.nba `ord`, so every game carries `no_livedata`, 9 team-periods have inferred starters (Bentes agrees with all 9), and period scores and event order cannot be compared with data.nba. pbpstats.com possession counts are equal in 1,240 of 1,288 games and within 2 in 1,259. Offense keys agree with data.nba for 893 of 893 events.

Canonical RAPM row set (`bil.data.rapm_rows`, variant `canonical`, build id `b77fe289`, 0 identity violations, no model fitted):

| Season type | Accepted possessions | Eligible | Multiple lineups | Pilot excluded | Unresolved | Eligible share of accepted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Regular | 233,493 | 203,037 | 30,456 | 2,664 | 71 | 86.95% |
| Playoffs | 14,877 | 12,847 | 2,030 | 178 | 61 | 86.36% |
| Season | 248,370 | 215,884 | 32,486 | 2,842 | 132 | 86.92% |

Ledger points are 227,541 modeled and 44,470 not modeled, from 272,011 final points. The row counts are 215,884 `model_row`, 251,344 `possession_disposition`, 146,507 `score_reconciliation` and 1,309 `game_reconciliation`.

## Backfill batch 2: 2004–05 through 2007–08

[Issue #97](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/97), under [#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53), builds four seasons with the default path at `2598f05` and parser `pbpstats-1.3.11-bil-v6`. The order repair of ADR-0023 (proposed) was not used, and no pipeline code changed: the only code change is the pins for 2004–05, 2006–07 and 2007–08, generated from the #51 register CSVs and checked against them by the existing pin test (2005–06 was already pinned). All four seasons are `no_datanba` and `no_livedata`. `capture --from-local` and `capture-evidence --from-local` verified 8 inputs and 4 evidence files per season by size and SHA-256, with no download. Private outputs, for each season `<s>`: `data/raw/<s>/issue-97-v1`, `issue-97-evidence-v1`, `data/processed/<s>/issue-97-v1`, `issue-97-rows-v1` (not for 2004–05), and `data/processed/quality/issue-97-v1`. The #90 build of 2005–06 was rebuilt rather than reused.

The commands are those of batch 1, with `--season 2004` to `2007`, `issue-97` directory names, `--code-commit 2598f05b619d55ab6d351a24be2fd0dbfb4b33cc` and one `season_quality.py` call with a `--build` pair per season.

Results are aggregates only. `build` and `check` pass 26 of 26 for every season, in 46 to 60 s and at most 0.84 GB. `check-seasons` over the four new builds, 2016–17, 2017–18 to 2022–23 and 2023–24 and 2024–25 (13 builds, 16,755 games) reports zero violations.

| Season | Type | Expected | Accepted | Quarantined | Possessions | Excluded | Unresolved | Unresolved share |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2004–05 | Regular | 1,230 | 1,203 (97.8%) | 27 | 224,139 | 2,912 | 66 | 0.029% |
| 2004–05 | Playoffs | 84 | 81 (96.4%) | 3 | 14,777 | 202 | 0 | 0.000% |
| 2004–05 | Season | 1,314 | 1,284 | 30 | 238,916 | 3,114 | 66 | 0.028% |
| 2005–06 | Regular | 1,230 | 1,220 (99.2%) | 10 | 226,027 | 2,949 | 45 | 0.020% |
| 2005–06 | Playoffs | 89 | 88 (98.9%) | 1 | 16,117 | 234 | 2 | 0.012% |
| 2005–06 | Season | 1,319 | 1,308 | 11 | 242,144 | 3,183 | 47 | 0.019% |
| 2006–07 | Regular | 1,230 | 1,209 (98.3%) | 21 | 226,958 | 2,968 | 62 | 0.027% |
| 2006–07 | Playoffs | 79 | 78 (98.7%) | 1 | 14,232 | 192 | 3 | 0.021% |
| 2006–07 | Season | 1,309 | 1,287 | 22 | 241,190 | 3,160 | 65 | 0.027% |
| 2007–08 | Regular | 1,230 | 1,214 (98.7%) | 16 | 228,694 | 2,899 | 57 | 0.025% |
| 2007–08 | Playoffs | 86 | 86 (100%) | 0 | 15,446 | 191 | 2 | 0.013% |
| 2007–08 | Season | 1,316 | 1,300 | 16 | 244,140 | 3,090 | 59 | 0.024% |

The full-season unresolved limit (0.1%) passes in all four seasons. The coverage floor (97%) passes in every cell except the **2004–05 playoffs** (81 of 84, 96.4%), a hard-gate failure: 2004–05 is **unavailable** under ADR-0022 and has no row set. The `season_quality.py` diagnostic gives:

| Season | Original M1 status | Revised status | Warnings |
| --- | --- | --- | --- |
| 2004–05 | fail | fails hard limit | None beyond the hard failure |
| 2005–06 | fail | meets with warnings | Playoff overtime stratum 9 of 10 (90.0%) |
| 2006–07 | pass | meets | None. One missingness flag (`systematic`): regular-season unresolved events by month, p = 0.0052, November 2006 lift 4.5 on 31 of 62 events |
| 2007–08 | pass | meets | None |

Quarantine causes (games): 2004–05 has 30, `player_plus_minus_mismatch` 14, `missing_period_end` 7, `parser_error` 3, and one each of `missing_period_start`, `shooter_outside_lineup`, `unresolved_clock_reset`, `unresolved_event_order`, `unresolved_starters` and `unsupported_reorder`. 2005–06 has 11: `parser_error` 3, `unresolved_starters` 2, `unsupported_reorder` 2, and one each of `missing_period_end`, `shooter_outside_lineup`, `v3_box_final_mismatch` and `v3_period_score_mismatch`. 2006–07 has 22: `missing_period_end` 6, `parser_error` 6, `player_plus_minus_mismatch` 6, `unsupported_reorder` 2, `shooter_outside_lineup` 1 and `unresolved_starters` 1. 2007–08 has 16: `parser_error` 12, `player_plus_minus_mismatch` 3 and `unsupported_reorder` 1. The 2004–05 missing-period and plus-minus cluster is the weakest of the four seasons.

Evidence (**Documented**, from `evidence`): without liveData and data.nba every game carries `no_livedata` and `no_datanba`, so period scores and event order cannot be compared with another feed. Bentes lineups cover every built game with a time share of 1.000 and no disagreement over 2 s. Inferred starters agree with Bentes in 10 of 11 team-periods (2004–05), 13 of 14 (2005–06), 13 of 13 (2006–07) and 13 of 15 (2007–08). pbpstats.com possession counts are equal in 1,253 of 1,284, 1,287 of 1,308, 1,258 of 1,287 and 1,276 of 1,300 games, and within 2 in 1,268, 1,298, 1,269 and 1,286.

Canonical RAPM row sets (`bil.data.rapm_rows`, variant `canonical`, 0 identity violations in each, no model fitted):

| Season | Build id | Type | Accepted possessions | Eligible | Multiple lineups | Eligible share of accepted |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 2005–06 | `40308b6e` | Regular | 223,033 | 192,218 | 30,815 | 86.18% |
| 2005–06 | | Playoffs | 15,881 | 13,536 | 2,345 | 85.23% |
| 2005–06 | | Season | 238,914 | 205,754 | 33,160 | 86.12% |
| 2006–07 | `b8d872c2` | Regular | 223,928 | 193,042 | 30,886 | 86.21% |
| 2006–07 | | Playoffs | 14,037 | 11,939 | 2,098 | 85.05% |
| 2006–07 | | Season | 237,965 | 204,981 | 32,984 | 86.14% |
| 2007–08 | `0daa90b4` | Regular | 225,738 | 196,672 | 29,066 | 87.12% |
| 2007–08 | | Playoffs | 15,253 | 13,159 | 2,094 | 86.27% |
| 2007–08 | | Season | 240,991 | 209,831 | 31,160 | 87.07% |

Row counts (`model_row`, `possession_disposition`, `score_reconciliation`, `game_reconciliation`): 2005–06 205,754, 242,144, 145,154 and 1,319; 2006–07 204,981, 241,190, 143,893 and 1,309; 2007–08 209,831, 244,140, 145,436 and 1,316.

## Season eligibility matrix (ADR-0022)

Maintainer decisions of 2026-11-23 ([#89](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/89)), applied to the revised M1 classification. "Primary training" is the retrospective cohort 2018–19 through 2022–23. "Outer validation" seasons receive data-quality diagnostics here and no model results until their planned evaluation. The 2025–26 and later seasons are the holdout and were not read.

| Season | Revised M1 class | Role | Conditions |
| --- | --- | --- | --- |
| 2004–05 | Fails hard limits | Unavailable | The playoff game coverage is 96.4% (81 of 84), below the 97% floor (ADR-0022). Not built into a row set. The build and checks ran and the quarantines are retained. Default build, no order repair ([#97](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/97)). |
| 2005–06 | Meets, one warning | Eligible history, outside the planned #26 window | Not part of the #26 primary window. Available for later use. Weaker verification (`no_livedata`, `no_datanba`). The playoff overtime stratum is 9 of 10 (90.0%), below the 95% target. Default build, no order repair ([#97](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/97)). |
| 2006–07 | Meets | Eligible history, outside the planned #26 window | Not part of the #26 primary window. Available for later use. Weaker verification (`no_livedata`, `no_datanba`). Missingness flag: the regular-season unresolved events concentrate in November 2006 (`systematic`, 31 of 62 events, lift 4.5). Default build, no order repair ([#97](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/97)). |
| 2007–08 | Meets | Eligible history, outside the planned #26 window | Not part of the #26 primary window. Available for later use. Weaker verification (`no_livedata`, `no_datanba`). Default build, no order repair ([#97](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/97)). |
| 2016–17 | Meets, two warnings | Eligible history, outside the planned #26 window | Not part of the #26 primary window (2018–19 to 2022–23). Available for later use. Weaker verification (`no_livedata`, data.nba without `ord`). Regular-season overtime stratum at 94.3% (66 of 70) and a playoff unresolved share of 0.404%. Default build, no order repair ([#96](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/96)). |
| 2017–18 | Fails hard limits | Excluded | Outside the primary cohort pending remediation ([#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53) feasibility). Early-season event-order failures, 14.6% of expected possessions lost to quarantines. |
| 2018–19 | Meets, one warning | Primary training, conditional | Subject to the missingness analysis. Weaker verification (`no_livedata`). Systematic quarantine concentration in overtime games and in November 2018, reported in the [report](research/season-quality-2017-2025.md). Sensitivity run excluding it, overtime and weaker strata. |
| 2019–20 | Meets | Primary training | Weaker verification (`no_livedata`); treat as a sensitivity stratum (ADR-0020). |
| 2020–21 | Meets | Primary training | None. |
| 2021–22 | Meets, one warning | Primary training, conditional | Subject to the missingness analysis. Overtime stratum at 94.8%, 3 quarantines in 58 overtime games. |
| 2022–23 | Meets | Primary training | None. The pilot season. |
| 2023–24 | Meets | Outer validation | Data-quality diagnostics only. |
| 2024–25 | Meets, one warning | Outer validation, playoffs included | The elevated playoff unresolved rate (0.135%) is documented, not a gate. Five `v2_home_designation` games (ADR-0017). Data-quality diagnostics only. |

All individual game quarantines are retained in every season. An eligibility role is a statement about the dataset, not a model result.
