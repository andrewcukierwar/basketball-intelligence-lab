# Retrained Skills SPM results

The registered #148 experiment improved on the applied-Skills version of Expected Impact. Its primary comparison with raw-box EI was inconclusive, so raw-box remains the baseline. All results are retrospective development evidence from already examined seasons. [Protocol](skills-spm-retraining-protocol.md) · [#148](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/148)

## Matched possession predictions

Lower deltas favor retraining. Each interval is a paired 95% game-cluster interval. Models used the same possession identities, context, window, ridge penalties and block calendar.

| Fold and season type | Possessions | Games | Δ MSE vs raw-box EI | Δ MSE vs applied-Skills EI |
| --- | ---: | ---: | ---: | ---: |
| 2021–23 regular season | 418,731 | 2,427 | +0.120 [−0.598, +0.812] | +0.028 [−0.419, +0.503] |
| 2021–23 playoffs | 28,351 | 171 | −1.443 [−3.329, +0.368] | −0.551 [−2.042, +0.838] |
| 2023–25 regular season | 418,479 | 2,423 | **−0.561 [−1.520, +0.331]** | −0.939 [−1.362, −0.505] |
| 2023–25 playoffs | 26,725 | 165 | +1.485 [−0.079, +2.877] | +1.334 [−0.032, +2.733] |

The primary raw-box delta was negative in both outer regular seasons (−0.819 and −0.299). The paired game interval crossed zero, as did the week interval [−1.524, +0.392]. The applied-Skills delta was also negative in both years (−0.910 and −0.969), and its pooled game and week intervals excluded zero. That descriptive contrast supports retraining when the inputs are shrunk Skills. It leaves the choice of raw-box EI unchanged. The outer playoff results are descriptive and favor neither retrained contrast under their game intervals.

## K0 agreement

The four chronological openings scored 1,829 player-seasons from 681 distinct players. Of these, 254 used cold intercepts. On offense, Full improved over both Zero and One-stat under the #120 paired rule. Defense did not meet that rule. Total is secondary. The units are points per 100 possessions.

| Fit or contrast | Offense | Defense | Total |
| --- | ---: | ---: | ---: |
| Full RMSE | 1.511 | 0.943 | 1.806 |
| Mean RMSE | 1.587 | 0.945 | 1.914 |
| Zero RMSE | 1.631 | 0.947 | 1.964 |
| One-stat RMSE | 1.549 | 0.938 | 1.871 |
| Full − Zero RMSE, paired player interval | −0.120 [−0.161, −0.075] | −0.003 [−0.022, +0.015] | −0.158 [−0.205, −0.109] |
| Full − One-stat RMSE, paired player interval | −0.037 [−0.068, −0.004] | +0.005 [−0.010, +0.020] | −0.065 [−0.104, −0.025] |

| Fit | Offense MAE / bias | Defense MAE / bias | Total MAE / bias |
| --- | ---: | ---: | ---: |
| Full | 1.203 / +0.218 | 0.740 / +0.015 | 1.443 / +0.234 |
| Mean | 1.274 / +0.146 | 0.740 / +0.006 | 1.527 / +0.152 |
| Zero | 1.322 / +0.404 | 0.743 / +0.061 | 1.579 / +0.465 |
| One-stat | 1.238 / +0.147 | 0.737 / +0.011 | 1.484 / +0.157 |

## Fit and run evidence

The five SPM origins close the 2018–19 through 2022–23 seasons on the #28 calendar. The final fit uses 2,276 joined player-seasons, with 447, 436, 459, 478 and 456 by target season. Each fit records its frozen target hashes, box pins, per-season feature cutoff and Skills parent ID. The old 2017–18 box snapshot supplies Skills history only. The K0 scorer uses the registered frozen contiguous labels, and the possession scorer pairs directly against both archived #125 prediction arrays.

Run `bil.models.spm_skills` from a clean checkout with the committed protocol digest. The registered run took 343.9 s and peaked at 2,742.6 MiB. Its local commit was `8fe3528`, with the same Git tree as PR #153's preregistered commit `a8c6f16`. Private `issue-148-v1` artifacts contain all fit IDs, K0 slices, per-block possession scores, cold and exposure slices, and the two matched prediction arrays. They remain in local processed storage. [PR #153](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/153)
