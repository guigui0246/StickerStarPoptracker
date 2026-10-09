"""Validate the eight CI outputs and give release assets distinct names."""

import argparse
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    assets: list[tuple[Path, str]] = []
    for runner, platform in (("ubuntu-22.04", "linux-x86_64"), ("windows-latest", "windows-x86_64")):
        for target, filename in (
            ("cli_randomizer", "cli_randomizer.exe" if runner == "windows-latest" else "cli_randomizer"),
            ("apworld", "sticker-star.apworld"),
            ("randomizer", "randomizer.exe" if runner == "windows-latest" else "randomizer"),
            ("tracker", "sticker-star-poptracker.zip"),
        ):
            folder = args.artifacts / f"build-{runner}-{target}"
            source = folder / filename
            if not source.is_file() or source.stat().st_size == 0 or list(folder.iterdir()) != [source]:
                raise ValueError(f"Expected exactly one nonempty build asset: {source}")
            assets.append((source, f"{source.stem}-{platform}{source.suffix}"))
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("Release output directory must be empty")
    args.output.mkdir(parents=True, exist_ok=True)
    for source, filename in assets:
        shutil.copyfile(source, args.output / filename)


if __name__ == "__main__":
    main()
