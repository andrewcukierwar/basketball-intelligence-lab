# ADR-0015 — Strict as-of clock and unnormalized exponential decay for dated RAPM

- **Date:** 2026-11-23
- **Status:** Accepted for the synthetic reference.
- **Context:** Historical fits need a leakage-safe cutoff and optional recency weighting on top of the prior-centered solver. EPM's decay form is not public.
- **Decision:** Compare Eastern calendar dates and keep only rows with `played_date < as_of`, using the evaluation contract's rule. Age is whole days. Multiply each supplied base weight by `0.5 ** (age / half_life_days)`, with `None` for no decay. Do not renormalize weights or rescale penalties. A missing or non-`date` played date, or an invalid or underflowing weight, raises. Excluded rows never reach the design, weights or player universe.
- **Evidence:** An independent dense normal-equation oracle agrees within `1e-8` for half-lives from 0.5 to 365 days and no decay, with the maximum observed delta near `6.5e-11`. Tests cover same-day and later exclusion, poison rows with unseen players, missing dates and no-decay equivalence.
- **Consequences:** Decay raises the effective penalty, so half-life and penalties must be chosen together. The half-life remains a free parameter to select without EPM outputs. Any future cache must be keyed by `as_of` and the eligible rows.
- **Links:** [Dated RAPM specification](../research/rapm-dated-weights.md), [Issue #64](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/64), [Parent #34](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/34)
