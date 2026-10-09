"""Exercise the original Faucet acquisition sequence in an isolated native fixture.

The test enters the Faucet room through the original world-map stage loader, receives
Thing unlocks first, then invokes its original animated acquisition routine.
It does not emulate the player's hammer button or validate the full stage route.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.access import WORLD_MAP_SCRIPT
from randomizer.integrations.rom.native_delivery import NativeReward, NativeRewardKind
from randomizer.integrations.rom.plan_io import decode_plan
from randomizer.integrations.rom.pickups import record, pointer, text
from randomizer.integrations.rom.project import RomProject, publish_directory
from randomizer.integrations.rom.script_build import (
    ScriptSource,
    add_declarations,
    compile_checked,
    prepend_body,
    replace_body,
)
from randomizer.integrations.rom.shared_runtime import RUNTIME_SCRIPT
from randomizer.integrations.rom.switches import register_flags
from randomizer.integrations.rom.things import SCRIPTED_THING_SCRIPTS, special_thing_checks
from randomizer.integrations.rom.tutorial_skip import compile_script


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("mod", type=Path)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--query-header", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--receive-after-initialization",
        action="store_true",
        help="Diagnostic: receive Thing unlocks after native actors have spawned",
    )
    parser.add_argument("--full-event", action="store_true", help="Invoke the original complete Faucet story event")
    parser.add_argument(
        "--manual-source",
        action="store_true",
        help="Observe collection through controller gameplay instead of invoking acquisition",
    )
    args = parser.parse_args()
    if args.manual_source and args.full_event:
        parser.error("Manual source collection uses the event selected by the original game")
    if args.output.exists():
        parser.error("Use a new isolated fixture directory")
    project = RomProject(args.rom)
    flags = tuple(
        "gf_rando_thing_probe_" + name
        for name in (
            "tap",
            "curling",
            "started",
            "before",
            "acquired",
            "water",
            "replay",
            "done",
            "dry",
            "uncollected",
            "owned",
            "visible",
            "present",
            "map",
            "once",
        )
    )
    if args.full_event:
        flags += ("gf_rando_thing_probe_story",)
    init_steps = (
        "map_default_init",
        "event_room_init",
        "koopa_face_init",
        "koopa_tape_init",
        "watersound_init",
        "waterhole_init",
        "bibcock_init",
    )
    init_flags = tuple("gf_rando_thing_probe_init_" + name for name in init_steps)
    detail_names = ("query_enter", "query_return", "actor_created", "actor_positioned", "actor_pera", "reaction_started")
    detail_flags = tuple("gf_rando_thing_probe_init_" + name for name in detail_names)
    query_imports = {}
    required_queries = ("pouch_get_coin", "item_check_pouch", "pouch_is_get_real_item_once", "character_is_being")
    for header in args.query_header:
        for line in header.read_text(encoding="utf-8").splitlines():
            for name in required_queries:
                if line.startswith(f"#import function {name} "):
                    query_imports[name] = line
    if set(required_queries) - query_imports.keys():
        raise ValueError(f"Missing original queries: {sorted(set(required_queries) - query_imports.keys())}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".thing-probe-", dir=args.output.parent) as directory:
        root = Path(directory)
        mod = root / "mod"
        shutil.copytree(args.mod, mod)
        report = json.loads((mod / "patch-report.json").read_text(encoding="utf-8"))
        if report.get("complete_randomizer") is not False or report.get("native_thing_probe"):
            raise ValueError("Use an unmodified experimental source fixture")
        fields = {
            key: report[key]
            for key in (
                "checks",
                "album_pages",
                "shuffle_royals",
                "remote_rewards",
                "remote_session",
                "sticker_policy",
                "starting_rewards",
                "starting_item_ids",
                "seed_name",
            )
        }
        fields.update({name: report.get("presentation", {}).get(name, True) for name in ("skip_opening", "skip_dialogue")})
        plan = decode_plan(fields)
        indices = special_thing_checks(plan)
        if set(indices) != {"REAL_TAP", "REAL_CURLING_STONE"} or plan.sticker_policy is None:
            raise ValueError("Fixture must contain both scripted Thing sources and their native policy")
        faucet = indices["REAL_TAP"]
        if plan.checks[faucet].reward != NativeReward(NativeRewardKind.COINS, 25):
            raise ValueError("Faucet probe requires a known 25-coin replacement")
        registry = mod / "romfs/Data/kdm_switch.bin"
        patched, allocated = register_flags(registry.read_bytes(), flags + init_flags + detail_flags)
        registry.write_bytes(patched)
        imports = {
            name: f"#import function {name} from 0x{sum(map(ord, name[len(name) // 2 :])) & 511:x} {{0x0}};"
            for name in (
                "rando_thing_probe_visibility",
                "rando_thing_probe_replay",
                "rando_thing_probe_map",
                *(("rando_thing_probe_receive",) if args.receive_after_initialization else ()),
            )
        }
        for filename in (RUNTIME_SCRIPT, SCRIPTED_THING_SCRIPTS["hei_2_04"], WORLD_MAP_SCRIPT):
            binary = root / filename
            binary.parent.mkdir(parents=True, exist_ok=True)
            original = (mod / "romfs" / filename).read_bytes()
            binary.write_bytes(original)
            compile_script(args.compiler, binary)
            script = ScriptSource(
                binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"), hashlib.sha256(original).hexdigest()
            )
            source = script.source.read_text(encoding="utf-8")
            if filename == RUNTIME_SCRIPT:
                source = prepend_body(source, "rando_deliver", "\trando_thing_probe_prepare*();\n")
                body = [
                    "private rando_thing_probe_prepare() {",
                    "\tlocal localVar0 = rando_seed_valid*();",
                    "\tif ( localVar0 == false ) {\n\t\treturn*;\n\t}",
                    "\ttemp tempVar0;",
                    "\tgf_rando_ability_hammer *= true;",
                    "\tpouch_attach_accessory*(pouch_hammer);",
                    "\tgf_rando_ability_paperization *= true;",
                    "\tpouch_attach_accessory*(pouch_lucie);",
                ]
                for item, receipt in (("SL_TAP", flags[0]), ("SL_CURLING_STONE", flags[1])):
                    if args.receive_after_initialization and item == "SL_TAP":
                        body.extend(["}", "public rando_thing_probe_receive() {", "\ttemp tempVar0;"])
                    body.append(f"\tif ( {receipt} == false ) {{")
                    body.extend(
                        "\t\t" + line.replace("\n", "\n\t\t")
                        for line in plan.grant_body(NativeReward(NativeRewardKind.STICKER_UNLOCK, item), receipt)
                    )
                    body.append("\t}")
                body.extend(
                    [
                        "}",
                        "public rando_thing_probe_visibility() {",
                        '\tlocal localVar0 = rando_thing_owned*("bibcock", "REAL_TAP");',
                        '\tlocal localVar1 = rando_thing_owned*("item_bibcock", "REAL_TAP");',
                        "\tlocalVar0 = localVar0 == false && localVar1 == false;\n\treturn* localVar0;",
                        "}",
                        "public rando_thing_probe_map() {\n\tlocal localVar0 = pouch_get_map"
                        '_name*();\n\tlocalVar0 = localVar0 == "hei_2_04";\n\treturn* localVar'
                        "0;\n}",
                        'public rando_thing_probe_replay() {\n\trando_pickup*("item_bibcock");\n}',
                    ]
                )
                source += "\n" + "\n".join(body) + "\n"
            elif filename == WORLD_MAP_SCRIPT:
                source = prepend_body(
                    source,
                    "e_wm_map_access",
                    """
    if ( gf_rando_ability_hammer && gf_rando_ability_paperization && gf_rando_thing_probe_started == false ) {
        wm_set_cspt*("A03");
        wm_entry_map*();
        wm_sb_disable*();
        ui_close_world_status*();
        sleep_frames* 25;
        wm_map_access_on*();
        return* true;
    }
