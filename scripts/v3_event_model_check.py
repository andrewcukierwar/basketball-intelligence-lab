"""Rerun the frozen #36 outer evaluation with V3-event rows for the scored seasons (#133).

The 2021–22 and 2022–23 rows stay the pinned V2-event `issue-93-v1` sets. The 2023–24 and
2024–25 rows come from canonical row sets built from `build --event-source v3` pilots. Every
model choice is read from the frozen #36 addendum; nothing is tuned. The output compares the
pooled deltas and verdicts with the `issue-36-v1` results.

    python scripts/v3_event_model_check.py RAW PROCESSED OUT.json \
        --rows 2023=2023-24/<pilot>:<rows> --rows 2024=2024-25/<pilot>:<rows>
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from bil.data.pilot_sources import sha256_file
from bil.models.expected_impact import SPM_MANIFEST, SPM_RUN, spm_fit
from bil.models.expected_impact_outer import (
    ADDENDUM,
    ROW_SEASONS,
    evaluate,
    outer_logs,
    parse_config,
    verdicts,
)
from bil.models.rapm.multiseason import (
    SEASON_PINS,
    Analysis,
    Scenario,
    assemble,
    build_matrix,
    load_season,
)
from bil.models.spm_build import checked_file, read_json

OUTER = "issue-36-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("processed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rows", action="append", required=True, help="SEASON=LABEL/PILOT:ROWS")
    args = parser.parse_args()
    pins = dict(SEASON_PINS)
    for item in args.rows:
        season_text, spec = item.split("=", 1)
        season = int(season_text)
        label_pilot, rows = spec.split(":", 1)
        label, pilot = label_pilot.split("/", 1)
        row_dir = args.processed / label / rows
        pilot_dir = args.processed / label / pilot
        pins[season] = replace(
            pins[season],
            row_manifest_sha256=sha256_file(row_dir / "manifest.json"),
            pilot_build=pilot,
            pilot_manifest_sha256=sha256_file(pilot_dir / "manifest.json"),
            row_set=rows,
        )
    config = parse_config(ADDENDUM.read_text(encoding="utf-8"))
    spm_dir = args.processed / "spm" / SPM_RUN
    checked_file(spm_dir / "manifest.json", SPM_MANIFEST)
    spm = spm_fit(read_json(checked_file(spm_dir / config["spm_fit"], config["spm_fit_sha256"])))
    logs = {
        int(key): outer_logs(args.raw, int(key), pin)[0] for key, pin in config["box_logs"].items()
    }
    temp = Path(tempfile.mkdtemp(prefix=".v3-model-check-", dir=args.output.parent))
    try:
        loads = [load_season(args.processed, s, ROW_SEASONS, temp, pins) for s in ROW_SEASONS]
    finally:
        shutil.rmtree(temp)
    rows = assemble(loads)
    design = build_matrix(rows.offense, rows.defense)
    analysis = Analysis(rows, design, Scenario("primary", np.ones(len(rows), dtype=bool)), [], [])
    results, _, _ = evaluate(rows, analysis, config, spm, logs)
    reference = read_json(args.processed / "expected_impact" / OUTER / "results.json")
    pooled = results["pooled_regular"]["ei_delta_vs"]
    before = reference["pooled_regular"]["ei_delta_vs"]
    summary: dict[str, Any] = {
        "row_pins": {
            str(s): {"row_set": pins[s].row_set, "pilot_build": pins[s].pilot_build}
            for s in ROW_SEASONS
        },
        "scored_possessions": results["pooled_regular"]["possessions"],
        "reference_scored_possessions": reference["pooled_regular"]["possessions"],
        "comparators": {
            name: {
                "v3": pooled[name],
                "issue_36_v1": before[name],
                "delta_change": pooled[name]["delta"] - before[name]["delta"],
            }
            for name in pooled
        },
        "verdicts_v3": verdicts(results, config["primary_comparator"]),
        "verdicts_issue_36_v1": reference["verdicts"],
    }
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary["comparators"]["rapm_context"], indent=2))


if __name__ == "__main__":
    main()
