"""Update binding identity after editing logic, without rereading the ROM.

Only graph rules, names, regions and the pool may change. Native item/location
identities remain fixed. New native sources must instead use `catalog bind`.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.data.catalog import Json, load_catalog_data, obj, parse_catalog
from randomizer.integrations.rom.native_generation import NativeBindings, catalog_digest


def rebind(previous: Json, updated: Json, raw_bindings: Json) -> dict[str, Json]:
    original = NativeBindings.parse(raw_bindings, previous)
    original.validate(parse_catalog(previous))
    # validate enforces the exact native identities and fixed event/victory
    # contracts before the new digest can be stamped onto an existing binding.
    rebound = replace(original, catalog_hash=catalog_digest(updated))
    rebound.validate(parse_catalog(updated))
    result = dict(obj(raw_bindings))
    result["catalog_sha256"] = rebound.catalog_hash
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-catalog", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--bindings", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = rebind(
        load_catalog_data(args.previous_catalog), load_catalog_data(args.catalog), load_catalog_data(args.bindings),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
