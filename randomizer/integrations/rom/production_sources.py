"""Assemble production check identities from the original European game.

This inventory contains native sources and reward identities, not guessed access
rules. Catalog authors must supply the independently reviewed graph. No test-room
pickups, empty chests or noncombat prop units become production checks.
"""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import re

from ...data.catalog import Json, parse_catalog
from ...domain import Event
from ...settings import Banners
from .containers import container_sources
from .doors import door_places
from .enemies import enemy_types, group_enemy_checks
from .events import KAMEK_FLAGS, SHOP_SCRIPTS, mini_stars, museum_exhibits, shop_conversation, stages
from .kdm import KdmDocument
from .ksm import KsmDocument
from .native_delivery import (
    HONORS, BannerReward, ContainerReward, EnemyReward, FlagReward, NativeReward, NativeRewardKind, PickupReward, ScriptReward,
)
from .native_generation import NativeBindings, NativeCheck, catalog_digest
from .peels import peel_sources
from .pickups import item_pickups
from .project import RomProject
from .royal_patch import FINAL_BOSS
from .scraps import audit_scrap_inventory, scrap_items, scripted_scraps
from .stickers import sticker_policy
from .switches import global_flags
from .things import scripted_things

# This below-map actor is a chest stand-in, not a second acquisition location.
OASIS_STAND_IN = ("w2_oas_02", "map_piece_c", "PK_FIELD_TOW_ENTRANCE_3")


def reward_id(reward: NativeReward) -> str:
    return f"{reward.kind.value}/{reward.value}"


@dataclass(frozen=True)
class ProductionSources:
    checks: tuple[NativeCheck, ...]
    rewards: tuple[NativeReward, ...]
    story_flags: frozenset[str]
    source_hashes: dict[str, str]

    def bind(self, catalog: Json) -> NativeBindings:
        """Require every observed check, plus explicitly fixed story observations."""
        game = parse_catalog(catalog)
        sources = {check.id: check for check in self.checks}
        rewards = {reward_id(reward): reward for reward in self.rewards}
        for item in game.items:
            if item.id.startswith("coins/"):
                amount = item.id.removeprefix("coins/")
                if not amount.isdecimal() or str(int(amount)) != amount:
                    raise ValueError("Coin reward identity requires a canonical integer amount")
                rewards[item.id] = NativeReward(NativeRewardKind.COINS, int(amount))
            if isinstance(item, Event) and item.id.startswith("event/"):
                flag = item.id.removeprefix("event/")
                if flag not in self.story_flags or item.location_id in sources:
                    raise ValueError("Fixed event must observe an original, separate story flag")
                native = NativeReward(NativeRewardKind.EVENT, flag)
                rewards[item.id] = native
                sources[item.location_id] = FlagReward("event", flag, native)
        if set(sources) != {location.id for location in game.locations}:
            raise ValueError("Production catalogs must cover every observed check and declared fixed event")
        if {item.id for item in game.items} - rewards.keys():
            raise ValueError("Production item IDs must use the observed kind/value reward identities")
        result = NativeBindings(
            {item.id: rewards[item.id] for item in game.items}, sources, catalog_digest(catalog),
        )
        result.validate(game)
        return result


