"""Add source-bound, explicitly reviewed native traversal rules to a typed catalog."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.data.native_routes import apply_native_routes
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.room_links import room_links
from randomizer.integrations.rom.seed_patch import unique_object


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--link-table", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
        review = json.loads(args.review.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
        raw = args.link_table.read_bytes()
        result = apply_native_routes(catalog, room_links(KdmDocument(raw)), review, hashlib.sha256(raw).hexdigest())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError) as error:
        parser.exit(2, f"Cannot compile native catalog: {error}\n")


if __name__ == "__main__":
    main()
