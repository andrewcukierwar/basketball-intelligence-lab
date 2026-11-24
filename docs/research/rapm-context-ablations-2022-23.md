# Context ablations of the zero-prior RAPM baseline (2022–23)

[Issue #24](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/24) tests home court, pre-possession score and time, fitted control against eligible offset, and exposure weighting. Each is tested one at a time against the zero-context #23 fit. The report also delivers the context-only comparator from [#77](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/77).

**Provenance.** The [protocol](rapm-context-protocol.md) was committed (`1d6a885`, SHA-256 `e4e9143d…c4b5f`) before the runner and tests (`9ad75e2`). The run happened once, from a clean working tree at `9ad75e2`. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). Player-level estimates are only in the private output directory `issue-24-v1`. This report contains aggregates.

**Evidence tier: `retrospective_capture_bound`.** The run is a chronological replay of stable-lineup possessions with realized lineups. It is not a pregame forecast or a strict rolling-origin backtest. Only 2022–23 was read. No 2023–24, 2024–25 or 2025–26 data and no EPM value were read or used.

| Claim | Label |
| --- | --- |
| EPM adjusts its RAPM for home court and score state ("rubber band") | **Documented** ([EPM-U08](epm-uncertainties.md), [methodology](epm-methodology.md)) |
| The column definitions, offset construction, late-blowout rule and verdict rule | **Original** BIL choices. They do not reconstruct EPM's unpublished formulas. |
| Every number below | **Experimental**, one development season, retrospective |
| Interpretations marked "Inferred" | **Inferred** |

## Result in one paragraph

Pre-possession **time** and **score** terms improve held-out possession scoring over the zero-context baseline. **Home court** and **late-blowout weighting** do not, measurably. All four context terms together (HST) cut held-out MSE by 32.3 (95% interval −39.0 to −25.4) in (points per 100)², on top of the −14.1 that player RAPM gains over the league mean. That is more than twice the player gain. Most of it comes from one time column: possessions that start with 24 seconds or less left in a period score about 30 points per 100 less. About 80% of that gain comes from run-out/no-action possessions that score exactly 0, mostly starting on the `period_end` event itself, which the #59 row set keeps (see the decomposition below). It is therefore largely a consequence of how possessions are defined, not evidence that game context outpredicts players. Fitted control and the eligible offset are indistinguishable on held-out data. The **context-only comparator** (no players) beats the league mean by 30.5 (−37.2 to −23.8), which is also more than player RAPM's 14.1. On the playoff check fold, time and HST again help, while home and score alone are null. The score term helps per possession but worsens team-game totals.

## Timing verification

Every covariate comes from pilot events sequenced strictly before the possession's first event (protocol). The audit on the pinned ledgers:

