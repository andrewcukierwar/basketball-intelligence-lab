"""Reproduce the development-only RAPM lineup exposure study in issue #110."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from pathlib import Path

import duckdb
import numpy as np
from scipy.sparse import csr_matrix, hstack, vstack

from bil.models.rapm.baseline import _peak_memory_mib, _sha256
from bil.models.rapm.multiseason import (
    DEV_SCORED_SEASONS,
    ROW_SET_VERSION,
    TEMPORAL_BY_NAME,
    build_matrix,
    check_season,
    paired_delta,
    season_blocks,
    team_game_rmse,
    temporal_weights,
    verify_pilot,
    verify_row_set,
)
from bil.models.rapm.reference import RAPMDesign, _solve_rapm

SEASONS = (2019, 2020, 2021, 2022)
RIDGES = (4000.0, 8000.0)
NAMES = ("stable", "start", "fractional")
PROTOCOL_COMMIT = "b76e2c41e2ec7e4e52198a01b83f224b994af387"
PROTOCOL_SHA = "625d953a6ba0badf5d57395634def980d46d4009e7e64412f6f3de8beec68143"
PROTOCOL_PATH = "docs/research/rapm-lineup-exposure-protocol.md"
# Aggregate, previously frozen ADR-0025 development outputs from the #27 replay.
REPLAY = {
    "regular": (2427, 418731, 14109.756094687764, 10.446688154517403),
    "playoffs": (171, 28351, 14161.9744598845, 10.609359348475506),
}
LEDGER_AUDIT = """
WITH control AS (
  SELECT game_id, stream_revision, possession_seq, sum(points_delta) AS points,
         min(scoring_team_id) AS scorer_min, max(scoring_team_id) AS scorer_max
  FROM score_allocation WHERE possession_reason = 'control_possession'
  GROUP BY ALL
)
SELECT count(*) FROM possession_disposition d FULL JOIN control c
  USING (game_id, stream_revision, possession_seq)
WHERE d.reason IS NULL OR d.control_points <> coalesce(c.points, 0)
  OR (c.scorer_min IS NOT NULL
      AND (c.scorer_min <> d.offense_team_id OR c.scorer_max <> d.offense_team_id))
"""

COHORT_AUDIT = """
SELECT count(*) FROM cohort c
FULL JOIN model_row m USING (game_id, stream_revision, possession_seq)
WHERE c.row_id IS NULL OR c.game_date IS NULL OR c.elapsed_to IS NULL
  OR c.elapsed_from > c.elapsed_to OR c.elapsed_to > c.period_end
  OR c.covered_ms <> c.elapsed_to - c.elapsed_from OR c.covered_seqs <> c.end_seq - c.start_seq
  OR c.pairs <> c.lineup_pairs OR c.multi <> (c.pairs > 1) OR c.control_points < 0
  OR c.multi <> (m.game_id IS NULL)
  OR (m.game_id IS NOT NULL AND (m.weight <> 1 OR m.exposure <> 1
     OR m.model_points <> c.control_points OR m.game_date <> c.game_date
     OR m.season_type <> c.season_type OR m.offense_team_id <> c.offense_team_id
     OR m.offense_player_ids::BIGINT[] <> c.offense OR m.defense_player_ids::BIGINT[] <> c.defense))
