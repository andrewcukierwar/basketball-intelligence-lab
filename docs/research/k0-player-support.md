# K0 agreement and player-level support results

Across four development seasons, the 64,000 ridge candidate agreed most closely with both the independent K0 analogue and the repeat ratings. The 4,000 ridge candidate had the lowest held-out lineup loss in every season. Zero individual contrasts met the registered lineup support rule. The evidence establishes a ranking reversal for lineup forecasts and leaves the player-level outcome question unresolved. [Protocol](k0-player-support-protocol.md) · [#137](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/137)

## Disjoint rating and outcome comparisons

The K0 analogue and repeat estimates were each fit at 16,000 on their own games. The matched rating cohort covers 1,062 offensive and 1,055 defensive player-seasons. Rating RMSE uses points per 100 possessions. Outcome deltas are possession MSE relative to 16,000. Negative deltas favor the candidate. Brackets show paired 95% game-cluster intervals.

| Candidate | Offense proxy / repeat RMSE | Defense proxy / repeat RMSE | Held-out Δ MSE |
| --- | ---: | ---: | ---: |
| Context only, zero player effects | 0.231 / 0.238 | 0.214 / 0.225 | +3.750 [+2.646, +4.807] |
| Ridge 1,000 | 1.600 / 1.599 | 1.614 / 1.611 | +6.063 [+0.597, +11.602] |
| Ridge 4,000 | 0.613 / 0.616 | 0.630 / 0.628 | −2.460 [−4.402, −0.479] |
| Ridge 16,000 | 0.249 / 0.256 | 0.258 / 0.260 | 0.000 |
| Ridge 64,000 | 0.215 / 0.222 | 0.205 / 0.214 | +2.497 [+1.700, +3.245] |

The outcome evaluation covers 199,434 regular-season possessions in 1,145 games. Taking out each franchise in turn kept the 4,000 deltas below zero (−3.092 to −1.929) and the 64,000 deltas above zero (+2.225 to +2.733). The paired week intervals have the same signs. The 4,000 outcome delta was −5.188 [−9.208, −1.071] on the 50,902 possessions with ten sufficiently exposed players and −0.924 [−4.264, +2.319] across the 52,759 possessions with at least one unseen player.

At the player level, the largest ridge also had the lowest repeat RMSE in both roles across every season's exposure and overlap slices. It led agreement with the disjoint proxy in all 250–999 exposure slices and most higher-exposure and overlap slices. Pooled player-cluster intervals preserve its advantage over 16,000 in both roles. The published full-season K0 labels had the lowest descriptive RMSE for 4,000 in every season and role. Those labels use the full season and share outcomes with the evaluation, which prevents interpreting that result as an independent test.

## Individual contrast coverage

Every role and season yielded zero contrasts with the same four teammates and five opponents and at least two games and 15 possessions per player in both the candidate and outcome blocks. Across roles and seasons, the candidate blocks had 57,414 to 63,203 distinct nine-player configurations and the outcome blocks had 53,175 to 65,534. The common-support requirement was fixed in advance. The analysis reports no observed player-level outcome ordering for this design. A player claim still needs an identifiable, sufficiently supported contrast that agrees with independent outcomes.

The run used pinned #28 regular-season row sets and the registered development-season partitions. Run `bil.models.k0_support` with the committed protocol digest to reproduce it. The clean run `52bf617` had the same Git tree as the preregistered GitHub commit `cdac679` and completed in 6.18 s. Private artifacts under `data/processed/rapm_targets/issue-137-v1` store the schedule digests, frozen predictions and role effects, stratified counts and score intervals. No model changes were selected from this diagnostic. [PR #154](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/154)
