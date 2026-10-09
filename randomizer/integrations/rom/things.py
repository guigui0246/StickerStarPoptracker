"""Scripted Thing sources and source effects independent of received unlocks."""

from dataclasses import dataclass
import re

from .native_delivery import DeliveryPlan, PickupReward
from .script_build import replace_body

SCRIPTED_THING_SCRIPTS = {
    "hei_2_04": "Script/Map/HEI/hei_2_04.bin",
    "w4_kaw_00": "Script/Map/W4_KAW/w4_kaw_00.bin",
}
FAUCET_EFFECT_SCRIPTS = ("Script/Map/HEI/hei_2_02.bin", "Script/Map/HEI/hei_2_04.bin")
THING_INITIALIZER_CALLERS = (
    "Script/Map/W2_YOS/w2_yos_06.bin",
    "Script/Map/W2_ISE/w2_ise_04.bin",
    "Script/Map/W4_YUK/w4_yuk_04.bin",
    "Script/Map/W4_YUK/w4_yuk_01.bin",
    "Script/Map/W4_YAK/w4_yak_04.bin",
    "Script/Map/W4_KAW/w4_kaw_01.bin",
    "Script/Map/W4_KAW/w4_kaw_00.bin",
)
SOURCE_EFFECTS = {
    "Script/Map/HEI/hei_3_01.bin": ("hei_3_01", "fan", "REAL_FAN", 1),
    "Script/Map/W3_THR/w3_thr_01.bin": ("w3_thr_01", "REAL_BILLIARD_BALL", "REAL_BILLIARD_BALL", 1),
    "Script/Map/W3_BEA/w3_bea_06.bin": ("w3_bea_06", "real", "REAL_OIL_HEATER", 1),
    "Script/Map/W5_MAG/w5_mag_19.bin": ("w5_mag_19", "RAREOBJECT_01", "REAL_TURKEY", 2),
    "Script/Map/W5_MAG/w5_mag_D1.bin": ("w5_mag_D1", "RAREOBJECT_01", "REAL_TUB", 1),
    "Script/Map/W5_WAN/w5_wan_D1.bin": ("w5_wan_D1", "RAREOBJECT_01", "REAL_AIR_CONDITIONER", 1),
}


@dataclass(frozen=True)
class ScriptedThing:
    map_name: str
    object_name: str
    source_item: str
    script_file: str
    display_objects: tuple[str, ...] = ()


def scripted_things(map_name: str, source: str) -> tuple[ScriptedThing, ...]:
    if map_name == "hei_2_04":
        assignments = re.findall(r'\b(localVar\d+) \*?= "item_bibcock";', source)
        if len(assignments) != 1:
            raise ValueError("Faucet acquisition lacks one named item actor")
        actor = re.escape(assignments[0])
        if (
            len(re.findall(r"\bitem_static_entry\*?\(" + actor + r', "REAL_TAP",', source)) != 1
            or len(re.findall(r"\bitem_get_evt_real\*?\(" + actor + r"\);", source)) != 1
        ):
            raise ValueError("Faucet actor does not match its native acquisition")
        displays = re.findall(r'\b(var_0x[0-9a-f]+) \*?= "bibcock";', source)
        if (
            len(displays) != 1
            or len(re.findall(r"\bitem_static_entry\*?\(" + re.escape(displays[0]) + r', "REAL_TAP",', source)) != 1
        ):
            raise ValueError("Faucet display actor does not match its native source")
        return (ScriptedThing(map_name, "item_bibcock", "REAL_TAP", SCRIPTED_THING_SCRIPTS[map_name], ("bibcock",)),)
    if map_name == "w4_kaw_00":
        table = re.findall(r"var_array evt_ski_arg_tbl = \{([^{}]+)\};", source)
        if len(table) != 1:
            raise ValueError("Curling Stone lacks one native skiing argument table")
        args = [value.strip() for value in table[0].split(",")]
        if len(args) != 13 or args[8] != '"REAL_CURLING_STONE"':
            raise ValueError("Skiing Thing reward does not match Curling Stone")
        reward_variables = re.findall(r"\barray_copy_1\*?\(tempVar0, 8, (var_0x[0-9a-f]+)\);", source)
        actors = re.findall(r'\b(var_0x[0-9a-f]+) \*?= "realobj001";', source)
        if len(reward_variables) != 1 or len(actors) != 1:
            raise ValueError("Curling Stone lacks unique reward and actor bindings")
        if (
            f"[{actors[0]} -> temp tempVar0]" not in source
            or len(re.findall(r"\bitem_static_entry\*?\(tempVar0, " + re.escape(reward_variables[0]) + r",", source)) != 1
            or len(re.findall(r"\bitem_get_real_name\*?\(tempVar1\);", source)) != 1
        ):
            raise ValueError("Curling Stone actor does not match its native acquisition")
        return (ScriptedThing(map_name, "realobj001", "REAL_CURLING_STONE", SCRIPTED_THING_SCRIPTS[map_name]),)
    return ()