"""


@dataclass
class StudyRows:
    """Aligned opportunities with the clock/state attributes needed by the frozen folds."""

    season: np.ndarray
    playoff: np.ndarray
    day: np.ndarray
    game: np.ndarray
    team_game: np.ndarray
    y: np.ndarray
    multi: np.ndarray
    start: csr_matrix
    fractional: csr_matrix
    player_ids: tuple[int, ...]


def read_verified(con, directory, manifest, tables):
    listed = {entry["filename"]: entry["sha256"] for entry in manifest["output_artifacts"]}
    for table in tables:
        name = f"{table}.parquet"
        path = directory / name
        if _sha256(path) != listed[name]:
            raise ValueError(f"{path} differs from its manifest digest")
        escaped = str(path).replace("'", "''")
        con.execute(f"CREATE TEMP VIEW {table} AS SELECT * FROM read_parquet('{escaped}')")


def count(con, sql):
    return int(con.execute(sql).fetchone()[0])


def profile(con):
    cuts = {}
    for field in ("season_type", "margin_band", "period_band", "clock_band"):
        cuts[field] = con.execute(f"""
            SELECT {field}, count(*) FILTER (NOT multi), count(*) FILTER (multi),
                   sum(control_points) FILTER (NOT multi), sum(control_points) FILTER (multi)
            FROM cohort GROUP BY 1 ORDER BY 1
        """).fetchall()
    cuts["substitutions"] = con.execute("""
        SELECT count(*) FILTER (offense_states > 1 AND defense_states = 1),
               count(*) FILTER (offense_states = 1 AND defense_states > 1),
               count(*) FILTER (offense_states > 1 AND defense_states > 1),
               count(*) FILTER (pairs = 2), count(*) FILTER (pairs >= 3),
               count(*) FILTER (zero_ms_pieces > 0), count(*) FILTER (covered_ms = 0)
        FROM cohort WHERE multi
    """).fetchone()
    cuts["team_exposure"] = con.execute("""
        WITH by_team AS (
          SELECT 'offense' AS role, offense_team_id AS team,
                 count_if(multi)::DOUBLE / count(*) AS omitted FROM cohort GROUP BY 1, 2
          UNION ALL
          SELECT 'defense', defense_team_id,
                 count_if(multi)::DOUBLE / count(*) FROM cohort GROUP BY 1, 2
        )
        SELECT role, count(*), quantile_cont(omitted, [0.1, 0.5, 0.9])
        FROM by_team GROUP BY 1 ORDER BY 1
    """).fetchall()
    cuts["player_exposure"] = con.execute("""
        WITH expanded AS (
          SELECT pw.share, c.multi, 'offense' AS role, unnest(pw.offense) AS player_id
          FROM pieces_with_weight pw JOIN cohort c USING (row_id)
          UNION ALL
          SELECT pw.share, c.multi, 'defense', unnest(pw.defense)
          FROM pieces_with_weight pw JOIN cohort c USING (row_id)
        ), by_player AS (
          SELECT role, player_id, sum(share) AS exposure,
                 sum(share) FILTER (multi) AS omitted FROM expanded GROUP BY 1, 2
        )
        SELECT role, count(*), quantile_cont(coalesce(omitted, 0) / exposure, [0.1, 0.5, 0.9])
        FROM by_player WHERE exposure >= 200 GROUP BY 1 ORDER BY 1
    """).fetchall()
    return cuts


def load(processed, season, offset):
    pin = check_season(season, SEASONS)
    row_dir = processed / pin.label / ROW_SET_VERSION
    pilot_dir = processed / pin.label / pin.pilot_build
    row_manifest = verify_row_set(row_dir, season, pin)
    verify_pilot(pilot_dir, pin, row_manifest)
    pilot_manifest = json.loads((pilot_dir / "manifest.json").read_text())
    with duckdb.connect(config={"threads": 2}) as con:
        read_verified(con, row_dir, row_manifest, ("model_row", "possession_disposition"))
        read_verified(
            con,
            pilot_dir,
            pilot_manifest,
            ("event", "game", "game_stream", "lineup", "stint", "score_allocation"),
        )
        if con.execute("SELECT DISTINCT season_start_year FROM game").fetchall() != [(season,)]:
            raise ValueError(f"{pin.label} game table contains a different season")
        if count(con, LEDGER_AUDIT):
            raise ValueError(f"{pin.label} canonical dispositions disagree with score allocations")
        con.execute(Path(__file__).with_suffix(".sql").read_text())
        accepted = count(
            con, "SELECT count(*) FROM possession_disposition WHERE pilot_status = 'accepted'"
        )
        if count(con, "SELECT count(*) FROM cohort") != accepted or count(con, COHORT_AUDIT):
            raise ValueError(
                f"{pin.label} study cohort fails canonical identity, clock or exposure"
            )
        if count(
            con,
            """
            SELECT count(*) FROM segments WHERE len(offense) <> 5 OR len(defense) <> 5
              OR len(list_distinct(list_concat(offense, defense))) <> 10
              OR list_min(offense) <= 0 OR list_min(defense) <= 0
        """,
        ):
            raise ValueError(f"{pin.label} candidate role player IDs are invalid")
        columns = ", ".join(
            f"{role}[{i}] AS {role[0]}{i}" for role in ("offense", "defense") for i in range(1, 6)
        )
        data = con.execute(f"""
            SELECT game_id::BIGINT AS game, game_date, season_type = 'playoffs' AS playoff,
                   offense_home, control_points, multi, {columns}
            FROM cohort ORDER BY row_id
        """).fetchnumpy()
        fractions = con.execute(f"""
            SELECT row_id + {offset} AS row_id, share, {columns}
            FROM pieces_with_weight JOIN (SELECT row_id FROM cohort WHERE multi) USING (row_id)
            WHERE share > 0 ORDER BY row_id, stint_seq
        """).fetchnumpy()
        summaries = profile(con) if season in DEV_SCORED_SEASONS else {}
        data["season"] = np.full(accepted, season)
    return (
        data,
        fractions,
        summaries,
        {
            "row_manifest_sha256": pin.row_manifest_sha256,
            "pilot_manifest_sha256": pin.pilot_manifest_sha256,
            "accepted_possessions": accepted,
            "admitted_multiple_lineups": int(np.sum(data["multi"])),
        },
    )


def lineup(data, prefix):
    return np.column_stack([data[f"{prefix}{i}"] for i in range(1, 6)]).astype(np.int64)


def fractional_rows(player_ids, row_index, share, offense, defense, rows):
    """Return W2 player columns for one fractional design row per opportunity."""
    if not np.all(np.isfinite(share)) or np.any(share <= 0) or np.any(share > 1):
        raise ValueError("fractional shares must be finite and in (0, 1]")
    np.testing.assert_allclose(np.bincount(row_index, share, minlength=rows), 1, rtol=0, atol=1e-12)
    size = len(player_ids)
    cols = np.concatenate(
        [np.searchsorted(player_ids, offense), size + np.searchsorted(player_ids, defense)], axis=1
    )
    values = share[:, None] * np.array([1.0] * 5 + [-1.0] * 5)
    pieces = csr_matrix(
        (values.ravel(), (np.repeat(row_index, 10), cols.ravel())), shape=(rows, 2 * size)
    )
    for block, signed_total in ((pieces[:, :size], 5), (pieces[:, size:], -5)):
        np.testing.assert_allclose(
            np.asarray(block.sum(axis=1)).ravel(), signed_total, rtol=0, atol=1e-12
        )
    return hstack([csr_matrix(np.ones((rows, 1))), pieces], format="csr")


def assemble(seasons, fractions):
    data = {key: np.concatenate([s[key] for s in seasons]) for key in seasons[0]}
    segment = {key: np.concatenate([s[key] for s in fractions]) for key in fractions[0]}
    begin_off = lineup(data, "o")
    begin_def = lineup(data, "d")
    stable = np.flatnonzero(~data["multi"])
    multi = np.flatnonzero(data["multi"])
    off = lineup(segment, "o")
    defense = lineup(segment, "d")
    # Players who only enter later in a multi-lineup possession must be available to
    # the fractional fit. Keep the canonical and start fit column maps aligned too.
    players = tuple(
        int(p)
        for p in np.unique(
            np.concatenate([begin_off.ravel(), begin_def.ravel(), off.ravel(), defense.ravel()])
        )
    )
    begin = build_matrix(begin_off, begin_def)
    starts = begin.matrix
    if begin.player_ids != players:
        left = starts.tocoo()
        lookup = np.searchsorted(players, begin.player_ids)
        positions = np.concatenate(([0], 1 + lookup, 1 + len(players) + lookup))
        starts = csr_matrix(
            (left.data, (left.row, positions[left.col])),
            shape=(starts.shape[0], 1 + 2 * len(players)),
        )
    del begin
    fractional = fractional_rows(
        players,
        np.searchsorted(multi, segment["row_id"]),
        segment["share"],
        off,
        defense,
        len(multi),
    )
    np.testing.assert_array_equal(
        multi[np.searchsorted(multi, segment["row_id"])], segment["row_id"]
    )
    joined = np.concatenate([stable, multi])
    fractional = vstack([starts[stable], fractional], format="csr")[np.argsort(joined)]
    game = data["game"]
    day = data["game_date"].astype("datetime64[D]").astype(np.int64) + date(1970, 1, 1).toordinal()
    if len(np.unique(np.column_stack((game, day)), axis=0)) != len(np.unique(game)):
        raise ValueError("a game has more than one played date")
    return StudyRows(
        data["season"],
        data["playoff"],
        day,
        game,
        2 * game + data["offense_home"],
        100.0 * data["control_points"],
        data["multi"],
        starts,
        fractional,
        players,
    )


def fit_one(rows, matrix, fit_index, score, score_players):
    info = {}
    fit_matrix = matrix[fit_index]
    fit = _solve_rapm(
        RAPMDesign(rows.player_ids, fit_matrix, rows.y[fit_index], np.ones(len(fit_index))),
        *RIDGES,
        info=info,
    )
    effects = np.array(
        [role[player] for role in (fit.offense, fit.defense) for player in rows.player_ids]
    )
    exposure = np.asarray(abs(fit_matrix[:, 1:]).sum(axis=0)).ravel()
    size = len(rows.player_ids)
    for role, block in (("offense", exposure[:size]), ("defense", exposure[size:])):
        np.testing.assert_allclose(block.sum(), 5 * len(fit_index), rtol=1e-12, atol=0)
        info[f"mean_{role}_opportunities_per_exposed_player"] = float(block[block > 0].mean())
    info["fit_possessions"] = len(fit_index)
    info["test_possessions"] = len(score)
    return fit.intercept + score_players @ effects, info


def score_study(rows):
    pred = {name: np.full(len(rows.y), np.nan) for name in NAMES}
    blocks = {}
    for season in DEV_SCORED_SEASONS:
        # season_blocks only uses the three aligned calendar arrays in StudyRows.
        for block in season_blocks(rows, season):
            fit_mask = temporal_weights(rows.day, block.cutoff, TEMPORAL_BY_NAME["W2"]) > 0
            score = np.flatnonzero(block.scored & ~rows.multi)
            if np.any(rows.day[score] < block.cutoff.toordinal()) or np.any(
                np.isfinite(pred["stable"][score])
            ):
                raise ValueError(f"duplicate or past score row in {block.label}")
            score_players = rows.start[score, 1:]
            blocks[block.label] = {}
            for name, matrix in zip(NAMES, (rows.start, rows.start, rows.fractional), strict=True):
                index = np.flatnonzero(fit_mask & ~rows.multi if name == "stable" else fit_mask)
                pred[name][score], stats = fit_one(rows, matrix, index, score, score_players)
                stats["mse"] = float(np.mean((pred[name][score] - rows.y[score]) ** 2))
                blocks[block.label][name] = stats
    eligible = np.isin(rows.season, DEV_SCORED_SEASONS) & ~rows.multi
    for estimates in pred.values():
        np.testing.assert_array_equal(np.isfinite(estimates), eligible)
    scores = {}
    masks = {
        "regular": eligible & ~rows.playoff,
        "playoffs": eligible & rows.playoff,
        "2021_regular": eligible & ~rows.playoff & (rows.season == 2021),
        "2022_regular": eligible & ~rows.playoff & (rows.season == 2022),
    }
    for label, mask in masks.items():
        y = rows.y[mask]
        game = rows.game[mask]
        metrics = {"possessions": len(y), "games": len(np.unique(game)), "models": {}}
        for name in NAMES:
            value = pred[name][mask]
            output = {
                "mse": float(np.mean((value - y) ** 2)),
                "team_game_rmse": team_game_rmse(rows.team_game[mask], y, value),
            }
            if name != "stable":
                output.update(paired_delta(y, value, pred["stable"][mask], {"game": game}))
            metrics["models"][name] = output
        if label in REPLAY:
            games, count_expected, mse, team_rmse = REPLAY[label]
            stable = metrics["models"]["stable"]
            if len(y) != count_expected or metrics["games"] != games:
                raise ValueError(f"{label} scoring coverage differs from the frozen reference")
            np.testing.assert_allclose(
                [stable["mse"], stable["team_game_rmse"]], [mse, team_rmse], rtol=0, atol=1e-6
            )
        scores[label] = metrics
    return {"by_block": blocks, "scores": scores}


def run(processed, output):
    root = Path(__file__).resolve().parents[1]
    if _sha256(root / PROTOCOL_PATH) != PROTOCOL_SHA:
        raise ValueError("protocol differs from the frozen content")
    if output.exists():
        raise FileExistsError(output)
    started = time.perf_counter()
    seasons, fractions, profiles, pins = [], [], {}, {}
    offset = 0
    for season in SEASONS:
        data, segments, summaries, pin = load(processed, season, offset)
        offset += len(data["game"])
        seasons.append(data)
        fractions.append(segments)
        if summaries:
            profiles[season] = summaries
        pins[season] = pin
    rows = assemble(seasons, fractions)
    del seasons, fractions
    results = score_study(rows)
    aggregate = {
        "evidence_tier": "retrospective_capture_bound",
        "protocol_commit": PROTOCOL_COMMIT,
        "protocol_sha256": PROTOCOL_SHA,
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "input_pins": pins,
        "exclusions": profiles,
        "duration_seconds": time.perf_counter() - started,
        "peak_mib": _peak_memory_mib(),
        "versions": {
            "python": platform.python_version(),
            **{name: version(name) for name in ("duckdb", "numpy", "scipy")},
        },
        **results,
    }
    with output.open("x") as stream:
        json.dump(aggregate, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    run(args.processed, args.output)


if __name__ == "__main__":
    main()
