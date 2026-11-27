"""V2-schema events rebuilt from V3 actions and liveData (#133), on a synthetic game."""

from __future__ import annotations

import csv
import io
import tarfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from bil.data.pilot_inputs import GameIssue
from bil.data.pilot_v3_events import (
    ACTION_TYPES,
    LIVE_FIELDS,
    V2_HEADERS,
    V3_FIELDS,
    Action,
    derive_home,
    fallback_code,
    flagrant_events,
    rebuild_game,
    rebuilt_games,
    v2_clock,
)

HOME, AWAY = 1610612738, 1610612755
H1, H2, H3, A1, A2, A3 = 11, 12, 13, 21, 22, 23
ROSTER = {H1: HOME, H2: HOME, H3: HOME, A1: AWAY, A2: AWAY, A3: AWAY}


def v3(
    action_id: int,
    number: int,
    kind: str,
    sub: str,
    person: int,
    team: int,
    text: str,
    clock: str = "PT11M00.00S",
    score: tuple[str, str] = ("", ""),
    name: str = "",
) -> Action:
    fields = dict.fromkeys(V3_FIELDS, "")
    fields.update(
        actionId=str(action_id),
        actionNumber=str(number),
        actionType=kind,
        subType=sub,
        personId=str(person),
        teamId=str(team),
        description=text,
        clock=clock,
        period="1",
        scoreHome=score[0],
        scoreAway=score[1],
        videoAvailable="1",
        playerName=name,
    )
    return Action(action_id + 1, fields)


def live(number: int, kind: str, sub: str = "", **extra: str) -> Action:
    fields = dict.fromkeys(LIVE_FIELDS, "")
    fields.update(actionNumber=str(number), actionType=kind, subType=sub, period="1", **extra)
    return Action(number, fields)


GAME = [
    v3(1, 2, "period", "start", 0, 0, "Start of 1st Period", "PT12M00.00S"),
    v3(2, 4, "Jump Ball", "", H1, HOME, "Jump Ball A vs. B: Tip to C", "PT12M00.00S"),
    v3(3, 7, "Missed Shot", "Jump Shot", A1, AWAY, "MISS A1 3PT Jump Shot", name="Aone"),
    v3(4, 7, "", "", H2, HOME, "H2 BLOCK (1 BLK)", name="Htwo"),
    v3(5, 9, "Rebound", "Unknown", H1, HOME, "H1 REBOUND", name="Hone"),
    v3(6, 10, "Turnover", "Bad Pass", H1, HOME, "H1 Bad Pass Turnover"),
    v3(7, 10, "", "", A2, AWAY, "A2 STEAL (1 STL)", name="Atwo"),
    v3(8, 12, "Made Shot", "Jump Shot", A2, AWAY, "A2 Jump Shot (2 PTS)", score=("0", "2")),
    v3(9, 14, "Foul", "Shooting", A1, AWAY, "A1 S.FOUL (P1.T1)"),
    v3(
        10,
        16,
        "Free Throw",
        "Free Throw 1 of 2",
        H1,
        HOME,
        "H1 Free Throw 1 of 2",
        score=("1", "2"),
    ),
    v3(11, 17, "Substitution", "", A1, AWAY, "SUB: Athree FOR Aone", "PT11M00.00S"),
    v3(12, 18, "Free Throw", "Free Throw 2 of 2", H1, HOME, "MISS H1 Free Throw 2 of 2"),
    v3(13, 20, "Rebound", "Normal Rebound", AWAY, 0, "Team Rebound"),
    v3(14, 22, "Timeout", "Regular", HOME, 0, "Home Timeout: Regular", "PT00M45.80S"),
    # Later baskets: enough running-score votes to fix the home team.
    *(
        v3(
            20 + i,
            30 + i,
            "Made Shot",
            "Jump Shot",
            player,
            team,
            "Jump Shot",
            "PT00M30.00S",
            score,
        )
        for i, (player, team, score) in enumerate(
            [
                (H1, HOME, ("3", "2")),
                (A1, AWAY, ("3", "4")),
                (H2, HOME, ("5", "4")),
                (A2, AWAY, ("5", "6")),
                (H1, HOME, ("7", "6")),
                (A1, AWAY, ("7", "8")),
                (H2, HOME, ("9", "8")),
                (A2, AWAY, ("9", "10")),
            ]
        )
    ),
]
LIVE = [
    live(
        4,
        "jumpball",
        "recovered",
        personId=str(H3),
        teamId=str(HOME),
        jumpBallWonPersonId=str(H1),
        jumpBallLostPersonId=str(A1),
        jumpBallRecoverdPersonId=str(H3),
    ),
    live(12, "2pt", assistPersonId=str(A3)),
    live(14, "foul", "personal", foulDrawnPersonId=str(H1)),
    live(17, "substitution", "out", personId=str(A1), teamId=str(AWAY), clock="PT10M58.00S"),
    live(
        19,
        "substitution",
        "in",
        personId=str(A3),
        teamId=str(AWAY),
        clock="PT10M58.00S",
        playerName="A. Athree",
    ),
]


