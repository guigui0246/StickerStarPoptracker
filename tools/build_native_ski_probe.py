"""Test the original Curling Stone initializer and shared acquisition callback.

This isolated fixture enters the original D02 course with its native world-map
loader. It receives the Thing unlock before initialization, then exercises the
shared acquisition callback. It does not validate skiing controls or the full
skiing event's position/state cleanup.
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
from randomizer.integrations.rom.access import WORLD_MAP_SCRIPT
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.native_delivery import NativeReward, NativeRewardKind
from randomizer.integrations.rom.pickups import pointer, record, text
from randomizer.integrations.rom.plan_io import decode_plan
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
        "--full-callback",
        action="store_true",
        help="Stage one valid native carrier slot and test the original skiing acquisition cleanup",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new isolated fixture directory")
    project = RomProject(args.rom)
    world = KdmDocument(project.read_file("Data/kdm_worldmap_data.bin"))
    courses = [
        (text(group[0]), text(destination[1]))
        for array in world.arrays.values()
        if array.type_id == 24
        for row in array.values
        for group in [record(row, 3)]
        for target in world.pointed_array(pointer(group[1])).values
        for destination in [record(target, 5)]
        if text(destination[0]) == "w4_kaw_00"
    ]
    if courses != [("D02", "")]:
        raise ValueError("Curling Stone course no longer matches the native stage entry")
    flags = tuple(
        "gf_rando_ski_probe_" + name
        for name in (
            "ready",
            "started",
            "initialized",
            "present",
            "owned",
            "available",
            "before",
            "acquired",
            "replay",
            "done",
        )
    )
    if args.full_callback:
        flags += ("gf_rando_ski_probe_cleanup",)
    imports = {}
    required = {"character_is_being", "item_check_pouch", "pouch_get_coin"}
    for header in args.query_header:
        for line in header.read_text(encoding="utf-8").splitlines():
            for name in required:
                if line.startswith(f"#import function {name} "):
                    imports[name] = line
    if required - imports.keys():
        raise ValueError("Missing native source queries")
    for name in ("rando_ski_probe_available", "rando_ski_probe_replay"):
        imports[name] = f"#import function {name} from 0x{sum(map(ord, name[len(name) // 2 :])) & 511:x} {{0x0}};"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ski-probe-", dir=args.output.parent) as directory:
        root = Path(directory)
        mod = root / "mod"
        shutil.copytree(args.mod, mod)
        report = json.loads((mod / "patch-report.json").read_text(encoding="utf-8"))
        if report.get("complete_randomizer") is not False or report.get("native_ski_probe"):
            raise ValueError("Use an unmodified experimental production fixture")
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
        if not plan.ability_mode or plan.sticker_policy is None:
            raise ValueError("Skiing fixture requires registered abilities and a native sticker policy")
        index = special_thing_checks(plan)["REAL_CURLING_STONE"]
        if plan.checks[index].reward != NativeReward(NativeRewardKind.COINS, 25):
            raise ValueError("Curling Stone probe requires a 25-coin replacement")
        registry = mod / "romfs/Data/kdm_switch.bin"
        data, allocated = register_flags(registry.read_bytes(), flags)
        registry.write_bytes(data)
        for filename in (RUNTIME_SCRIPT, WORLD_MAP_SCRIPT, SCRIPTED_THING_SCRIPTS["w4_kaw_00"]):
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
                source = prepend_body(source, "rando_deliver", "\trando_ski_probe_prepare*();\n")
                grant = "\n".join(
                    "\t" + line.replace("\n", "\n\t")
                    for line in plan.grant_body(NativeReward(NativeRewardKind.STICKER_UNLOCK, "SL_CURLING_STONE"), flags[0])
                )
                source += f"""
private rando_ski_probe_prepare() {{
    local localVar0 = rando_seed_valid*();
    if ( localVar0 == false || gf_rando_ski_probe_ready ) {{
        return*;
    }}
    gf_rando_ability_hammer *= true;
    gf_rando_ability_paperization *= true;
    pouch_attach_accessory*(pouch_hammer);
    pouch_attach_accessory*(pouch_lucie);
    temp tempVar0;
{grant}
}}
public rando_ski_probe_available() {{
    local localVar0 = rando_thing_owned*("realobj001", "REAL_CURLING_STONE");
    localVar0 = localVar0 == false;
    return* localVar0;
}}
public rando_ski_probe_replay() {{
    rando_pickup*("realobj001");
}}
"""
                required_flags = (flags[0],)
            elif filename == WORLD_MAP_SCRIPT:
                source = prepend_body(
                    source,
                    "e_wm_map_access",
                    """
    if ( gf_rando_ski_probe_ready && gf_rando_ski_probe_started == false ) {
        wm_set_cspt*("D02");
        wm_entry_map*();
        wm_sb_disable*();
        ui_close_world_status*();
        sleep_frames* 25;
        wm_map_access_on*();
        return* true;
    }
