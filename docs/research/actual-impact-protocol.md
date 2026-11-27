# Retrospective Actual impact analogue

This experiment addresses [#41](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/41). It tests a preseason-anchored estimate of impact for a completed season. It is an original retrospective diagnostic motivated by EPM-U11. The 2023–24 and 2024–25 cohorts were already examined under #36. Use only the pinned #36 eligible possession and box-log inputs. The 2025–26 holdout, EPM values and pregame forecasts are outside the experiment.

## Freeze the preseason anchors

For each season, reconstruct the #36 EI snapshot at October 1 with the locked raw-box SPM, historical eligible rows, `W2`, and the frozen 8,000/8,000 penalties. Verify the #36 addendum digest `1076ab0bcfd022f39b68e99eaf9398ce7bec6d99985933821bf8f8bd68762d7c`. Apply #135's eligible roster and explicit per-role cold prior. Save the exact player values, cold values, cutoff, snapshot ID and parent identities before running the season fits. All model rows and box-line dates used for an anchor must precede its cutoff. Historical source revisions have retrospective capture bounds.

## Game-held-out retrospective estimates

Use five whole-game folds based on SHA-256 of `issue-41-v1:<game ID>`. In each fold, fit on all other eligible games of that season. A retrospective model can use observations later than a held-out game. No row from the held-out game can enter that fit, including its context coefficients. Score the known lineups separately for regular season and playoffs. Later seasons cannot enter the fit. Every model uses the same unpenalized pre-possession context and regular/playoff level, trained within the game fold.

| Candidate | Player fit |
| --- | --- |
| Preseason only | Freeze the player effects. Fit only the level and context around their contribution. |
| Season only | Fit within-season RAPM with penalty 8,000 per role and unit weights. |
| Uniform anchor | Fit deviations from the preseason ratings with penalty 8,000 per role and unit weights. |
| Weaker anchor | Fit deviations with penalty 4,000 per role and unit weights. |
| Playoff emphasis | Fit deviations with penalty 8,000 per role. Weight each playoff possession four times as much as a regular-season possession. |

Freeze all held-out prediction arrays and their game/possession identities before scoring. Report pooled and per-season possession MSE and paired 95% game- and week-cluster intervals. The primary contrast is playoff-emphasis minus uniform-anchor MSE on pooled playoff possessions. The registered rule requires the game interval to lie below zero and both playoff-season deltas to be negative for evidence in favor. Apply the mirror rule for evidence of harm. Report other comparisons and regular-season effects descriptively. Any resulting rating choice would need separate validation and registration. The existing pregame model lineage stays separate.
