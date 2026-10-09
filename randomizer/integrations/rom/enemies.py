"""Observed native enemy types and victory-only collection hooks."""

from dataclasses import dataclass
import json

from .kdm import KdmDocument, KdmPointer
from .native_delivery import DeliveryPlan, EnemyReward, EnemyVariant, NativeReward
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
        result.append(
            EnemyType(text(fields[0]), text(fields[1]), "Script/Battle/" + script + ".bin", text(fields[16]), text(fields[4]))
        )
    if not result or len({enemy.unit_id for enemy in result}) != len(result):
        raise ValueError("Native enemy identities are missing or duplicated")
    return tuple(result)


def group_enemy_checks(native: tuple[EnemyType, ...], checks: tuple[EnemyReward, ...]) -> tuple[EnemyReward, ...]:
    """Group explicitly selected combat hooks by the game's displayed type.

    Selection stays explicit: props and unobserved/debug-only hooks are never
    invented. Every included variant retains its native callback, but all
    callbacks in a named type share one pending flag and one saved receipt.
    Run before placement; conflicting rewards cannot be silently discarded.
    """
    by_unit = {enemy.unit_id: enemy for enemy in native}
    groups: dict[str, list[EnemyVariant]] = {}
    rewards: dict[str, NativeReward] = {}
    selected: set[str] = set()
    for check in checks:
        for hook in check.hooks:
            enemy = by_unit.get(hook.unit_id)
            if enemy is None or (hook.script_file, hook.function) != (enemy.script_file, enemy.death_function):
                raise ValueError("Enemy grouping requires observed native combat hooks")
            if hook.unit_id in selected:
                raise ValueError("Enemy variants cannot occur in multiple checks")
            selected.add(hook.unit_id)
            label = enemy.name_label
            if label == "enemy_name_DOOR":
                raise ValueError("Door, candle and Peach prop units are not combat enemy types")
            if label in rewards and rewards[label] != check.reward:
                raise ValueError("Group enemies before placement; conflicting rewards cannot be merged")
            rewards[label] = check.reward
            groups.setdefault(label, []).append(hook)
    result = []
    for label, variants in sorted(groups.items()):
        variants.sort(key=lambda variant: variant.unit_id)
        first = variants[0]
        result.append(
            EnemyReward(first.unit_id, first.script_file, first.function, rewards[label], label, tuple(variants[1:]))
        )
    return tuple(result)


def death_hook(source: str, function: str, checks: list[tuple[int, EnemyReward]], plan: DeliveryPlan) -> str:
    lines = [
        "\ttemp tempVar90 = rando_seed_valid*();",
        "\tif ( tempVar90 ) {",
        "\t\ttemp tempVar91 = battle_unit_get_hp*(self);",
        "\t\tif ( tempVar91 <= 0 ) {",
        "\t\t\ttemp tempVar92 = battle_unit_get_unit_data_id*(self);",
    ]
    for index, check in checks:
        for hook in check.hooks:
            if hook.function == function:
                lines.extend(
                    [
                        f"\t\t\tif ( tempVar92 == {json.dumps(hook.unit_id, ensure_ascii=False)} ) {{",
                        f"\t\t\t\trando_enemy_mark*({index});",
                        "\t\t\t}",
                    ]
                )
    lines.extend(["\t\t}", "\t}"])
    return prepend_body(source, function, "\n".join(lines) + "\n")


def reset_hook(source: str, plan: DeliveryPlan) -> str:
    lines = ["\ttemp tempVar90 = rando_seed_valid*();", "\tif ( tempVar90 ) {"]
    lines.append("\t\trando_enemy_reset*();")
    lines.append("\t}")
    return prepend_body(source, "init", "\n".join(lines) + "\n")


def victory_hook(source: str, plan: DeliveryPlan) -> str:
    lines = [
        "\ttemp tempVar90 = rando_seed_valid*();",
        "\tif ( tempVar90 ) {",
        "\t\ttempVar90 = battle_is_museum*();",
        "\t\tif ( tempVar90 == false ) {",
    ]
    for index, check in enumerate(plan.checks):
        if isinstance(check, EnemyReward):
            checked, _ = plan.receipt(index)
            lines.extend(
                [
                    f"\t\t\ttemp tempVar91 = rando_enemy_get*({index});",
                    "\t\t\tif ( tempVar91 ) {",
                    f"\t\t\t\t{checked} *= true;",
                    "\t\t\t}",
                ]
            )
    lines.append("\t\t}")
    lines.append("\t\trando_enemy_reset*();")
    lines.append("\t}")
    # Collection only; the overworld poll grants rewards after battle teardown.
    return prepend_body(source, "battle_win_event", "\n".join(lines) + "\n")