""",
                )
                required_flags = (flags[0], flags[1])
            else:
                acquisition = 'item_get_real_name*("realobj001");'
                if args.full_callback:
                    match = re.search(r"private ski_realobj_get\([^\n]*\)[^\n{]*\{\n(.*?)\n\}", source, re.DOTALL)
                    if match is None:
                        raise ValueError("Missing original skiing acquisition callback")
                    body = match[1]
                    variables = re.findall(r"(?m)^\t(var_0x[0-9a-f]+) \*?= (var_0x[0-9a-f]+);$", body)
                    if len(variables) != 3 or variables[1][0] != variables[2][0]:
                        raise ValueError("Skiing callback state/position bindings changed")
                    position_index, carrier_slot = variables[0]
                    state, completed = variables[2]
                    copy = re.search(
                        r"\barray_copy_1\*?\(penpos_tbl, " + re.escape(position_index) + r", (var_0x[0-9a-f]+)\);", body
                    )
                    if copy is None:
                        raise ValueError("Skiing callback lacks its native carrier-position read")
                    position = copy[1]
                    body = body.replace(copy[0], copy[0] + f"\n\tlocal localVar90 = {position};", 1)
                    marker = re.search(r"\bsystem_set_flag\*?\(false, system_flag_itemget\);", body)
                    if marker is None:
                        raise ValueError("Skiing callback lacks its native item-event cleanup")
                    body = body.replace(
                        marker[0],
                        f"localVar90 = {position} == - localVar90 - 1000.0 && {state} == {completed};\n\t"
                        + marker[0]
                        + "\n\tgf_rando_ski_probe_cleanup *= localVar90;",
                        1,
                    )
                    source = replace_body(source, "ski_realobj_get", body)
                    acquisition = f"""local localVar6 = length penpos_tbl;
    if ( localVar6 < 1 ) {{
        gf_rando_ski_probe_done *= true;
        return*;
    }}
    {carrier_slot} *= 0;
    ski_real_get_dai001*();"""
                pattern = r'(?m)^([ \t]*local (localVar\d+) = real_obj_init\*?\(tempVar0, "ski_real_get"\);)$'
                source, count = re.subn(
                    pattern, lambda match: match[1] + f"\n\t\t\tgf_rando_ski_probe_initialized *= {match[2]};", source
                )
                if count != 1:
                    raise ValueError("Compile the corrected native skiing initializer first")
                source, count = re.subn(
                    r"(?m)^(\tthread evt_ski_main\*?\(\);)$",
                    "\\1\\n\\tif ( gf_rando_ski_probe_started == false ) {\\n\\t\\tgf_rando_"
                    "ski_probe_started *= true;\\n\\t\\tthread rando_ski_probe_main*();\\n"
                    "\\t}",
                    source,
                )
                if count != 1:
                    raise ValueError("Skiing map lacks one original main-thread initialization")
                source += f"""
private rando_ski_probe_main() {{
    sleep_frames* 180;
    local localVar0 = character_is_being*("realobj001");
    gf_rando_ski_probe_present *= localVar0;
    local localVar1 = item_check_pouch*("REAL_CURLING_STONE", true);
    gf_rando_ski_probe_owned *= localVar1;
    local localVar2 = rando_ski_probe_available*();
    gf_rando_ski_probe_available *= localVar2;
    local localVar3 = rando_thing_source_collected*({index});
    local localVar4 = localVar0 && localVar1 && localVar2 && localVar3 == false && gf_rando_ski_probe_initialized;
    gf_rando_ski_probe_before *= localVar4;
    if ( localVar4 == false ) {{
        gf_rando_ski_probe_done *= true;
        return*;
    }}
    local localVar5 = pouch_get_coin*();
    {acquisition}
    sleep_frames* 120;
    localVar0 = rando_thing_source_collected*({index});
    localVar1 = pouch_get_coin*();
    localVar2 = rando_ski_probe_available*();
    localVar4 = localVar0 && localVar1 == localVar5 + 25 && localVar2 == false;
    gf_rando_ski_probe_acquired *= localVar4;
    rando_ski_probe_replay*();
    localVar0 = pouch_get_coin*();
    localVar4 = localVar0 == localVar1;
    gf_rando_ski_probe_replay *= localVar4;
    gf_rando_ski_probe_done *= true;
}}
"""
                required_flags = flags[1:]
            script.source.write_text(source, encoding="utf-8")
            script.header.write_text(
                add_declarations(
                    script.header.read_text(encoding="utf-8"),
                    flags + ("gf_rando_ability_hammer", "gf_rando_ability_paperization"),
                    imports,
                ),
                encoding="utf-8",
            )
            compiled = compile_checked(
                script,
                args.compiler,
                required_flags,
                required_function="wm_entry_map" if filename == WORLD_MAP_SCRIPT else "rando_ski_probe",
            )
            (mod / "romfs" / filename).write_bytes(compiled)
            report["script_hashes"][filename] = hashlib.sha256(compiled).hexdigest()
        report["allocated_flags"] += [asdict(flag) for flag in allocated]
        report["native_ski_probe"] = {
            "check": plan.checks[index].id,
            "method": (
                "original_ski_initializer_and_full_acquisition_callback"
                if args.full_callback
                else "original_ski_initializer_and_shared_acquisition"
            ),
            "full_callback": args.full_callback,
            "staged_native_carrier_slot": 0 if args.full_callback else None,
            "controller_input_verified": False,
            "ski_callback_cleanup_verified": False,
        }
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        publish_directory(mod, args.output.absolute())
    print(args.output)


if __name__ == "__main__":
    main()
