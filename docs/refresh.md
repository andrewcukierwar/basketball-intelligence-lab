# Local origin refresh (#142)

`bil.refresh` builds one Expected Impact snapshot per origin date from pinned inputs. It is the first piece of the #43 local refresh. It is **replay-only**: it reads the pinned 2023–24 and 2024–25 inputs and refuses any origin outside those seasons or on/after 2025-07-01. Per-origin source revisions (#143) are described below. Live capture, incremental checkpoints (#144) and failure drills (#145) are separate issues.

## Commands

```sh
uv run python -m bil.refresh build RAW PROCESSED ROOT --origin 2024-01-15 [--origin ...]
uv run python -m bil.refresh verify-frozen RAW PROCESSED ROOT
```

- **`build`** prints one JSON line per origin: `artifact_id`, `created` and `path`.
- **`verify-frozen`** refreshes the #36 block cutoffs and compares the results with the published `issue-36-v1` ratings. It exits nonzero unless every cutoff has the same players and a maximum gap of at most 1e-6.
- **`ROOT`** should be under `data/` (for example `data/interim/refresh-<run>`), so artifacts are never committed.

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
- **Atomicity.** Writing happens in a dot-prefixed staging directory beside the target. The files are fsynced, then a single `rename` publishes the directory.
  - A run interrupted by an exception removes its staging directory and leaves no artifact.
  - A killed process or a power loss can leave a `.<id>.staging-*` directory. It is never read as an artifact and can be deleted.
  - On macOS, `fsync` does not flush the drive cache (`F_FULLFSYNC` would). Power-loss durability there is best effort, and a damaged manifest is refused, never repaired.
- **Code changes.** The identity covers the module `VERSION`, not the model code, so a code change that changes outputs must bump `VERSION`. Otherwise a rerun returns the earlier artifact.

## Verification (2026-11-27)

`verify-frozen` reproduced all 10 #36 block snapshots of 2023–24 and 2024–25 against `issue-36-v1`:

- **Roster ratings.** The maximum absolute gap was 0.0, and every refreshed player was in the published export.
- **Off-roster players.** The published export (v1) lists every globally indexed player, 926 per cutoff. The v2 roster keeps only eligible players. The 2,077 published player-cutoffs off the v2 roster all equal the artifact's explicit cold prior, with a maximum gap of 0.0, as #135 specifies.
- **Runtime.** Loading plus the 10 refreshes took 6.7 s, with a peak resident set of 1.9 GiB.
- **Rerun.** A rerun at 2023-12-01 was a no-op.

The command exits nonzero if any cutoff fails these checks at 1e-6.

## Source revisions per origin (#143)

`bil.refresh_sources` resolves one immutable revision per game for each origin. The refresh records that resolution:

- **`sources.json`** in the artifact lists every selected game: `source:game_id` → revision, content SHA-256, capture.
- **The manifest** records a `source_resolution` summary: mode, cutoff, counts, exclusion reasons and digest.
- **The artifact identity** includes the resolution digest.

The digest covers only the selected revisions, not the exclusion counts, because later games change those counts.

### Timing fields the pinned sources actually carry

| Source | Official date | Finish time | Finality | Availability |
| --- | --- | --- | --- | --- |
| NBA.com box-log snapshot | `game_date`, the Eastern official date | Not recorded | No per-game flag | `retrieved_at` of the player and team logs in `snapshot.json`, a capture bound |
| Possession row set (pilot) | `game_date` | Not recorded | `complete` in the pilot `game_stream` table | `available_at` in the pilot `game_stream` table, the latest `retrieved_at` of its sources and a capture bound. It reaches model rows as `stream_available_at` |

The loaded possession rows keep neither the pilot `complete` flag nor `available_at`. The box logs are believed to list only completed games, but that is **Inferred**, not recorded. Both adapters therefore leave finality unknown, which only retrospective resolution accepts.

A **capture** is one pinned retrieval of a source. A game's revision increases whenever a later capture shows different content.

### Rules

- **Cutoff.** The cutoff of origin `D` is midnight Eastern at the start of `D`.
- **`strict_rolling`.** For live captures:
  - A revision is visible only if its capture was retrieved **strictly before** the cutoff. The game's latest visible revision is used.
  - The game must have an official date before `D`, and must have finished before the cutoff.
  - **Finality.** Only content the source marks final is a revision. A capture of a game in progress never enters, and a game whose captures never show final content is refused (`never_final`).
  - **Conservative finish rule:** with no recorded finish time, final content is taken as finished no later than the capture that first showed it.
  - **Corrections.** A correction captured after the cutoff never enters that origin, but enters the first origin after its capture.
  - **Late games.** A game that ends after Eastern midnight keeps its official date. It enters at the first origin after the capture that shows it.
- **Refusals.** These games are refused and counted, never guessed:
  - a game in any capture with no retrieval time (`availability_unknown`);
  - a game in any capture with unknown finality (`finality_unknown`);
  - a non-UTC time, or a recorded finish later than its capture (`time_ambiguous`);
  - a missing official date (`played_date_unknown`);
  - official dates that disagree across captures (`played_date_ambiguous`).
- **Order and retractions.** Captures of a source must be in retrieval order. A game absent from a later capture keeps its earlier revision: captures may be partial, so absence is not a retraction.
- **`retrospective`.** For the pinned 2023–25 replay. Every replay snapshot was captured after its season, so strict resolution would select nothing at any in-season origin. Retrospective resolution:
  - requires exactly one capture per source, and does not ask for finality;
  - selects games whose official date is before `D`, which is the #36 rule.

### Limits of retrospective pins

