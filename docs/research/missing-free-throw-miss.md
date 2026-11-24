# Missing miss markers before team rebounds

[Issue #115](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/115) follows the [same-clock ordering study](same-clock-rebound-order.md). The older V2 archive sometimes records a missed free throw as a bare attempt label with a blank score field, followed by a team rebound at the same clock. The pinned parser recognizes misses from its description marker and otherwise interprets the attempt as made. It may then reject the rebound. The examples below are hand-adjudicated from the pinned, NBA.com-attributed archives used for private research.

## Evidence rule

Enable `build --free-throw-miss-rule` to offer `free-throw-miss-v1` after earlier configured attempts fail with a rebound-order error. The rule qualifies a conventional numbered attempt with a bare description on the shooter's side and no score field. A team rebound must be directly next, within the same period and clock, with a team ID confirmed by the game and no score field. An intermediate attempt requires the shooter's own team rebound and the next numbered attempt by that shooter at the same clock. A later missed field goal in the same clock segment makes the pairing ambiguous.

For each affected shooter, reconcile all V2 free-throw attempts with the pinned player box. Every other attempt needs a recorded miss or an observed one-point score increase on the shooter's side alone. Only offer the annotation when treating the candidates as misses reproduces both box totals exactly. When a score contradicts the text, a relevant attempt remains unknown, or a candidate has insufficient box evidence, retain the existing quarantine. The rule does not search event orders or edit source records.

The retry passes a copy of the description with the parser's miss marker. The parser must attribute the rebound to that exact shot. The original source rows and event IDs remain the normalization input. The original score, player-box, lineup and chronology checks run before acceptance. The `free_throw_miss` stratum, manifest and quality warning identify the variant, affected source events and box totals. Failed offers remain quarantined. This rule does not change any game accepted by the existing path.

## Hand-adjudicated cases

| Game | Evidence and disposition |
| --- | --- |
| `0021000044` | The first of two attempts advances the home score. The second attempt (356) has a blank score and is immediately followed by a visiting team rebound (357) at 4:19 of the third period. The player's box is 2-for-6. The adjusted description gives the parser the basis to link the rebound, and the ordinary reconciliation passes. |
| `0041200215` | V2 lists attempt 261 directly before team rebound 284 despite the gap in source event numbers. The attempt has a blank score and the player's box is 2-for-4. The rule uses recorded sequence and the clock, and the retry passes. |
| `0041100167` | The local evidence supports an offer, but the repaired game still fails the parser. It stays quarantined. |

## Verification

All 26 hard checks passed for each of the eight rebuilds. Across 10,075 games accepted by the comparison builds, every row matched in ten tables, apart from the expected ingestion timestamps. The 2008–15 comparison uses `issue-111-rule-v5`. The 2022–23 comparison uses `issue-90-rebuild-v2`. The 2022–23 verification rebuild recovered no games and produced identical rows apart from ingestion time.

| Season | Regular season before → after | Playoffs before → after | Games recovered | Unresolved share | ADR-0022 hard limits |
| --- | ---: | ---: | ---: | ---: | --- |
| 2008–09 | 1,206 → 1,220 / 1,230 | 85 → 85 / 85 | 14 | 0.030% | Meets |
| 2009–10 | 1,214 → 1,220 / 1,230 | 82 → 82 / 82 | 6 | 0.025% | Meets |
| 2010–11 | 1,209 → 1,216 / 1,230 | 81 → 81 / 81 | 7 | 0.025% | Meets |
| 2011–12 | 969 → 979 / 990 | 81 → 81 / 84 | 10 | 0.030% | Fails playoff coverage |
| 2012–13 | 1,192 → 1,200 / 1,229 | 84 → 85 / 85 | 9 | 0.027% | Meets |
| 2013–14 | 1,203 → 1,218 / 1,230 | 86 → 86 / 89 | 15 | 0.029% | Fails playoff coverage |
| 2014–15 | 1,212 → 1,216 / 1,230 | 79 → 80 / 81 | 5 | 0.019% | Meets |
| 2022–23 | 1,208 → 1,208 / 1,230 | 84 → 84 / 84 | 0 | 0.020% | Meets |

Of the 69 games where the rule reached a parser retry, 66 were recovered. Two retries failed in the parser and one failed box plus-minus reconciliation. All three games kept their original quarantine reasons. The original V2 and V3 retry paths continue to handle games accepted by those paths.

The 2012–13 variant now meets the hard limits. The full missingness diagnostic still flags April regular-season quarantines (17 of 29, lift 5.54) and unresolved possessions in the 6–10 point regular-season margin band (35 of 64, lift 3.41). Preserve those strata for any proposed use. The frozen SPM target cohort remains governed by ADR-0026. The 2011–12 and 2013–14 variants remain below the 97% playoff floor, with overtime coverage warnings.

Pinned evidence comparisons for 2011–12, 2012–13 and 2013–14 agree with Bentes on lineup time across all accepted games. Possession counts match pbpstats.com in 1,033 of 1,060 games, 1,251 of 1,285, and 1,269 of 1,304, respectively. These are aggregate corroboration. Bentes shares the upstream event feed, and the archived V3 row can carry the same missing text.

## Reproduce with private pins

Rebuild into a new private directory. The receipt reports `free_throw_miss_rule.version` and the applied or rejected games. Use the matching archived evidence snapshot with the `evidence` command.

```sh
uv run python -m bil.data.pilot build SNAPSHOT OUTPUT \
  --code-commit "$(git rev-parse HEAD)" --same-clock-rule --free-throw-miss-rule
uv run python -m bil.data.pilot check OUTPUT SNAPSHOT
uv run python -m bil.data.pilot evidence OUTPUT SNAPSHOT EVIDENCE_SNAPSHOT
uv run python scripts/season_quality.py QUALITY_OUTPUT --build OUTPUT SNAPSHOT
```

The verification uses snapshot `issue-111-v1` in 2008–09, 2009–10 and 2011–12, `issue-90-v1` in 2010–11, `issue-98-v1` in 2012–13 through 2014–15, and `issue-5-v2` in 2022–23. The private builds are in each season's `issue-115-v2` directory. No later season outcomes were accessed.
