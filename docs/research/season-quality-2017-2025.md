# Season quality and missingness, 2017–18 through 2024–25

**Evidence class:** Original (data-quality diagnostic, no model). **Issue:** [#89](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/89). **Policy:** [ADR-0022](../DECISIONS.md#adr-0022--revise-the-m1-quality-policy-hard-correctness-dataset-eligibility-and-representativeness). **Experiment:** EXP-0012.

This report applies the revised M1 policy to the eight private builds and asks whether the games and possessions the pipeline did not keep are missing at random. It reads only exported tables and the pinned box logs, makes no network request, and fits or scores no model. No 2025–26 or later file was read. Outer-validation seasons (2023–24, 2024–25) get data-quality diagnostics only. Eligibility decisions belong to the maintainer; this report supplies the evidence.

## Command and inputs

```sh
uv run python scripts/season_quality.py data/processed/quality/issue-89-v2 \
  --build data/processed/2017-18/issue-25-v1 data/raw/2017-18/issue-25-v1 \
  --build data/processed/2018-19/issue-25-v1 data/raw/2018-19/issue-25-v1 \
  --build data/processed/2019-20/issue-25-v1 data/raw/2019-20/issue-25-v1 \
  --build data/processed/2020-21/issue-25-v1 data/raw/2020-21/issue-25-v1 \
  --build data/processed/2021-22/issue-25-v1 data/raw/2021-22/issue-25-v1 \
  --build data/processed/2022-23/issue-19-v6 data/raw/2022-23/issue-5-v2 \
  --build data/processed/2023-24/issue-52-v1 data/raw/2023-24/issue-52-v1 \
  --build data/processed/2024-25/issue-52-v1 data/raw/2024-25/issue-52-v1 --run-checks
```

Seed 20261123, 5,000 permutations, 20,000 bootstrap replicates. This is output `issue-89-v2`; `v1` used 1,000 replicates and is superseded (see Revision history). The run is deterministic: a rerun gives identical files. All 26 `check` invariants pass (0 failures) for every build, so none of the hard correctness results changed. Per-cell CSV and JSON output stays private under `data/processed/quality/issue-89-v2/` (`tests.csv` holds every test, `flags.csv` the flagged ones, `sensitivity.csv` the cohort table).

## Classification: original and revised

| Season | Original M1 | Revised (ADR-0022) | Why |
| --- | --- | --- | --- |
| 2017–18 | Fail | Fails hard limits | Regular-season game coverage 85.5% (floor 97%); season unresolved share 0.391% (limit 0.1%); three stratum warnings. |
| 2018–19 | Fail | Meets, with warning | Overtime stratum 58 of 67 (86.6%) below the 95% target. |
| 2019–20 | Pass | Meets | |
| 2020–21 | Pass | Meets | |
| 2021–22 | Fail | Meets, with warning | Overtime stratum 55 of 58 (94.8%) below the 95% target. |
| 2022–23 | Pass | Meets | |
| 2023–24 | Pass | Meets | |
| 2024–25 | Pass | Meets, with warning | Playoff unresolved share 0.135% above 0.1%; the season is at 0.070%. |

Original results are those recorded in [data-pilot.md](../data-pilot.md#development-seasons-201718-through-202122) and EXP-0007 and EXP-0009; the script reproduces them exactly.

## Flag rule

Each dimension gets a flag, from one rule. The quarantine rule was fixed before the first run. The unresolved-possession rule was revised after it (see Revision history):

- **Quarantined games.** Games are the unit. For each season type with at least 5 quarantines, a chi-square statistic compares observed with expected quarantines in each cell (team incidence with both teams of a game counted, calendar month, overtime or regulation, final-margin band 0–5, 6–10, 11–20, 21+). The null shuffles the quarantine labels across games, 5,000 times, so it needs no large-sample approximation. A player-level test uses the largest share of a player's box minutes lost, among players with at least 500 minutes (100 in playoffs).
- **Unresolved possessions.** Possessions in accepted games are the unit (denominator: all possessions, as the M1 share is). Each cell of offense team, month, period (Q1–Q4, OT) and score margin before the possession is compared with all other cells as a rate ratio, with a game-clustered bootstrap. The p-value of the most elevated cell is multiplied by the number of cells with at least 5 unresolved possessions (Bonferroni). The bootstrap p-value is approximate: twice the smaller tail share of resampled rate ratios around 1. Its floor is 2k / replicates, so the script refuses to run when that reaches 0.01 (30 team cells need more than 6,000 replicates).
- **Flag.** *Systematic* when p < 0.01, the most affected cell is at least 2 times its expected rate, and it holds at least 5 events. *Watch* when p < 0.05 only. Season types with too few events are *not testable*.
- Estimated possessions in a quarantined game use the box log: field goal attempts, 0.44 times free throw attempts, minus offensive rebounds plus turnovers, averaged over the two teams (Inferred, an exposure proxy only).

## What was lost

| Season and type | Games quarantined | Est. possessions lost | Box minutes lost | Appearances lost | Unresolved share (95% interval) |
| --- | ---: | ---: | ---: | ---: | --- |
| 2017–18 regular | 178 of 1230 (14.5%) | 14.56% | 14.46% | 3813 of 26104 | 0.418% (0.364–0.473%) |
| 2017–18 playoffs | 2 of 82 (2.4%) | 2.38% | 2.43% | 42 of 1729 | 0.019% (0.000–0.052%) |
| 2018–19 regular | 24 of 1230 (2.0%) | 2.07% | 2.06% | 514 of 26098 | 0.068% (0.053–0.083%) |
| 2018–19 playoffs | 2 of 82 (2.4%) | 2.54% | 2.41% | 45 of 1761 | 0.063% (0.013–0.125%) |
| 2019–20 regular | 18 of 1059 (1.7%) | 1.72% | 1.70% | 379 of 22392 | 0.036% (0.026–0.048%) |
| 2019–20 playoffs | 1 of 83 (1.2%) | 1.09% | 1.19% | 21 of 1692 | 0.055% (0.012–0.105%) |
| 2020–21 regular | 8 of 1080 (0.7%) | 0.74% | 0.74% | 160 of 23054 | 0.026% (0.018–0.036%) |
| 2020–21 playoffs | 0 of 85 (0.0%) | 0.00% | 0.00% | 0 of 1864 | 0.024% (0.000–0.055%) |
| 2021–22 regular | 11 of 1230 (0.9%) | 0.92% | 0.91% | 230 of 26036 | 0.026% (0.018–0.036%) |
| 2021–22 playoffs | 0 of 87 (0.0%) | 0.00% | 0.00% | 0 of 1891 | 0.024% (0.000–0.054%) |
| 2022–23 regular | 22 of 1230 (1.8%) | 1.76% | 1.78% | 473 of 25892 | 0.021% (0.014–0.029%) |
| 2022–23 playoffs | 0 of 84 (0.0%) | 0.00% | 0.00% | 0 of 1728 | 0.000% (0.000–0.000%) |
| 2023–24 regular | 12 of 1230 (1.0%) | 1.00% | 0.99% | 243 of 26399 | 0.035% (0.025–0.046%) |
| 2023–24 playoffs | 1 of 82 (1.2%) | 1.25% | 1.21% | 18 of 1684 | 0.092% (0.026–0.172%) |
| 2024–25 regular | 25 of 1230 (2.0%) | 2.07% | 2.04% | 520 of 26303 | 0.065% (0.051–0.081%) |
| 2024–25 playoffs | 0 of 84 (0.0%) | 0.00% | 0.00% | 0 of 1804 | 0.135% (0.056–0.228%) |

Quarantined games are almost exactly the share of possessions, minutes and appearances lost, so a season's loss is a game loss. 2017–18 is the outlier at 14.5%.

## Findings

**Systematic flags (all tests, all seasons).** Of 83 testable tests (144 including those with too few events), five are flagged systematic and four are on watch. The rest are clear.

| Season | Test | Result | Flag |
| --- | --- | --- | --- |
| 2017–18 regular | Quarantines by month | 57 of 104 games in October 2017, 81 of 213 in November, 20 of 227 in December, at most 5% afterwards; p = 0.0002 | Systematic |
| 2017–18 regular | Largest player minutes share lost | 3.4 times the season rate, p = 0.0008 | Systematic |
| 2017–18 regular | Unresolved by month | October 2017 (151 events) at 4.4 times the rest, adjusted p = 0.0007 | Systematic |
| 2018–19 regular | Quarantines by overtime | 9 of 67 overtime games (13.4%) against 15 of 1,163 regulation games (1.3%); lift 6.9, p = 0.0002 | Systematic |
| 2018–19 regular | Quarantines by month | 11 of 219 games in November 2018 (5.0%) against 13 of 1,011 elsewhere (1.3%); lift 2.6, p = 0.006 | Systematic |
| 2021–22 regular | Quarantines by overtime | 3 of 58 overtime games (5.2%) against 8 of 1,172 (0.7%); only 3 events, p = 0.013 | Watch |
| 2022–23 regular | Quarantines by month | 10 of 22 in March 2023, p = 0.027 | Watch |
| 2023–24 regular | Unresolved by period | Q3 at 2.3 times the rest, adjusted p 0.048 | Watch |
| 2024–25 regular | Quarantines by month | 8 of 25 in December 2024, p = 0.014 | Watch |

**2018–19 (conditionally authorized): material systematic missingness found, small in size.** Two patterns are flagged.
- *Overtime games are under-retained.* Nine of the 24 regular-season quarantines are overtime games, though overtime games are 5.4% of the season. The causes are parser reorder failures (2 overtime games of 10), missing period start (3 of 4), parser error (2 of 4) and unresolved starters (2 of 2); the pipeline fails more often when a game has a fifth period (Inferred). Overtime is 4.81% of accepted games against 5.45% of expected, a shortfall of 0.6 percentage points. Excluding overtime periods removes 0.6% of cohort possessions (table below).
- *November 2018 is under-retained* (11 of 24 quarantines in one month). The causes in that month were not examined individually.
- Team, final margin and the player minutes statistic are not flagged (team p = 0.81, margin p = 0.051, player p = 0.20). The season loses 2.07% of possessions and 2.06% of box minutes. Its unresolved share is 0.068% (0.053–0.083%) in the regular season, 0.063% in the playoffs, spread across 81 of 1,206 games with no flag.
- The lost data are a small, nonrandom slice of overtime and November games. Whether that bias is material for primary training is the maintainer's decision; the sensitivity table quantifies the dependence.

**2021–22 (conditionally authorized): no systematic pattern.** 11 regular-season quarantines (0.92% of possessions, 0.91% of box minutes), none in the playoffs. The overtime miss is 3 of 58 games, flagged only as watch on 3 events, and no team, month, margin or player pattern is flagged. Unresolved possessions are 0.026% with no flag.

**2024–25 playoffs (outer validation): elevated rate, diffuse.** 22 unresolved of 16,278 possessions (0.135%, interval 0.056–0.228%, so the interval includes the 0.1% limit). No quarantined playoff games. They sit in 10 of 84 games, the largest holding 4. By month (April 3, May 13, June 6 events), period and margin, no cell is flagged (adjusted p between 0.30 and 1.0). The elevated share is therefore not tied to a team, round timing, period or score state that can be tested here, but with 22 events the power is low. The regular season is at 0.065% (0.051–0.081%) with no flag, and its 25 quarantines carry only a watch for December.

**2017–18 (outside the primary cohort).** Quarantines are strongly concentrated in the first months, and the player minutes statistic is flagged. This agrees with the earlier inferred diagnosis of early-season event-order failure and gives the remediation feasibility assessment ([#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53)) a measured target. It is a diagnostic, not a new cause.

**Other seasons.** 2019–20 and 2020–21 have no flag. 2022–23, 2023–24 and 2024–25 each have one watch and no systematic flag.

## Sensitivity of the primary cohort (data only)

The primary cohort is 2018–19 through 2022–23: accepted games, possessions with status accepted, and players on court at the start of those possessions. 'Weaker verification' removes games carrying `no_livedata` (all of 2018–19 and 2019–20) or `v2_home_designation` (none in the cohort; the five such games are in 2024–25). 'Overtime periods' removes possessions and minutes after the fourth period but keeps the game.

| Scenario | Games | Possessions | Players (≥1,000 poss.) | On-court player-hours | Change in games / possessions / players |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline | 6,164 | 1,223,735 | 970 (720) | 49,628 |  |
| exclude 2018–19 | 4,878 | 966,890 | 863 (643) | 39,278 | -20.9% / -21.0% / -107 |
| exclude 2021–22 | 4,858 | 967,718 | 924 (693) | 39,126 | -21.2% / -20.9% / -46 |
| exclude both conditional seasons | 3,572 | 710,873 | 807 (615) | 28,776 | -42.1% / -41.9% / -163 |
| exclude overtime periods | 6,164 | 1,216,341 | 970 (720) | 49,312 | +0.0% / -0.6% / +0 |
| exclude overtime games | 5,830 | 1,150,936 | 968 (716) | 46,640 | -5.4% / -5.9% / -2 |
| exclude weaker verification games | 3,755 | 741,663 | 785 (576) | 30,227 | -39.1% / -39.4% / -185 |
| exclude conditional seasons and overtime periods | 3,572 | 706,151 | 807 (615) | 28,576 | -42.1% / -42.3% / -163 |
| exclude all three | 2,449 | 482,547 | 717 (545) | 19,592 | -60.3% / -60.6% / -253 |

Reading the table:
- Dropping either conditional season costs about a fifth of games and possessions and 46 to 107 players (27 to 77 with at least 1,000 possessions). Dropping both removes 42% of the cohort.
- Dropping overtime periods changes possessions by 0.6% and loses no player. Dropping whole overtime games changes games by 5.4% and possessions by 5.9%, with two players lost.
- The `no_livedata` stratum is the largest dependency. Excluding weaker-verification games removes 39% of the cohort, essentially 2018–19 and 2019–20. All three exclusions together leave 2,449 games, 482,547 possessions and 717 players.

## Limitations

- The tests find association with the listed dimensions, not the mechanism. Quarantine cause is reported by count, not diagnosed per game.
- Game-state tests for quarantined games use only box and final-score information, because those games have no events. Score margin there is the final margin; for unresolved possessions it is the running margin before the possession.
- With 3 to 25 quarantines a season, the permutation tests have little power, so *none* does not rule out a pattern. Playoffs are mostly not testable.
- 83 testable tests were run across the eight seasons, with no global correction; the flag rule combines a 1% threshold with a minimum effect size and event count instead. Watch flags are expected by chance.
- Exposure in possessions for lost games is estimated from the box log.

## Revision history

- **Unresolved flag rule revised after the first run.** The first full run flagged cells with as few as 3 unresolved possessions, and some had an infinite ratio because nothing was unresolved elsewhere (for example 3 events in 2017–18 playoffs). The rule was tightened to at least 5 events per cell, with Bonferroni over cells, and the output was regenerated. Calls that changed from the first run: 2017–18 playoffs unresolved from systematic to not testable; 2023–24 regular Q3 from systematic to watch; and the loose rule had also produced watches on 2018–19 margin, 2019–20 team, 2020–21 Q2 and 2024–25 regular-season team, which no longer appear. None of these changes affects the 2018–19 overtime and November findings, the 2021–22 result or the 2024–25 playoff result.
- **Review fix: the bootstrap p-value floor (v1 to v2).** With 1,000 replicates the smallest Bonferroni-adjusted p is 2k/1000, so a 1% flag was unreachable for 5 or more cells and a 5% flag for 25 or more, and the 30-cell team tests could never flag. The default is now 20,000 replicates, and the script refuses a run whose floor reaches 0.01. Rerun as `issue-89-v2`. The only flag that changed is 2017–18 regular unresolved by month (October 2017, 151 events, 4.4 times the rest), from watch (p = 0.014, at the v1 floor) to systematic (p = 0.0007). 2018–19, 2021–22 and the 2024–25 playoffs are unchanged (the playoffs' adjusted p-values stay at 0.30 to 1.0, so no team or month pattern appears even though team tests can now flag). The team tests in all other seasons stay unflagged.
- The player minutes test now takes its event count from the player who holds the maximum, not a fixed minimum.
