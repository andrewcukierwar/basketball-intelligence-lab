"""R1 v2 external agreement D1 (#42 protocol §3.3): the #40 method, unchanged, on 2025–26.

The EI side is the R1 final snapshot (2026-07-01) from the scored holdout run, checked against
its pre-score manifest. Its on-court part ends with 2024–25 rows; 2025–26 enters only through the
box-score prior. The EPM side is the capture pinned in ``r1-holdout-pins.json`` (selected by
timestamps and metadata only). EPM is used under written permission, non-commercial only, and
changes nothing in C1–T2. matched.csv stays private under ``data/``.

    python scripts/r1_d1.py data/raw data/processed/r1/holdout-2025 data/processed/r1/d1
"""

from __future__ import annotations

import argparse
import csv
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np

from bil.data.pilot_sources import sha256_file, utc_now, write_json
from bil.models.epm_agreement import (
    ATTRIBUTION,
    CAPTURE_DIR,
    PARSERS,
    PROTOCOL,
    EiRow,
    agreement,
    bootstrap,
    match,
    season_table,
    slices,
    summarize,
    top_overlap,
)
from bil.models.r1_holdout import HOLDOUT_SEASON, PINS, guard
from bil.models.spm_build import checked_file, read_json

VERSION = "r1-v2-d1"
PRE_SCORE_MANIFEST = "7d49a867d40f73dea1810d75c91950a63ace9bf8b51e4cce0c2f27bd70704b0e"
FINAL_AS_OF = "2026-07-01"


def load_final_ei(run: Path) -> dict[int, EiRow]:
    manifest = read_json(checked_file(run / "manifest.json", PRE_SCORE_MANIFEST))
    path = checked_file(run / "ratings.csv", manifest["outputs"]["ratings.csv"])
    out = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["as_of"] != FINAL_AS_OF:
                continue
            out[int(row["player_id"])] = EiRow(
                (float(row["rating_offense"]), float(row["rating_defense"])),
                (float(row["prior_offense"]), float(row["prior_defense"])),
                float(row["window_possessions"]),
                row["box_history"] == "True",
            )
    if not out:
        raise ValueError("the R1 final snapshot is missing")
    return out


def run(raw: Path, holdout: Path, output: Path) -> dict[str, Any]:
    started = time.monotonic()
    freeze = guard()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite a run: {output}")
    pin = read_json(PINS)["epm_capture_d1"]
    path = checked_file(raw / CAPTURE_DIR / f"{pin['capture']}.html", pin["sha256"])
    records = PARSERS[pin["form"]](path.read_text(encoding="utf-8"))
    epm, info = season_table(records, HOLDOUT_SEASON, pin["form"])
    ei = load_final_ei(holdout)
    m = match(ei, epm)
    masks = slices(m)
    primary = masks["primary_window_1000_plus"]
    report: dict[str, Any] = {
        "version": VERSION,
        "evidence": "external agreement diagnostic; not predictive validity",
        "label": f"{pin['form']} EPM (data date {pin['data_date']})",
        "attribution": ATTRIBUTION,
        "ei_snapshot": {"run": "r1-v2 holdout", "as_of": FINAL_AS_OF},
        "epm_capture": {"capture": pin["capture"], "sha256": pin["sha256"], "form": pin["form"]}
        | info,
        "unmatched": {"epm_only": len(set(epm) - set(ei)), "ei_only": len(set(ei) - set(epm))},
        "slices": {name: summarize(m, mask) for name, mask in masks.items()},
        "top_overlap_total": {
            str(n): {
                "ei": top_overlap(m.ei[primary, 2], m.epm[primary, 2], n),
                "spm_prior": top_overlap(m.prior[primary, 2], m.epm[primary, 2], n),
            }
            for n in (25, 50)
        },
        "primary": {
            "players": int(primary.sum()),
            "ei": agreement(m.ei[primary], m.epm[primary]),
            "spm_prior": agreement(m.prior[primary], m.epm[primary]),
            "bootstrap": bootstrap(
                m.players[primary], m.ei[primary], m.prior[primary], m.epm[primary]
            ),
        },
    }
    output.mkdir(mode=0o700, parents=True)
    with (output / "matched.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("player_id", "epm_off", "epm_def", "ei_off", "ei_def", "window"))
        for k, player in enumerate(m.players):
            writer.writerow(
                (int(player), *m.epm[k, :2].tolist(), *m.ei[k, :2].tolist(), m.window[k])
            )
    write_json(output / "results.json", report)
    write_json(
        output / "manifest.json",
        {
            "version": VERSION,
            "generated_at": utc_now(),
            "attribution": ATTRIBUTION,
            "r1_protocol": freeze,
            "method_protocol": {"path": str(PROTOCOL.name), "sha256": sha256_file(PROTOCOL)},
            "inputs": {"pre_score_manifest": PRE_SCORE_MANIFEST, "epm_capture": pin},
            "outputs": {p.name: sha256_file(p) for p in sorted(output.iterdir())},
            "versions": {"python": platform.python_version(), "numpy": np.__version__},
            "runtime_seconds": time.monotonic() - started,
        },
    )
    return report


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("raw", type=Path)
    cli.add_argument("holdout", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    report = run(args.raw.resolve(), args.holdout.resolve(), args.output.resolve())
    print(sha256_file(args.output.resolve() / "results.json"), report["primary"]["players"])


if __name__ == "__main__":
    main()
