# Retrospective Actual impact results

The registered #41 experiment found no clear playoff benefit from weighting playoff possessions four times as heavily in the preseason-anchored fit. The playoff delta was **+4.686 MSE [−1.466, +10.579]** against the uniform anchor, an inconclusive result under the registered rule. The uniform and weaker anchors remain research comparators. [Protocol](actual-impact-protocol.md) · [#41](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/41)

## Preseason and game coverage

The October 1 #36 anchors include 712 eligible players for 2023–24 and 661 for 2024–25. The rebuilt rating values matched the published archive within `5e-7` points per 100. The anchors omitted 214 and 265 off-roster IDs, respectively, which receive explicit cold priors at inference. Each game holds out all its possessions from the corresponding current-season player and context fits. The complete predictions cover 418,479 regular-season possessions in 2,423 games and 26,725 playoff possessions in 165 games. All scored game and possession keys are unique within season.

## Held-out games

Deltas are MSE relative to the uniform anchored model. Negative deltas favor the candidate. Intervals are paired by game at 95%.

| Candidate | Regular-season Δ MSE | Playoff Δ MSE |
| --- | ---: | ---: |
| Preseason only | +11.969 [+9.999, +13.912] | +8.159 [−1.077, +17.629] |
| Season only | +8.810 [+6.924, +10.597] | +6.812 [+0.537, +13.539] |
| Uniform anchor | 0.000 | 0.000 |
| Weaker anchor | −0.957 [−1.716, −0.132] | +1.942 [−1.588, +5.356] |
| Playoff emphasis | +1.317 [+0.564, +2.097] | +4.686 [−1.466, +10.579] |

The playoff-emphasis deltas were +2.069 in 2023–24 and +7.142 in 2024–25. The pooled playoff week interval [−1.304, +10.547] also crossed zero. The other comparisons are descriptive. The uniform anchor had the lowest playoff MSE among the tested candidates. The weaker anchor had lower regular-season MSE. The study covers two previously examined seasons and its retrospective fits can use other games after a scored game. Any claim about pregame accuracy needs a separate chronological evaluation.

The clean run of `bil.models.actual_impact` took 9.27 s at local commit `7689af7`, with the same Git tree as preregistered GitHub commit `c43f53b`. Private artifacts under `data/processed/expected_impact/issue-41-v1` contain the frozen anchors, fit diagnostics, held-out predictions, game and week intervals and artifact digests. The separate experiment did not change the pregame pipeline. [PR #155](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/155)
