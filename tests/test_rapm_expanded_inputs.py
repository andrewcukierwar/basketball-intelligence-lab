from hashlib import sha256
from pathlib import Path

import duckdb
import numpy as np
import pytest

from bil.models.rapm.expanded_inputs import _exclude, _excluded_control_keys, load_inputs


def test_scoreless_wrong_side_excludes_only_the_registered_stream(tmp_path: Path) -> None:
    tables = {
        "model_row": """
            select '001' game_id, 1 stream_revision, 1 possession_seq
            union all select '001', 2, 1
            union all select '002', 1, 1
        """,
        "possession": """
            select '001' game_id, 1 stream_revision, 1 possession_seq, 1 start_seq, 3 end_seq,
                   '100' offense_team_id, 'accepted' status
            union all select '001', 2, 1, 1, 3, '100', 'accepted'
            union all select '002', 1, 1, 1, 3, '100', 'accepted'
        """,
        "event": """
            select '001' game_id, 1 stream_revision, 1 seq, 1 period, 1000 elapsed_ms,
                   'shot' kind, '100' team_id
            union all select '001', 2, 1, 1, 1000, 'shot', '200'
            union all select '002', 1, 1, 1, 1000, 'turnover', '200'
            union all select '002', 1, 2, 1, 1000, 'free_throw', '100'
        """,
    }
    with duckdb.connect() as connection:
        for name, query in tables.items():
            connection.sql(query).write_parquet(str(tmp_path / f"{name}.parquet"))

    keys = _excluded_control_keys(tmp_path, tmp_path / "model_row.parquet")
    assert keys == [("001", 2, 1)]
    digest = sha256(b"001,2,1\n").hexdigest()
    data = {
        "game_id": np.array(["001", "001", "002"]),
        "stream_revision": np.array([1, 2, 1]),
        "possession_seq": np.array([1, 1, 1]),
        "model_points": np.array([0, 0, 0]),
    }
    eligible = _exclude(data, keys, 1, digest)
    assert eligible["game_id"].tolist() == ["001", "002"]
    assert eligible["stream_revision"].tolist() == [1, 1]
    with pytest.raises(ValueError, match="keys differ"):
        _exclude(data, keys, 1, sha256(b"001,1,1\n").hexdigest())


def test_invalid_registration_is_refused_before_opening_data(tmp_path: Path) -> None:
    manifest = tmp_path / "changed.json"
    manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unregistered"):
        list(load_inputs(tmp_path / "missing", manifest, "frozen_5", tmp_path))
    with pytest.raises(ValueError, match="unexpected registered digest"):
        list(load_inputs(tmp_path / "missing", manifest, "expanded_15", tmp_path))
