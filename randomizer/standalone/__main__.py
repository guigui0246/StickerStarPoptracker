import argparse
from dataclasses import asdict
import json
from pathlib import Path
from ..data.example import example_game
from ..data.catalog import load_catalog
from .generation import generate_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a typed catalog seed (not a playable ROM patch).")
    parser.add_argument("catalog_path", nargs="?", type=Path, help="Version 2 catalog (also accepted as --catalog)")
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Version 2 JSON catalog; defaults to the example graph",
    )
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.catalog and args.catalog_path:
        parser.error("Use either a positional catalog or --catalog, not both")
    catalog_path = args.catalog or args.catalog_path
    game = load_catalog(catalog_path) if catalog_path else example_game()
    result = generate_seed(game, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["fixed_rewards"] = game.fixed_rewards
    payload["location_names"] = {location.id: location.name for location in game.locations}
    payload["item_names"] = {item.id: item.name for item in game.items}
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(result.placements)} randomized placements and {len(game.fixed_rewards)} fixed rewards to {args.output}")
    if catalog_path is None:
        print("Logic demo only: supply --catalog for your reviewed location/item list. This is not a full-game seed.")


if __name__ == "__main__":
    main()
