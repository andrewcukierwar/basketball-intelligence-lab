# Historical NBA feed coverage and verification tiers

**Audit date** 2026-11-23. NBA game data are attributed to NBA.com. This audit extends the [2022–23 source validation](nba-source-validation.md) for [issue #51][issue]. It covers regular-season and playoff archives from 2001–02 through 2024–25. Inventory alone is recorded for the reserved 2025–26 season and in-progress 2026–27 season. Use the ledger as an acquisition and reconciliation plan for [#25][development-build], [#52][outer-build] and [#53][historical-build].

## Coverage register

Each asset row includes season and type, status, file URL, publisher revision, size, observed SHA-256, row and game counts, game-set differences against the team box logs, and missing columns needed for the pilot rules. Regular season means NBA ID prefix `002`. Playoffs means `004`. Other game types, including play-in and standalone NBA Cup finals, stay outside the scoped counts.

| Register | Contents |
| --- | --- |
| [Event, shot and possession verification archives](nba-feed-coverage-shufinskiy.csv) | Shufinskiy's V2, V3, NBA liveData, data.nba, shot-detail and pbpstats.com CSV archives. Publisher revision identifies the pinned Git tree and asset blob. |
| [Separate lineup and possession comparisons](nba-feed-coverage-bentes.csv) | Bentes play-by-play, possessions and lineup stints. Publisher revision identifies the GitHub release asset and the reported SHA-256. |
| [Box logs](nba-feed-coverage-box.csv) | Bill Mill's NBA-derived team and player game logs. Each file spans season types. `artifact_rows` repeats across both entries and `season_type_rows` counts only the indicated ID prefix. The local SHA-256 pins the exact captured partition. The publisher catalog timestamp applies to the dataset as a whole. |
| [Adjudication evidence](nba-feed-coverage-rules.csv) | Counts of V2 games with the corresponding evidence available. See the rules below for interpretation. |

`measured` means the exact bytes were counted. `absent` means the named asset is absent from the pinned provider inventory. `inventory_only` means the metadata lists an asset and its payload was outside the audit. `listed_payload_unavailable` means the expected payload was unavailable to the local scan. Blank counts have no measurement. A zero among measured counts is a measured zero.

Game-set differences use the team box logs as a comparison denominator, subject to their own coverage and lineage limits. A zero difference establishes matching IDs, with season acceptance still governed by the [pilot reconciliation checks](../data-pilot.md). The register retains both full-file and scoped row counts. Shufinskiy's processed pbpstats.com archives may contain multiple rows for a possession. Their raw row counts cannot serve as counted possessions.

## Observed coverage and build exceptions

The audit measured 412 unique assets and 460 feed-by-season-type entries. Team logs cover 30,835 game IDs, with the same IDs in the player logs and shot-detail files. The exceptions below affect inputs or the strength of evidence.

| Season and type | Measured exception | Batch implication |
| --- | --- | --- |
| 2001–02, 2005–06, 2015–16 regular | V3 has every game ID. Valid terminal scores cover all V2 periods in all but 3, 1 and 1 games respectively. One 2015–16 game also fails the full V3 order coverage condition. | Surface incomplete period evidence and any rejected V3 retries before accepting affected games. |
| 2009–10 regular | pbpstats.com omits one of 1,230 box-log games. | Record a possession-evidence gap. |
| 2012–13 regular | V3 has 1,213 of 1,229 V2 and box-log games. | The 16 absent games have no V3 fallback or period comparison. Under the existing pilot acceptance rules they quarantine unless equivalent evidence is verified and approved. |
| 2016–17, both types | The first two data.nba archives have offense event keys and lack `ord`. The whole-game offense-key signal covers 1,215 of 1,230 regular games and 78 of 79 playoff games. | The historical loader must allow offense evidence independently of ordered period scores. The current `cross_feeds` loader assumes `ord` exists. |
| 2019–20 regular | V2, data.nba and pbpstats.com each cover the same 1,056 of 1,059 box-log games. V3, shot detail and Bentes cover all 1,059. | Treat the three as missing primary input. A V3-first recovery would need its own verification and stratum. |
| 2020–21 playoffs | Both archived NBA cross-feeds include all 85 game IDs. Their period scores jointly cover all V2 periods in 84 games. The data.nba whole-game offense-key signal covers 80 games. | Check cross-feed applicability at game and period grain. Bentes documents that its playoff build used an older process. |
| 2022–23 and 2023–24 regular | V3 contains all 1,230 games in each season. The full V3 event-order precondition is met by 1,217 V2 games in each. | The unavailable retry applies to 13 games per season only if their V2-order attempt needs it. |
| 2023–24 regular | data.nba and pbpstats.com omit the same two of 1,230 V2 games. Joint cross-feed period evidence is complete for 1,225 games. | Expect partial period-score and possession verification for the 2023–24 outer fold. |
| 2024–25 playoffs | data.nba and all three Bentes tables omit the same one of 84 V2 games. | Report data.nba and Bentes verification denominators separately from accepted games. |

## Pilot rule applicability and fallback

| Rule | Required evidence and measurable signal | Fallback |
| --- | --- | --- |
| V3 event-order fallback and V3-primary retry | Across all 24 measured seasons, the V3 file exists for both season types. A game can use the retry only when V3 provides numeric unique action IDs and its deduplicated event keys exactly cover V2. The rule register counts this precondition. Accepted reordered streams still preserve clock order and pass score and lineup reconciliation. | Use V2's native order and valid parser repairs. Quarantine a failed stream if V3 coverage or safe reorder is unavailable or the retry cannot reconcile. |
| liveData between-period starter propagation | Requires a matching liveData game. An observed start-clock substitution after period 1 is a presence signal, and games with no such row can still carry a consistent closing lineup through a period break. The pilot's partial-starter and valid in/out guards apply in both cases. Unavailable in the pinned archive through 2019–20. | Use the box-guided candidate starter search when liveData is unavailable or inconsistent. Record `inferred_starters` or `immaterial_starters` when applicable. Quarantine if the candidates fail reconciliation or imply materially different lineups. |
| V3 period-score defect adjudication | Requires qualifying terminal scores in both liveData and data.nba for every disputed period, with exact agreement with the V2 reconstruction. The register tallies V2 games where both feeds carry usable score evidence for every V2 period. Partial signals may still cover individual disputed periods. Full two-feed adjudication is absent through 2019–20. | Reconcile to the recorded V3 periods and box final. Quarantine a V3 disagreement unless the two-feed test is satisfied. Keep any accepted V3 defect as its own stratum. |
| data.nba offense relabel | A matching data.nba game must have exactly one named offense across that possession's shots, free throws and turnovers. Both adjacent offenses and scoring must still reconcile. The register counts games with data.nba offense on every eligible V2 live-ball key, a stronger whole-game coverage condition than the per-possession rule. The feed is absent through 2015–16. | Retain unresolved possession rows with no counted exposure. Keep score allocations reconciled and record missing relabel evidence. |
| External verification | Compare lineup stints with Bentes and possession counts with pbpstats.com for matched games. Compare live-ball offense and period scores where cross-feed evidence exists, while excluding uses where that feed selected the reconstruction. V2, V3, liveData and data.nba share upstream NBA event lineage. | Document missing comparisons and denominators by feed and season type. Check box minutes, plus-minus, final, and canonical rows as usual. Treat weaker verification strata separately in downstream sensitivity analyses. |

The rules apply per game. A season can include a mix of verification tiers because files with complete game IDs can still have unsuitable keys, clocks or period evidence. The current pilot requires both cross-feeds at the input-loading level. Historical batch implementation must permit absent feeds explicitly and preserve the fallbacks above.

## Build sequence

| Issue and batch | Seasons | Expected verification tier |
| --- | --- | --- |
| [#52][outer-build], each outer fold separately | 2023–24 and 2024–25 | All pilot feed types are listed. Pin and reconcile each window separately. Report by feed and season type. |
| [#25][development-build], modern development batch | 2020–21 and 2021–22 | Both cross-feeds are listed. Verify the 2020–21 playoff coverage and schema separately. Bentes documents its older reconstruction for that playoff season. |
| [#25][development-build], preceding development batch | 2017–18 through 2019–20 | data.nba is listed. V3 retries, box-guided starters, eligible offense relabels and the Bentes/pbpstats.com comparisons remain available. Record absent liveData and two-feed score-adjudication coverage. |
| [#53][historical-build], transition batch | 2016–17 | data.nba first appears without its later order field. Separate offense mapping from period-score evidence. |
| [#53][historical-build], V2/V3 baseline batches | 2012–13 through 2015–16, 2008–09 through 2011–12, 2004–05 through 2007–08 and 2001–02 through 2003–04 | V2/V3, shot detail, boxes, Bentes and pbpstats.com remain listed without liveData or data.nba. Verify period, participant and substitution coverage before making a historical claim. |
| [#42][holdout] | 2025–26 | Reserve build and outcome access for the registered confirmatory protocol. The pinned inventory has no V2, data.nba or pbpstats.com files for that season. The eventual holdout build requires a separately verified input path. |

No 2025–26 or 2026–27 outcomes were requested, read or processed by the audit. The 2026–27 inventory metadata establishes no readiness for scheduled capture.

## Usage and source lineage

The following applies across all cataloged seasons and both types. The measured values are for private noncommercial research within the project's recorded [source terms](../data-sources.md). NBA game data remain attributed to NBA.com. Publisher file access and software licenses do not establish permission to redistribute NBA-derived files, serve them in a statistics product, or use them commercially. No game-level rows, lineups, scores, or events are included in the register. [NBA Statistics terms][nba-terms]

| Provider | Evidence, rights limits and provenance |
| --- | --- |
| Shufinskiy | Archived NBA and pbpstats.com outputs. The repository's software license does not establish upstream data redistribution rights. Git revision and file hashes establish the audited bytes and exclude any claim about contemporaneous historical publication or correction availability. [Pinned provider inventory][shuf-tree] [License][shuf-license] |
| Bentes | Processing comparison over NBA feeds. Use the frozen release digests for private comparisons. Upstream endpoints and license for redistribution remain unverified. In 2020–21 playoffs Bentes reports a fallback to the older construction, and from 2025–26 reports a CDN-derived field set. [Provider source and era notes][bentes] |
| Bill Mill | NBA-derived logs with processed team plus-minus, plus player and team appearances. The provider catalog describes its changing publishing workflow. Use capture digest and scoped game IDs for reproducibility. Wider reuse rights and historical revision visibility remain unverified. [Provider data dictionary][billmill] |
| ESPN through SportsDataverse | A separate provider candidate with release inventory outside these measured feeds. Keep it outside automated reconstruction and verification pending permission for the intended use and a tested game-ID crosswalk. [Source ledger](../data-sources.md) [Disney terms][disney] |

## Reproduce the local scan

Populate a private directory with the basenames from the register, using the recorded sources and revisions. Reuse the pinned 2022–23 pilot files for matching names and rename only the copied box logs to their year-qualified audit basenames. The audit checks expected bytes, the Git blob or release digest where supplied, and the observed SHA-256. The local reproduction command never makes a network request and never opens a post-2024–25 payload.

```sh
PYTHONPATH=src .venv/bin/python scripts/audit_feed_coverage.py \
  /path/to/private/archives /path/to/coverage-output \
  --pins docs/research --jobs 4
```

Original publisher metadata came from the Git tree at `46488f0f8e1cab58fc1256511ea808166a443a15`, Bentes release tags `pbp`, `possessions`, and `lineup_stats`, and the Bill Mill dataset catalog. The scan streams the single CSV member of each compressed file without extracting it to disk and counts Parquet records with the pilot's DuckDB version. See the [run record](../agent-runs/2026-11-23-issue-51-feed-coverage.md) for verification and limitations.

[issue]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/51
[development-build]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/25
[outer-build]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/52
[historical-build]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53
[holdout]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/42
[shuf-tree]: https://github.com/shufinskiy/nba_data/tree/46488f0f8e1cab58fc1256511ea808166a443a15/datasets
[shuf-license]: https://github.com/shufinskiy/nba_data/blob/46488f0f8e1cab58fc1256511ea808166a443a15/LICENSE
[bentes]: https://github.com/ramirobentes/nba_data
[billmill]: https://github.com/llimllib/nba_data/blob/main/docs/DATA_DICTIONARY.md
[nba-terms]: https://www.nba.com/termsofuse
[disney]: https://disneytermsofuse.com/english/
