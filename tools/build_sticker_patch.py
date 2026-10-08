"""Build an experimental real-game sticker shuffle for emulator testing."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.project import RomProject
from randomizer.integrations.rom.sticker_patch import write_sticker_patch


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experimental combat-sticker patch; progression/AP runtime are unfinished."
    )
    parser.add_argument("rom", type=Path)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    patch = write_sticker_patch(RomProject(args.rom), args.output, args.seed)
    changed = sum(change.pickup.item_name != change.reward for change in patch.changes)
    print(
        f"Built {changed} changed pickups from {len(patch.changes)} shuffled placements in {args.output}"
    )
    print("Emulator testing required. This is not the complete progression randomizer.")


if __name__ == "__main__":
    main()
