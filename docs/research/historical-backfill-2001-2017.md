# Historical possession backfill, 2001–02 through 2016–17

[#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53) covers all 16 seasons in the historical interval. Eleven meet the [ADR-0022](../DECISIONS.md#adr-0022--revise-the-m1-quality-policy-hard-correctness-dataset-eligibility-and-representativeness) hard limits in the versions below. Five miss a hard limit and are unavailable for modeling. The adjacent 2017–18 experiment is shown for continuity.

Earlier batches pinned and reconciled 2016–17 ([#96](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/96)), 2004–05 through 2007–08 ([#97](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/97)), 2012–13 through 2015–16 ([#98](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/98)), 2002–03 ([#105](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/105)) and 2001–02 plus 2003–04 ([#108](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/108)). [#111](same-clock-rebound-order.md) pinned 2008–09 through 2011–12 and verified `same-clock-v1`. [#115](missing-free-throw-miss.md) verified `free-throw-miss-v1`. The [pilot guide](../data-pilot.md#backfill-batch-1-201617) retains the original batch results.

## Coverage and eligibility

The gates are at least 97% game coverage separately for the regular season and playoffs, at most 0.1% full-season unresolved possessions, and all hard checks on accepted games. Each row shows accepted over expected games. The remainder is quarantined and contributes zero modeling exposure. The unresolved denominator includes all canonical possessions in accepted games, including parser-excluded intervals. The two-rule version uses both reviewed opt-in retries. The experimental order repair is used only in the separately listed 2017–18 build.

| Season | Pilot build | Source snapshot | Regular | Playoffs | Unresolved | Role |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 2001–02 | `issue-53-two-rules-v1` | `batch4-v1` | 1,152 / 1,189 | 63 / 71 | 0.198% | Unavailable, both coverage gates and unresolved limit |
| 2002–03 | `issue-53-two-rules-v1` | `issue-105-v1` | 1,172 / 1,189 | 85 / 88 | 0.039% | Unavailable, playoff coverage |
| 2003–04 | `issue-53-two-rules-v1` | `batch4-v1` | 1,170 / 1,189 | 79 / 82 | 0.024% | Unavailable, playoff coverage |
| 2004–05 | `issue-111-rule-v5` | `issue-97-v1` | 1,204 / 1,230 | 82 / 84 | 0.028% | Eligible versioned history |
| 2005–06 | `issue-97-v1` | `issue-97-v1` | 1,220 / 1,230 | 88 / 89 | 0.019% | Eligible, playoff overtime warning |
| 2006–07 | `issue-97-v1` | `issue-97-v1` | 1,209 / 1,230 | 78 / 79 | 0.027% | Eligible, November unresolved concentration |
| 2007–08 | `issue-97-v1` | `issue-97-v1` | 1,214 / 1,230 | 86 / 86 | 0.024% | Eligible |
| 2008–09 | `issue-115-v2` | `issue-111-v1` | 1,220 / 1,230 | 85 / 85 | 0.030% | Eligible versioned history, October quarantine watch |
| 2009–10 | `issue-115-v2` | `issue-111-v1` | 1,220 / 1,230 | 82 / 82 | 0.025% | Eligible versioned history |
| 2010–11 | `issue-115-v2` | `issue-90-v1` | 1,216 / 1,230 | 81 / 81 | 0.025% | Eligible versioned history, playoff Q2 unresolved concentration |
| 2011–12 | `issue-115-v2` | `issue-111-v1` | 979 / 990 | 81 / 84 | 0.030% | Unavailable, playoff coverage |
| 2012–13 | `issue-115-v2` | `issue-98-v1` | 1,200 / 1,229 | 85 / 85 | 0.027% | Meets hard limits, conditional row-set candidate |
| 2013–14 | `issue-115-v2` | `issue-98-v1` | 1,218 / 1,230 | 86 / 89 | 0.029% | Unavailable, playoff coverage |
| 2014–15 | `issue-115-v2` | `issue-98-v1` | 1,216 / 1,230 | 80 / 81 | 0.019% | Eligible versioned history, known Bentes lineup outlier |
| 2015–16 | `issue-98-v1` | `issue-98-v1` | 1,208 / 1,230 | 85 / 86 | 0.026% | Eligible, regular-season overtime warning and quarantine concentration |
| 2016–17 | `issue-96-v1` | `issue-96-v1` | 1,209 / 1,230 | 79 / 79 | 0.053% | Eligible, regular-season overtime and playoff unresolved warnings |
| 2017–18 | `issue-99-order-repair-v2-c` | `issue-25-v1` | 1,067 / 1,230 | 80 / 82 | 0.388% | Unavailable, regular coverage and unresolved limit, [experimental build](order-repair-v2-2017-18.md) |

The earliest reruns recovered nine games compared with the original default builds. The same-clock rule recovered four in 2001–02 (one playoff) and four in 2003–04 (all regular). The free-throw retry recovered one regular game in 2002–03. The 3,712 previously accepted games match across all ten pilot tables apart from the ingestion timestamp. The 2001–02 rerun is two regular games and six playoff games short, with 447 unresolved possessions. The 2002–03, 2003–04, 2011–12 and 2013–14 playoff totals are each one game short. No row sets were built for those five seasons or 2017–18.

The 2010–11 playoff diagnostic flags all five unresolved possessions occurring in the second quarter. Its regular-season player-minute coverage also has a watch flag tied to three of fourteen quarantines. In 2012–13, April holds 17 of 29 regular-season quarantines (5.54× lift), and 35 of 64 regular-season unresolved possessions fall in the 6–10 point margin band (3.41× lift). The 2012–13 row set is available for a conditional sensitivity analysis that accounts for both flags. Any proposed primary use needs a per-use missingness assessment under ADR-0022. Use the [missingness methodology](season-quality-2017-2025.md) and retain these dimensions in any proposed cohort comparison.

## Canonical stable-lineup rows

Each new output is `data/processed/<season>/issue-53-rows-v1`. The [canonical contract](rapm-historical-rows.md) gives one unit of exposure to an eligible possession with a single actual lineup pair and accounts separately for points and exposure on other dispositions. These six builds produced 1,251,142 model rows. The other five eligible backfill seasons already have row sets in the original batches, `issue-97-rows-v1` for 2005–06 through 2007–08, `issue-98-rows-v1` for 2015–16 and `issue-96-rows-v1` for 2016–17.

| Season | Model rows | Multiple lineups | Parser excluded | Unresolved | Same-clock / free-throw retry games | Build ID prefix |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2004–05 | 203,465 | 32,635 | 3,118 | 68 | 2 / 0 | `eba238e34d33` |
| 2008–09 | 209,819 | 30,780 | 3,061 | 74 | 4 / 14 | `f8240e142424` |
| 2009–10 | 211,229 | 30,846 | 3,021 | 61 | 12 / 6 | `002a334404ce` |
| 2010–11 | 208,010 | 31,504 | 3,003 | 60 | 23 / 7 | `0bd8b21c69a3` |
| 2012–13 | 206,729 | 31,031 | 2,897 | 66 | 5 / 9 | `307c077e7024` |
| 2014–15 | 211,890 | 33,013 | 2,965 | 46 | 3 / 5 | `50efd43074ed` |

These inputs support retrospective research on stable-lineup possessions, with original game dispositions and the `same_clock_order`, `free_throw_miss` and feed-availability strata retained. All six row sets have `no_livedata` and `no_datanba` throughout. The broader interval gains data.nba in 2016–17 without entry order, and entries with `ord` are available in the 2017–18 experiment. The hard checks use pinned V3 and official box evidence. Bentes agrees on all lineup seconds in the nine rerun evidence comparisons except 2014–15, where agreement is 99.996% and the lowest game is 96.03%. pbpstats.com matches aggregate possession counts in 7,591 of 7,771 games in the six row sets, and Bentes agrees with 75 of 83 inferred team-period starters. These comparisons share upstream NBA feeds and provide corroboration at their measured grains.

The artifacts carry capture-bound availability. Strict historical rolling-origin availability would require time-stamped source revisions. A continuous full-history replication would require the missing seasons, and whole-game inference would require validation on all possessions. Any incorporation into [#28](rapm-targets-protocol.md) or its #30 consumer requires a separately versioned cohort under ADR-0026 and ADR-0027. No new model was fitted, and the 2025–26 confirmatory holdout stayed reserved.

NBA source data are attributed to **NBA.com**. The local archives, derived tables and receipts remain in private noncommercial research storage. The [source ledger](../data-sources.md) and [feed audit](nba-feed-coverage.md#usage-and-source-lineage) document terms and unresolved wider-use rights. This report contains aggregate counts only.

## Verification and runtime

- From code `8eac253006592f9ac597758f50d1cdbddf858a1e`, `season_quality.py --run-checks` reports 26 of 26 invariants passing for every selected build. The combined `check-seasons` sweep reports zero violations across five cross-season checks, 21,959 expected games and 933 player-seasons with several on-court teams. The sweep includes the separate 2017–18 experiment.
- The selected source snapshots, evidence archives, pilot manifests' table digests and row-set output digests were rechecked. All 16 row identities pass for each new row set. Each new row set was replayed from its exact pilot manifest pin and produced the same build ID and four byte-identical Parquet outputs.
- The 2001–04 reruns took 40.8–42.6 seconds per build and at most 0.74 GB peak RSS. Row extraction took 4.3–4.7 seconds per season and at most 0.77 GB. The full 17-build quality sweep took 80.0 seconds at 2.26 GB peak RSS. These are wall times and process peaks from the local machine. Earlier batches measured 36–60 seconds per parser build at up to 0.84 GB. Private quality receipts and timings are in `data/processed/quality/issue-53-v1`, `issue-53-evidence-v1` and `issue-53-timings-v1`.

The six pilot-manifest SHA-256 pins are recorded here for replay against the archived pilot outputs. A fresh pilot rebuild records new ingestion timestamps, so its manifest digest and the derived row-set build ID can differ.

```text
2004-05  a255a84694be31a776f5efa71342b9940bc68d85f327259cb05dce22d63f0708
2008-09  35ef0c5382fd6ab6da88da841fa18f6526114444ceb3f8cda938de4f04899cca
2009-10  a558d8d0f5b48e22597005e965405eb6943ab69ac7a8544e4e0f0ae6557e9e32
2010-11  38de0099ef20325ad9527e4dadfc18d18d6384822c76761b96b122ece10c31e7
2012-13  38c4b6fe802ca10dbd4a59aa8e2b81852d594d2350d7c096224d7d088a304285
2014-15  f661be3a2e7e0dd01e46e60a02bae0e7c190f371f1180b8f389f0ed0c73d8ca2
```

Use the source snapshot and build directories in the matrix under `data/raw/<season>` and `data/processed/<season>`, respectively. For the three earliest seasons, rebuild with `--same-clock-rule --free-throw-miss-rule` at the code SHA above into a fresh directory. To check and replay selected artifacts, run the following from that revision with `pilot_manifest_sha256` set to the corresponding pin above. Repeat the quality command's `--build` argument for each matrix entry to reproduce the full sweep.

```sh
uv run python -m bil.data.pilot check "$pilot" "$snapshot"
uv run python scripts/season_quality.py "$new_quality_dir" --run-checks --build "$pilot" "$snapshot"
uv run python -m bil.data.rapm_rows "$pilot" "$new_rows_dir" --variant canonical \
  --pilot-manifest-sha256 "$pilot_manifest_sha256" \
  --code-commit "$(git rev-parse HEAD)"
```