| Check | Count |
| --- | ---: |
| The possession's own control points sequenced before its start (would leak the outcome; the run aborts if nonzero) | 0 |
| The event-ledger and score-allocation-ledger pre-possession scores disagree (run aborts if nonzero) | 0 |
| The possession's own points sequenced at or after its end (only later possessions' state affected) | 0 |
| The prior-event clock is later than the possession's first-event clock | 0 |
| The clock is clamped to the period start | 0 |
| Possessions with no prior event (each game's first eligible possession, scored 0–0 at 0:00) | 1,291 |

Synthetic tests check that rewriting every event at or after a possession's start leaves its covariates unchanged. They also check that an own-points leak placed before the start is detected.

## Strata and skipped strata

| Stratum | Regular season | Playoffs |
| --- | ---: | ---: |
| Possessions (games) | 209,942 (1,208) | 14,097 (84) |
| Late blowout (period ≥ 4, pre-possession margin ≥ 20 either way) | 8,281 | 654 |
| Offense at home | 105,066 | 7,047 |
| Overtime | 1,524 | 67 |
| **Neutral-court flagged** | **0** | **0** |

**The neutral-court stratum is skipped.** The pinned pilot's `game.neutral_site` field is null for all games, so no possession can be identified as neutral, and every game is coded by its nominal home team. It is **Inferred**, and not verified in the pinned inputs, that 2022–23 had two regular-season international games at neutral venues. They are games `0022200439` (2022-12-17) and `0022200678` (2023-01-19), 346 model possessions, and both are coded as home games here. The protocol adds no external neutral-site list. In held-out scoring, the pooled R1–R4 late-blowout stratum has 5,486 possessions from 243 games, and the playoff late-blowout stratum has 654 possessions from 28 games.

## Held-out results (pooled R1–R4, the primary metric)

The delta is MSE(variant) − MSE(C0) on the same 136,730 possessions from 786 games. Negative is better. Intervals are 95% game-clustered bootstrap (2,000 resamples, seed 2023). $\lambda$ = 4,000 for every variant, as in #23, and it was not re-tuned. C0 reproduces #23 exactly (MSE 14,095.4, −14.09 against the league mean). On every fold the zero-context solver matched the #23 solver to 9e-14.

| Variant | What changes | Δ vs C0 | 95% interval | Verdict | Δ vs C0, P1 playoffs (interval) |
| --- | --- | ---: | --- | --- | --- |
| `H_fit` | home, fitted | −0.39 | −1.94 to +1.15 | inconclusive | −2.5 (−6.4 to +1.3) |
| `H_off` | home, eligible offset | −0.33 | −1.93 to +1.27 | inconclusive | −2.6 (−6.6 to +1.4) |
| `S_fit` | clipped margin, fitted | −6.32 | −9.64 to −3.02 | supported | −1.5 (−12.4 to +11.8) |
| `S_off` | clipped margin, offset | −6.36 | −8.74 to −4.00 | supported | −2.9 (−9.9 to +5.6) |
| `Sbin_fit` | margin bins, fitted | −5.77 | −9.07 to −2.31 | supported | −2.1 (−13.6 to +10.7) |
| `Slate_fit` | margin + margin × late, fitted | −5.95 | −9.42 to −2.60 | supported | −1.9 (−13.1 to +11.4) |
| `T_fit` | period, end-of-period, final two minutes, fitted | −25.69 | −31.47 to −19.72 | supported | −40.9 (−59.3 to −20.5) |
| `T_off` | same, offset | −25.68 | −31.59 to −19.67 | supported | −41.0 (−59.6 to −20.2) |
| `HST_fit` | home + score + time, fitted | −32.25 | −39.03 to −25.39 | supported | −47.2 (−68.0 to −27.1) |
| `HST_off` | same, offset | −32.68 | −39.11 to −26.07 | supported | −48.1 (−67.3 to −28.3) |
| `W_half` | late-blowout fit weight 0.5, mean-1 normalized | +0.00 | −0.29 to +0.30 | rejected | +0.2 (−0.5 to +0.8) |
| `W_drop` | late blowouts excluded from fit | +0.17 | −0.44 to +0.78 | rejected | +0.4 (−0.9 to +1.7) |

Verdict rule (frozen): **supported** if the interval is wholly below 0, **rejected** if the point delta is ≥ 0, otherwise **inconclusive**. P1 does not change a verdict. Pooled MSE: C0 14,095.4, league 14,109.5, HST_fit 14,063.1, T_fit 14,069.7, S_fit 14,089.0. The possession RMSE is still about 118.6, so every gain is small relative to possession noise.

**By fold** (Δ vs C0 for the fitted variants, R1 / R2 / R3 / R4): H −0.3 / −2.5 / −2.4 / **+3.6** (+0.2 to +7.0); S −4.7 / −10.2 / −7.9 / −2.5; T −31.5 / −14.9 / −28.9 / −28.7; HST −35.7 / −28.9 / −41.3 / −24.4; W_half and W_drop within ±0.3 on every fold. Time is consistent. The score term is negative on every fold, but R1 and R4 intervals include 0. Home hurt on R4 alone.

### Fitted control versus eligible offset

Fitted minus offset, paired on the same possessions:

| Family | Pooled R1–R4 | P1 |
| --- | --- | --- |
| H | −0.06 (−0.11 to −0.01) | +0.04 (−0.10 to +0.20) |
| S | +0.04 (−0.92 to +1.00) | +1.34 (−2.58 to +6.02) |
| T | −0.01 (−0.39 to +0.39) | +0.02 (−1.18 to +1.17) |
| HST | +0.43 (−0.65 to +1.52) | +0.93 (−3.23 to +5.71) |

The held-out evidence does not separate the two treatments. The only interval excluding 0, H at −0.06, is negligible. They do differ in coefficients. The fitted score slope is −0.30 per point of margin against −0.20 for the context-only offset, at every fold and in the final fit. Interpretation (**Inferred**): a context-only fit confounds a lead with the leading team's quality, which attenuates the rubber-band slope, and joint fitting with player terms removes part of that confounding. Synthetic tests confirm both properties. The two treatments agree exactly when context is balanced across lineups, and fitted control recovers a confounded effect that an offset misstates.

### Late blowouts and the playoffs

On held-out late-blowout possessions (regular season), time is the main gain: T_fit −116 (−143 to −91) and HST_fit −153 (−195 to −111). Score helps too: S_fit −37 (−71 to −3). Weighting late blowouts down or out changes nothing on those possessions (W_half −0.5, −3.0 to +2.1; W_drop −0.7, −6.1 to +4.7). On non-blowout possessions, S_fit is −5.0 (−8.4 to −1.4) and T_fit −21.9 (−27.9 to −15.7). In the playoff late-blowout stratum (654 possessions, 28 games), only the time-bearing variants have intervals below 0. Score and home alone are null in the playoffs.

### Team-game aggregates (descriptive)

| Model | Regular-season team-game RMSE (points) | Playoffs |
| --- | ---: | ---: |
| League | 10.69 | 10.32 |
| C0 | 10.45 | 10.42 |
| H_fit | 10.43 | 10.33 |
| T_fit | 10.44 | 10.46 |
| S_fit / S_off | 11.44 / 11.15 | 11.50 / 11.12 |
| HST_fit / HST_off | 11.54 / 11.24 | 11.46 / 11.08 |

Score terms **worsen** summed team-game predictions while improving per-possession scoring. Interpretation (**Inferred**): within one game, the team that trails is usually the one realizing fewer points, so a term that predicts trailing teams score more pushes each team's summed prediction away from its realized total. Using realized pre-possession margins in a game aggregate is itself in-game information, so this aggregate is a diagnostic, not a pregame claim.

## Context-only comparator (#77)

These models use no players: intercept and context columns by least squares on each fold's fit rows. The delta is against the league mean, pooled R1–R4.

| Comparator | Δ vs league | 95% interval | P1 Δ vs league (interval) |
| --- | ---: | --- | --- |
| C0, player RAPM with no context (reference) | −14.09 | −18.33 to −9.85 | −8.0 (−24.0 to +7.5) |
| CTX home | −0.44 | −2.07 to +1.18 | −2.9 (−7.0 to +1.0) |
| CTX score (linear) | −3.32 | −5.92 to −0.66 | −2.2 (−8.8 to +5.3) |
| CTX score (binned) | −3.40 | −6.21 to −0.52 | −3.9 (−11.5 to +3.9) |
| CTX score × late | −2.87 | −5.69 to −0.06 | −2.6 (−9.3 to +5.0) |
| CTX time | −26.86 | −32.68 to −20.97 | −42.7 (−61.7 to −21.5) |
| CTX home + score + time | −30.50 | −37.16 to −23.78 | −49.5 (−69.1 to −29.0) |

Under the current #59 possession definition, a context-only model with time terms beats zero-context player RAPM on held-out possessions. This comparison depends on that definition. Most of the time gain comes from predictable zero-point no-action possessions, so it should not be read as context outpredicting players until #82 settles their eligibility. Player RAPM adds a further −15.8 on top of context (HST_fit −46.3 against the league mean). The player gain should therefore be read against a context comparator, not only against the league mean.

Final context-only coefficients on all 224,039 rows, in points per 100 with game-clustered 95% intervals:
- Home: +1.24 (0.81 to 1.65) per side, so about 2.5 between home and away offense.
- Clipped margin: −0.20 (−0.25 to −0.15) per point.
- End of period: −30.5 (−33.4 to −27.7).
- Final two minutes: −3.8 (−6.3 to −1.3).
- Period 3: +1.8 (0.5 to 3.1).
- Period 2, period 4 and overtime intervals include 0.
- Margin bins (reference −2 to +2): ≥ +15 is −5.1 (−7.1 to −3.1), +8 to +14 is −4.5 (−6.2 to −2.8), ≤ −15 is +2.0 (0.1 to 3.8). The middle bins include 0.

## Fit and coefficient sensitivity (final in-sample fits, descriptive)

Each fit uses all rows at $\lambda$ = 4,000. Shifts are against C0, for the 541 players in both fits (539 for W_drop).

| Variant | In-sample MSE Δ vs C0 | Context coefficients (fitted) | Total RMS shift | Total max shift | Total correlation |
| --- | ---: | --- | ---: | ---: | ---: |
| H_fit | −1.3 | home +1.19 | 0.066 | 0.25 | 0.999 |
| S_fit | −9.2 | margin −0.296 | 0.231 | 0.70 | 0.989 |
| Sbin_fit | −9.5 | ≤ −15: +5.0; ≥ +15: −5.3 | 0.222 | 0.66 | 0.990 |
| Slate_fit | −9.4 | margin −0.265, × late −0.086 | 0.237 | 0.77 | 0.988 |
| T_fit | −26.9 | end of period −30.2, final 2 min −3.9 | 0.038 | 0.16 | 1.000 |
| HST_fit | −38.5 | home +1.60, margin −0.32, end of period −30.2 | 0.257 | 0.81 | 0.986 |
| HST_off | −36.9 | (offset) home +1.52, margin −0.22 | 0.186 | 0.61 | 0.992 |
| W_half | +0.3 | — | 0.129 | 0.60 | 0.995 |
| W_drop | +1.4 | — | 0.267 | 1.32 | 0.978 |

Player totals move little. The largest RMS shift (0.27, W_drop) is below the 0.37 shift from dropping flagged games in #23, and well inside the noise implied by the #23 split-half correlation of 0.38. Score terms move players most, consistent with players' minutes depending on score state (**Inferred**). Time terms shift offense and defense separately (RMS 0.09 each) but leave totals almost unchanged. The fitted context coefficients are stable across folds:
- Home: +1.68, +1.41, +1.46, +1.46 for R1–R4, then +1.16 at P1 and +1.19 in the final fit.
- Margin slope: −0.29 to −0.31 at every fold.
- End of period: −28.9 to −30.0.
- Overtime: −3.9 to −9.0. Its context-only interval includes 0.

## Choices rejected or not supported by this evidence

- **Late-blowout down-weighting (W_half) and exclusion (W_drop):** rejected. There is no held-out gain overall, in blowouts or in the playoffs, and W_drop moves player totals more than any other variant.
- **Home court as a separate term:** inconclusive. The coefficient is clearly positive, but it does not improve held-out scoring, and it hurt on R4. It is not rejected as a control, because its cost is negligible and EPM documents it. A held-out gain is not shown.
- **Nonlinear score (bins) and the late score interaction:** no gain over the linear clipped margin. Point deltas are −5.8 and −6.0 against −6.3, and their intervals overlap almost entirely. A direct paired test between them was not part of the protocol. Prefer the one-parameter form (**Inferred** from the overlap).
- **Fitted control versus eligible offset:** held-out evidence does not choose between them. The coefficients differ for score, and the offset gives better team-game RMSE. The choice stays open for EPM-U08.
- **Score terms for game-total use:** score terms are not supported where team-game aggregates matter, because they worsen team-game RMSE.

## Limitations

- One development season, with retrospective, capture-bound data and realized lineups. Nothing here is confirmatory, and no verdict admits a context family into a reference specification without a registered outer-fold protocol.
- Twelve variants and six comparators were scored on the same folds without multiplicity adjustment. Bootstrap intervals cluster by game but ignore dependence across folds.
- **End-of-period decomposition (independent review audit, Original).** 6,028 eligible possessions (2.69%) start with 24 s or less left. They score 80.2 points per 100, against 112.0 for all others.
  - 996 of them (16.5%) are run-out/no-action possessions: no shot, free throw, turnover, foul or violation, and exactly 0 points.
    - 962 start on the `period_end` event itself.
    - 706 are in the 4th quarter, with median absolute margin 13.
  - Separately, 853 of the 6,028 are game-final possessions. They average 0.6 points per 100, but they are not a subset of the no-action group.
  - The other 5,032 score 96.1 per 100.
  - An end-of-period dummy alone gives an in-sample MSE gain of 26.5, close to the held-out time gain of 25.7. With the no-action possessions removed, it falls to 5.6.
  - No parser artifact was found. Possessions tile the event stream exactly, with no duplicate or zero-length possessions, and the covariates are pre-possession.
  - The effect is real game structure combined with a possession-definition choice. Whether no-action possessions should be eligible was decided in #82 ([ADR-0019](../DECISIONS.md)): they stay, because a `period_end` start does not show a pseudo-possession. The [report](rapm-no-action-2022-23.md) gives the audit and the sensitivity runs that drop them.
- The 0–2 s bucket (149 possessions, about 207 points per 100) is probably intentional-foul free throws (**Inferred**).
- No neutral-court evidence, and multiple-lineup possessions (12.6%) are excluded as in #23.
- The penalty was fixed at the #23 value. A context-aware $\lambda$ or separate role penalties (#77) were not searched.

## Reproduce

```sh
uv sync --locked --extra dev --extra pilot --extra rapm
uv run python -m bil.models.rapm.context_ablation \
  data/processed/2022-23/issue-59-v1 data/processed/2022-23/issue-19-v6 \
  data/processed/2022-23/issue-24-v1
```

The runner verifies the #59 and pilot pins, refuses an existing output directory and writes `results.json` (aggregates and per-fit LSQR diagnostics), `manifest.json` and the private `player_estimates.csv`. Run facts:
- 83 fits, all LSQR stop 2, 18 to 28 iterations, maximum condition estimate 34.5.
- 24.7 s of fitting and 33.8 s wall time, with 1,050 MiB peak resident memory.
- Python 3.14.3, NumPy 2.5.5, SciPy 1.18.1 and DuckDB 2.0.1.
- Output SHA-256: results.json `787fce59…7967`, player_estimates.csv `a4fcd366…99d2`.
