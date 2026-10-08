"""Observed game event identities, without guessing access requirements."""

from dataclasses import dataclass
import hashlib
import re

from .kdm import KdmDocument
from .native_delivery import GoalBlockReward, NativeReward, NativeRewardKind
from .pickups import integer, record, text
from .switches import global_flags


SHOP_SCRIPTS = {
    "Script/Map/MAC/mac_1_00.bin": ("SHOP_TOWN", "talk_kinopio_shop"),
    "Script/Map/IWA/iwa_4_02.bin": ("SHOP_IWA", "talk_kinopio1"),
    "Script/Map/W3_DOR/w3_dor_00.bin": ("SHOP_DOR", "talk_kinopio_shop"),
    "Script/Map/W4_SHO/w4_sho_00.bin": ("SHOP_SNOW", "talk_kinopio_shop"),
    "Script/Map/W5_BOS/w5_bos_04.bin": ("SHOP_KAZAN", "talk_kinopio_shop"),
    "Script/Map/MAC/mac_1_05.bin": ("SHOP_MONO", "talk_kinopio_mono"),
}
KAMEK_FLAGS = {
    "Script/Map/HEI/hei_2_01.bin": "gf_evt_1_3_kameck_battle",
    "Script/Map/W2_YOS/w2_yos_01.bin": "gf_evt_2_2_kameck_battle",
    "Script/Map/W6_BOS/w6_bos_01.bin": "gf_evt_6_3_kameck",
}


@dataclass(frozen=True)
class ShopConversation:
    script_file: str
    shop: str
    function: str
    source_sha256: str

    @property
    def id(self) -> str:
        return f"shop/{self.script_file}/{self.function}"


def shop_conversation(script_file: str, source: str, binary: bytes) -> ShopConversation:
    shop, function = SHOP_SCRIPTS[script_file]
    if len(re.findall(r"\bprivate " + re.escape(function) + r"\(", source)) != 1:
        raise ValueError("Shop does not have one observed conversation callback")
    if shop == "SHOP_MONO":
        if "ui_monoshop_load" not in source:
            raise ValueError("Thing shop initialization is missing")
    elif source.count(f'"{shop}"') != 1:
        raise ValueError("Shop stock binding is missing or ambiguous")
    return ShopConversation(script_file, shop, function, hashlib.sha256(binary).hexdigest())


@dataclass(frozen=True)
class MiniStarCheck:
    map_name: str
    source_flag: str
    script_file: str
    source_sha256: str

    @property
    def id(self) -> str:
        return f"mini_star/{self.map_name}/{self.source_flag.lower()}"

    def placement(self, reward: NativeReward | None = None) -> GoalBlockReward:
        return GoalBlockReward(self.map_name, self.source_flag,
                               reward or NativeReward(NativeRewardKind.MINI_STAR, self.source_flag))


@dataclass(frozen=True)
class Stage:
    code: str
    map_name: str
    alternate_map: str
    entrance: str
    world: int
    level: int


@dataclass(frozen=True)
class MuseumExhibit:
    lock_id: str
    map_name: str
    object_name: str
    completion_flag: str
    accepted_stickers: tuple[str, ...]

    @property
    def id(self) -> str:
        return f"museum/{self.completion_flag}"


def museum_exhibits(document: KdmDocument, switches: KdmDocument) -> tuple[MuseumExhibit, ...]:
    known = {flag.name for flag in global_flags(switches)}
    result: dict[str, MuseumExhibit] = {}
    for table in document.arrays.values():
        if table.type_id != 21 or table.field_count != 72:
            continue
        for row in table.values:
            values = record(row, 72)
            lock_id = text(values[0])
            if "_test_" in lock_id:
                continue
            if not re.fullmatch(r"museum_(?:btl|robj)_[0-9]{2}_[0-9]{2}", lock_id):
                raise ValueError("Unknown museum record identity")
            flag = text(values[44]).lower()
            if not re.fullmatch(r"gf_museum_(?:btl|robj)_seal_[0-9]{3}", flag) or flag not in known:
                raise ValueError("Museum record lacks a registered donation flag")
            exhibit = MuseumExhibit(lock_id, text(values[11]), text(values[46]), flag,
                                    tuple(text(value) for value in values[60:] if text(value)))
            if not exhibit.accepted_stickers:
                raise ValueError("Museum exhibit has no accepted sticker")
            if flag in result and result[flag] != exhibit:
                raise ValueError("Museum exhibits share a conflicting donation identity")
            result[flag] = exhibit
    if not result:
        raise ValueError("Museum registry is empty")
    return tuple(result[flag] for flag in sorted(result))


def stages(document: KdmDocument) -> tuple[Stage, ...]:
    if document.structures[23].fields != (3, 3, 3, 1, 1) or document.structures[24].fields != (3, 15, 1):
        raise ValueError("Unsupported world-map schema")
    result: dict[str, Stage] = {}
    for table in document.arrays.values():
        if table.type_id != 24:
            continue
        for row in table.values:
            values = record(row, 3)
            code = text(values[0])
            from .pickups import pointer
            target = pointer(values[1])
            if not target.address:
                continue
            for entry in document.pointed_array(target).values:
                fields = record(entry, 5)
                stage = Stage(code, text(fields[0]), text(fields[1]), text(fields[2]), integer(fields[3]), integer(fields[4]))
                if code in result and result[code] != stage:
                    raise ValueError("Stage code has conflicting destinations")
                result[code] = stage
    return tuple(result[code] for code in sorted(result))


def mini_stars(script_file: str, source: str, binary: bytes,
               switches: KdmDocument) -> tuple[MiniStarCheck, ...]:
    if not re.fullmatch(r"Script/Map/[A-Za-z0-9_]+/[a-z0-9_]+\.bin", script_file):
        raise ValueError("Expected an original map script path")
    map_name = script_file.rsplit("/", 1)[1][:-4]
    known = {flag.name for flag in global_flags(switches)}
    digest = hashlib.sha256(binary).hexdigest()
    pattern = r'\bmobj_goal_block_exit\*?\(self, "(GF_WM_[A-F][0-9]{2}_[A-F][0-9]{2})"\);'
    matches = re.findall(pattern, source)
    if len(matches) != len(set(matches)):
        raise ValueError("A map reuses a mini-star identity; explicit disambiguation is required")
    if any(flag.lower() not in known for flag in matches):
        raise ValueError("Mini-star event refers to an unregistered save flag")
    return tuple(MiniStarCheck(map_name, flag, script_file, digest) for flag in sorted(matches))
