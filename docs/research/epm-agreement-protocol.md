# External agreement between Expected impact v1 and published EPM

**Registration:** [#40](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/40). This protocol is committed before any EPM rating value is read or compared.

**Classification:**
- Experimental diagnostic for EPM-U12.
- **External agreement is not predictive validity.** It selects nothing and tunes nothing.

**Rights:**
- **Permission.** The maintainer reports express written permission from Dunks & Threes to obtain and privately store EPM for this project, for non-commercial use only. See the [data-sources ledger](../data-sources.md).
- **Storage.** EPM values stay under `data/`.
- **Repository.** It holds only aggregate statistics, attributed to dunksandthrees.com.

## 1. Frozen model and boundary

- **Frozen model.** The independent model is frozen before this protocol: Expected impact v1 ([ADR-0031](../DECISIONS.md#adr-0031--expected-impact-v1-as-the-m5-integrated-reference)), with the #38 tracking comparison frozen as recorded ([ADR-0032](../DECISIONS.md#adr-0032--keep-expected-impact-v1-box-only-after-the-38-tracking-comparison)).
- **Ratings.** These come from the private `ratings.csv` of `expected_impact/issue-35-v1` (manifest `db254b8c…e5d1`) and `issue-36-v1` (manifest `f74fc2a5…a131`). Verify both manifests and their `ratings.csv` digests.
- **No EPM in any model input.** EPM never enters training, calibration, feature selection, penalty choice, any model or ADR revision, or #42 candidate selection. A disagreement is reported, not acted on.
- **Holdout.** No EPM for 2025–26 or later is read. The newest registered capture is dated 2025-07-18, before the 2025–26 regular season.

## 2. EPM source and pins

- **Source.** The free public page `https://dunksandthrees.com/epm`, as archived by the Internet Archive.
- **Why archived captures.** The live free page shows only current values, and its historical views are subscriber-only. The archive holds the free page as served on each capture date.
- **Fetching.** Fetch raw captures (`id_` mode) and store them in `data/raw/epm-wayback/`. Verify each SHA-256 before parsing.

| Season | Capture | SHA-256 | Embedded format | Content |
| --- | --- | --- | --- | --- |
| 2021–22 | `20220703130813` | `ffe649f5…d7ab` | `var data` JSON, `player_stats` | Season EPM, regular season |
| 2022–23 | `20230705024653` | `1e86fa8a…bbb1` | Columnar rows with key map `k` | Season EPM; keep `seasontype = 2` (regular) |
| 2023–24 | `20240701155753` | `6db67c2c…f5df` | As 2022–23 | As 2022–23 |
| 2024–25 | `20250718200357` | `93189c0b…739e` | Records with `game_dt` | Expected EPM as of `game_dt` (2025-06-22) |

**How these were chosen.**
- Registration probed the archive's capture list. Fourteen further captures from 2022 to 2025 were downloaded only to read their structure: format, keys, season and data dates.
- Values were masked in that probe, and no rating value was compared.
- The rule: for each season, take the first capture on or after 1 July whose embedded data is that season's, or the nearest such capture.
- For 2024–25 the only parseable capture near season end holds the dated Expected EPM view, not season EPM. Its alignment differs and is reported separately.

**Parsing rules.**
- Keep rows whose `season` equals the season's end year.
- Read `player_id` (the NBA person ID), `off`, `def` and `tot`.
- If a player has several rows (team stints), combine them as the minutes-weighted mean of `off` and `def` using `mp`, and set `tot = off + def`.
- A row with missing `off` or `def` is dropped and counted. Non-numeric values stop the run.
- **Sign convention.** EPM `def` is taken as positive = better defense, as Dunks & Threes documents. EI's positive defense means points prevented. No sign is flipped after reading. A negative defense correlation is reported as observed.

## 3. Alignment, cohort and metrics

**Snapshot alignment.** Each EPM season is compared with the EI snapshot that is the end-of-season state:

| EPM season | EI snapshot (`as_of`) | Run |
| --- | --- | --- |
| 2021–22 | 2022-10-01 | `issue-35-v1` |
| 2022–23 | 2023-07-01 | `issue-35-v1` |
| 2023–24 | 2024-10-01 | `issue-36-v1` |
| 2024–25 | 2025-07-01 | `issue-36-v1` |

Report each EPM data date and capture date, and the gap in days.

**Known differences, reported and not adjusted:**
- EI uses a two-season window including playoffs.
- Season EPM covers the regular season.
- The 2024–25 EPM is an expected rating.

**Cohort.**
- **Primary.** Players present in both sources with EI `window_possessions ≥ 1000`.
- **Slices:**
  - EI window possessions of 1,000–2,999 and 3,000 or more;
  - all matched players, with no threshold;
  - players whose EI prior is the SPM intercept fallback (`box_history = False`).
- **Counts reported:**
  - EPM players unmatched to EI, and EI players unmatched to EPM;
  - dropped rows;
  - multi-stint players.

**Metrics.** For offense, defense and total, per season and pooled:
- Pearson r and Spearman ρ.
- MAE and RMSE of EI − EPM, and the mean signed bias.
- **Top-N overlap.** Top 25 and top 50 by total within the primary cohort. Report the share of EPM's top N that is also in EI's top N.

**Comparisons.**
- Each metric is reported for EI and for its SPM prior alone (`prior_*`), so the on-court update's effect on agreement is visible.
- Plain RAPM ratings were not stored by #35 or #36 and are not refitted for this diagnostic.

**Uncertainty.**
- Pooled-primary 95% intervals come from 1,000 player-cluster bootstrap resamples with seed 40. Pooled players are resampled together with all their seasons.
- Intervals cover r for EI, and r for EI minus r for the SPM prior, on each side.

## 4. Artifacts and run

- **Private outputs.** One new directory per run holds the parsed EPM table with its digest, the matched pairs, and `results.json` and `manifest.json`.
- **Repository.** Aggregates only.
- **Run discipline:**
  - The run happens on a clean committed tree.
  - A crash before results allows a rerun.
  - Results are reported regardless of direction.
- **Tests.** Synthetic tests cover:
  - all three parsers on masked fixtures;
  - the multi-stint rule;
  - season filtering;
  - refusal of a capture outside the pins, or with a season of 2025–26 or later.