def special_thing_checks(plan: DeliveryPlan) -> dict[str, int]:
    expected = {("hei_2_04", "item_bibcock", "REAL_TAP"), ("w4_kaw_00", "realobj001", "REAL_CURLING_STONE")}
    return {
        check.source_item: index
        for index, check in enumerate(plan.checks)
        if isinstance(check, PickupReward) and (check.map_name, check.object_name, check.source_item) in expected
    }


def thing_effect_scripts(plan: DeliveryPlan) -> tuple[str, ...]:
    special = special_thing_checks(plan)
    scripts: list[str] = list(FAUCET_EFFECT_SCRIPTS) if "REAL_TAP" in special else []
    if "REAL_CURLING_STONE" in special:
        scripts.append(SCRIPTED_THING_SCRIPTS["w4_kaw_00"])
    for filename, (map_name, object_name, item, _) in SOURCE_EFFECTS.items():
        if any(
            isinstance(check, PickupReward)
            and (check.map_name, check.object_name, check.source_item) == (map_name, object_name, item)
            for check in plan.checks
        ):
            scripts.append(filename)
    if any(isinstance(check, PickupReward) and check.source_item.startswith("REAL_") for check in plan.checks):
        # The shared initializer changes for all actors, including sources not
        # configured in a partial plan. Preserve every original inline caller.
        scripts.extend(THING_INITIALIZER_CALLERS)
    return tuple(dict.fromkeys(scripts))


def thing_state_functions(plan: DeliveryPlan) -> str:
    lines = [
        "private rando_thing_owned(temp tempVar0, temp tempVar1) {",
        "\tlocal localVar0 = pouch_get_map_name*();",
        "\tlocal localVar1;",
    ]
    for index, check in enumerate(plan.checks):
        if not isinstance(check, PickupReward) or not check.source_item.startswith("REAL_"):
            continue
        flag, _ = plan.receipt(index)
        actors = f'tempVar0 == "{check.object_name}"'
        if (check.map_name, check.object_name, check.source_item) == ("hei_2_04", "item_bibcock", "REAL_TAP"):
            actors = f'( {actors} || tempVar0 == "bibcock" )'
        lines.extend(
            [
                f'\tif ( localVar0 == "{check.map_name}" && {actors} ) {{',
                "\t\tlocalVar1 = rando_seed_valid*();",
                "\t\tif ( localVar1 == false ) {\n\t\t\treturn* true;\n\t\t}",
                f"\t\treturn* {flag};\n\t}}",
            ]
        )
    lines.extend(
        [
            "\tlocalVar1 = item_check_pouch*(tempVar1, true);",
            "\treturn* localVar1;",
            "}",
            "public rando_thing_source_collected(temp tempVar0) {",
            "\tlocal localVar0 = rando_seed_valid*();",
            "\tif ( localVar0 == false ) {\n\t\treturn* false;\n\t}",
        ]
    )
    for index, check in enumerate(plan.checks):
        if not isinstance(check, PickupReward) or not check.source_item.startswith("REAL_"):
            continue
        flag, _ = plan.receipt(index)
        lines.append(f"\tif ( tempVar0 == {index} ) {{\n\t\treturn* {flag};\n\t}}")
    return "\n".join(lines + ["\treturn* false;", "}"]) + "\n"


