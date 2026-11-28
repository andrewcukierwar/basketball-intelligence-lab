"""Fit and publish one reviewed #168 origin. Outcome scoring lives in a separate stage."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, cast

import numpy as np

from bil.data.pilot_sources import sha256_file
from bil.models.rapm.baseline import _peak_memory_mib
from bil.models.rapm.expanded_inputs import COHORTS, REGISTRATION_SHA256, load_inputs
from bil.models.rapm.multiseason import REPO_ROOT, _versions, assemble
from bil.models.rapm.targets import (
    PRIMARY_KERNEL,
    WIDE_KERNEL,
    fit_season,
    label_digest,
    labels,
    origin_data,
    team_codes,
    verify_protocol,
)

ORIGIN_CUTOFFS = {
    2018: date(2019, 6, 14),
    2019: date(2020, 10, 12),
    2020: date(2021, 7, 21),
    2021: date(2022, 6, 17),
    2022: date(2023, 6, 13),
}
PENALTIES = (2000.0, 4000.0)
KERNELS = {kernel.name: kernel for kernel in (PRIMARY_KERNEL, WIDE_KERNEL)}
VERSION = "expanded-rapm-targets-issue-168-v1"


def fit_origin(
    data_root: Path,
    output: Path,
    cohort: str,
    closes_season: int,
    kernel_name: str,
    protocol_sha256: str,
    repo: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Bind the fit to an approved protocol and publish all its files together."""
    if closes_season not in ORIGIN_CUTOFFS:
        raise ValueError(f"unregistered target origin: {closes_season}")
    if kernel_name not in KERNELS or (kernel_name == WIDE_KERNEL.name and closes_season != 2022):
        raise ValueError(f"unregistered kernel for the selected origin: {kernel_name}")
    start = perf_counter()
    research = repo / "docs/research"
    provenance = verify_protocol(
        research / "expanded-rapm-target-protocol.md", protocol_sha256, repo
    )
    if output.exists():
        raise FileExistsError(f"refusing to replace an existing checkpoint: {output}")
    cutoff = ORIGIN_CUTOFFS[closes_season]
    kernel = KERNELS[kernel_name]
    with TemporaryDirectory(prefix="bil-expanded-rapm-") as temp:
        loads = load_inputs(
            data_root,
            research / "expanded-rapm-cohort-v1.json",
            cohort,
            Path(temp),
            closes_season=closes_season,
        )
        rows = assemble(loads)
        if int(np.max(rows.day)) >= cutoff.toordinal():
            raise ValueError("loaded rows cross the registered origin cutoff")
        teams = team_codes(
            np.concatenate([item.data["offense_team_id"] for item in loads]), rows.game
        )
        del loads

    fit_log: list[dict[str, Any]] = []
    data = origin_data(rows, teams, np.ones(len(rows), dtype=np.bool_), fit_log, label=cohort)
    del rows, teams
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".bil-target-stage-", dir=output.parent) as temp:
        stage = Path(temp) / "checkpoint"
        stage.mkdir(mode=0o700)
        artifacts: dict[str, Any] = {}
        for target in data.seasons:
            fit = fit_season(data, target, kernel, *PENALTIES)
            table = labels(data, fit)
            if any(not np.all(np.isfinite(column)) for column in table.values()):
                raise ValueError(f"nonfinite target labels for season {target}")
            path = stage / f"labels-{target}.npz"
            np.savez_compressed(path, **cast(dict[str, Any], table))
            kernel_seasons = sorted(np.unique(data.rows.season[fit.index]).tolist())
            artifacts[str(target)] = {
                "file": path.name,
                "file_sha256": sha256_file(path),
                "label_digest": label_digest(table),
                "players": len(table["player_id"]),
                "fit_rows": int(fit.index.size),
                "total_weight": float(fit.weights.sum()),
                "kernel_seasons": kernel_seasons,
                "forward_support": any(year > target for year in kernel_seasons),
                "offset": {
                    "intercept": fit.offset.intercept,
                    "context": fit.offset.context.tolist(),
                    "levels": fit.offset.levels,
                    "level_effects": fit.offset.level_effects.tolist(),
                },
            }

        result = {
            "version": VERSION,
            "cohort": cohort,
            "closes_season": closes_season,
            "cutoff_exclusive": cutoff.isoformat(),
            "protocol": provenance,
            "registration_sha256": REGISTRATION_SHA256,
            "input_digest": data.digest,
            "input_rows": len(data.rows),
            "kernel": kernel.name,
            "penalties": PENALTIES,
            "artifacts": artifacts,
            "solver": fit_log,
            "versions": _versions(),
            "seconds": perf_counter() - start,
            "peak_rss_mib": _peak_memory_mib(),
            "evidence_tier": "retrospective_capture_bound",
        }
        (stage / "manifest.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )
        stage.rename(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cohort", required=True, choices=COHORTS)
    parser.add_argument("--closes-season", required=True, type=int, choices=ORIGIN_CUTOFFS)
    parser.add_argument("--kernel", default=PRIMARY_KERNEL.name, choices=KERNELS)
    parser.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    result = fit_origin(
        args.data_root,
        args.output,
        args.cohort,
        args.closes_season,
        args.kernel,
        args.protocol_sha256,
    )
    print(
        json.dumps(
            {
                "cohort": result["cohort"],
                "input_rows": result["input_rows"],
                "target_seasons": len(result["artifacts"]),
                "seconds": result["seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
