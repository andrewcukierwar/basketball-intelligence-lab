"""Assess M1 quality under the ADR-0022 policy and missingness for built pilot seasons.

Example:
    uv run python scripts/season_quality.py OUT_DIR \
        --build data/processed/2018-19/issue-25-v1 data/raw/2018-19/issue-25-v1 \
        --build data/processed/2019-20/issue-25-v1 data/raw/2019-20/issue-25-v1

OUT_DIR must not exist. Builds and snapshots are opened read-only. The output is aggregate CSV
and JSON only, and no model is fitted or scored.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bil.data.season_quality import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("output", type=Path, help="New directory for the aggregate results")
    parser.add_argument(
        "--build",
        nargs=2,
        action="append",
        metavar=("BUILD_DIR", "SNAPSHOT_DIR"),
        required=True,
        help="A built season and the snapshot it was built from; repeat for several seasons",
    )
    parser.add_argument("--seed", type=int, default=20261123)
    parser.add_argument("--permutations", type=int, default=5000)
    parser.add_argument("--bootstrap", type=int, default=20_000)
    parser.add_argument(
        "--primary-years",
        type=int,
        nargs="+",
        default=[2018, 2019, 2020, 2021, 2022],
        help="Season start years of the primary training cohort for the sensitivity table",
    )
    parser.add_argument(
        "--run-checks",
        action="store_true",
        help="Also run the hard correctness checks (pilot check) on each build",
    )
    args = parser.parse_args()
    summary = run(
        [(Path(build), Path(snapshot)) for build, snapshot in args.build],
        args.output,
        seed=args.seed,
        permutations=args.permutations,
        replicates=args.bootstrap,
        primary_years=args.primary_years,
        run_checks=args.run_checks,
    )
    for row in summary["classification"]:
        print(
            f"{row['season']}: original {row['original_status']}, revised {row['revised_status']}"
        )


if __name__ == "__main__":
    main()
