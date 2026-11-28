from pathlib import Path

import numpy as np
import pytest

from bil.models.rapm import expanded_score


def test_paired_game_draws_are_deterministic_and_keep_pairing() -> None:
    actual = np.array([1.0, -1.0, 3.0, 0.0])
    baseline = actual + 1.0
    result = expanded_score._comparison(baseline, actual, actual, np.array(["a", "a", "a", "b"]))
    for metric in result.values():
        assert metric["matched_10"] == 1.0
        assert metric["delta"] == -1.0
        assert metric["interval_95"] == [-1.0, -1.0]


def test_bad_receipt_refuses_before_opening_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "receipt.json").write_text("{}")
    monkeypatch.setattr(expanded_score, "verify_protocol", lambda *_: {})
    monkeypatch.setattr(
        expanded_score, "_evaluation_view", lambda *_, **__: pytest.fail("opened outcomes")
    )
    with pytest.raises(ValueError, match="unexpected registered digest"):
        expanded_score.score(tmp_path, tmp_path, "wrong-sha")
