"""Write a file inventory without copying or modifying game content."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom import inspect_rom


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_rom(args.rom)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"{result.product_code}: decrypted={result.decrypted}, {len(result.romfs)} RomFS files"
    )


if __name__ == "__main__":
    main()
