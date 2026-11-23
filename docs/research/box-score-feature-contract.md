# 2022–23 box-score feature contract

This specification supports the first box-score SPM panels in [#29][parent] and the player-game history in [#31][skills]. It defines an interpretable BIL baseline. The public EPM methodology does not give the exact feature columns or opportunity definitions. [EPM methodology][epm] · [Uncertainty register](epm-uncertainties.md)

## Source and identity

Use the player and team game logs in the private `issue-5-v2` snapshot. The player log supplies traditional counts and decimal minutes. The team log supplies game-side, opponent, and played-date evidence. Pin both manifest entries and their SHA-256 hashes. The source stores no contemporaneous publication history or source revision for these partitions. The snapshot records their first known capture at 18:04 UTC on November 23, 2026. [Pilot source validation](nba-source-validation.md#machine-readable-box-score-comparison) · [Publisher data dictionary][dictionary]

NBA game data are attributed to NBA.com. Keep these source rows and private derived feature artifacts outside Git and use them for private, noncommercial research. Broader publication or commercial use requires separately established rights. [NBA Statistics terms][terms] · [Source ledger](../data-sources.md)

Normalize source game IDs to ten digits. Prefix `002` designates regular season and `004` playoffs in this cohort. The player observation key is `(game_id, player_id)`. Retain the team from that appearance, regardless of trades or current roster. Match the own and opposing team row within the same game. Verify the expected season, played date, home flag and reciprocal opponents before accepting the observation. Retain player identity across team changes. Keep the observation grain through normalization, then aggregate across teams over the declared window. Team splits remain available for diagnostics.

Use the box-verified cohort across all 1,314 games. Event-pipeline quarantines need not remove verified box rows. The SPM fit separately intersects feature windows with eligible RAPM targets and reports both cohorts. Publish separate regular-season and playoff counts. An explicitly registered mixed training window pools the two only when the target uses that same convention.

### Measured inputs

The pinned logs have 25,894 regular-season and 1,728 playoff player rows, covering 539 and 217 distinct players, respectively. All player-game keys are unique. Every scoped player row matches both team logs, with no discrepancies in date, home side or reciprocal team IDs. Seventy-one players have appearances for multiple teams. The required traditional fields and minutes are populated across the scoped rows. No row violated the shooting, scoring or rebound identities below.

Across both season types, 1,378 rows have no field-goal attempts, 6,016 have no three-point attempts, and 12,102 have no free-throw attempts. Two regular-season appearances record zero minutes and zero traditional event counts. Keep those observations and their known zero time. The player logs omit DNPs. A missing player-game row alone gives no reason for the absence.

## Counts and denominators

Persist the primitive source fields `min`, `fgm`, `fga`, `fg3m`, `fg3a`, `ftm`, `fta`, `pts`, `oreb`, `dreb`, `ast`, `tov`, `stl`, `blk`, and `pf`. Convert minutes to integer milliseconds using the pilot conversion, `round(min * 60000)`. Carry games with positive time and total minutes as exposure diagnostics. Keep observed zero values.

Require nonnegative, integral counts and finite nonnegative minutes. For populated components, check makes against attempts, three-point components within field-goal totals, two-point makes within two-point attempts, `pts = 2*fgm + fg3m + ftm`, and `reb = oreb + dreb` when total rebounds are supplied. Invalid values need a recorded correction or exclusion before aggregation. Use official definitions for source counts. [NBA Stats glossary][glossary] · [Canonical observation contract](../data-contracts.md#box-scores-tracking-and-feature-snapshots)

| Model group | Feature code | Numerator | Denominator and scale |
| --- | --- | --- | --- |
| Offense | `fg2_pct` | `fgm - fg3m` | `fga - fg3a`, fraction |
| Offense | `fg3_pct` | `fg3m` | `fg3a`, fraction |
| Offense | `ft_pct` | `ftm` | `fta`, fraction |
| Offense | `fg3_share` | `fg3a` | `fga`, fraction |
| Offense | `fga_per_36`, `fta_per_36` | Matching attempt count | Played milliseconds, multiplied by 2,160,000 |
| Offense | `ast_per_36`, `tov_per_36`, `oreb_per_36` | Matching event count | Played milliseconds, multiplied by 2,160,000 |
| Defense | `dreb_per_36`, `stl_per_36`, `blk_per_36`, `pf_per_36` | Matching event count | Played milliseconds, multiplied by 2,160,000 |

Use official box free throws, including any technical or flagrant points present in the count. The features describe box production and shot opportunities observed in the box. Unmodeled context includes on-court team and opponent possessions by role, assistable teammate makes, available offensive and defensive rebounds, defended shots and matchup opportunities. The optional advanced `poss` field supplies neither a verified role-specific possession ledger nor those event denominators. Keep it outside this baseline. Genuine opportunity rates need further stint or tracking evidence. Exclude same-window plus-minus, team outcomes, and advanced impact composites from the feature set. Defense features are box proxies.

Aggregate each metric as a ratio of numerator and denominator sums over appearances where both components are known. Derive two-point counts before summing. Keep both sums, eligible appearance count, component-covered appearance count and coverage fraction with the resulting feature. A known zero denominator leaves the rate unavailable while retaining measured components. A missing component removes that appearance from both sums for that metric only. If no complete component pair exists, leave both sums and the value null. A partial aggregate stays identifiable through its smaller covered count. A valid zero numerator and positive denominator yield an observed zero. Preserve empty or cold-start rows with null statistics when a requested player has no history.

## Training windows and dated views

- **Same-window training.** Declare the feature start and end dates and exact season types before selecting rows. Key each aggregate by `(window_id, player_id, feature_code, feature_definition_version)`. Pool counts only from eligible finalized games whose played dates are in that window. Use the same declared target window for a training join. Record feature-data and target-build cutoffs in the fit manifest.
- **Dated retrospective.** For an `America/New_York` rating date, select earlier league played dates only. A later frozen snapshot can support a retrospective result with the historical-revision gap recorded. Record the policy, input snapshot, time basis, player coverage and missingness in the manifest. Same-day and future games remain outside the aggregate, including a same-day early tip.
- **Strict as of.** A row needs an earlier league played date, verified finalization and a visible revision by the effective cutoff. When evidence is available, apply the latest eligible revision and its retraction semantics before aggregating. For these 2022–23 snapshots, the capture bound is in 2026 and historical finalization instants are unavailable. Emit an unavailable historical strict cohort for this source. A date-only source value cannot supply either timestamp.

Use `(snapshot_id, player_id, feature_code)` for the dated view. Bind the snapshot ID to the exact source digests, feature version, window and season types, cohort mode, cutoff and aggregation rules. Keep the dated history and same-window training tables distinct so a fit cannot use a season aggregate to predict an earlier day. The basic feature contract has no projected role, lineup, or team context. [As-of rules](../data-contracts.md#provenance-and-time) · [Evaluation strategy](../validation-strategy.md)

## Hand-calculated fixture

The [synthetic fixture](../../tests/fixtures/box_features/pilot_windows.json) follows one player across two teams. It tests a January 11 date boundary, an excluded playoff appearance, a known zero free-throw denominator and a missing assist observation. The January 11 retrospective features use the two earlier games and yield 13 points, 30 minutes, 1-for-2 three-point shooting and 6.0 assists per 36 minutes over the 18 minutes with observed assists. The same-window training view includes the January 11 game and yields 26 points and 54 minutes. Strict January 2023 availability remains unknown under the later archive probe, so that view has zero eligible appearances.

[parent]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/29
[skills]: https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/31
[epm]: https://dunksandthrees.com/about/epm
[dictionary]: https://github.com/llimllib/nba_data/blob/main/docs/DATA_DICTIONARY.md
[terms]: https://www.nba.com/termsofuse
[glossary]: https://www.nba.com/stats/help/glossary
