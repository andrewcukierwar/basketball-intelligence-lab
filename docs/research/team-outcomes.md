# Team outcomes from frozen Expected impact ratings

This is the [#39](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/39) run of the [registered protocol](team-outcomes-protocol.md) (SHA-256 `c4b7cb8f…62302`).

**Evidence class:** retrospective rolling-origin.
- **Strict historical pregame evidence is unavailable.** No archived availability, roster or pregame receipt exists (#55).
- **Development evidence for M7.** Every season here was already scored at possession level in #35 and #36.
- **Not read:** the 2025–26 holdout and any EPM output.
- **Run:** clean commit `4bcb200`, 6 s, 0.77 GiB peak memory. Manifest SHA-256 `8486bf8c42a30c708b12717c4955617d43aef044c4cf0cbc5b6da5fa8b1b1cee`. An independent pre-run review (Sonnet subagent) found no blockers.

## Frozen choices from the development folds (2021–22 and 2022–23)

| Item | Value |
| --- | --- |
| Pace | 99.93 possessions per team-game |
| Team-rating baseline | Half-life 60 days, ridge 4. Development RMSE 13.585; the grid spans 13.585–13.771 |
| Calibration `ei` | Margin = 2.021 + 0.950·x, σ = 13.54 |
| Calibration `team_rating` | Margin = 2.087 + 0.982·t, σ = 13.58 |
| Calibration `hca` | 2.111, σ = 14.51 |

## Evaluation folds, 2023–24 and 2024–25

The table covers 2,455 regular-season games and 166 playoff games. Margin errors are in points. Log loss and Brier score refer to the home win.

| Model | Reg. MAE | Reg. RMSE | Reg. log loss | Reg. Brier | Reg. accuracy | Playoff RMSE | Playoff log loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Home court only | 12.506 | 15.735 | 0.6897 | 0.2483 | 0.544 | 16.931 | 0.6817 |
| Team rating (ridge) | **11.017** | **14.091** | **0.6097** | **0.2113** | 0.655 | **16.135** | 0.6443 |
| EI, pregame minutes | 11.163 | 14.233 | 0.6149 | 0.2136 | 0.659 | 16.290 | 0.6331 |
| *EI, oracle minutes (diagnostic)* | *11.063* | *14.145* | *0.6060* | *0.2092* | *0.676* | *15.972* | *0.6185* |

**EI minus comparator, regular season (95% game-resampling / week-cluster intervals):**

| Comparator | Margin RMSE delta | Log-loss delta |
| --- | --- | --- |
| Team rating, pooled | **+0.142** [+0.018, +0.262] / [−0.021, +0.298] | +0.0052 [−0.0019, +0.0123] / [−0.0018, +0.0123] |
| Team rating, 2023–24 | +0.147 [−0.031, +0.342] | +0.0043 [−0.0052, +0.0143] |
| Team rating, 2024–25 | +0.136 [−0.041, +0.315] | +0.0061 [−0.0044, +0.0156] |
| Home court only, pooled | −1.502 [−1.717, −1.291] / [−1.724, −1.267] | −0.0748 [−0.0862, −0.0628] / [−0.0859, −0.0632] |

**Registered verdicts against the team rating:**
- **Margin RMSE: `ei_worse`.** The game interval excludes 0 and both seasons are positive. The week-cluster interval includes 0.
- **Log loss: inconclusive.**

In the playoffs, which are reported but not adjudicated, EI and the team rating are within noise. EI's playoff log loss is 0.6331 against 0.6443 (delta −0.0111 [−0.0371, +0.0145]).

## Calibration

- **Logistic recalibration slopes above 1 in evaluation.** `ei` is 1.23 and `team_rating` 1.16, so both calibrations are under-dispersed out of sample. Development slopes were 1.09 and 1.05.
- **Intercepts** are close to 0: −0.09 and −0.08.
- The private results hold ten-bin tables.

## Interpretation and hypotheses

- **Player ratings help, but don't win at game level.** Frozen player ratings plus a no-availability minutes projection clearly beat home court. They do not beat a daily-updated opponent-adjusted team rating at the game level.
- **Oracle minutes.** Perfect knowledge of who played and for how long recovers 0.09 RMSE of the 0.14 gap. That is not enough to overtake the team rating.
- **Inner folds.** The ordering reversed: EI 13.54 against 13.58 RMSE in sample. This is optimistic, since the EI penalties were chosen on those seasons.
- **Untested hypotheses for a later registered revision:**
  - EI ratings refresh only at M2's five cutoffs per season, while the team baseline updates daily.
  - The pace and calibration are season-agnostic.
  - The 10-game minutes window ignores injuries.

  None was tuned here.

## Coverage

- **Scored games:** 5,252 regular-season and playoff games in 2021–22 through 2024–25.
- **Excluded:** five 2024–25 games had no single home team (neutral sites, ADR-0017), and 314 had play-in, Cup final or preseason prefixes.
- **Opening-week fallback:** 63 team-games used previous-season minutes.
- **Roster heuristic:** it dropped 1,596 player-team projections.
- **Cold ratings:** no projected minutes fell on the cold rating. Every projected player had a snapshot row, either from the ratings design universe or with an SPM fallback prior inside it. Some of those rows were players not yet eligible at the snapshot cutoff, each carrying the cold total. Margins are unaffected, but the cold-minute share is understated. See the [as-of artifact note](expected-impact-v1.md#as-of-rating-artifact-135) (#135).

## Frozen for M7

The minutes rule, pace, calibrations, team baseline `(60, 4)` and metrics are frozen for the joint #42 registration. The negative team-level result is preserved. The private `predictions.csv` holds every game's frozen inputs and predictions.
