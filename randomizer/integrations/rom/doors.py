"""Observed Secret Door placements and ownership checks before fit commit."""

from dataclasses import dataclass
import re

from .events import Stage
from .kdm import KdmDocument
from .native_delivery import DeliveryPlan
from .pickups import record, text

PAPERIZATION_SCRIPT = "Script/ksm_pepalyze.bin"
DOOR_IMPORT_SCRIPT = "Script/Map/HEI/hei_3_01.bin"


@dataclass(frozen=True)
class DoorPlace:
    lock_id: str
    map_name: str
    stage_code: str
    completion_flag: str


def door_places(data: bytes, world_stages: tuple[Stage, ...]) -> tuple[DoorPlace, ...]:
    numbered = tuple(stage for stage in world_stages if stage.world > 0 and stage.level > 0)
    result = []
    for array in KdmDocument(data).arrays.values():
        if array.type_id != 21 or array.field_count != 72:
            continue
        for row in array.values:
            fields = record(row, 72)
            if "SL_DOOR" not in {text(field) for field in fields[60:]}:
                continue
            map_name = text(fields[11])
            prefix = map_name.rsplit("_", 1)[0]
            matches = [
                stage
                for stage in numbered
                if prefix in {stage.map_name.rsplit("_", 1)[0], stage.alternate_map.rsplit("_", 1)[0]}
            ]
            if len(matches) != 1:
                raise ValueError(f"Secret Door map does not identify one native stage: {map_name}")
            result.append(DoorPlace(text(fields[0]), map_name, matches[0].code, text(fields[44]).lower()))
    if not result or len({place.lock_id for place in result}) != len(result):
        raise ValueError("Secret Door identities are missing or duplicated")
    return tuple(sorted(result, key=lambda place: place.lock_id))


def door_access_key(plan: DeliveryPlan, place: DoorPlace) -> str | None:
    exact = place.lock_id in plan.door_access_codes
    stage = place.stage_code in plan.door_access_codes
    if exact and stage:
        raise ValueError("Exact and stage-wide Secret Door rewards overlap")
    return place.lock_id if exact else place.stage_code if stage else None


def validate_door_access(plan: DeliveryPlan, places: tuple[DoorPlace, ...]) -> None:
    known = {place.lock_id for place in places} | {place.stage_code for place in places}
    if set(plan.door_access_codes) - known:
        raise ValueError("Door admission reward references an unobserved Secret Door")
    for place in places:
        door_access_key(plan, place)


def gate_door_fit(source: str, plan: DeliveryPlan, places: tuple[DoorPlace, ...], *, shared_seed: bool = False) -> str:
    # The existing miss path traces the placement and takes the selected sticker
    # back. The successful fit routine (which sets native completion flags) is
    # never reached for an unowned place. Other paperization modes are retained.
    validate_door_access(plan, places)
    pattern = r"\bdecal_dokodemo_mario_control_main\*?\(\)"
    if len(re.findall(pattern, source)) != 3:
        raise ValueError("Paperization control flow no longer matches the inspected revision")
    source = re.sub(pattern, "rando_door_control*()", source)
    lines = [
        "private rando_door_control()  {",
        "\ttemp tempVar0 = decal_dokodemo_mario_control_main*();",
        "\ttemp tempVar1 = pepalyze_get_mode*();",
        "\tif ( tempVar1 != pepalyze_mode_unlock ) {\n\t\treturn* tempVar0;\n\t}",
        "\tif ( tempVar0 == pepalyze_select_cancel || tempVar0 == pepalyze_"
        "cancel || tempVar0 == pepalyze_miss || tempVar0 == pepalyze_area_"
        "out_miss || tempVar0 == pepalyze_miss_mappiece ) {\n\t\treturn* temp"
        "Var0;\n\t}",
        "\ttempVar1 = rando_seed_valid*();",
        "\tif ( tempVar1 == false ) {\n\t\treturn* pepalyze_miss;\n\t}",
        "\ttemp tempVar2 = pouch_get_map_name*();",
    ]
    for place in places:
        key = door_access_key(plan, place)
        if key is None:
            continue
        lines.extend(
            [
                f'\tif ( tempVar2 == "{place.map_name}" && gf_rando_door_{key.lower()} == false ) {{',
                f'\t\ttempVar1 = pepalyze_is_now_play_unlock*("{place.lock_id}");',
                "\t\tif ( tempVar1 ) {\n\t\t\treturn* pepalyze_miss;\n\t\t}",
                "\t}",
            ]
        )
    lines.extend(["\treturn* tempVar0;", "}"])
    return source + "\n" + "\n".join(lines) + "\n" + ("" if shared_seed else plan.seed_function())
