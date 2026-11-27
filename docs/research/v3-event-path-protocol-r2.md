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

Everything in §1 of the first protocol holds, except the handling of V3 `(actionType, subType)` pairs missing from the type table. Version `v3-live-events-2` adds a class-preserving fallback (`fallback_code`):

| Unknown pair | Code | Reason |
| --- | --- | --- |
| Foul whose subtype or text names a flagrant or double foul | none, so the game is quarantined | No safe class: flagrant and double fouls change free-throw and possession handling. |
| Other foul whose subtype contains "Technical" or whose text contains `T.FOUL` | (6, 11) technical | pbpstats treats every technical code alike. |
| Any other foul | (6, 1) personal | |
| Turnover with a named subtype | (5, 1) | The parser reads turnover codes only as zero ("no turnover") or not. |
| Anything else | none, so the game is quarantined | As before. |

**How the rule was chosen.**
- **Inputs.** It uses only:
  - the pbpstats 1.3.11 foul and turnover predicates;
  - the 2022–23 V3 description markers of known subtypes (for example `T.FOUL` for technicals and `FLAGRANT.FOUL.TYPE` for flagrants);
  - NBA rules.
- **What was not read.** The rule was fixed without reading any 2023–24 or 2024–25 row of the unmapped pairs, whether V3 descriptions, liveData or V2 codes. Only the pair names and game counts in the failure report are known.
- **Development seasons unchanged.** No 2020–23 V3 row reaches the fallback, so the 2020–23 builds and measures are unchanged.

**Reporting.** `event_source_comparison fields` lists every fallback row by pair and code (`fallback_events`).

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
- **Limits.** L1–L7 and the verdict script are unchanged from §4 of the first protocol.

## 4. Outcome rules

- **All pass.**
  - **ADR.** A proposed ADR adopts `v3-live-events-2` for seasons without V2, as Experimental evidence.
  - **#42 amendment.** Its use in R1 needs an amendment of #42 §4.1–4.2. The amendment states:
    - that the 2025–26 event path rests on this exposed validation;
    - that the 2025–26 build's `fallback_events` are reported with R1;
    - that any 2025–26 game quarantined by the adapter counts against the #42 quality gate as usual.
- **Any fail.** The path is not adopted, and there is no further revision on 2023–25. #42 stays blocked, and R1 needs a design without 2025–26 play-by-play.
- **Single shot.** The rule of the first protocol applies.

**Residual risk.**
- **Wrong fallback class.** A 2025–26 subtype may get the wrong class. For example, a new non-technical foul that awards free throws would be coded personal. Such errors no longer quarantine the game. They can surface only through `check`, the quality gate or row-level effects, which R1 cannot compare against V2.
- **Reporting.** Reporting `fallback_events` bounds how many events this can affect.
