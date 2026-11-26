# V2-free event path: validation protocol

**Registration:** [#133](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/133). This protocol is committed before any V3-event build of 2023–24 or 2024–25 is run.

- **Registration commit.** The commit that last changes this file before the first validation build. The validation runs start from that commit with a clean tracked tree. The run log records its hash and this file's SHA-256.
- **Frozen files.** This file, `src/bil/data/pilot_v3_events.py`, `src/bil/data/pilot.py`, `src/bil/data/pilot_check.py`, `src/bil/data/event_source_comparison.py`, `scripts/v3_event_model_check.py` and `scripts/v3_event_verdict.py`. A change to any of them after the first validation build is a deviation and is reported with the result.

**Classification:**
- **Development validation** of a data-pipeline component (Inferred). It is not model evidence.
- **Holdout.** The 2025–26 holdout is not read. Only file names and HTTP headers of its files were seen (#42 exposure table).

**Why.** The NBA retired the V2 play-by-play endpoint. The pinned archive has no 2025–26 `nbastats` (V2) file, and the pilot build parses V2 events for every game. For 2025–26 the archive does hold V3 actions (`nbastatsv3`) and liveData (`cdnnba`).

## 1. Method (frozen at the registration commit)

**Where.** `bil/data/pilot_v3_events.py`, version `v3-live-events-1`, opt-in through `pilot build --event-source v3`.

**What it does.** For each game it rebuilds the V2 rows the parser and build read, from V3 actions and liveData. V2 is never opened. Everything downstream of the event rows is unchanged: the parser, checks, repairs, row builder and models.

- **Event identity.** V3 `actionNumber` is the V2 `EVENTNUM`. The rows of one number form one event. The first typed row is the primary action, and untyped rows carry its block or steal.
- **Event order.** V3 action order (`actionId`), except that a period's start row leads its period.
- **Types.** V2 `EVENTMSGTYPE` and `EVENTMSGACTIONTYPE` come from a table of 186 V3 `(actionType, subType)` pairs.
  - The table was learned on the 2020–21, 2021–22 and 2022–23 files. Every pair maps to one V2 code except one-off source quirks.
  - A new shot subtype becomes a plain made or missed shot (shot codes are unread).
  - Any other unknown pair quarantines the game.
- **Clock.** `PTmmMss.ffS` becomes `m:ss` with tenths truncated, as in V2.
- **Descriptions.** Each V3 row's text goes to the home, visitor or neutral column by its team. Double fouls and double technicals are neutral.
- **Home team.** Inferred from V3 running scores: a team's baskets move `scoreHome` exactly when it is home.
  - At least 90% of each team's scoring changes must agree, with at least 5 per team.
  - A conflict with a box home flag quarantines the game.
  - Games without a box flag take the inferred side.
- **Players.**
  - **Player 1 and its team:** from the primary V3 row. Team actions keep the team ID as the player and no team.
  - **Assist:** from the liveData row with the same event number and period.
  - **Steal and block:** from V3's untyped rows, with liveData as the fallback.
  - **Foul drawn and both jump-ball players:** from liveData.
  - **Double-foul partner:** from liveData.
  - **No liveData.** A game with no liveData actions is quarantined (`v3_livedata_missing`).
  - **Incoming substitute:**
    1. The surname in the V3 text "SUB: X FOR Y", if it names exactly one player of that team in the game's own V3 rows.
    2. Otherwise a liveData `in` row of the same team in the same substitution batch.
    3. Otherwise one at the same clock.
    4. Otherwise the game is quarantined.
  - **Secondary player teams:** from the box roster.

**Known losses of independence.**
- **liveData** supplies player IDs here, so liveData starters and checks are no longer fully independent of the events.
- **V3 cross-checks** become self-checks: the period scores, the substitution counts and the V3-order fallback.
- **Flagrant fouls.** `pilot check` exempts possession pairs split by a flagrant foul. In a V3-event build it reads the flagrant fouls from the V3 file through the same type table, so V2 is never opened. In each development season the V3 set equals the V2 set (141, 183 and 191 regular-season fouls; 32, 24 and 19 in the playoffs).
- **Not rebuilt from source.** The `PERSON*TYPE` columns are derived from the teams and are not compared, because the parser, normalizer and build never read them.

## 2. Development seasons and exposure

- **Development.** The table and every rule were developed on **2020–21, 2021–22 and 2022–23** only. The work used field-level agreement with archived V2 and full builds compared with the canonical `issue-93-v1` rows.
- **Exposure of the validation seasons.**
  - Before registration, the agent printed about 30 rows of one 2024–25 game (`0022400001`) from V2, V3 and liveData, to read the schema.
  - The 2023–24 and 2024–25 V3 and liveData files were never otherwise read. Their action vocabulary was never listed, so the type table carries no knowledge of it.
  - No 2023–24 or 2024–25 V3-event build, field comparison or row comparison has been run.
  - The V2-built 2023–24 and 2024–25 builds and row sets were used in #36, and the agent knows the #36 results. L7 compares with those results. It tests whether the V3 rows reproduce them, not whether they hold.

Development results with the frozen code (adapter builds `issue-133-dev-v4`, measures `issue-133-dev-v5`):

| Season | Regular games V2 / V3 | Playoff games V2 / V3 | Rows differing | Per-game points gap | Lowest core field | Lowest player slot by type | Unmatched events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2020–21 | 1,072 / 1,072 | 85 / 85 | 0.113% | 0.137% | 100.000% | 99.816% (foul, player 2) | 0 / 0 |
| 2021–22 | 1,219 / 1,218 | 87 / 86 | 0.113% | 0.128% | 100.000% | 99.758% (missed shot, player 3) | 0 / 0 |
| 2022–23 | 1,208 / 1,219 | 84 / 84 | 0.151% | 0.158% | 99.998% | 99.865% (foul, player 2) | 10 / 18 |

- **Quality and model (development).**
  - Every limit passes in all three seasons, by `scripts/v3_event_verdict.py` on these outputs. Season quality: no hard failure, unresolved possessions at most 0.027%. 2021–22 carries one warning: overtime stratum 55 of 58 (94.8%).
  - In a model check with the 2021–22 and 2022–23 rows replaced, the `rapm_context` delta moves by −0.058, both intervals exclude 0, and every verdict is unchanged. This check reuses #36 scores on 2023–25. It exercises the script, not the validation.

- **Checks.** All 26 `check` invariants pass in every development build, and no game failed to rebuild.
- **Row differences.** They come mostly from substitutions between free throws: V3 and V2 store some of them in different places, so a few possessions change lineup, or become multi-lineup and drop out.
- **Extra 2022–23 games.** The V3 build accepts 14 regular-season games that the V2 build quarantines, and loses 3.

## 3. Validation runs

For each validation season, 2023–24 and 2024–25, from snapshot `issue-52-v1`, each into a new directory:
1. `pilot build --event-source v3` with default flags.
2. `pilot check`.
3. `rapm_rows`, canonical variant.
4. `event_source_comparison rows`, against the season's `issue-93-v1` row set, saved as JSON.
5. `event_source_comparison fields`, saved as JSON.

Then, once for both seasons:
6. `scripts/season_quality.py --run-checks` on the two builds.
7. `scripts/v3_event_model_check.py`, with the 2023 and 2024 rows replaced by the V3-event row sets. This reruns the frozen #36 outer evaluation unchanged.
8. `scripts/v3_event_verdict.py` on the outputs of steps 4–7. Its verdict is the result.

## 4. Limits

All limits must hold in both seasons. `scripts/v3_event_verdict.py` encodes them. Where this table and the script differ, the script decides, and the difference is reported.

| ID | Limit | Source |
| --- | --- | --- |
| L1 | Every `check` invariant passes. | `m1_classification.csv`, `invariants_failed` = 0 |
| L2 | No ADR-0022 hard failure: at least 97% of expected games accepted in each season type, and at most 0.1% unresolved possessions in the season. | `m1_classification.csv`, `hard_failures` empty |
| L3 | Accepted games, V3 at least V2 minus 15 in the regular season and minus 3 in the playoffs. | rows JSON, `games` |
| L4 | Row mismatch share at most 0.5%. It counts possession rows that differ in period, offense team, either lineup or points, in games both builds accept. | rows JSON |
| L5 | Points gap at most 0.5%: the sum over games both builds accept of the absolute difference in modeled points, divided by the V2 points. | rows JSON |
| L6a | Agreement at least 99.5% for event type, action type, period and clock, over events both sources hold. | fields JSON |
| L6b | Agreement at least 99.0% for each player slot of each V2 event type with at least 200 events. It counts only events where either source names a player in that slot. | fields JSON |
| L6c | V2-only and V3-only events each at most 0.1% of that source's events, in games both hold. | fields JSON |
| L7 | In the #36 rerun, the pooled regular-season `ei` − `rapm_context` delta moves by at most 0.5 (points per 100)². Both its game and week intervals still exclude 0, and every #36 verdict is unchanged. | model-check JSON |

- **Descriptions** are excluded from L6, because the sources format names differently.
- **Baseline.** The model check with the canonical V2 rows in place of the V3 rows gives `delta_change` 0.000 exactly, so L7 measures only the swapped rows.

## 5. Outcome rules

- **All pass.** A proposed ADR adopts the path for seasons without V2. Its use in R1 then needs an amendment of #42 §4.1–4.2:
  - 2025–26 is built with `--event-source v3` at the frozen code.
  - The 2023–24 and 2024–25 rows stay the V2-built `issue-93-v1` sets.
  - Everything else is unchanged.
- **Any fail.** The failure is reported and the path is not adopted. The adapter is not tuned on 2023–24 or 2024–25: they would then be development seasons, and no V2-paired validation season with liveData would remain. #42 stays blocked.
- **Single shot.** The verdict of the first complete run stands. A crash is a nonzero exit of a step before its output JSON is written. After a crash, the steps rerun at the same commit, and the crash is reported. A failed `pilot check` is a result (L1), not a crash, and the remaining steps still run.

**Residual risk.** The 2025–26 V3 and liveData formats cannot be inspected before R1 freezes. New action types, changed numbering or missing liveData there would show up as quarantined games at the #42 quality gate, which ends the confirmatory attempt.
