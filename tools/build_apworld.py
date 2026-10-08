"""Package the shared code and AP adapter without bundling game assets."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("dist/sticker_star.apworld")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
        for folder in ("domain", "data", "integrations"):
            for source in sorted((root / "randomizer" / folder).rglob("*.py")):
                archive.write(
                    source,
                    "sticker_star/"
                    + source.relative_to(root / "randomizer").as_posix(),
                )
        archive.writestr(
            "sticker_star/__init__.py",
            "from .integrations.archipelago.world import StickerStarWorld\n",
        )
        archive.writestr(
            "sticker_star/archipelago.json",
            json.dumps(
                {
                    "game": "Paper Mario: Sticker Star (Logic Demo)",
                    "world_version": "0.1.0",
                    "minimum_ap_version": "0.6.8",
                    "compatible_version": 7,
                    "version": 7,
                }
            ),
        )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
