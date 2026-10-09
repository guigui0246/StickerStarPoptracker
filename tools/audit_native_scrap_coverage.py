"""Audit native scrap descriptors against field and peel source hooks.

Restoration transformations and Wiggler story inputs are evidence, not guessed
additional locations or verified traversal rules.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.native_delivery import PickupReward, ContainerReward, PeelReward
from randomizer.integrations.rom.plan_io import checks
from randomizer.integrations.rom.project import RomProject
from randomizer.integrations.rom.scraps import audit_scrap_inventory, scrap_items
from randomizer.integrations.rom.peels import peel_sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output file")
    project = RomProject(args.rom)
    names = ("Data/kdm_item_data.bin", "Data/kdm_pepalyze.bin")
    raw = {name: project.read_file(name) for name in names}
    items, puzzles = (KdmDocument(raw[name]) for name in names)
    audit = audit_scrap_inventory(items, puzzles)
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    selected = checks(report["checks"])
    field_hooks = {check.source_item for check in selected if isinstance(check, (PickupReward, ContainerReward))}
    peel_hooks = {
        (check.map_name, variant.lock_id, variant.source_item)
        for check in selected
        if isinstance(check, PeelReward)
        for variant in check.hooks
    }
    missing_fields = sorted(entry.field_item for entry in scrap_items(items) if entry.field_item not in field_hooks)
    missing_peels = sorted(
        (source.map_name, variant.lock_id, variant.source_item)
        for source in peel_sources(puzzles)
        for variant in source.variants
        if (source.map_name, variant.lock_id, variant.source_item) not in peel_hooks
    )
    result = {
        "title_id": project.inspection.title_id,
        "descriptors": asdict(audit),
        "source_hashes": {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()},
        "unhooked_field_reward_families": missing_fields,
        "unhooked_peel_variants": missing_peels,
        "story_acquisition_verified": False,
        "physical_sources_verified": False,
        "progression_verified": False,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "inventory_descriptors": len(audit.inventory_items),
                "field_rewards": len(audit.field_rewards),
                "peeled_rewards": len(audit.peeled_rewards),
                "restoration_inputs": len(audit.restoration_inputs),
                "story_inputs": len(audit.story_inputs),
                "unclassified": len(audit.unclassified),
                "unhooked_field_families": len(missing_fields),
                "unhooked_peels": len(missing_peels),
            }
        )
    )
    if audit.unclassified or missing_fields or missing_peels:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
