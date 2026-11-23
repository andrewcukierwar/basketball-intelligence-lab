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
| Source order | Read V2 file order and retain raw CSV record locators. Collapse exact repeats with all their locators. Quarantine conflicting duplicate keys, parser event loss or parser moves across clocks. Record supported same-clock parser reorders. |
| Lineup state and timing | Run the pinned `pbpstats` parser offline on locally wrapped V2 events and team shot charts. Verify each side has five distinct players in that team's box, that outgoing and incoming IDs explain each state change, and that stints cover every period. A substitution changes the following event's lineup. Unresolved clock restorations, starters and event order stay quarantined. |
| Score and credited lineups | Compute scoring deltas from parsed makes and reconcile every period against the archived V3 end marker. Verify the shooter is on court on the correct team for every field goal or free-throw attempt. Each known scoring delta has a ledger row. For a free throw tied to a same-clock foul, use the foul lineup when it contains the shooter. Credit other made shots to the scoring-event lineup. The credited stint is explicit. Compare player plus-minus exactly and minutes within 2,000 ms per player to the pinned box log. The time tolerance accommodates differences in clock precision without changing a source clock or a box value. |
| Possessions | Use the pinned parser's possession segments and countability flag. Check that intervals are ordered, disjoint, within a period and have known offense and defense IDs. A possession can span multiple stints. Technical and flagrant free-throw points are recorded outside the control-possession total and still count for final scoring. Unsupported score attribution quarantines the game. |
| Second-feed checks | Compare each expected game's V2 and V3 substitution multisets by period, team and outgoing player ID. In the pinned V3 sample the substitution `personId` identifies the outgoing player. Compare reconstructed period scores as soon as the parser produces them. Report matched, mismatched and unattempted checks separately from acceptance, by season type and for overtime, technical free throws, same-clock free-throw substitutions and exact source repeats. Both feeds describe NBA events. The checks provide separate feed evidence for outcomes and substitution identity. |

The typed Parquet tables follow the [canonical contract](data-contracts.md) for games, game streams, events, actors, lineups, stints, possessions and scoring allocations. Quarantined games retain a game row, a quarantined stream and a quality issue. Their normalized event, lineup and possession records are excluded from the accepted tables. `game_review.parquet` supplies one row per expected or requested game and points to each game's disposition and comparison strata. Player box rows serve as reconciliation evidence in the pinned inputs.

The pilot quarantines unresolved games without live fallback requests or manual overrides. Full-season reports are generated in the local manifest. [Source validation](research/nba-source-validation.md) [pbpstats 1.3.11](https://pypi.org/project/pbpstats/1.3.11/)
