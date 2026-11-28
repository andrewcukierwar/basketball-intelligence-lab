# Expanded RAPM first historical contrast

[#182](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/182) scored the first [registered #168 comparison](expanded-rapm-target-protocol.md). Adding 2004–05 to the closing-2005–06 fit reduced pooled 2006–07 possession RMSE by 0.0202 points per 100. The change is small. The playoff interval includes zero. This is a retrospective diagnostic on realized lineups and earlier possession state.

## Matched outcomes

The expanded fit adds 203,465 past-season rows with positive K365 weight. Both arms use the same fitted common context, 401 eligible player IDs and identical stable-lineup opportunities. Future outcome data is projected out during prediction. The independently reviewed scorer separately verified the already frozen forecast receipt and exact game, stream and possession keys before opening its outcome vector. Intervals use 2,000 paired full-game bootstrap draws.

| Cohort | Games / possessions | Reference RMSE | Expanded RMSE | Δ RMSE (95%) | Δ MAE (95%) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pooled | 1,287 / 204,981 | 110.7518 | 110.7316 | −0.0202 [−0.0279, −0.0126] | −0.0234 [−0.0310, −0.0153] |
| Regular season | 1,209 / 193,042 | 110.7141 | 110.6931 | −0.0210 [−0.0288, −0.0129] | −0.0245 [−0.0326, −0.0164] |
| Playoffs | 78 / 11,939 | 111.3599 | 111.3534 | −0.0065 [−0.0340, +0.0214] | −0.0058 [−0.0360, +0.0256] |

We scored 1,209 of 1,230 expected regular-season games and 78 of 79 expected playoff games. In accepted games, 193,042 of 226,958 regular-season possessions and 11,939 of 14,232 playoff possessions were stable and modeled. The primary exclusions, regular/playoffs, were 30,886/2,098 mixed-lineup possessions, 2,968/192 parser exclusions, and 62/3 unresolved-control possessions. There were no additional registered #138 model-row exclusions for this season. Both arms used zero on 109,158 offense and 109,168 defense player slots lacking the common exposure minimum.

## Exact inputs and outputs

- The trainer ran from independently reviewed commit `1f5a674686cb65a3f58019074a7f43ab28e1dcd0`, with 205,753 reference and 409,218 expanded rows. The exact same-input expanded replay reproduced both target-season label digests and every array value. All fits converged. Peak RSS was 1,270 MiB and the runs took 1.78–3.67 seconds on the development host.
- The predictor and scorer ran from independently reviewed commit `1ce840ac72c4d0d56f07205e7914a3d3f543261e`. The private forecast receipt is `15d0548ea4d659bf52e4e5a7762651e23eab187db848de4b5047e2900687169d`. Forecast bytes SHA-256 `15f8870252bfbe92b883b5c82049b93161e9f22468e30a5328398411c8194cfc`. Outcome vector SHA-256 `0e0061b087b51619d09819c90cebf100f10b6ee7309ff2b9db6e963048e6d600`.
- Replaying the scorer generated private aggregate JSON with SHA-256 `a8c179469543f5014703939e31526e7c35367755c9051d100dfcbc1791c92131`. Files remain under `data/processed/rapm_targets/issue-168-first-origin-1f5a674/`. Use the prediction and scoring subcommands of `bil.models.rapm.expanded_score` and the exact receipt described above.

The remaining historical contrasts and modern negative controls are separate tests in #168. This single exposed-season result does not establish broad target reliability or downstream SPM or EI improvement.
