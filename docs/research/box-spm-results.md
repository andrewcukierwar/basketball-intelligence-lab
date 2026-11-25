# Box-score SPM development results

The frozen [#120 protocol](box-spm-protocol.md) was evaluated for [#121](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/121) and [#30](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/30). The evidence is a partial-history methodology replication under retrospective capture bounds. Strict source evidence and prospective evidence have zero eligible observations. The outer and confirmatory seasons remain unopened.

## Chronological K0 agreement

The primary contiguous comparison covers 1,829 player-seasons and 681 players in 2019–20 through 2022–23. Errors are per 100 possessions, with positive defense denoting points prevented.

| Candidate | Offense RMSE | Defense RMSE | Total RMSE |
| --- | ---: | ---: | ---: |
| Zero | 1.631 | 0.947 | 1.964 |
| One-stat | 1.546 | 0.945 | 1.878 |
| Full | 1.537 | 0.952 | 1.837 |

Full improved offense against Zero by −0.094 RMSE (95% paired interval [−0.134, −0.048]). Its offensive delta against One-stat was −0.009 (interval [−0.040, 0.021]). Defense deltas were +0.005 against Zero (interval [−0.015, 0.028]) and +0.007 against One-stat (interval [−0.008, 0.021]). Neither side met the registered criterion of improving against both controls. The total was descriptively better than both controls. This is agreement with a noisy K0 label.

The first season of each reference lacked earlier calibration labels. Four contiguous and nine extended folds were scored. Cold starts accounted for 284 contiguous K0 player-seasons. The extended 2015–16 and 2018–19 opening artifacts had no eligible immediately preceding season, so all 425 and 447 scored players respectively used the frozen cold fallback. The private aggregate reports same-truth cross-reference comparisons, regular-season and playoff results, separate era and verification groups, age, minutes, shot-volume role, exposure, calibration coverage and target changes. Roster position was unavailable.

## Realized-lineup scoring

There were 842,466 possessions in the four common modern folds. Context plus Full lowered possession MSE from 1.410245 to 1.409115 points per possession squared. The paired delta was −0.001130 (95% week-block interval [−0.001231, −0.001029]). This met the registered on-court criterion. The delta against standalone RAPM was −0.002699 (interval [−0.003006, −0.002419]) and against fixed-offset context RAPM was −0.000024 (interval [−0.000175, 0.000123]). The offense-only contribution accounted for most of the possession-level improvement. Standalone RAPM achieved lower represented game-margin RMSE than context plus Full in each contiguous fold. The realized-lineup diagnostic uses the ten players actually on court and pre-possession context.

The results retain dated player-side intercept fallbacks by candidate and possession counts for missing minutes history. Possession counts attributable specifically to all-selected-inputs-missing intercept fallbacks among players with positive-minute history are not included. The #28 verification groups are retained by name.

## Freeze and provenance

The corrected run wrote `data/processed/spm/issue-30-v2` on clean commit `b2fd49df5804dd66f6136273714f4501e71a188d` in 23.38 s with 1.50 GiB peak RSS (macOS bytes). The manifest records and pins 54 files. Its SHA-256 is `376d89ceb41ca8b90b1e36b3c6a6ad5d9ea09c32acd4e78114c16ec73f96786d`. The aggregate `results.json` SHA-256 is `30881ae38ee2e2587ecfab6d2f1d2f0abb9e3c42f8566485668e6dddf35754f3`. Protocol SHA-256 is `8f121cd9d828560d8198bb3360061efbea9b6361fdcfaa4dfda4091e83a03265`.

The final contiguous coefficient bundle is `final_contiguous_fit.json`, origin `contiguous@2023-06-13`, SHA-256 `1025774a8d327cbb25f6c284b49b9cbd80406e88a0406108a0877bf77b1edd90`. It is available as a provisional candidate for a registered downstream comparison. The mixed side-level evidence should govern any decision about treating it as a validated prior for [#35](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/35).

Independent review rejected v1 because its opening player keys came from later realized lineups. For v2, opening keys come from strictly earlier positive-minute appearances. The scorer applies the frozen cold fallback after opening artifacts are written. A synthetic test changes later lineup IDs and checks byte-identical opening artifacts. The protocol and candidate specifications were unchanged. The initial v1 directory was preserved privately as a failed acceptance artifact.
