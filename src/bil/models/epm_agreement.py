"""Run the registered #40 agreement diagnostic between frozen EI v1 and archived public EPM.

EPM values are diagnostic only: nothing here feeds any model, selection or tuning.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import re
import shutil
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from bil.data.pilot_sources import sha256_file, utc_now, write_json
from bil.models.rapm.multiseason import REPO_ROOT
from bil.models.rapm.targets import verify_protocol
from bil.models.spm_build import checked_file, read_json

VERSION = "issue-40-v1"
PROTOCOL = REPO_ROOT / "docs/research/epm-agreement-protocol.md"
CAPTURE_DIR = Path("epm-wayback")
ATTRIBUTION = "EPM data: dunksandthrees.com (archived public page), used with written permission"
HOLDOUT_START_YEAR = 2025
RATING_RUNS = {
    "issue-35-v1": "db254b8c450034a0142255c40301e74cd6ddc59d505ab6d7aef983f846fce5d1",
    "issue-36-v1": "f74fc2a5e76b7a22964ca8b96736344bc49f3611dd0acf37fbdaeb9ae130a131",
}


@dataclass(frozen=True)
class Pin:
    capture: str
    sha256: str
    form: str  # "json", "columnar" or "expected"
    ei_as_of: str
    ei_run: str


PINS = {
    2021: Pin(
        "20220703130813",
        "ffe649f5b188d2fd399534419b35550772c1b0d7926feea9003172b7c217d7ab",
        "json",
        "2022-10-01",
        "issue-35-v1",
    ),
    2022: Pin(
        "20230705024653",
        "1e86fa8abf8c9082d90915af2fd4d5bdfcfb9ab75f652dfb48d2b87231dbbbb1",
        "columnar",
        "2023-07-01",
        "issue-35-v1",
    ),
    2023: Pin(
        "20240701155753",
        "6db67c2ca0470cb6f8c378309987b24739b06e4f452a2dc29a9d8e44b588f5df",
        "columnar",
        "2024-10-01",
        "issue-36-v1",
    ),
    2024: Pin(
        "20250718200357",
        "93189c0b359c29583d1e40dcc256398bad648970a906b47a4add27a1b018739e",
        "expected",
        "2025-07-01",
        "issue-36-v1",
    ),
}
SIDES = ("offense", "defense", "total")
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 40


# --- JavaScript literal reader (no evaluation) --------------------------------------------

_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


def read_literal(text: str, start: int) -> tuple[Any, int]:
    """Parse one JS object/array/scalar literal at `start`; return the value and end index."""
    i = _skip(text, start)
    char = text[i]
    if char == "[":
        items: list[Any] = []
        i = _skip(text, i + 1)
        while text[i] != "]":
            value, i = read_literal(text, i)
            items.append(value)
            i = _skip(text, i)
            if text[i] == ",":
                i = _skip(text, i + 1)
        return items, i + 1
    if char == "{":
        obj: dict[str, Any] = {}
        i = _skip(text, i + 1)
        while text[i] != "}":
            if text[i] in "\"'":
                key, i = _string(text, i)
            else:
                match = _NAME.match(text, i)
                if not match:
                    raise ValueError(f"bad object key at {i}")
                key, i = match.group(), match.end()
            i = _skip(text, i)
            if text[i] != ":":
                raise ValueError(f"expected ':' at {i}")
            obj[key], i = read_literal(text, i + 1)
            i = _skip(text, i)
            if text[i] == ",":
                i = _skip(text, i + 1)
        return obj, i + 1
    if char in "\"'":
        return _string(text, i)
    number = _NUMBER.match(text, i)
    if number:
        return float(number.group()), number.end()
    name = _NAME.match(text, i)
    if name:
        word = name.group()
        if word == "void":
            after = _NUMBER.match(text, _skip(text, name.end()))
            if not after:
                raise ValueError(f"bad void at {i}")
            return None, after.end()
        constants = {"null": None, "undefined": None, "true": True, "false": False}
        if word in constants:
            return constants[word], name.end()
        raise ValueError(f"unsupported identifier {word!r} at {i}")
    raise ValueError(f"unexpected character {char!r} at {i}")


def _skip(text: str, i: int) -> int:
    while text[i].isspace():
        i += 1
    return i


def _string(text: str, i: int) -> tuple[str, int]:
    quote = text[i]
    out = []
    i += 1
    while text[i] != quote:
        if text[i] == "\\":
            out.append(
                json.loads(f'"{text[i : i + 2]}"')
                if text[i + 1] != "u"
                else chr(int(text[i + 2 : i + 6], 16))
            )
            i += 6 if text[i + 1] == "u" else 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out), i + 1


# --- capture parsers ------------------------------------------------------------------------

Record = dict[str, Any]


def parse_json_form(page: str) -> list[Record]:
    start = page.index("var data = `") + len("var data = `")
    payload = json.loads(page[start : page.index("`", start)])
    records: list[Record] = payload["player_stats"]
    return records


def parse_columnar_form(page: str) -> list[Record]:
    position = page.index("stats:[[")
    rows, end = read_literal(page, position + len("stats:"))
    keys_at = page.index("k:{", end)
    if keys_at - end > 5:
        raise ValueError("the column key map does not follow the rows")
    keys, _ = read_literal(page, keys_at + 2)
    return [
        {key: row[int(index)] for key, index in keys.items() if int(index) < len(row)}
        for row in rows
    ]


def parse_expected_form(page: str) -> list[Record]:
    position = page.index("stats:[{")
    records, _ = read_literal(page, position + len("stats:"))
    return list(records)


PARSERS = {
    "json": parse_json_form,
    "columnar": parse_columnar_form,
    "expected": parse_expected_form,
}


@dataclass(frozen=True)
class Epm:
    offense: float
    defense: float
    stints: int

    @property
    def total(self) -> float:
        return self.offense + self.defense


def season_table(
    records: Sequence[Record], season: int, form: str
) -> tuple[dict[int, Epm], dict[str, Any]]:
    """Season rows (end-year label) keyed by NBA person ID, combining stints by minutes."""
    end_year = season + 1
    grouped: dict[int, list[Record]] = defaultdict(list)
    dropped = other = 0
    for record in records:
        if int(record["season"]) != end_year or (
            form == "columnar" and record.get("seasontype") != 2
        ):
            other += 1
            continue
        if record.get("off") is None or record.get("def") is None:
            dropped += 1
            continue
        for key in ("off", "def"):
            if not isinstance(record[key], (int, float)) or not np.isfinite(record[key]):
                raise ValueError("non-numeric EPM value")
        grouped[int(record["player_id"])].append(record)
    table = {}
    for player, rows in grouped.items():
        if len(rows) == 1:
            table[player] = Epm(float(rows[0]["off"]), float(rows[0]["def"]), 1)
            continue
        minutes = np.asarray([float(row.get("mp") or 0) for row in rows])
        if minutes.sum() <= 0:
            raise ValueError("multi-stint player without minutes")
        off = float(np.average([row["off"] for row in rows], weights=minutes))
        dfn = float(np.average([row["def"] for row in rows], weights=minutes))
        table[player] = Epm(off, dfn, len(rows))
    dates = sorted({str(r["game_dt"]) for r in records if r.get("game_dt")})
    return table, {
        "players": len(table),
        "multi_stint_players": sum(e.stints > 1 for e in table.values()),
        "dropped_missing": dropped,
        "other_season_or_type_rows": other,
        "data_dates": dates[-1:] if dates else [],
    }


def load_capture(raw: Path, season: int) -> tuple[dict[int, Epm], dict[str, Any]]:
    if season >= HOLDOUT_START_YEAR:
        raise ValueError(f"season {season} is the confirmatory holdout or later")
    if season not in PINS:
        raise ValueError(f"no registered EPM capture for {season}")
    pin = PINS[season]
    path = checked_file(raw / CAPTURE_DIR / f"{pin.capture}.html", pin.sha256)
    page = path.read_text(encoding="utf-8")
    table, info = season_table(PARSERS[pin.form](page), season, pin.form)
    return table, {"capture": pin.capture, "sha256": pin.sha256, "form": pin.form, **info}


# --- EI ratings -------------------------------------------------------------------------------


@dataclass(frozen=True)
class EiRow:
    rating: tuple[float, float]
    prior: tuple[float, float]
    window_possessions: float
    box_history: bool


def load_ei(processed: Path) -> tuple[dict[tuple[str, str], dict[int, EiRow]], dict[str, Any]]:
    wanted = {(pin.ei_run, pin.ei_as_of) for pin in PINS.values()}
    out: dict[tuple[str, str], dict[int, EiRow]] = defaultdict(dict)
    inputs = {}
    for run, digest in RATING_RUNS.items():
        directory = processed / "expected_impact" / run
        manifest = read_json(checked_file(directory / "manifest.json", digest))
        path = checked_file(directory / "ratings.csv", manifest["outputs"]["ratings.csv"])
        inputs[run] = {"manifest_sha256": digest}
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = (run, row["as_of"])
                if key not in wanted:
                    continue
                out[key][int(row["player_id"])] = EiRow(
                    (float(row["rating_offense"]), float(row["rating_defense"])),
                    (float(row["prior_offense"]), float(row["prior_defense"])),
                    float(row["window_possessions"]),
                    row["box_history"] == "True",
                )
    if set(out) != wanted:
        raise ValueError("a registered EI snapshot is missing")
    return dict(out), inputs


# --- metrics ----------------------------------------------------------------------------------


def with_total(pairs: np.ndarray) -> np.ndarray:
    result: np.ndarray = np.column_stack((pairs, pairs.sum(axis=1)))
    return result


def ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    result = np.empty(len(values))
    result[order] = np.arange(len(values))
    for value in np.unique(values):  # average ties
        tied = values == value
        if tied.sum() > 1:
            result[tied] = result[tied].mean()
    return result


def agreement(model: np.ndarray, epm: np.ndarray) -> dict[str, Any]:
    """Per side: Pearson, Spearman, MAE, RMSE and mean signed bias (model minus EPM)."""
    out: dict[str, Any] = {"players": len(model)}
    if len(model) < 3:
        return out
    for k, side in enumerate(SIDES):
        a, b = model[:, k], epm[:, k]
        diff = a - b
        out[side] = {
            "pearson": float(np.corrcoef(a, b)[0, 1]),
            "spearman": float(np.corrcoef(ranks(a), ranks(b))[0, 1]),
            "mae": float(np.mean(np.abs(diff))),
            "rmse": float(np.sqrt(np.mean(diff**2))),
            "bias": float(np.mean(diff)),
        }
    return out


def top_overlap(model: np.ndarray, epm: np.ndarray, n: int) -> float | None:
    if len(model) < n:
        return None
    top_model = set(np.argsort(-model, kind="stable")[:n].tolist())
    top_epm = set(np.argsort(-epm, kind="stable")[:n].tolist())
    return len(top_model & top_epm) / n


def bootstrap(
    players: np.ndarray, ei: np.ndarray, prior: np.ndarray, epm: np.ndarray
) -> dict[str, Any]:
    ids, inverse = np.unique(players, return_inverse=True)
    members = [np.flatnonzero(inverse == k) for k in range(len(ids))]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = np.empty((BOOTSTRAP_RESAMPLES, 3, 2))
    for b in range(BOOTSTRAP_RESAMPLES):
        rows = np.concatenate([members[k] for k in rng.integers(0, len(ids), len(ids))])
        for side in range(3):
            draws[b, side, 0] = np.corrcoef(ei[rows, side], epm[rows, side])[0, 1]
            draws[b, side, 1] = np.corrcoef(prior[rows, side], epm[rows, side])[0, 1]
    out = {}
    for side, name in enumerate(SIDES):
        out[name] = {
            "ei_pearson_ci95": np.quantile(draws[:, side, 0], [0.025, 0.975]).tolist(),
            "ei_minus_prior_pearson_ci95": np.quantile(
                draws[:, side, 0] - draws[:, side, 1], [0.025, 0.975]
            ).tolist(),
        }
    return out


@dataclass(frozen=True)
class Matched:
    players: np.ndarray
    ei: np.ndarray
    prior: np.ndarray
    epm: np.ndarray
    window: np.ndarray
    box_history: np.ndarray


def match(ei: Mapping[int, EiRow], epm: Mapping[int, Epm]) -> Matched:
    common = sorted(set(ei) & set(epm))
    return Matched(
        np.asarray(common, dtype=np.int64),
        with_total(np.asarray([ei[p].rating for p in common]).reshape(-1, 2)),
        with_total(np.asarray([ei[p].prior for p in common]).reshape(-1, 2)),
        with_total(np.asarray([(epm[p].offense, epm[p].defense) for p in common]).reshape(-1, 2)),
        np.asarray([ei[p].window_possessions for p in common]),
        np.asarray([ei[p].box_history for p in common], dtype=bool),
    )


def slices(m: Matched) -> dict[str, np.ndarray]:
    return {
        "primary_window_1000_plus": m.window >= 1000,
        "window_1000_to_2999": (m.window >= 1000) & (m.window < 3000),
        "window_3000_plus": m.window >= 3000,
        "all_matched": np.ones(len(m.players), dtype=bool),
        "spm_intercept_fallback": ~m.box_history,
    }


def summarize(m: Matched, mask: np.ndarray) -> dict[str, Any]:
    return {
        "ei": agreement(m.ei[mask], m.epm[mask]),
        "spm_prior": agreement(m.prior[mask], m.epm[mask]),
    }


def run(raw: Path, processed: Path, output: Path, protocol_sha256: str) -> None:
    started = time.monotonic()
    protocol = verify_protocol(PROTOCOL, protocol_sha256)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    ei_tables, ei_inputs = load_ei(processed)
    report: dict[str, Any] = {
        "version": VERSION,
        "evidence": "external agreement diagnostic; not predictive validity",
        "attribution": ATTRIBUTION,
        "seasons": {},
    }
    pooled: dict[str, list[Any]] = defaultdict(list)
    parsed_rows = []
    captures = {}
    for season, pin in PINS.items():
        epm, info = load_capture(raw, season)
        captures[str(season)] = info
        ei = ei_tables[pin.ei_run, pin.ei_as_of]
        m = match(ei, epm)
        masks = slices(m)
        primary = masks["primary_window_1000_plus"]
        report["seasons"][str(season)] = {
            "ei_snapshot": {"run": pin.ei_run, "as_of": pin.ei_as_of},
            "epm_capture": info,
            "unmatched": {"epm_only": len(set(epm) - set(ei)), "ei_only": len(set(ei) - set(epm))},
            "slices": {name: summarize(m, mask) for name, mask in masks.items()},
            "top_overlap_total": {
                str(n): {
                    "ei": top_overlap(m.ei[primary, 2], m.epm[primary, 2], n),
                    "spm_prior": top_overlap(m.prior[primary, 2], m.epm[primary, 2], n),
                }
                for n in (25, 50)
            },
        }
        pooled["players"].append(m.players[primary])
        for name in ("ei", "prior", "epm"):
            pooled[name].append(getattr(m, name)[primary])
        for k, player in enumerate(m.players):
            parsed_rows.append(
                (season, int(player), *m.epm[k, :2].tolist(), *m.ei[k, :2].tolist(), m.window[k])
            )
    players = np.concatenate(pooled["players"])
    ei_all, prior_all, epm_all = (np.concatenate(pooled[n]) for n in ("ei", "prior", "epm"))
    report["pooled_primary"] = {
        "player_seasons": len(players),
        "distinct_players": len(np.unique(players)),
        "ei": agreement(ei_all, epm_all),
        "spm_prior": agreement(prior_all, epm_all),
        "bootstrap": bootstrap(players, ei_all, prior_all, epm_all),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(output.name + ".partial")
    if stage.exists():  # leftovers of a crashed run that wrote no results
        shutil.rmtree(stage)
    stage.mkdir()
    with (stage / "matched.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("season", "player_id", "epm_off", "epm_def", "ei_off", "ei_def", "window_possessions")
        )
        writer.writerows(parsed_rows)
    write_json(stage / "results.json", report)
    write_json(
        stage / "manifest.json",
        {
            "version": VERSION,
            "generated_at": utc_now(),
            "attribution": ATTRIBUTION,
            "protocol": protocol,
            "outputs": {p.name: sha256_file(p) for p in sorted(stage.iterdir())},
            "inputs": {"ei_ratings": ei_inputs, "epm_captures": captures},
            "versions": {"python": platform.python_version(), "numpy": np.__version__},
            "runtime_seconds": time.monotonic() - started,
        },
    )
    stage.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    run(args.raw.resolve(), args.processed.resolve(), args.output.resolve(), args.protocol_sha256)


if __name__ == "__main__":
    main()
