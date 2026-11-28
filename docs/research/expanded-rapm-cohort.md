# Expanded historical RAPM cohort registration

[#161](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/161) registers inputs for a retrospective stable-lineup experiment. The [machine-readable cohort](expanded-rapm-cohort-v1.json) pins every game-event parent, row set and box snapshot, including complete season-level coverage and timing diagnostics. The experiment uses the existing stable-lineup estimand and capture-bound evidence. #168 owns target fits and reliability testing. #169 owns any downstream SPM and EI comparison.

## Nested comparisons

| Cohort | Seasons | Model rows before ownership exclusions | Eligible rows |
| --- | ---: | ---: | ---: |
| Frozen #28 contiguous | 5 | 1,066,152 | 1,066,152 |
| Frozen #28 extended | 10 | 2,117,689 | 2,117,689 |
| Matched contiguous | 5 | 1,066,152 | 1,066,123 |
| Matched extended | 10 | 2,117,689 | 2,117,658 |
| Expanded primary | 15 | 3,162,102 | 3,162,069 |
| Expanded conditional | 16 | 3,368,831 | 3,368,797 |

Use the matched ten-season cohort for attribution of the five-season addition. Use the matched five-season cohort to measure the effect of moving to the extended reference, and the 15-to-16 comparison to isolate 2012–13. Keep the original #28 and #30 results as archived reference points. The eligibility view applies the same ownership exclusion across all matched and expanded branches. The newer diagnostic flagged 74 accepted pilot possessions, with 34 in the 16 archived stable-lineup modeling sets. Its evidence is the parser's own event team, which can disprove some assignments. Agreement gives no independent validation of the remainder. [#138 diagnostic and limits](possession-ownership.md)

### Ownership and availability

For a matched or expanded fit, anti-join the model rows on distinct `(game_id, stream_revision, possession_seq)` keys. Obtain the exclusion keys by joining the pinned `possession` to same-game and same-revision events in `[start_seq, end_seq)`. Require `possession.status = 'accepted'` and a qualifying event with a populated team that differs from `possession.offense_team_id`. Use BIL's existing `bil.data.rapm_rows.DECISIVE_CONTROL` definition, which includes attempts and eligible turnovers and ignores a turnover at an opponent free-throw clock. Intersect the result with the archived model row keys. Sort by the three key columns, serialize as headerless UTF-8 `game_id,stream_revision,possession_seq\n` records, and verify the registered SHA-256 and count per season. Fail the experimental fit if a pin, count, ownership anti-join or score/context timing check disagrees. The verified exclusions change fit eligibility only. Original ledgers retain all points, archive bytes, game dispositions and coverage decisions. Source verification still requires independent event evidence.

All possession and box game dates must be strictly before 2023-07-01 and strictly earlier than the relevant origin. The manifest's season endpoint is the day after the latest expected game in each pinned calendar, including quarantines. Use the paired evaluation game's date and game ID to align outcome examples. Use only labels frozen at an earlier eligible origin. Never let a later-season appending operation revise labels that an earlier origin consumed. Score common folds on identical player/game eligibility and use a fixed, disjoint or season-only scoring reference as registered in #168. Keep per-origin label exposure and forward support, split-half reliability and same-input reproducibility, with 250 possessions per role as the existing training/scoring exposure floor. Minimum exposure here is a coverage diagnostic. Reliability remains to be measured.

All 16 box panels pass the existing [box-v1 appearance contract](box-score-feature-contract.md), using private pinned NBA.com player and team logs. Every modeled player has positive-minute history at season close. The season-close panel aggregates raw sufficient statistics from dated positive-minute appearances across teams. It can include valid box appearances from quarantined possession games. For a dated forecast or season opening, only earlier games may contribute. An opening may use the immediately prior eligible calendar season's earlier box games, preserving the frozen #30 rule. Missing recent history takes the appropriate cold path. Capture dates postdate historical cutoffs, so these comparisons are retrospective. This registration reads no 2023–24 or later outcomes, EPM or Skills fit data.

## Coverage and per-use eligibility

Accepted/expected games and accepted-game shares of positive player minutes are listed separately for regular season and playoffs. The box-log minute denominators include all eligible box appearances. On-court players are distinct IDs in archived stable-lineup rows. The exact post-exclusion row counts by type are in the manifest.

| Season | Regular | Playoffs | Regular / playoff box minutes retained | On-court players | Eligible rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2004–05 | 1,204/1,230 | 82/84 | 97.89% / 97.64% | 464 | 203,465 |
| 2005–06 | 1,220/1,230 | 88/89 | 99.15% / 98.77% | 458 | 205,753 |
| 2006–07 | 1,209/1,230 | 78/79 | 98.26% / 98.74% | 458 | 204,981 |
| 2007–08 | 1,214/1,230 | 86/86 | 98.69% / 100% | 451 | 209,831 |
| 2008–09 | 1,220/1,230 | 85/85 | 99.19% / 100% | 445 | 209,819 |
| 2009–10 | 1,220/1,230 | 82/82 | 99.18% / 100% | 441 | 211,229 |
| 2010–11 | 1,216/1,230 | 81/81 | 98.86% / 100% | 452 | 208,009 |
| 2012–13 | 1,200/1,229 | 85/85 | 97.65% / 100% | 471 | 206,728, conditional |
| 2014–15 | 1,216/1,230 | 80/81 | 98.85% / 98.78% | 491 | 211,889 |
| 2015–16 | 1,208/1,230 | 85/86 | 98.16% / 98.84% | 478 | 215,087 |
| 2016–17 | 1,209/1,230 | 79/79 | 98.27% / 100% | 486 | 215,883 |
| 2018–19 | 1,206/1,230 | 80/82 | 97.94% / 97.59% | 530 | 223,681 |
| 2019–20 | 1,041/1,059 | 82/83 | 98.30% / 98.81% | 530 | 195,124 |
| 2020–21 | 1,072/1,080 | 85/85 | 99.26% / 100% | 540 | 200,249 |
| 2021–22 | 1,219/1,230 | 87/87 | 99.08% / 100% | 606 | 223,032 |
| 2022–23 | 1,208/1,230 | 84/84 | 98.22% / 100% | 541 | 224,037 |

- **2012–13.** Support a conditional training sensitivity only. April accounts for 17 of 29 regular-season quarantines and 35 of 64 regular-season unresolved possessions sit in the 6–10 point margin band. Complete playoff coverage, 97.65% of box minutes and positive-minute history for all labeled players do not resolve those concentration risks. In the conditional fit, report model exposure by April, team and margin band, report estimates both with and without 2012–13, and use the same evaluation targets and games. [#53 missingness](historical-backfill-2001-2017.md)
- **Older verification.** All six recovered seasons lack liveData and data.nba, so their V2/V3 and lineup corroboration share NBA lineage. Keep the `no_livedata`, `no_datanba`, `same_clock_order` and `free_throw_miss` strata. Cross-tabulate reliability and missingness by source stratum, era, role, team and game type, and measure a sensitivity excluding retry-game rows and the six-season addition. Aided reconstruction of a few historically flagged games is not proof of independent coverage. In particular, retain the 2010–11 second-quarter playoff watch and the 2014–15 Bentes outlier from #53. All 16 seasons cover 30 teams in accepted games. Track shooting-denominator nulls, particularly three-point percentage for older low-volume players. Apply fit-only imputation following #30 and keep missingness counts per season.
- **Limits.** The five one-game-short or weaker #53 seasons and 2017–18 remain outside this registered cohort. Whole-game, externally observed and strict historical availability claims require separate evidence. This is a 15-season primary and 16-season sensitivity with research use only. Source data stay private under the [source ledger](../data-sources.md).

## Verification

The audit rechecked the selected raw snapshots against the source pins. For each season, it ran the archived pilot's hard checks, verified every row-set output digest and reused the #26/#28 context loader with the registered season pins. All sixteen loaded without score/clock violations. The loader recorded opening possessions without a prior event in its existing separate accounting. At `8eac253006592f9ac597758f50d1cdbddf858a1e`, each of the six #53 row sets produced its archived build ID and four byte-identical Parquet files. Use the [#53 replay commands](historical-backfill-2001-2017.md#verification-and-runtime) and the manifest's pilot/snapshot pins. Use `bil.features.box_build.load_appearances` with the explicit season year, and `bil.features.box.Accumulator` to derive full-season feature coverage for positive-minute players. No target fit or outcome comparison was run.

The experimental input-only dry run verifies the registered archives and reports eligible counts without fitting.

```sh
uv run python -m bil.models.rapm.expanded_inputs data \
  docs/research/expanded-rapm-cohort-v1.json --cohort conditional_16
```
