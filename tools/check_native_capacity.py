"""Measure network-only check storage from actual native patch reports.

This checks storage feasibility, not progression or enemy-type classification.
Reports are read only; no game files, memory or saves are modified.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.native_delivery import NativeReward, NativeRewardKind, PickupReward, ScriptReward
from randomizer.integrations.rom.events import SHOP_SCRIPTS
from randomizer.integrations.rom.events import stages, mini_stars
from randomizer.integrations.rom.ksm import KsmDocument
from randomizer.integrations.rom.script_build import decompile
from randomizer.integrations.rom.scraps import scrap_items
import tempfile
from randomizer.integrations.rom.doors import door_places
from randomizer.integrations.rom.mailbox import RemoteReward
from randomizer.integrations.rom.stickers import sticker_policy
from randomizer.settings import AlbumPages
from randomizer.integrations.rom.plan_io import checks, decode_plan, encode_plan
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.pickups import item_pickups
from randomizer.integrations.rom.project import RomProject


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--base", type=Path, required=True, help="Report supplying incoming rewards, session and settings")
    parser.add_argument("--output", type=Path, help="Write an explicit experimental combined plan to a new file")
    parser.add_argument("--rom-pickups", type=Path, help="Include all observed Thing and scrap dispositions from your ROM")
    parser.add_argument("--exercise-rewards", action="store_true", help="Exercise all observed capability/unlock rewards with provisional selectors; not an AP seed")
    parser.add_argument("--compiler", type=Path, help="Include exact mini-star reward routes when exercising all native reward kinds")
    args = parser.parse_args()
    base_data = json.loads(args.base.read_text(encoding="utf-8"))
    keys = ("checks", "album_pages", "shuffle_royals", "remote_rewards", "remote_session", "sticker_policy", "skip_opening", "skip_dialogue", "seed_name")
    base_fields = {key: base_data.get(key) for key in keys}
    base_fields["starting_rewards"] = base_data.get("starting_rewards", [])
    base_fields["starting_item_ids"] = base_data.get("starting_item_ids", [])
    for key in ("skip_opening", "skip_dialogue"):
        base_fields[key] = base_data.get("presentation", {}).get(key, True)
    base = decode_plan(base_fields)
    if base.remote_session is None or not base.remote_rewards:
        parser.error("Base report must contain a bound incoming mailbox")
    merged = {}
    excluded_shops = set()
    for path in args.reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("title_id") != "00040000000A5F00":
            parser.error(f"Unsupported report title: {path}")
        for check in checks(report["checks"]):
            if isinstance(check, ScriptReward) and check.category == "shop" and SHOP_SCRIPTS.get(check.script_file, (None, None))[1] != check.function:
                excluded_shops.add(check.id)
                continue
            # Victory stays tied to Bowser's actual win, not a network reward.
            network = check if check.reward.kind == NativeRewardKind.VICTORY else replace(check, reward=NativeReward(NativeRewardKind.REMOTE, base.remote_session.slot))
            if network.id in merged and merged[network.id] != network:
                parser.error(f"Conflicting native check identity: {network.id}")
            merged[network.id] = network
    if args.rom_pickups:
        project = RomProject(args.rom_pickups)
        for pickup in item_pickups(KdmDocument(project.read_file("Data/kdm_dispos_data.bin"))):
            if not pickup.item_name.startswith(("REAL_", "PK_")):
                continue
            network = PickupReward(pickup.map_name, pickup.object_name, pickup.item_name,
                                   NativeReward(NativeRewardKind.REMOTE, base.remote_session.slot))
            if network.id in merged and merged[network.id] != network:
                parser.error(f"Ambiguous pickup identity: {network.id}")
            merged[network.id] = network
    plan = replace(base, checks=tuple(merged.values()), shuffle_royals=False,
                   seed_name=base.remote_session.seed)
    if args.exercise_rewards:
        if not args.rom_pickups:
            parser.error("Reward exercise requires --rom-pickups")
        project = RomProject(args.rom_pickups)
        policy = sticker_policy(project.read_file("Data/kdm_item_data.bin"))
        world_stages = stages(KdmDocument(project.read_file("Data/kdm_worldmap_data.bin")))
        doors = door_places(project.read_file("Data/kdm_pepalyze.bin"), world_stages)
        rewards = [NativeReward(NativeRewardKind.STICKER_UNLOCK, item) for item in policy.generic]
        rewards += [NativeReward(NativeRewardKind.STICKER_UNLOCK, sticker) for sticker, _ in policy.things]
        rewards += [NativeReward(NativeRewardKind.STAGE_ACCESS, stage.code) for stage in world_stages if (stage.world > 0 and stage.level > 0) or stage.code in {"X00", "X01"}]
        rewards += [NativeReward(NativeRewardKind.DOOR_ACCESS, code) for code in sorted({place.stage_code for place in doors})]
        rewards += [NativeReward(NativeRewardKind.BOSS_ACCESS, code) for code in ("w1", "w2", "w3", "w4", "w5", "w6", "harbor")]
        rewards += [NativeReward(NativeRewardKind.ROYAL, index) for index in range(1, 7)]
        rewards += [NativeReward(NativeRewardKind.PAGE, 1)]
        # Scraps use the native key-item inventory, not generic sticker flags.
        rewards += [scrap.reward for scrap in scrap_items(KdmDocument(project.read_file("Data/kdm_item_data.bin")))]
        if args.compiler:
            switches = KdmDocument(project.read_file("Data/kdm_switch.bin"))
            with tempfile.TemporaryDirectory(prefix=".reward-routes-", dir=args.output.parent if args.output else None) as directory:
                for entry in project.inspection.romfs:
                    if not entry.name.startswith("Script/Map/") or not entry.name.endswith(".bin"):
                        continue
                    binary = project.read_file(entry.name)
                    if not any(imported.name == "mobj_goal_block_exit" for imported in KsmDocument(binary).imports):
                        continue
                    script = decompile(project, entry.name, Path(directory), args.compiler.resolve(strict=True))
                    rewards += [NativeReward(NativeRewardKind.MINI_STAR, check.source_flag)
                                for check in mini_stars(entry.name, script.source.read_text(encoding="utf-8"), binary, switches)]
        registered = {(entry.reward.kind, entry.reward.value) for entry in base.remote_rewards}
        selectors = list(base.remote_rewards)
        next_id = max(entry.item_id for entry in selectors) + 1
        for item in rewards:
            if (item.kind, item.value) not in registered:
                selectors.append(RemoteReward(next_id, item))
                registered.add((item.kind, item.value))
                next_id += 1
        plan = replace(plan, remote_rewards=tuple(selectors), sticker_policy=policy,
                       album_pages=AlbumPages.RANDOMIZED, shuffle_royals=True)
    required = len(plan.flags)
    available = 2560 - 1446
    print(json.dumps({"checks": len(plan.checks), "allocated_bits": required,
                      "available_bits": available, "remaining_bits": available - required,
                      "excluded_obsolete_shop_hooks": sorted(excluded_shops),
                      "incoming_selectors": len(plan.remote_rewards),
                      "provisional_reward_exercise": args.exercise_rewards,
                      "fits": required <= available, "progression_verified": False}, indent=2))
    if required > available:
        raise SystemExit(1)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(encode_plan(plan), stream, indent=2)


if __name__ == "__main__":
    main()
