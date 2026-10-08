"""Build the revision-2 experimental tutorial skip."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.tutorial_skip import write_tutorial_skip
from randomizer.integrations.rom.project import RomProject


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_tutorial_skip(RomProject(args.rom), args.output, args.compiler)
    print(f"Built tutorial-skip test in {args.output}")


if __name__ == "__main__":
    main()
