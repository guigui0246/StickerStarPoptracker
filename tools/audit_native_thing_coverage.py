"""Audit production Thing checks, including scripted rewards and debug exclusions."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.native_delivery import PickupReward
from randomizer.integrations.rom.pickups import item_pickups
from randomizer.integrations.rom.plan_io import checks
from randomizer.integrations.rom.project import RomProject
from randomizer.integrations.rom.script_build import decompile
from randomizer.integrations.rom.stickers import sticker_policy
from randomizer.integrations.rom.things import SCRIPTED_THING_SCRIPTS, scripted_things


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output file")
    project = RomProject(args.rom)
    raw = project.read_file("Data/kdm_dispos_data.bin")
    policy = sticker_policy(project.read_file("Data/kdm_item_data.bin"))
    pickups = tuple(entry for entry in item_pickups(KdmDocument(raw)) if entry.item_name.startswith("REAL_"))
    ordinary = tuple(entry for entry in pickups if entry.group_name != "TST")
    debug = tuple(entry for entry in pickups if entry.group_name == "TST")
    selected = checks(json.loads(args.patch_report.read_text(encoding="utf-8"))["checks"])
    hooked = {(entry.map_name, entry.object_name, entry.source_item) for entry in selected if isinstance(entry, PickupReward)}
    source_hashes = {"Data/kdm_dispos_data.bin": hashlib.sha256(raw).hexdigest()}
    scripted = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".thing-audit-", dir=args.output.parent) as directory:
        for map_name, filename in SCRIPTED_THING_SCRIPTS.items():
            script = decompile(project, filename, Path(directory), args.compiler.resolve(strict=True))
            scripted.extend(scripted_things(map_name, script.source.read_text(encoding="utf-8")))
            source_hashes[filename] = script.original_sha256
    sources = {(entry.map_name, entry.object_name, entry.item_name) for entry in ordinary}
    sources.update((entry.map_name, entry.object_name, entry.source_item) for entry in scripted)
    debug_sources = {(entry.map_name, entry.object_name, entry.item_name) for entry in debug}
    missing = sorted(sources - hooked)
    incorrectly_included = sorted(debug_sources & hooked)
    missing_types = sorted({real for _, real in policy.things} - {item for _, _, item in sources})
    data = {"title_id": project.inspection.title_id, "source_hashes": source_hashes,
            "production_disposition_sources": [asdict(entry) for entry in ordinary],
            "scripted_sources": [asdict(entry) for entry in scripted],
            "excluded_debug_sources": [asdict(entry) for entry in debug],
            "unhooked_production_sources": missing, "included_debug_sources": incorrectly_included,
            "unrepresented_thing_types": missing_types,
            "physical_sources_verified": False, "progression_verified": False}
    args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"production_sources": len(sources), "production_types": len({item for _, _, item in sources}),
                      "excluded_debug_sources": len(debug), "unhooked_sources": len(missing),
                      "included_debug_sources": len(incorrectly_included), "unrepresented_types": len(missing_types)}))
    if missing or incorrectly_included or missing_types:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