""",
                )
            else:
                source = replace_body(
                    source,
                    "mizuhiki_check",
                    f"""
    gf_rando_thing_probe_init_query_enter *= true;
    local localVar90 = rando_thing_source_collected*({faucet});
    gf_rando_thing_probe_init_query_return *= true;
    return* localVar90;
""",
                )
                # Match the production fix when diagnosing an older compiled
                # fixture: native expressions cannot nest the new script call.
                source = re.sub(
                    r"(?m)^([ \t]*)if \( false == mizuhiki_check\*?\(\) \)",
                    lambda match: f"{match[1]}local localVar91 = mizuhiki_check*();\n{match[1]}if ( false == localVar91 )",
                    source,
                )
                actor_steps = {
                    r'\titem_static_entry\*?\(var_0x[0-9a-f]+, "REAL_TAP", 0, -1000, 0\);': "actor_created",
                    r"\tcharacter_set_position\*?\(var_0x[0-9a-f]+, tempVar0, tempVar1, tempVar2\);": "actor_positioned",
                    r"\tcharacter_set_pera\*?\(var_0x[0-9a-f]+, pera_3d\);": "actor_pera",
                    r"\tthread bibcock_check_hit\*?\(\);": "reaction_started",
                }
                for pattern, name in actor_steps.items():
                    source, count = re.subn(
                        rf"(?m)^(\t*{pattern})$", rf"\1\n\t\tgf_rando_thing_probe_init_{name} *= true;", source
                    )
                    if count != 1:
                        raise ValueError(f"Expected one Faucet actor initialization step: {name}")
                for name, flag in zip(init_steps, init_flags, strict=True):
                    pattern = rf"(?m)^(\t{re.escape(name)}\*?\([^\n]*\);)$"
                    source, count = re.subn(pattern, rf"\1\n\t{flag} *= true;", source)
                    if count != 1:
                        raise ValueError(f"Expected one native initialization step: {name}")
                # Start after the original initializer so the acquisition test
                # cannot race native actor creation and map setup.
                source, count = re.subn(
                    r"(?m)^(\tgf_w1_hei_2_04_enter \*?= true;)$",
                    "\\1\\n\\tif ( gf_rando_thing_probe_started == false ) {\\n\\t\\tgf_rand"
                    "o_thing_probe_started *= true;\\n\\t\\tthread rando_thing_probe_main"
                    "*();\\n\\t}",
                    source,
                )
                if count != 1:
                    raise ValueError("Faucet lacks one original initialization completion flag")
                source += f"""