A retrospective pin shows each game as of its post-season capture. Any correction published between the game and the capture is therefore in every origin's inputs, including origins before the correction existed. This cannot be undone from one capture. It applies to every #35 to #42 result, and is why confirmatory refresh claims need live, strictly resolved captures. The replay refresh refuses `strict_rolling`: assembling inputs from several captures belongs with live capture, in the rest of #43.

The identity still includes the whole-season pin digests, so re-versioning a pin changes every origin's ID, as in #142. This is conservative: it can create a new artifact without need, but never reuses a stale one.

### Verification (2026-11-27)

`verify-frozen` with resolution reproduced all 10 #36 block snapshots, with roster gap 0.0 and cold gap 0.0. For example, the 2024-02-01 origin resolves 5,329 games and excludes 3,797 on or after `D`. The resolution added about 0.3 s, for 7.0 s in total and a peak of 1.9 GiB. `sources.json` is about 0.9 MB per origin.

## Checkpoints, late revisions and capacity (#144)

### Checkpoints

`refresh_origin(..., checkpoints=STORE)` saves the fitted state of each origin. The state is the window row indices and weights, the context fit, the priors and box-history flags, and the player effects, intercept and exposure.

- **Reuse.** A later refresh of that origin reuses the state only when the stored identity (version, origin, input digests including the source resolution, parents and configuration) and the state digest both match exactly. Otherwise it refits and overwrites the checkpoint.
- **Size.** The per-loaded-row prior offset is recomputed from the priors on load, so a checkpoint is bounded by the window, not the row set.
- **Retention.** Checkpoints of the latest 14 origins are retained by default (`CHECKPOINT_RETENTION`).

Warm builds repeat cold computations exactly, so warm and cold artifacts are identical. An approximate rolling update of the solver, such as decaying the normal equations from day to day, was rejected: it cannot give bit-identical artifacts, and a full refit already costs well under a second. Most incrementality therefore comes from idempotent artifacts: a daily run computes only the origins not yet published.

### Late revisions

If an origin already holds a valid artifact with a different ID, the refresh appends a record to `ROOT/<origin>/revisions.jsonl` and raises `RevisionConflict` without publishing. The record holds:

- the previous and new IDs;
- the input digests that changed;
- the counts of games with changed content, recaptured with unchanged content, added and removed, with examples.

`--accept-revision` publishes the new artifact beside the old one, and that is recorded too. Nothing is overwritten.

### Capacity budget (registered before the #144 measurement run)

**Workload.** A daily replay of every origin from 2025-01-01 to 2025-01-31, plus the weekly 2024–25 plan from #129 (1 October and every Monday through the last game). It runs in two passes:

1. **Cold:** fresh artifact root, no checkpoint reuse, checkpoints written.
2. **Warm:** fresh artifact root, reusing pass 1's checkpoints, with retention set to cover the workload.

It also runs one **cold daily job**: a fresh process running `bil.refresh build` for one new origin (2025-02-03), which loads, resolves, fits and publishes. A **late-revision drill** alters one pre-origin game's captured content at a published origin.

**Pass criteria.** These are fixed before the run:

| Check | Budget |
| --- | --- |
| Warm/cold equality | Every workload origin has the same artifact ID and byte-identical `ratings.csv` in both passes. |
| Peak resident memory | At most 4 GiB, for the capacity process and for the daily job. |
| Per-origin refresh, in process | At most 5 s at the maximum. |
| Cold daily job, wall clock (compute freshness) | At most 120 s. |
| Checkpoint store at default retention | At most 500 MB (14 × the mean checkpoint size). |
| Late-revision drill | Refused, recorded with the altered game, and the original artifact untouched. |

**Supported cadence.** Daily if every row passes. The weekly cadence is reported for comparison. Replay measures only compute freshness. Live freshness adds the wait for source captures after the last game, which replay cannot measure.

### Capacity results (`refresh-capacity-issue-144-v1`, 2026-11-27)

Run once from a clean tree at `3d645b8`, after the budget above was committed. The total was 45 s wall. Outputs are under `data/interim/refresh-capacity-issue-144-v1`.

**Workload.** 65 distinct origins:

- 31 daily origins in January 2025;
- 38 weekly origins, 2024-10-01 to 2025-06-16;
- 4 Mondays shared between the two.

| Check | Budget | Measured | Pass |
| --- | --- | --- | --- |
| Warm/cold equality | All origins identical | 65 of 65 with the same artifact ID and byte-identical ratings | yes |
| Peak resident memory | ≤ 4 GiB | 1.98 GiB (capacity process); 1.88 GiB (daily job) | yes |
| Per-origin refresh, maximum | ≤ 5 s | 0.56 s | yes |
| Cold daily job, wall clock | ≤ 120 s | 3.8 s | yes |
| Checkpoint store at retention 14 | ≤ 500 MB | 9.8 MB (0.70 MB per checkpoint) | yes |
| Late-revision drill | Refused and recorded | Refused. Recorded one changed game (`box_logs/2024:0022400001`, input `source_resolution`). The original artifact was untouched | yes |

**Supported cadence: daily.**

**Per-origin cost.**

| Pass | Mean | Maximum | Includes |
| --- | --- | --- | --- |
| Cold | 0.52 s | 0.56 s | Prepare, fit and checkpoint save |
| Warm | 0.06 s | 0.07 s | Checkpoint load and publish |

The daily job (3.8 s) is about 70% input loading (2.7 s). A weekly cadence costs the same per refresh with 7 times fewer refreshes. Neither is near the budget.

**Freshness.** Replay measures compute freshness only: seconds from job start to publish. Live freshness adds the wait for final captures after the night's last game, which replay cannot measure.
