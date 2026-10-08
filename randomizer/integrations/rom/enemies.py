"""Observed native enemy types and victory-only collection hooks."""

from dataclasses import dataclass
import json

from .kdm import KdmDocument, KdmPointer
from .native_delivery import DeliveryPlan, EnemyReward
from .pickups import record, text
from .script_build import prepend_body

PLAYER_SCRIPT = "Script/Battle/Player/btl_mario.bin"
WIN_SCRIPT = "Script/Battle/Event/btl_win.bin"


@dataclass(frozen=True)
class EnemyType:
    unit_id: str
    name_label: str
    script_file: str
    death_function: str
    init_function: str = ""


def enemy_types(data: bytes) -> tuple[EnemyType, ...]:
    document = KdmDocument(data)
    result = []
    for reference in document.tables["unitDataTable"].values:
        if not isinstance(reference.value, KdmPointer):
            raise ValueError("Expected a native unit pointer")
        if not reference.value.address:
            continue
        array = document.pointed_array(reference.value)
        if array.type_id != 40 or len(array.values) != 1 or array.field_count != 44:
            raise ValueError("Unsupported native enemy schema")
        fields = record(array.values[0], 44)
        script = text(fields[3])
        if not script.startswith("Enemy/"):
            continue
        result.append(EnemyType(text(fields[0]), text(fields[1]), "Script/Battle/" + script + ".bin", text(fields[16]), text(fields[4])))
    if not result or len({enemy.unit_id for enemy in result}) != len(result):
        raise ValueError("Native enemy identities are missing or duplicated")
    return tuple(result)


def death_hook(source: str, function: str, checks: list[tuple[int, EnemyReward]], plan: DeliveryPlan) -> str:
    lines = ["\ttemp tempVar90 = rando_seed_valid*();", "\tif ( tempVar90 ) {",
             "\t\ttemp tempVar91 = battle_unit_get_hp*(self);", "\t\tif ( tempVar91 <= 0 ) {",
             "\t\t\ttemp tempVar92 = battle_unit_get_unit_data_id*(self);"]
    for index, check in checks:
        lines.extend([f"\t\t\tif ( tempVar92 == {json.dumps(check.unit_id, ensure_ascii=False)} ) {{",
                      f"\t\t\t\t{plan.enemy_pending(index)} *= true;", "\t\t\t}"])
    lines.extend(["\t\t}", "\t}"])
    return prepend_body(source, function, "\n".join(lines) + "\n")


def reset_hook(source: str, plan: DeliveryPlan) -> str:
    lines = ["\ttemp tempVar90 = rando_seed_valid*();", "\tif ( tempVar90 ) {"]
    lines.extend(f"\t\t{flag} *= false;" for flag in plan.enemy_pending_flags)
    lines.append("\t}")
    return prepend_body(source, "init", "\n".join(lines) + "\n")


def victory_hook(source: str, plan: DeliveryPlan) -> str:
    lines = ["\ttemp tempVar90 = rando_seed_valid*();", "\tif ( tempVar90 ) {",
             "\t\ttempVar90 = battle_is_museum*();", "\t\tif ( tempVar90 == false ) {"]
    for index, check in enumerate(plan.checks):
        if isinstance(check, EnemyReward):
            checked, _ = plan.receipt(index)
            lines.extend([f"\t\t\tif ( {plan.enemy_pending(index)} ) {{", f"\t\t\t\t{checked} *= true;", "\t\t\t}"])
    lines.append("\t\t}")
    lines.extend(f"\t\t{flag} *= false;" for flag in plan.enemy_pending_flags)
    lines.append("\t}")
    # Collection only; the overworld poll grants rewards after battle teardown.
    return prepend_body(source, "battle_win_event", "\n".join(lines) + "\n")