def hook_thing_initialization(source: str) -> str:
    original = r"\bitem_check_pouch\*?\(tempVar3, true\)"
    if len(re.findall(original, source)) != 1:
        raise ValueError("Native Thing initialization ownership test changed")
    identity = r"\btemp tempVar3 = item_get_item_id\*?\(tempVar0\);"
    if len(re.findall(identity, source)) != 1:
        raise ValueError("Native Thing initialization identity lookup changed")
    # A private script call inside an if expression does not survive the
    # external compiler's round trip. Evaluate it explicitly before branching.
    source = re.sub(
        identity, lambda match: match.group() + "\n\tlocal localVar90 = rando_thing_owned*(tempVar0, tempVar3);", source
    )
    return re.sub(original, "localVar90", source)


def hook_thing_effects(source: str, script_file: str, plan: DeliveryPlan) -> str:
    if script_file in THING_INITIALIZER_CALLERS and any(
        isinstance(check, PickupReward) and check.source_item.startswith("REAL_") for check in plan.checks
    ):
        inline = r"(?m)^([ \t]*)if \(\s*real_obj_init\*?\(([^()\n]*)\)\s*\)"
        source, count = re.subn(
            inline,
            lambda match: f"{match[1]}local localVar92 = real_obj_init*({match[2]});\n{match[1]}if ( localVar92 )",
            source,
        )
        if count != 1:
            raise ValueError(f"Native Thing initializer expression changed: {script_file}")
    checks = special_thing_checks(plan)
    if script_file in FAUCET_EFFECT_SCRIPTS and "REAL_TAP" in checks:
        if len(re.findall(r'\bitem_check_pouch\*?\("REAL_TAP", true\)', source)) != 1:
            raise ValueError("Faucet water effect ownership test changed")
        source = replace_body(
            source,
            "mizuhiki_check",
            f"\tlocal localVar90 = rando_thing_source_collected*({checks['REAL_TAP']});\n\treturn* localVar90;",
        )
        # This native inline call originally only inspected the pouch. The
        # replacement crosses into another script; evaluate it before entering
        # the expression evaluator, as the other water-state callers already do.
        inline = r"(?m)^([ \t]*)if \(\s*false\s*==\s*mizuhiki_check\*?\(\)\s*\)"
        source = re.sub(
            inline,
            lambda match: f"{match[1]}local localVar91 = mizuhiki_check*();\n{match[1]}if ( false == localVar91 )",
            source,
        )
    if script_file == SCRIPTED_THING_SCRIPTS["w4_kaw_00"] and "REAL_CURLING_STONE" in checks:
        (variable,) = re.findall(r"\barray_copy_1\*?\(tempVar0, 8, (var_0x[0-9a-f]+)\);", source)
        pattern = r"\bitem_check_pouch\*?\(" + re.escape(variable) + r", true\)"
        if len(re.findall(pattern, source)) != 2:
            raise ValueError("Skiing source initialization ownership tests changed")
        source = re.sub(pattern, f"rando_thing_source_collected*({checks['REAL_CURLING_STONE']})", source)
    if script_file in SOURCE_EFFECTS:
        map_name, object_name, item, count = SOURCE_EFFECTS[script_file]
        indices = [
            index
            for index, check in enumerate(plan.checks)
            if isinstance(check, PickupReward)
            and (check.map_name, check.object_name, check.source_item) == (map_name, object_name, item)
        ]
        if indices:
            pattern = r'\bitem_check_pouch\*?\("' + re.escape(item) + r'", true\)'
            if len(indices) != 1 or len(re.findall(pattern, source)) != count:
                raise ValueError(f"Thing source effect ownership tests changed: {script_file}")
            # The Heater tests its original native function directly in an if.
            # Explicitly evaluate the replacement script call before branching.
            inline = r"(?m)^([ \t]*)if \(\s*" + pattern + r"\s*== false\s*\)"
            source = re.sub(
                inline,
                lambda match: (
                    f"{match[1]}"
                    "local localVar90 = rando_thing_source_collected*("
                    f"{indices[0]}"
                    ");\n"
                    f"{match[1]}"
                    "if ( localVar90 == false )"
                ),
                source,
            )
            source = re.sub(pattern, f"rando_thing_source_collected*({indices[0]})", source)
    return source
