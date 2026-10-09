import argparse
from dataclasses import asdict
import json
from pathlib import Path
from ..data.example import example_game
from ..data.catalog import load_catalog
from .generation import generate_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a typed catalog seed (not a playable ROM patch).")
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Version 2 JSON catalog; defaults to the example graph",
    )
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    game = load_catalog(args.catalog) if args.catalog else example_game()
    result = generate_seed(game, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote example seed to {args.output}")


if __name__ == "__main__":
    main()
