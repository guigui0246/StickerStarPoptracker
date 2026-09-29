import argparse
import json
from pathlib import Path
from .core import Settings, generate


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a seed description; this does not patch the game."
        )
    )
    parser.add_argument(
        "catalog", type=Path, help="Verified game logic catalog JSON"
    )
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-banners", action="store_true")
    parser.add_argument(
        "--banner-divisor", type=int, choices=(1, 10), default=1
    )
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    result = generate(
        catalog, args.seed, Settings(not args.no_banners, args.banner_divisor)
    )
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {len(result['placements'])} rewards to {args.output}. "
        "Game patch integration is not implemented."
    )


if __name__ == "__main__":
    main()
