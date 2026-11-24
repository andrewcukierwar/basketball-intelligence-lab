# ADR-0014 — Center RAPM deviations on the supplied role priors

- **Date:** 2026-11-23
- **Status:** Accepted for the synthetic reference.
- **Context:** Separate offense and defense priors may use different levels and have missing player entries. The free intercept still absorbs uniform shifts in either role.
- **Decision:** Use a positive penalty per role on the distance from the supplied prior in points per 100 possessions. Keep the intercept unpenalized and set each role's mean deviation from its prior to zero. A missing player-role prior defaults to zero. An unobserved role for a player in the fit retains its prior. The fit universe is the union of players appearing in at least one input lineup.
- **Evidence:** An independently assembled weighted dense oracle verifies coefficients, fitted rates and the role centering convention. Shared penalties and zero prior values recover ADR-0012 exactly on the synthetic fixture.
- **Consequences:** Uniform input prior levels move the intercept and the corresponding coefficient levels. Supply priors expressed in the documented sign and unit convention. Prior construction, chronological eligibility and decay are separate modeling decisions.
- **Links:** [Prior-centered RAPM specification](../research/rapm-prior-centered.md), [Issue #61](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/61)
