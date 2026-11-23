# Issue #4 rolling-origin evaluation contract

- **Date:** 2026-11-23
- **Status:** Evaluation design and fixtures independently reviewed. Ready for maintainer review.
- **Branch:** `codex/issue-4-evaluation-contract`, based on the merged data contract at `1ae2218`.
- **Commits:** `72d4f4a` (contract and fixtures), `2aa6286` (review corrections).
- **Issue and PR:** [Issue #4](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/4) and [PR #11](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/11).

## Results and decisions

- The [validation contract](../validation-strategy.md) sets history through 2022–23 for initial fitting, 2023–24 and 2024–25 for validation, and 2025–26 for the registered historical holdout. Same-day games are excluded from daily EPM inputs. Strict rolling origins use evidenced source availability, even within the declared date windows.
- The contract distinguishes retrospective, strict rolling and prospective evidence. It defines skill, player-impact and team comparators and independent basketball outcomes, and keeps permitted EPM agreement diagnostics outside any learning or selection loop.
- The [manifest contract](../run-manifest.md) separates frozen forecast artifacts from append-only scoring, with exact hashes, source views, fit lineage and pinned outcomes. The [decision record](../DECISIONS.md) explains the split and freeze policy.
- A cold GPT‑6.2 Astra review of GPT‑6.2 Sol's exact diff identified two gaps. Prospective receipts now commit the cohort and predictions, and wholly missed origins remain in coverage accounting. Forward stacking and calibration now require the parent fit used for each example to be eligible at that example's origin. Focused re-review closed both findings.

## Verification

| Check | Observed result |
| --- | --- |
| Ad hoc `.venv/bin/python` checks on the synthetic manifest pair | Validated split and cutoff consistency, artifact references, fit ancestry, coverage counts and actual SHA-256 of the linked forecast fixture. |
| Ad hoc negative examples | Rejected late source revisions and fit ancestors, cyclic dependencies, EPM inputs, unknown availability, late paper freezes, target deletion, omitted origins and in-sample parent fits for older training examples. |
| Local pytest, Ruff lint and formatting, mypy, Markdown links and `git diff --check` | Passed. Pytest ran the existing smoke test. [CI on the reviewed correction](https://github.com/andrewcukierwar/basketball-intelligence-lab/actions/runs/45198338231) |
| Independent review and re-review | Checked exact diffs `1ae2218..72d4f4a` and `72d4f4a..2aa6286`. The reviewer verified the manifest digest and reproduced the targeted counterexamples. No remaining blockers. |

## Next work

- [Issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5) owns acquisition rights, dated availability evidence, lineup/score reconciliation and real pilot coverage. The design and synthetic checks do not establish enough source history for a strict historical result.
- Implement the evaluator when the relevant data and models exist. Freeze the actual cohort, configuration, metrics and access log at registration. This run used the synthetic examples and public methodology sources.
