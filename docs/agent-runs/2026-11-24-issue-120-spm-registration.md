# Issue #120 box-score SPM registration

- **Status** Frozen protocol independently cleared before fitting.
- **Issue** [#120](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/120), under #30. Apply the protocol in #121.
- **Protocol identity** Commit `1df64caccc70b9f19e15943edc5ccc6f194d33dc`, SHA-256 `8f121cd9d828560d8198bb3360061efbea9b6361fdcfaa4dfda4091e83a03265`.

The [protocol](../research/box-spm-protocol.md) freezes exposure-based reliability weights, the one-sided and early-era sensitivities, chronological fits, baselines and outcome checks. Independent review identified an ambiguous context comparator and predictor boundary. The revised protocol uses M2's fixed context offset with a free RAPM intercept. Earlier box history supplies the player priors. The context model alone uses pre-possession context.

Captured ten digest-pinned historical SportsDataverse roster assets privately for scorer-only age strata. The recorded data uses English abbreviated-month birth dates. Same-season joins to positive-minute box IDs cover 477 of 606 in 2021–22 and 466 of 541 in 2022–23, with no conflicting birth dates. Keep unknown ages as a separate scoring stratum. Earlier shot volume supplies the registered role proxy.

Verified the #28 targets manifest and four named output digests, the protocol digest, all ten roster asset sizes and digests, and clean diff whitespace. An independent review cleared the exact methodological revision. No real fit or outcome inspection preceded the freeze. The base suite passed 408 tests with both private parser fixtures enabled.
