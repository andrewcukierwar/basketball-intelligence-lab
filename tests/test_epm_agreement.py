from pathlib import Path

import numpy as np
import pytest

from bil.models.epm_agreement import (
    agreement,
    load_capture,
    parse_columnar_form,
    parse_expected_form,
    parse_json_form,
    read_literal,
    season_table,
    top_overlap,
)


def test_literal_reader_handles_js_forms_without_evaluation():
    value, end = read_literal('{a:.5,"b":-1e2,c:[void 0,null,true,"x\\"y"],d:{z:-.25}} tail', 0)
    assert value == {"a": 0.5, "b": -100.0, "c": [None, None, True, 'x"y'], "d": {"z": -0.25}}
    assert end == len(value and '{a:.5,"b":-1e2,c:[void 0,null,true,"x\\"y"],d:{z:-.25}}')
    with pytest.raises(ValueError):
        read_literal("[alert(1)]", 0)


def test_three_capture_forms_parse_to_records():
    json_page = 'x var data = `{"player_stats":[{"season":2022,"player_id":1,"off":1.0,"def":0.5,"mp":900}]}` y'
    assert parse_json_form(json_page)[0]["player_id"] == 1
    columnar = "q={stats:[[2023,2,7,1.5,{z:1,rk:2},-0.5],[2022,2,8,0.1,null,0.2]],k:{season:0,seasontype:1,player_id:2,off:3,mpg_attr:4,def:5},settings:a}"
    rows = parse_columnar_form(columnar)
    assert rows[0] == {
        "season": 2023,
        "seasontype": 2,
        "player_id": 7,
        "off": 1.5,
        "mpg_attr": {"z": 1, "rk": 2},
        "def": -0.5,
    }
    expected = 'data:{date:"2025-06-22",stats:[{season:2025,game_dt:"2025-06-22",player_id:9,off:.5,def:-.5,tot:0}]}'
    assert parse_expected_form(expected)[0]["def"] == -0.5


def test_season_filter_stints_and_missing_values():
    records = [
        {"season": 2023, "seasontype": 2, "player_id": 1, "off": 2.0, "def": 0.0, "mp": 300},
        {"season": 2023, "seasontype": 2, "player_id": 1, "off": 0.0, "def": 1.0, "mp": 100},
        {"season": 2023, "seasontype": 4, "player_id": 2, "off": 9.0, "def": 9.0, "mp": 100},
        {"season": 2022, "seasontype": 2, "player_id": 3, "off": 9.0, "def": 9.0, "mp": 100},
        {"season": 2023, "seasontype": 2, "player_id": 4, "off": None, "def": 1.0, "mp": 50},
    ]
    table, info = season_table(records, 2022, "columnar")
    assert set(table) == {1}
    assert table[1].offense == pytest.approx(1.5) and table[1].defense == pytest.approx(0.25)
    assert table[1].total == pytest.approx(1.75)
    assert info["multi_stint_players"] == 1 and info["dropped_missing"] == 1
    assert info["other_season_or_type_rows"] == 2
    with pytest.raises(ValueError):
        season_table([{**records[0], "off": "x"}], 2022, "columnar")


def test_holdout_and_unregistered_captures_refuse(tmp_path: Path):
    with pytest.raises(ValueError, match="holdout"):
        load_capture(tmp_path, 2025)
    with pytest.raises(ValueError, match="no registered"):
        load_capture(tmp_path, 2020)


def test_agreement_metrics_and_overlap():
    rng = np.random.default_rng(0)
    epm = rng.normal(size=(200, 3))
    model = epm + 0.1
    out = agreement(model, epm)
    assert out["total"]["pearson"] == pytest.approx(1.0)
    assert out["offense"]["bias"] == pytest.approx(0.1) and out["defense"]["rmse"] == pytest.approx(
        0.1
    )
    assert top_overlap(model[:, 2], epm[:, 2], 25) == 1.0
    assert top_overlap(-model[:, 2], epm[:, 2], 25) == 0.0