private rando_thing_probe_main() {{
    sleep_frames* 600;
    {"rando_thing_probe_receive*();" if args.receive_after_initialization else ""}
    local localVar0 = mizuhiki_check*();
    local localVar1 = rando_thing_source_collected*({faucet});
    local localVar2 = item_check_pouch*("REAL_TAP", true);
    local localVar9 = pouch_is_get_real_item_once*("REAL_TAP");
    gf_rando_thing_probe_once *= localVar9;
    local localVar3 = rando_thing_probe_visibility*();
    local localVar6 = localVar0 == false;
    gf_rando_thing_probe_dry *= localVar6;
    localVar6 = localVar1 == false;
    gf_rando_thing_probe_uncollected *= localVar6;
    gf_rando_thing_probe_owned *= localVar2;
    gf_rando_thing_probe_visible *= localVar3;
    local localVar7 = character_is_being*("bibcock");
    gf_rando_thing_probe_present *= localVar7;
    local localVar8 = rando_thing_probe_map*();
    gf_rando_thing_probe_map *= localVar8;
    localVar6 = gf_rando_thing_probe_tap && gf_rando_thing_probe_curling && localVar0 == false && localVar1 == false && localVar2 && localVar3 && localVar7 && localVar8;
    gf_rando_thing_probe_before *= localVar6;
    if ( localVar6 == false ) {{
        gf_rando_thing_probe_done *= true;
        return*;
    }}
    local localVar4 = pouch_get_coin*();
    {
                    f'''local localVar10 = rando_thing_source_collected*({faucet});
    while ( localVar10 == false ) {{
        sleep_frames* 30;
        localVar10 = rando_thing_source_collected*({faucet});
    }}'''
                    if args.manual_source
                    else (
                        "as_hei_2_bibcock_num *= 3;\n    "
                        + ("bibcock_main*();" if args.full_event else "bibcock_realobj_get*();\n    waterhole_off*();")
                    )
                }
    {"localVar9 = gf_evt_1_3_koopa_bibcock;\n    gf_rando_thing_probe_story *= localVar9;" if args.full_event else ""}
    sleep_frames* 120;
    localVar0 = rando_thing_source_collected*({faucet});
    localVar1 = pouch_get_coin*();
    localVar6 = localVar0 && localVar1 == localVar4 + 25;
    gf_rando_thing_probe_acquired *= localVar6;
    localVar0 = mizuhiki_check*();
    localVar6 = localVar0;
    gf_rando_thing_probe_water *= localVar6;
    rando_thing_probe_replay*();
    localVar0 = pouch_get_coin*();
    localVar6 = localVar0 == localVar1;
    gf_rando_thing_probe_replay *= localVar6;
    gf_rando_thing_probe_done *= true;
}}
"""
            script.source.write_text(source, encoding="utf-8")
            declarations = flags + init_flags + detail_flags + ("gf_rando_ability_hammer", "gf_rando_ability_paperization")
            script.header.write_text(
                add_declarations(script.header.read_text(encoding="utf-8"), declarations, query_imports | imports),
                encoding="utf-8",
            )
            required_flags = (
                flags + init_flags + detail_flags
                if filename == SCRIPTED_THING_SCRIPTS["hei_2_04"]
                else (
                    (flags[2], "gf_rando_ability_hammer", "gf_rando_ability_paperization")
                    if filename == WORLD_MAP_SCRIPT
                    else flags[:2]
                )
            )
            compiled = compile_checked(
                script,
                args.compiler,
                required_flags,
                required_function="rando_thing_probe" if filename != WORLD_MAP_SCRIPT else "wm_entry_map",
            )
            (mod / "romfs" / filename).write_bytes(compiled)
            report["script_hashes"][filename] = hashlib.sha256(compiled).hexdigest()
        # A normal room link across courses omits native area initialization.
        # Keep the standard tutorial/world-map route and enter the actual A03
        # course through its native loader, changing only this fixture's room.
        original_world = KdmDocument(project.read_file("Data/kdm_worldmap_data.bin"))
        document = KdmDocument(original_world.add_strings(("hei_2_04", "af_e_bero1")))
        groups = [
            record(row, 3)
            for array in document.arrays.values()
            if array.type_id == 24
            for row in array.values
            if text(record(row, 3)[0]) == "A03"
        ]
        (group,) = groups
        (destination,) = [record(row, 5) for row in document.pointed_array(pointer(group[1])).values]
        if text(destination[0]) != "hei_2_00":
            raise ValueError("A03 does not match the native Faucet course")
        data = document.edit_strings({destination[0].offset: "hei_2_04", destination[1].offset: "af_e_bero1"})
        KdmDocument(data)
        (mod / "romfs/Data/kdm_worldmap_data.bin").write_bytes(data)
        report["allocated_flags"] += [asdict(flag) for flag in allocated]
        report["native_thing_probe"] = {
            "faucet_check": plan.checks[faucet].id,
            "method": (
                "observed_controller_source_collection"
                if args.manual_source
                else ("original_full_faucet_event" if args.full_event else "original_animated_acquisition_and_water_method")
            ),
            "entry_method": "original_world_map_stage_entry",
            "receive_after_initialization": args.receive_after_initialization,
            "full_event": args.full_event,
            "manual_source": args.manual_source,
            "controller_input_verified": False,
            "complete_native_event_verified": False,
        }
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        publish_directory(mod, args.output.absolute())
    print(args.output)


if __name__ == "__main__":
    main()