def rebuilt(**changes: object) -> dict[int, dict[str, str]]:
    events = rebuild_game("0022200001", GAME, LIVE, (HOME, AWAY), HOME, ROSTER)
    return {int(e.fields["EVENTNUM"]): e.fields for e in events}


def test_clock_truncates_tenths() -> None:
    assert v2_clock("PT11M43.00S") == "11:43"
    assert v2_clock("PT00M47.90S") == "0:47"
    with pytest.raises(GameIssue):
        v2_clock("11:43")


def test_home_from_running_scores() -> None:
    assert derive_home(GAME, (HOME, AWAY)) == HOME
    assert derive_home(GAME, (AWAY, HOME)) == HOME
    assert derive_home(GAME[:3], (HOME, AWAY)) is None
    # One misattributed basket among many does not block the decision.
    more = [
        v3(
            41 + i,
            41 + i,
            "Made Shot",
            "Jump Shot",
            A1,
            AWAY,
            "Jump Shot",
            score=("9", str(12 + 2 * i)),
        )
        for i in range(5)
    ]
    stray = v3(50, 50, "Made Shot", "Jump Shot", A1, AWAY, "Jump Shot", score=("11", "20"))
    assert derive_home([*GAME, *more, stray], (HOME, AWAY)) == HOME


def test_rebuilt_rows_carry_the_v2_fields_the_parser_reads() -> None:
    rows = rebuilt()
    assert list(rows) == [2, 4, 7, 9, 10, 12, 14, 16, 17, 18, 20, 22, *range(30, 38)]  # V3 order
    assert all(list(row) == list(V2_HEADERS) for row in rows.values())
    jump = rows[4]
    assert (jump["EVENTMSGTYPE"], jump["PLAYER1_ID"], jump["PLAYER2_ID"]) == (
        "10",
        str(H1),
        str(A1),
    )
    assert (jump["PLAYER3_ID"], jump["PLAYER3_TEAM_ID"]) == (str(H3), str(HOME))
    miss = rows[7]
    assert (miss["EVENTMSGTYPE"], miss["EVENTMSGACTIONTYPE"]) == ("2", "1")
    assert (miss["PLAYER3_ID"], miss["PLAYER3_TEAM_ID"]) == (str(H2), str(HOME))
    assert miss["VISITORDESCRIPTION"].startswith("MISS") and "BLOCK" in miss["HOMEDESCRIPTION"]
    assert rows[10]["PLAYER2_ID"] == str(A2)  # steal
    made = rows[12]
    assert (made["PLAYER2_ID"], made["SCORE"], made["SCOREMARGIN"]) == (str(A3), "2 - 0", "-2")
    assert rows[14]["PLAYER2_ID"] == str(H1)  # foul drawn
    assert rows[16]["SCORE"] == "2 - 1" and rows[18]["SCORE"] == ""
    sub = rows[17]
    assert (sub["EVENTMSGTYPE"], sub["PLAYER1_ID"], sub["PLAYER2_ID"]) == ("8", str(A1), str(A3))
    team = rows[20]
    assert (team["PLAYER1_ID"], team["PLAYER1_TEAM_ID"]) == (str(AWAY), "")
    assert team["VISITORDESCRIPTION"] == "Team Rebound"
    timeout = rows[22]
    assert (timeout["HOMEDESCRIPTION"], timeout["PCTIMESTRING"]) == (
        "Home Timeout: Regular",
        "0:45",
    )
    assert rows[2]["NEUTRALDESCRIPTION"] == "Start of 1st Period"


