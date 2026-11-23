# M0 EPM methodology and source audit

- **Date:** 2026-11-23
- **Status:** Research changes independently reviewed and available for maintainer review.
- **Scope:** Local and CI verification, primary-source methodology audit and historical input audit for issues #1 and #2.
- **Branch:** `codex/m0-epm-research`
- **Commits:** `7485714` (development lock), `bd7e67c` (research audit), `a716707` (reconciliation correction)
- **Pull request:** [PR #8](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/8)

## Results

- The [methodology specification](../research/epm-methodology.md) uses the October 2026 Dunks & Threes description as the reference. It records the separate SPM label windows, the distinction between per-stat skill decay and final RAPM decay, same-date game exclusion, and the differences between Expected and Actual EPM. The [uncertainty register](../research/epm-uncertainties.md) assigns later validation work to 14 open questions.
- The [source audit](../data-sources.md) distinguishes published asset availability, field and game completeness, access, and usage rights. [ADR-0004](../DECISIONS.md#adr-0004--202223-source-and-reconciliation-candidates) provisionally selects Bentes 2022–23 event files and identifies box-score, parser and event-feed comparisons. The pilot requires permitted inputs and actual reconciliation evidence.
- Independent review of `bd7e67c` found that the proposed `pbpstats` comparison mixed a JSON parser with archived CSV inputs. The reviewer confirmed that `a716707` resolved the documentation issue. For the pilot, test the native JSON on a sample from each season type and compare the pinned V3 CSVs separately.

## Verification

| Check | Observed result |
| --- | --- |
| Clean temporary environments using `uv sync --locked --extra dev --python 3.11` and `--python 3.12` on macOS arm64 | Resolved and installed from the existing lock under Python 3.11.17 and 3.12.13. The lock is now tracked. |
| `pytest -q`, `ruff check .`, `ruff format --check .`, `mypy src` in each temporary environment | One smoke test passed on each interpreter. Ruff lint and formatting passed. Mypy reported success in seven source files. |
| Local environment recovery | The first attempt to switch the existing `.venv` to Python 3.12 stopped while replacing it. Restored it with Python 3.14.3 and the locked dependencies. The smoke test passed there. The independent reviewer also ran Ruff, mypy and pytest on 3.14.3. |
| GitHub Actions on `main` | Install, Ruff, mypy and pytest passed at `9660792` on Ubuntu/Python 3.12. CI installs extras with pip. An earlier scaffold commit failed with pytest exit 5 because it had no tests. [Baseline run](https://github.com/andrewcukierwar/basketball-intelligence-lab/actions/runs/45115147155) |
| GitHub Actions on the reviewed research commit | PR CI passed at `a716707`. [PR run](https://github.com/andrewcukierwar/basketball-intelligence-lab/actions/runs/45116832287) |
| Public GitHub asset metadata | Checked contiguous filenames by season and type for the audited archives, then checked documented sizes and digests or blob IDs for ten pilot files. Release checks used the GitHub releases-by-tag endpoint and the Shufinskiy checks used the pinned recursive Git tree. [Pilot assets](../data-sources.md#pilot-asset-identifiers-and-observed-metadata) |
| `git diff --check` and internal Markdown link checks | Passed. |

## Next work

- [Issue #1](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/1) is linked for closure on merge. [Issue #2](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/2) retains source rights, game-level and tracking coverage, and parser compatibility questions. The audit acquired public documentation and file metadata only.
- Use the audit findings for canonical contracts in [issue #3](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/3) and the rolling-origin contract in [issue #4](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/4). Use permitted inputs for the one-season pilot in [issue #5](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/5). The pilot must pass its data-quality gate before the RAPM baseline.
