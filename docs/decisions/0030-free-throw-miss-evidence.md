# ADR-0030 — Infer missing free-throw miss markers with box evidence

- **Date** 2026-11-24
- **Status** Accepted for the opt-in pilot variant.
- **Decision** Use the numbered attempt, score transitions, immediate same-clock team rebound and exact shooter box totals to annotate a missing parser miss marker on a retry. Require the parser to link the identified rebound to that shot. Retain raw source rows, the default behavior and every reconciliation check.
- **Evidence** Independent review reproduced an ambiguity in the first score test. The final rule requires an observed one-point change for every corroborating make and rejects competing missed shots. The [verification report](../research/missing-free-throw-miss.md) records rebuilt season results.
- **Consequences** Recovered games are a separate verification stratum. Eligibility of a versioned build leaves canonical dataset selection and the frozen SPM target window to their existing decisions.
- **Links** [Issue #115](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/115), [Pilot guide](../data-pilot.md), [ADR-0022 and ADR-0028](../DECISIONS.md)