def test_undesignated_box_takes_home_from_scores_and_conflict_quarantines() -> None:
    events = rebuild_game("0022200001", GAME, LIVE, (AWAY, HOME), None, ROSTER)
    assert next(e for e in events if e.fields["EVENTNUM"] == "12").fields["VISITORDESCRIPTION"]
    with pytest.raises(GameIssue) as conflict:
        rebuild_game("0022200001", GAME, LIVE, (HOME, AWAY), AWAY, ROSTER)
    assert conflict.value.code == "v3_home_conflict"


def test_unmapped_action_and_unpaired_substitution_quarantine() -> None:
    odd = [*GAME, v3(15, 23, "Mystery", "New", H1, HOME, "?")]
    with pytest.raises(GameIssue) as unmapped:
        rebuild_game("0022200001", odd, LIVE, (HOME, AWAY), HOME, ROSTER)
    assert unmapped.value.code == "v3_unmapped_action"
    new_shot = [*GAME, v3(15, 23, "Made Shot", "Brand New Shot", H1, HOME, "H1 shot")]
    events = rebuild_game("0022200001", new_shot, LIVE, (HOME, AWAY), HOME, ROSTER)
    shot = next(e.fields for e in events if e.fields["EVENTNUM"] == "23")
    assert (shot["EVENTMSGTYPE"], shot["EVENTMSGACTIONTYPE"]) == ("1", "0")
    with pytest.raises(GameIssue) as unpaired:
        rebuild_game("0022200001", GAME, LIVE[:3], (HOME, AWAY), HOME, ROSTER)
    assert unpaired.value.code == "v3_substitution_unpaired"


def test_learned_table_is_complete_for_core_types() -> None:
    assert ACTION_TYPES[("Free Throw", "Free Throw 1 of 2")] == (3, 11)
    assert ACTION_TYPES[("Rebound", "Unknown")] == (4, 0)
    assert ACTION_TYPES[("Substitution", "")] == (8, 0)


def _archive(path: Path, actions: Sequence[Action], game_id: str = "22200001") -> Path:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["gameId", *actions[0].fields])
    writer.writeheader()
    for action in actions:
        writer.writerow({"gameId": game_id, **action.fields})
    data = stream.getvalue().encode()
    with tarfile.open(path, "w:xz") as archive:
        member = tarfile.TarInfo(path.name.replace(".tar.xz", ".csv"))
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return path


def test_flagrant_events_and_games_without_livedata(tmp_path: Path) -> None:
    flagrant = v3(15, 23, "Foul", "Flagrant Type 1", A1, AWAY, "A1 FLAGRANT.FOUL.TYPE1")
    v3_path = _archive(tmp_path / "nbastatsv3_2022.tar.xz", [*GAME, flagrant])
    assert flagrant_events(v3_path, {"0022200001"}) == {("0022200001", "23")}
    assert flagrant_events(v3_path, {"0022200002"}) == set()
    boxes = {"0022200001": ((HOME, AWAY), HOME, ROSTER)}
    live_path = _archive(tmp_path / "cdnnba_2022.tar.xz", LIVE)
    [(game_id, events)] = rebuilt_games(v3_path, live_path, boxes)
    assert game_id == "0022200001" and not isinstance(events, GameIssue)
    other = _archive(tmp_path / "cdnnba_other.tar.xz", LIVE, game_id="22200002")
    [(_, missing)] = rebuilt_games(v3_path, other, boxes)
    assert isinstance(missing, GameIssue) and missing.code == "v3_livedata_missing"


def test_unknown_foul_and_turnover_subtypes_keep_their_class() -> None:
    assert fallback_code("Foul", "Novel", "X Novel T.FOUL (P1.PN)") == (6, 11)
    assert fallback_code("Foul", "Novel Technical", "X") == (6, 11)
    assert fallback_code("Foul", "Novel", "X NOVEL.FOUL (P2.T1)") == (6, 1)
    assert fallback_code("Foul", "Novel", "X FLAGRANT.FOUL.TYPE1") is None
    assert fallback_code("Foul", "Double Novel", "X") is None
    assert fallback_code("Turnover", "Novel Turnover", "X") == (5, 1)
    assert fallback_code("Violation", "Novel", "X") is None
    game = [*GAME, v3(15, 23, "Foul", "Novel", A1, AWAY, "A1 Novel T.FOUL (P1.PN)")]
    events = rebuild_game("0022200001", game, LIVE, (HOME, AWAY), HOME, ROSTER)
    foul = next(e.fields for e in events if e.fields["EVENTNUM"] == "23")
    assert (foul["EVENTMSGTYPE"], foul["EVENTMSGACTIONTYPE"]) == ("6", "11")
