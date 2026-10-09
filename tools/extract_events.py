"""Extract observed stage destinations and exact mini-star checks from your ROM."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.events import (
    KAMEK_FLAGS,
    SHOP_SCRIPTS,
    mini_stars,
    museum_exhibits,
    shop_conversation,
    stages,
)
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.ksm import KsmDocument
from randomizer.integrations.rom.project import RomProject
from randomizer.integrations.rom.script_build import decompile
from randomizer.integrations.rom.enemies import enemy_types
from randomizer.integrations.rom.doors import door_places
from randomizer.integrations.rom.peels import peel_sources
from randomizer.integrations.rom.containers import container_sources
from randomizer.integrations.rom.pickups import item_pickups
from randomizer.integrations.rom.things import SCRIPTED_THING_SCRIPTS, scripted_things


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output file to preserve prior manifests")
    project = RomProject(args.rom)
    compiler = args.compiler.resolve(strict=True)
    switches = KdmDocument(project.read_file("Data/kdm_switch.bin"))
    checks = []
    shops = []
    kamek = []
    things = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".event-survey-", dir=args.output.parent) as directory:
        for filename in sorted(SHOP_SCRIPTS.keys() | KAMEK_FLAGS.keys() | set(SCRIPTED_THING_SCRIPTS.values())):
            binary = project.read_file(filename)
            script = decompile(project, filename, Path(directory), compiler)
            source = script.source.read_text(encoding="utf-8")
            if filename in SCRIPTED_THING_SCRIPTS.values():
                things.extend(asdict(entry) for entry in scripted_things(filename.rsplit("/", 1)[1][:-4], source))
            if filename in SHOP_SCRIPTS:
                shop = shop_conversation(filename, source, binary)
                shops.append({"id": shop.id, **asdict(shop)})
            if filename in KAMEK_FLAGS:
                import re

                flag = KAMEK_FLAGS[filename]
                if len(re.findall(r"\b" + flag + r" \*?= true;", source)) != 1:
                    raise ValueError("Kamek completion flag is missing or ambiguous")
                kamek.append(
                    {
                        "id": f"kamek/{flag}",
                        "source_flag": flag,
                        "script_file": filename,
                        "source_sha256": hashlib.sha256(binary).hexdigest(),
                    }
                )
        for entry in project.inspection.romfs:
            if not entry.name.startswith("Script/Map/") or not entry.name.endswith(".bin"):
                continue
            binary = project.read_file(entry.name)
            parsed = KsmDocument(binary)
            if not any(imported.name == "mobj_goal_block_exit" for imported in parsed.imports):
                continue
            script = decompile(project, entry.name, Path(directory), compiler)
            checks.extend(mini_stars(entry.name, script.source.read_text(encoding="utf-8"), binary, switches))
    if not checks or len({check.id for check in checks}) != len(checks):
        raise ValueError("Mini-star registry is empty or ambiguous")
    world_stages = stages(KdmDocument(project.read_file("Data/kdm_worldmap_data.bin")))
    script_files = {entry.name for entry in project.inspection.romfs}
    disposition = KdmDocument(project.read_file("Data/kdm_dispos_data.bin"))
    pickups = item_pickups(disposition)
    containers = container_sources(disposition)
    data = {
        "format_version": 1,
        "title_id": project.inspection.title_id,
        "verified_access_rules": False,
        "shops": shops,
        "kamek": kamek,
        "enemy_types": [
            {
                **asdict(enemy),
                "script_present": enemy.script_file in script_files,
                "has_death_hook": bool(enemy.death_function),
            }
            for enemy in enemy_types(project.read_file("Data/kdm_battle.bin"))
        ],
        "pickups": [asdict(source) for source in pickups if source.group_name != "TST"],
        "scripted_things": things,
        "excluded_debug_pickups": [asdict(source) for source in pickups if source.group_name == "TST"],
        "container_sources": [asdict(source) for source in containers if source.group_name != "TST"],
        "excluded_debug_containers": [asdict(source) for source in containers if source.group_name == "TST"],
        "peeled_scraps": [asdict(source) for source in peel_sources(KdmDocument(project.read_file("Data/kdm_pepalyze.bin")))],
        "door_places": [asdict(place) for place in door_places(project.read_file("Data/kdm_pepalyze.bin"), world_stages)],
        "museum": [
            {"id": exhibit.id, **asdict(exhibit)}
            for exhibit in museum_exhibits(KdmDocument(project.read_file("Data/kdm_pepalyze_museum.bin")), switches)
        ],
        "stages": [asdict(stage) for stage in world_stages],
        "mini_stars": [{"id": check.id, **asdict(check)} for check in sorted(checks, key=lambda check: check.id)],
    }
    data["manifest_hash"] = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(data, indent=2) + "\n")
    print(f"Extracted {len(checks)} mini-star checks and {len(data['stages'])} stage destinations")


if __name__ == "__main__":
    main()
