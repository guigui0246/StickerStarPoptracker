"""Export exact native paperization input alternatives for catalog binding."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.paperization import paperization_locks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock_table", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.lock_table.read_bytes()
    locks = paperization_locks(KdmDocument(raw))
    result = {"format_version": 1, "source_sha256": hashlib.sha256(raw).hexdigest(),
              "traversal_effects_verified": False, "locks": [asdict(lock) for lock in locks]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {len(locks)} locks with exact accepted item alternatives.")


if __name__ == "__main__":
    main()