def production_sources(project: RomProject, read_source: Callable[[str], str]) -> ProductionSources:
    """Read native tables and original decompiled scripts; never fill a seed."""
    hashes: dict[str, str] = {}

    def read(name: str) -> bytes:
        raw = project.read_file(name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
        return raw

    switches = KdmDocument(read("Data/kdm_switch.bin"))
    known_flags = frozenset(flag.name for flag in global_flags(switches))
    items_raw = read("Data/kdm_item_data.bin")
    items = KdmDocument(items_raw)
    policy = sticker_policy(items_raw)
    field_scraps = {item.field_item: item.inventory_item for item in scrap_items(items)}
    disposition = KdmDocument(read("Data/kdm_dispos_data.bin"))
    locks = KdmDocument(read("Data/kdm_pepalyze.bin"))
    world_stages = stages(KdmDocument(read("Data/kdm_worldmap_data.bin")))
    dummy = NativeReward(NativeRewardKind.COINS, 25)
    sources: dict[str, NativeCheck] = {}
    rewards: dict[str, NativeReward] = {}

    def add_reward(reward: NativeReward) -> None:
        rewards[reward_id(reward)] = reward

    def add(check: NativeCheck) -> None:
        previous = sources.get(check.id)
        if previous is not None and previous != check:
            raise ValueError(f"Conflicting production source: {check.id}")
        sources[check.id] = check

    for pickup in item_pickups(disposition):
        if pickup.group_name == "TST" or (pickup.map_name, pickup.object_name, pickup.item_name) == OASIS_STAND_IN:
            continue
        if pickup.item_name.startswith("REAL_") or pickup.item_name in field_scraps:
            add(PickupReward(pickup.map_name, pickup.object_name, pickup.item_name, dummy))
    for container in container_sources(disposition):
        if container.group_name != "TST":
            add(ContainerReward(container.map_name, container.object_name, container.source_item, dummy))
    for peel in peel_sources(locks):
        add(peel.check(dummy))
    files = {entry.name for entry in project.inspection.romfs}
    for filename in sorted(files):
        if not filename.startswith("Script/Map/") or not filename.endswith(".bin"):
            continue
        if filename.split("/")[2] in {"TST", "TEST", "Debug"}:
            continue
        binary = read(filename)
        source = read_source(filename)
        if re.search(r"\brando_[A-Za-z0-9_]+", source):
            raise ValueError("Production sources require original scripts, not patched research fixtures")
        map_name = filename.rsplit("/", 1)[1][:-4]
        if any(imported.name == "mobj_goal_block_exit" for imported in KsmDocument(binary).imports):
            for star in mini_stars(filename, source, binary, switches):
                add(star.placement(dummy))
                add_reward(NativeReward(NativeRewardKind.MINI_STAR, star.source_flag))
        for thing in scripted_things(map_name, source):
            add(PickupReward(thing.map_name, thing.object_name, thing.source_item, dummy))
        for scrap in scripted_scraps(map_name, source):
            if (scrap.map_name, scrap.object_name, scrap.field_item) == OASIS_STAND_IN:
                continue
            if scrap.field_item not in field_scraps:
                raise ValueError("Scripted production scrap lacks an inventory mapping")
            add(PickupReward(scrap.map_name, scrap.object_name, scrap.field_item, dummy))
        if filename in SHOP_SCRIPTS:
            shop = shop_conversation(filename, source, binary)
            add(ScriptReward("shop", filename, shop.function, dummy))
        if filename in KAMEK_FLAGS:
            flag = KAMEK_FLAGS[filename]
            if len(re.findall(r"\b" + flag + r" \*?= true;", source)) != 1 or flag not in known_flags:
                raise ValueError("Kamek completion no longer matches the original callback")
            add(FlagReward("kamek", flag, dummy))
    for world, level in ((1, 6), (2, 5), (3, 12), (4, 5), (5, 6)):
        flag = f"gf_evt_{world}_{level}_royal_seal"
        if flag not in known_flags:
            raise ValueError("Original Royal source flag is missing")
        add(FlagReward("boss", flag, dummy))
    add(ScriptReward("boss", FINAL_BOSS, "get_royal_seal_event", dummy))
    add(ScriptReward("victory", FINAL_BOSS, "koopa_battle_after_event_init", NativeReward(NativeRewardKind.VICTORY, 1)))
    for exhibit in museum_exhibits(KdmDocument(read("Data/kdm_pepalyze_museum.bin")), switches):
        add(FlagReward("museum", exhibit.completion_flag, dummy))
    for honor in sorted(HONORS):
        add(BannerReward(honor, Banners.ORIGINAL, dummy))
    native = enemy_types(read("Data/kdm_battle.bin"))
    enemy_checks = tuple(
        EnemyReward(enemy.unit_id, enemy.script_file, enemy.death_function, dummy)
        for enemy in native
        if enemy.script_file in files and enemy.death_function and enemy.name_label != "enemy_name_DOOR"
    )
    for check in group_enemy_checks(native, enemy_checks):
        add(check)
    for item in policy.generic:
        add_reward(NativeReward(NativeRewardKind.STICKER_UNLOCK, item))
        add_reward(NativeReward(NativeRewardKind.STICKER_COPY, item))
    for sticker, _ in policy.things:
        add_reward(NativeReward(NativeRewardKind.STICKER_UNLOCK, sticker))
    audit = audit_scrap_inventory(items, locks)
    if audit.unclassified:
        raise ValueError("Production scrap inventory contains unclassified descriptors")
    for item in audit.inventory_items:
        add_reward(NativeReward(NativeRewardKind.ITEM, item))
    for ability in ("hammer", "paperization"):
        add_reward(NativeReward(NativeRewardKind.ABILITY, ability))
    for stage in world_stages:
        add_reward(NativeReward(NativeRewardKind.STAGE_ACCESS, stage.code))
    for door in door_places(project.read_file("Data/kdm_pepalyze.bin"), world_stages):
        add_reward(NativeReward(NativeRewardKind.DOOR_ACCESS, door.lock_id))
    for boss in ("w1", "w2", "w3", "w4", "w5", "w6", "harbor"):
        add_reward(NativeReward(NativeRewardKind.BOSS_ACCESS, boss))
    for index in range(1, 7):
        add_reward(NativeReward(NativeRewardKind.ROYAL, index))
    for reward in (dummy, NativeReward(NativeRewardKind.PAGE, 1), NativeReward(NativeRewardKind.VICTORY, 1)):
        add_reward(reward)
    return ProductionSources(
        tuple(sources[key] for key in sorted(sources)), tuple(rewards[key] for key in sorted(rewards)), known_flags, hashes,
    )
