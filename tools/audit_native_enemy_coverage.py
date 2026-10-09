"""Audit all native formations against an explicit compiled combat-check plan.

Includes debug tables as evidence without making them accessible game checks.
Unavailable script records and units without death callbacks stay explicit.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.battle_formations import battle_formations
from randomizer.integrations.rom.enemies import enemy_types, group_enemy_checks
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.native_delivery import EnemyReward
from randomizer.integrations.rom.plan_io import checks
from randomizer.integrations.rom.project import RomProject


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = RomProject(args.rom)
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    selected = tuple(check for check in checks(report["checks"]) if isinstance(check, EnemyReward))
    hooks = {hook.unit_id for check in selected for hook in check.hooks}
    native = {enemy.unit_id: enemy for enemy in enemy_types(project.read_file("Data/kdm_battle.bin"))}
    group_enemy_checks(tuple(native.values()), selected)
    represented = {native[unit].name_label for unit in hooks}
    files = {entry.name for entry in project.inspection.romfs}
    formations = []
    occurrences: dict[str, list[str]] = {}
    hashes = {}
    for name in sorted(files):
        if not name.startswith("Data/kdm_battle_set_") or not name.endswith(".bin"):
            continue
        raw = project.read_file(name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
        for formation in battle_formations(KdmDocument(raw)):
            identity = f"{name}/{formation.id}"
            formations.append({"table": name, **asdict(formation)})
            for unit in set(formation.units):
                if unit not in native:
                    raise ValueError(f"Formation {identity} references an unknown enemy unit")
                occurrences.setdefault(unit, []).append(identity)
    missing_types = sorted({native[unit].name_label for unit in occurrences}
                           - represented - {"enemy_name_DOOR"})
    missing_hooks = sorted(unit for unit in occurrences if unit not in hooks
                           and native[unit].script_file in files and native[unit].death_function
                           and native[unit].name_label != "enemy_name_DOOR")
    result = {"format_version": 1, "source_hashes": hashes,
              "encounter_access_verified": False, "formations": formations,
              "unrepresented_formation_types": missing_types,
              "unhooked_available_formation_variants": missing_hooks,
              "units": [{**asdict(enemy), "formations": occurrences.get(unit, []),
                         "selected_hook": unit in hooks,
                         "script_available": enemy.script_file in files,
                         "type_represented": enemy.name_label in represented}
                        for unit, enemy in sorted(native.items())]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Audited {len(formations)} formations, {len(occurrences)} referenced units and {len(represented)} selected types.")
    print(f"Unrepresented combat types: {len(missing_types)}; unhooked available variants: {len(missing_hooks)}.")
    if missing_types or missing_hooks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
