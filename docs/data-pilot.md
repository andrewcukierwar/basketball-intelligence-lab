# 2022–23 NBA possession pilot

This is the first implementation for [issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5). It covers the eligible 2022–23 regular season and playoffs. Play-in, preseason and All-Star games are outside this pilot. NBA game data are attributed to **NBA.com**. Work is scoped to private, noncommercial research. Keep input and output data outside Git and establish separate permissions before any publication or broader use. [NBA Statistics terms](https://www.nba.com/termsofuse) [Source ledger](data-sources.md)

## Reproduce locally

Install the pinned optional dependencies and capture the audited source bytes once.

```sh
uv sync --locked --extra pilot --extra dev
.venv/bin/python -m bil.data.pilot capture data/raw/2022-23/issue-5-v1
```

Capture writes a new private directory and verifies the exact size and SHA-256 of every source file. Reuse that directory for later builds. Capture fails on publisher changes instead of assigning changed bytes to the audited release. The source snapshot records URLs, artifact IDs, rights references and UTC retrieval times.

Run a build from a clean checkout, with a new output directory for each run. Omit `--game-id` for the full season or repeat it for a targeted run.

```sh
.venv/bin/python -m bil.data.pilot build \
  data/raw/2022-23/issue-5-v1 \
  data/processed/2022-23/issue-5-v1 \
  --code-commit "$(git rev-parse HEAD)"
```

The manifest records output file digests, row counts, the snapshot digest, code commit, parser version, reconciliation tolerances and coverage. Its ingestion timestamps identify this build. Availability for a canonical stream is the latest captured time of the pinned evidence used by that stream. The box feeds have no actual tip or finalization instant in this pilot. These are retrospective snapshots and carry no claim of availability at a 2022–23 forecast origin. DuckDB spills and intermediate rows stay under the private build staging directory and are removed when the build exits. [Canonical availability rules](data-contracts.md#provenance-and-time)

## Reconstruction and acceptance

| Check | Implementation |
| --- | --- |
| Game inventory and identity | Use Bill Mill's pinned team and player game logs for expected games, official dates, teams and player IDs. Use NBA IDs as strings in output. Compare the V3 final-period marker with the team boxes. |
| Source order | Read V2 file order and retain raw CSV record locators. Collapse exact repeats with all their locators. Quarantine conflicting duplicate keys, parser event loss or parser moves across clocks. Record supported same-clock parser reorders. When the parser's own rebound-order repairs fail, it would request data.nba.com event order. The pilot substitutes the pinned V3 action order: V3 `actionNumber` is the V2 `EVENTNUM`, rows are taken in `actionId` order and the first occurrence of each event number is kept. It is used only if V3 covers exactly the V2 events. Rebound order is checked again afterward. Every such game carries a `v3_event_order_applied` warning and a `v3_event_order` stratum, and the existing cross-clock and reconciliation checks still apply. |
| Lineup state and timing | Run the pinned `pbpstats` parser offline on locally wrapped V2 events and team shot charts. Verify each side has five distinct players in that team's box, that outgoing and incoming IDs explain each state change, and that stints cover every period. A substitution changes the following event's lineup. Unresolved clock restorations, starters and event order stay quarantined. |
| Score and credited lineups | Compute scoring deltas from parsed makes and reconcile every period against the archived V3 end marker. Verify the shooter is on court on the correct team for every field goal or free-throw attempt. Each known scoring delta has a ledger row. For a free throw tied to a same-clock foul, use the foul lineup when it contains the shooter. Credit other made shots to the scoring-event lineup. The credited stint is explicit. Compare player plus-minus exactly and minutes within 2,000 ms per player to the pinned box log. The time tolerance accommodates differences in clock precision without changing a source clock or a box value. |
| Possessions | Use the pinned parser's possession segments and countability flag. Check that intervals are ordered, disjoint, within a period and have known offense and defense IDs. A possession can span multiple stints. Technical and flagrant free-throw points are recorded outside the control-possession total and still count for final scoring. Unsupported score attribution quarantines the game. |
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
