# V2-free event path: revised validation protocol (revision 2)

**Registration:** [#133](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/133). It is committed before any revision-2 build of 2023–24 or 2024–25.

**Classification.**
- **Experimental** validation of a data-pipeline component. It is not independent.
- **Why not independent.** The first registered run ([protocol](v3-event-path-protocol.md), [result](v3-event-path-validation.md)) failed on these same seasons, and its results are known.
- **Holdout.** The 2025–26 holdout is not read.

**Maintainer approval.** After the failure, the maintainer chose this revision ("Revised protocol").

**Registration rules.** These are the rules of the first protocol, applied here:
- **Registration commit.** The commit that last changes this file before the first revision-2 build. The runs start from it with a clean tracked tree. The run log records its hash and this file's SHA-256.
- **Frozen files.** The frozen list of the first protocol applies, with this file added. A change to any of them after the first build is a deviation and is reported.

## 1. The one change

Everything in §1 of the first protocol holds, except the handling of V3 `(actionType, subType)` pairs missing from the 2020–23 type table. Version `v3-live-events-2` adds two layers.

**A documented rule pair.** `('Foul', 'Flopping')` becomes (6, 12), a non-unsportsmanlike technical. This rests on the NBA rule introduced for 2023–24 (Documented), under which in-game flopping is a non-unsportsmanlike technical foul. Only the pair's name, known from the failure report, was used.

**A class-preserving fallback** (`fallback_code`) for any other missing pair:

| Unknown pair | Code | Reason |
| --- | --- | --- |
| Foul whose subtype or text names a flagrant or double foul | none: the game is quarantined | Flagrant and double fouls change free-throw and possession handling. |
| Other foul whose subtype contains "Technical", or whose text has the `T.FOUL` marker | (6, 11) technical | pbpstats treats every technical code alike. |
| Other foul whose text has the `P.FOUL` marker | (6, 1) personal | |
| Any other foul | none: the game is quarantined | Inbound, block, take, charge, clear-path and similar classes change free-throw or possession handling. |
| Turnover with a named subtype | (5, 1) | The parser reads turnover codes only as zero ("no turnover") or not. |
| Anything else | none: the game is quarantined | As before. |

- **Marker matching.** A marker must not follow a letter or a period, so `C.P.FOUL` is not `P.FOUL`.
- **Basis.** The rule was fixed from:
  - the pbpstats 1.3.11 foul and turnover predicates;
  - the 2022–23 V3 description markers of known subtypes (`T.FOUL`, `P.FOUL`, `FLAGRANT.FOUL.TYPE`);
  - NBA rules.
- **Not read.** No 2023–24 or 2024–25 row of the unmapped pairs was read before registration: no V3 description, no liveData and no V2 code.
- **Development seasons.** No 2020–23 V3 row reaches either layer, so the 2020–23 builds and measures are unchanged.
- **Reporting.** `event_source_comparison fields` lists every revision-2 row by pair (`revised_events`). It also gives each matched event's parser class in V2 and V3 (`event_class`).

## 2. Exposure

Before this registration, all of these were known from the first run:
- **Results.** Every limit's value for 2023–24 and 2024–25.
- **Unmapped pairs** and their game counts:
  - `('Foul', 'Flopping')`: 74 and 17 games;
  - `('Foul', 'Bench')`: 1 and 3;
  - `('Turnover', '10 Second Violaton')`: 1 and 1;
  - `('Foul', '')`: 0 and 1.
- **Accepted games.** The fidelity limits passed in the games V3 accepted.

The rerun tests two things: whether the fallback restores coverage, and whether the restored games keep the fidelity of the others. It cannot test the adapter's other rules independently a second time.

## 3. Validation runs and limits

- **Runs.** The runs are those of §3 of the first protocol, into new directories labeled `issue-133-v2`.
- **Limits.** L1–L7 and the verdict script are those of §4 of the first protocol, with one added limit:

| ID | Limit | Source |
| --- | --- | --- |
| L8 | Among the revision-2 events of games both sources hold, the parser class agrees with V2's in at least 99%. Classes: technical, double, flagrant, personal, each other foul code, turnover or no turnover. If no revision-2 row exists, L8 passes. If such rows exist but none is matched, L8 fails. | fields JSON, `revised_events` |

- **Scope.** L8 is computed from V2 after the run and does not inform the rule.
- **Frozen files.** `scripts/v3_event_verdict.py`, which now includes L8, is among them.

## 4. Outcome rules

- **All pass.** A proposed ADR adopts `v3-live-events-2` for seasons without V2, as Experimental evidence. Its use in R1 needs an amendment of #42 §4.1–4.2. The amendment states:
  - that the 2025–26 event path rests on this exposed validation;
  - that the 2025–26 build's `revised_events` rows are reported with R1, and are at most 0.1% of the season's V3 rows, or the R1 quality gate fails;
  - that any 2025–26 game the adapter quarantines counts against the #42 quality gate as usual.
- **Any fail.** The path is not adopted, and there is no further revision on 2023–25. #42 stays blocked, and R1 needs a design without 2025–26 play-by-play.
- **Single shot.** The rule of the first protocol applies.

**Residual risk.**
- **Wrong fallback class.** A 2025–26 subtype may get the wrong class, for example a new foul whose text carries `P.FOUL` but which pbpstats should treat differently. Such errors no longer quarantine the game, and nothing in 2025–26 can compare them with V2.
- **Bound.** The 0.1% cap and the reporting in the #42 amendment bound how many events this can affect.
