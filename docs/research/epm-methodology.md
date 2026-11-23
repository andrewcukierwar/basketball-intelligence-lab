# EPM Methodology — Evidence and Replication Specification

**Purpose:** Track what is publicly documented about Taylor Snarr's modern Estimated Plus-Minus and map it to a reproducible independent implementation. Not a specification of private code.

**Primary source:** https://dunksandthrees.com/about/epm (reconfirm exact details and publication version before coding).

## Scope and terminology

- **Expected EPM:** Dynamic, career-informed estimate of current/future offensive and defensive player impact.
- **Actual EPM:** Retrospective season-specific impact measure, with a preseason prior that diminishes as season evidence accumulates.
- Units: offensive, defensive and total points per 100 possessions, with explicit centering and defensive signs.

## Documented building blocks

| Component | Publicly documented information | Our intended replication |
| --- | --- | --- |
| Historical RAPM | Adjusted offensive/defensive player on-court impact using regularization | Sparse multi-season RAPM on validated lineup/possession outcomes |
| Box-score SPM | Trained on multi-season RAPM; historical training approximately 2003–04 to 2022–23 | Build historical player statistical panels with independent long-term RAPM targets |
| Defensive tracking SPM | Uses player-tracking data; training approximately 2017–18 to 2022–23 | Audit public tracking aggregates; quantify missing features and periods |
| Estimated Skills | Career history, stat-specific exponential decay and optimized parameters including Differential Evolution | Independent player-skill prediction engine, trained on future statistical outcomes |
| Context | Home court, score/rubber-band effects and skill-projection factors such as age, team/opponent strength, seasonality and rest | Separate documented from speculative implementations; ablate each adjustment |
| Final EPM | Prior-informed RAPM using SPM statistical prior and decayed historical possessions | Center regularized coefficient estimates on SPM-based priors |
| Historical scale | 2001–02 onward; about 6.2M possessions through 2025–26 cited in methodology | Start one validated season, then build historical coverage |

## Core conceptual model

A ridge RAPM estimate is the weighted regression of possession outcomes on on-court participants with regularization.

An SPM prior predicts a player's statistical impact from individually estimated skills.

A conceptual prior-centered objective is:

    min_beta (y - X beta)' W (y - X beta)
             + (beta - mu)' Lambda (beta - mu)

where mu is the SPM prior. This is a **research reconstruction**, not the creator's full unpublished production formula.

## Specific research requirements

1. Define possession response, offset/baseline, coefficient identification, player signs and exposure weighting.
2. Determine whether long-term SPM training targets and final RAPM use different dates/windows.
3. Investigate distinct offensive and defensive prior construction.
4. Evaluate feature quality, tracking missingness and sample-size reliability.
5. Implement age-of-observation weighting without future-data leakage.
6. Reproduce stat-specific next-game skill forecasting and optimize using out-of-time skill outcomes.
7. Keep actual-season ratings separate from forward-looking expected ratings.
8. Record documented/inferred/experimental/original choices in epm-uncertainties.md.

## Fidelity versus correctness

**Correctness:** Synthetic effect recovery, lineups, score reconciliation, sparse solver equivalence, chronological prediction and independent holdouts.

**Fidelity:** Compare original EPM offense/defense/total values only where permitted, and only for diagnosis. Never fit models or tune parameters to the original outputs.

Historical EPM API values from a later rebuilt methodology should not be misrepresented as exact as-of-date forecasts produced by an older version.

## Reading list

- [Dunks & Threes EPM methodology](https://dunksandthrees.com/about/epm)
- [EPM metric comparison](https://dunksandthrees.com/blog/metric-comparison)
- [Engelmann RAPM](https://github.com/jerryengelmann/RAPM)
- [OpenRAPM](https://github.com/bbstats/openrapm)
- [Basketball-Reference BPM methodology](https://www.basketball-reference.com/about/bpm2.html)

**Next action:** Create a source-by-source evidence matrix with exact quotes/section references, date, model component and confidence. Do not fill gaps by claiming undocumented facts.