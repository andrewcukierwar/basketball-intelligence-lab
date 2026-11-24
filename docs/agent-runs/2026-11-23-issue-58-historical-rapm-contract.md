# Issue #58 historical RAPM row contract

- **Status:** Specification and synthetic fixture independently reviewed.
- **Related:** [#58](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/58), parent [#20](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/20), builder [#59](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/59).
- **Branch:** `codex/issue-58-historical-rapm-contract` from main at `d3d01f3`.

The [contract](../research/rapm-historical-rows.md) defines exposure, lineup and scoring assignment, exclusions, timing provenance, manifest identity and reconciliation. The first baseline keeps actual stable-lineup possessions with unit exposure. It preserves control assignments and accounts for other points in the score reconciliation ledger.

Verified the fixture's six dispositions, three model rows and complete score and team exposure totals with an independent local calculation. Ran a DuckDB exploratory sequence-interval join on the private #19 pilot. It measured 224,039 stable-lineup and 32,417 multiple-lineup possessions among 256,456 accepted opportunities. The groups differ by 27.02 assigned control points per 100. No data rows were added to Git.

An independent reviewer reproduced all fixture results and the season-type exposure profile. Clarified player-ID conversion at the estimator boundary and adjusted the fixture to exercise an exact lineup boundary.

Issue #59 implements the extractor, pins row artifacts and verifies the complete game, score and exposure identities. Model fitting and performance claims remain in downstream issues.
