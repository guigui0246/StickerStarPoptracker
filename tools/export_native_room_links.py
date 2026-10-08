"""Export exact native connection evidence without assuming traversal requirements."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.room_links import room_links


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_table", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.link_table.read_bytes()
    links = room_links(KdmDocument(raw))
    result = {"format_version": 1, "source_sha256": hashlib.sha256(raw).hexdigest(),
              "access_rules_verified": False,
              "links": [{"id": link.id, **asdict(link)} for link in links]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(links)} directed records across {len({link.source_room for link in links})} room groups.")


if __name__ == "__main__":
    main()
