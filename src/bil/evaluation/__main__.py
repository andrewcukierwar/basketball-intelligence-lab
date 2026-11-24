"""Read-only validation of a local historical evaluation."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from bil.evaluation.eligibility import require
from bil.evaluation.scoring import validate_forecast, validate_score


def local_reader(manifest: Path) -> Callable[[str], bytes]:
    root = manifest.resolve().parent

    def read(uri: str) -> bytes:
        path = (root / uri).resolve()
        require(path.is_relative_to(root), f"artifact path escapes manifest directory: {uri}")
        return path.read_bytes()

    return read


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("forecast", type=Path, help="path to forecast manifest")
    parser.add_argument("--score", type=Path, help="optional linked scoring manifest")
    args = parser.parse_args()
    try:
        forecast_bytes = args.forecast.read_bytes()
        if args.score is None:
            batches = validate_forecast(forecast_bytes, local_reader(args.forecast))
            print(f"Validated {len(batches)} forecast batches")
        else:
            results = validate_score(
                args.score.read_bytes(),
                local_reader(args.score),
                forecast_bytes,
                local_reader(args.forecast),
            )
            print(f"Validated frozen forecast and recomputed {len(results)} scoring results")
    except (KeyError, OSError, TypeError, ValueError, OverflowError) as exc:
        print(f"Evaluation validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
