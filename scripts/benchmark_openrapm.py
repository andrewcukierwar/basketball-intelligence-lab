"""Compare BIL's sparse fit with pinned OpenRAPM on shared synthetic rows."""

from __future__ import annotations

import argparse
import hashlib
import runpy
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from platform import python_version
from types import SimpleNamespace

import numpy as np
import pandas as pd

from bil.models.rapm import build_design, fit_rapm
from bil.models.rapm.synthetic import generate_possessions

OPENRAPM_REVISION = "8cfb3df786ceb1cd362a67c4683c37a473ee9c2b"
OPENRAPM_SOURCES = {
    "design.py": "59f0fff71bfb1d60806ed1dedb98ededdbdb9b628792ea197d474468a1d84528",
    "rapm.py": "74f56adc5c788549fc5d271ec75010b8b7ac29b78ed43fa0cf5e720e9c1769b2",
}
ATOL = 1e-8


def load_openrapm(source_dir: Path):
    for filename, expected in OPENRAPM_SOURCES.items():
        path = source_dir / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"{path} does not match OpenRAPM revision {OPENRAPM_REVISION}")
    return (
        runpy.run_path(str(source_dir / "design.py"), run_name="benchmark_openrapm_design"),
        runpy.run_path(str(source_dir / "rapm.py"), run_name="benchmark_openrapm_solver"),
    )


def run_benchmark(design_matrix, season_sums, label, rows, ridge, probe_rows):
    player_ids = sorted({player for row in rows for player in (*row.offense, *row.defense)})
    columns = {player: index for index, player in enumerate(player_ids)}
    size = len(player_ids)
    sign_map = np.concatenate([np.ones(size), -np.ones(size), [1]])

    def openrapm_matrix(possessions):
        offense = np.array(
            [sorted(columns[player] for player in row.offense) for row in possessions]
        )
        defense = np.array(
            [sorted(columns[player] for player in row.defense) for row in possessions]
        )
        # OpenRAPM's final matrix column holds game metadata, outside the regression.
        return design_matrix(
            offense, defense, np.ones((len(possessions), 1)), np.zeros(len(possessions)), size
        )

    response = np.array([100 * row.points for row in rows])
    weights = np.array([row.weight for row in rows])
    reference = SimpleNamespace(
        X=openrapm_matrix(rows),
        y=response,
        w=weights,
        spec=SimpleNamespace(
            n_players=size,
            players=pd.DataFrame({"player_id": player_ids}),
            context_names=["intercept"],
        ),
        rows=pd.DataFrame({"poss": np.ones(len(rows))}),
    )
    open_fit = season_sums().add(0, reference)
    open_coef, _ = open_fit.solve(penalties=(ridge, ridge, 0))
    bil_design = build_design(rows)
    assert bil_design.player_ids == tuple(player_ids)
    np.testing.assert_array_equal(bil_design.response, response)
    np.testing.assert_array_equal(bil_design.weights, weights)
    np.testing.assert_array_equal(
        bil_design.matrix[:, [*range(1, 2 * size + 1), 0]].toarray(),
        reference.X[:, :-1].toarray() * sign_map,
    )

    fit = fit_rapm(rows, ridge=ridge)
    bil_coef = np.array(
        [
            *(fit.offense[p] for p in player_ids),
            *(fit.defense[p] for p in player_ids),
            fit.intercept,
        ]
    )
    bil_probe = build_design(probe_rows)
    assert bil_probe.player_ids == tuple(player_ids)
    bil_coef_in_design_order = np.roll(bil_coef, 1)  # BIL stores its intercept first.
    train_delta = np.max(
        np.abs(bil_design.matrix @ bil_coef_in_design_order - reference.X[:, :-1] @ open_coef)
    )
    probe_delta = np.max(
        np.abs(
            bil_probe.matrix @ bil_coef_in_design_order
            - openrapm_matrix(probe_rows)[:, :-1] @ open_coef
        )
    )
    coefficient_delta = np.abs(bil_coef - open_coef * sign_map)
    deltas = (
        np.max(coefficient_delta[:size]),
        np.max(coefficient_delta[size:-1]),
        coefficient_delta[-1],
        train_delta,
        probe_delta,
    )
    print(f"{label} | {len(rows)} | {ridge:g} | " + " | ".join(f"{d:.3e}" for d in deltas))
    np.testing.assert_allclose(deltas, 0, rtol=0, atol=ATOL, err_msg=label)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_dir", type=Path, help="directory containing pinned design.py and rapm.py"
    )
    args = parser.parse_args()
    design, solver = load_openrapm(args.source_dir)
    print(f"OpenRAPM {OPENRAPM_REVISION} | Absolute tolerance {ATOL:g} points per 100 possessions")
    print(f"Python {python_version()}")
    print(", ".join(f"{name} {version(name)}" for name in ("numpy", "scipy", "pandas")))
    print(
        "Fixture | Rows | Ridge | Max O delta | Max D delta | Intercept delta | Train delta | Probe delta"
    )
    weighted = [
        replace(row, weight=(index % 5 + 1) / 3)
        for index, row in enumerate(generate_possessions(64, seed=721, noisy=True))
    ]
    paired = generate_possessions(128, seed=6014, paired=True)
    probes = generate_possessions(48, seed=6992)
    for label, rows, ridge in (
        ("Unequal weights", weighted, 7.5),
        (
            "Common 8x weight and penalty scale",
            [replace(row, weight=8 * row.weight) for row in weighted],
            60,
        ),
        ("Paired players, weak ridge", paired, 0.01),
        ("Paired players, strong ridge", paired, 1000),
    ):
        run_benchmark(design["design_matrix"], solver["SeasonSums"], label, rows, ridge, probes)


if __name__ == "__main__":
    main()
