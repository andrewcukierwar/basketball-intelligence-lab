# Local origin refresh (#142)

`bil.refresh` builds one Expected Impact snapshot per origin date from pinned inputs. It is the first piece of the #43 local refresh. It is **replay-only**: it reads the pinned 2023–24 and 2024–25 inputs and refuses any origin outside those seasons or on/after 2025-07-01. Live capture, per-origin source revisions (#143), incremental checkpoints (#144) and failure drills (#145) are separate issues.

## Commands

```sh
uv run python -m bil.refresh build RAW PROCESSED ROOT --origin 2024-01-15 [--origin ...]
uv run python -m bil.refresh verify-frozen RAW PROCESSED ROOT
```

- **`build`** prints one JSON line per origin: `artifact_id`, `created` and `path`.
- **`verify-frozen`** refreshes the #36 block cutoffs and compares the results with the published `issue-36-v1` ratings.
- **`ROOT`** must be under `data/` (for example `data/interim/refresh-<run>`), so artifacts are never committed.

## What one refresh does

The model is the #36 configuration:

- the `W2` window and context offset;
- 8,000/8,000 penalties;
- the locked `final_contiguous_fit.json` SPM;
- box logs from the preceding and current season.

Every input is dated strictly before the origin. `expected_impact.prepare` raises otherwise.

The output is a #135 as-of rating artifact (`ratings.csv`, `ei-ratings-as-of-v2`) with a `manifest.json` recording:

- the input digests: row-set manifests, box-log pins, SPM fit, addendum;
- the parent IDs: SPM fit and penalty selection;
- the configuration;
- the snapshot ID, coverage and eligibility audit;
- the code commit and clean-tree flag, which are informational.

## Identity, idempotence and atomicity

- **Identity.** The artifact ID is the SHA-256 of the origin, input digests, parent IDs and configuration. The code commit is not part of it, so a code change that leaves outputs unchanged does not create a new artifact.
- **Idempotence.** If `ROOT/<origin>/<artifact_id>/` exists and its manifest and ratings digest agree, a rerun returns `created: false` without fitting or writing. If the directory exists but is inconsistent (missing manifest, other ID, ratings digest mismatch), the refresh refuses and does not overwrite.
- **Atomicity.** Writing happens in a dot-prefixed staging directory beside the target, then a single `rename` publishes it. An interrupted run removes its staging directory and leaves no artifact.

## Verification (2026-11-27)

`verify-frozen` reproduced all 10 #36 block snapshots of 2023–24 and 2024–25 with a maximum absolute rating gap of 0.0 against `issue-36-v1`. No v2 roster player was missing from the published export. Loading plus the 10 refreshes took 6.4 s. A rerun at 2023-12-01 was a no-op.
