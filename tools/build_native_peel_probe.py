"""Exercise first-peel/re-peel delivery in an isolated native VM fixture.

This tests the delivery helper. Physical selection, native null-grant handling
and original map effects require separate gameplay validation.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.project import publish_directory
from randomizer.integrations.rom.script_build import ScriptSource, add_declarations, compile_checked, prepend_body
from randomizer.integrations.rom.shared_runtime import RUNTIME_SCRIPT
from randomizer.integrations.rom.switches import register_flags
from randomizer.integrations.rom.tutorial_skip import compile_script


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod", type=Path)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--query-header", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exercise-pending", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new disposable output directory")
    imports = {}
    required = ("item_check_pouch", "pouch_get_coin", "backup_task_save", "evtcond_pouch_clear")
    for path in args.query_header:
        for line in path.read_text(encoding="utf-8").splitlines():
            for name in required:
                if line.startswith(f"#import function {name} "):
                    imports[name] = line
    imports["e_wm_save_execute"] = f"#import function e_wm_save_execute from 0x{sum(map(ord, 'e_wm_save_execute'[len('e_wm_save_execute') // 2:])) & 511:x} {{0x0}};"
    if set(imports) != set(required) | {"e_wm_save_execute"}:
        raise ValueError("Original headers do not cover the native query/save imports")
    with tempfile.TemporaryDirectory(prefix=".peel-probe-", dir=args.output.parent) as directory:
        root = Path(directory)
        mod = root / "mod"
        shutil.copytree(args.mod, mod)
        report = json.loads((mod / "patch-report.json").read_text(encoding="utf-8"))
        if report.get("complete_randomizer") is not False or not report.get("peeled_scrap_sources"):
            raise ValueError("Use only an experimental compiled peel fixture")
        checks = report["checks"]
        if any("lock_id" not in check or check["reward"] != {"kind": "coins", "value": 25} for check in checks):
            raise ValueError("Use a peel-only fixture with known 25-coin placements")
        flags = ("gf_rando_peel_probe_started", "gf_rando_peel_probe_first", "gf_rando_peel_probe_return", "gf_rando_peel_probe_saved", "gf_rando_peel_probe_done")
        variants = [(index, variant["source_item"]) for index, check in enumerate(checks) for variant in [{"source_item": check["source_item"]}, *check["variants"]]]
        query_flags = () if args.exercise_pending else tuple(f"gf_rando_peel_probe_item_{index:03d}" for index in range(len(variants)))
        flags += query_flags
        if args.exercise_pending:
            if len(checks) < 2:
                raise ValueError("Pending-return test requires another uncollected first-peel source")
            flags += ("gf_rando_peel_probe_pending_held", "gf_rando_peel_probe_pending_saved", "gf_rando_peel_probe_pending_survived", "gf_rando_peel_probe_pending_first")
        registry = mod / "romfs/Data/kdm_switch.bin"
        patched, allocated = register_flags(registry.read_bytes(), flags)
        registry.write_bytes(patched)
        binary = root / "ksm_item.bin"
        original = (mod / "romfs" / RUNTIME_SCRIPT).read_bytes()
        binary.write_bytes(original)
        compile_script(args.compiler, binary)
        script = ScriptSource(binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"), hashlib.sha256(original).hexdigest())
        source = prepend_body(script.source.read_text(encoding="utf-8"), "rando_deliver", '''
    temp tempVar95 = rando_seed_valid*();
    if ( tempVar95 && gf_rando_album_initialized && gf_evt_mac_mario_wakeup && gf_evt_mac_battle_tutorial_end && gf_mac_1_roll_evt_end && gf_rando_peel_probe_started == false ) {
        gf_rando_peel_probe_started *= true;
        thread rando_peel_probe*();
    }
''')
        lines = ["private rando_peel_probe() {", "\tsleep_frames* 600;", "\ttemp tempVar0 = true;", "\ttemp tempVar1;"]
        names = []
        selector = 1
        deferred_selector = 0
        for index, check in enumerate(checks):
            names.extend([check["source_item"], *(variant["source_item"] for variant in check["variants"])])
            if args.exercise_pending and index == len(checks) - 1:
                deferred_selector = selector
                break
            lines.append(f"\trando_peel_can_return*({selector});")
            selector += 1 + len(check["variants"])
            lines.append(f'\trando_peel_collect_selected*({index});')
        for name in dict.fromkeys(names):
            lines.extend([f'\ttempVar1 = item_check_pouch*("{name}", true);', "\ttempVar0 = tempVar0 && tempVar1 == false;"])
        expected = len(checks) * 25
        initial_expected = expected - 25 if args.exercise_pending else expected
        lines.extend(["\ttempVar1 = pouch_get_coin*();", f"\ttempVar0 = tempVar0 && tempVar1 == {initial_expected};", "\tgf_rando_peel_probe_first *= tempVar0;"])
        lines.append("\ttempVar0 = true;")
        for _ in range(0 if args.exercise_pending else 1):
            for position, (index, name) in enumerate(variants):
                lines.extend(['\tevtcond_pouch_clear*();', '\tlocal localVar5 = pouch_get_coin*();', f'\trando_peel_can_return*({position + 1});', f'\trando_peel_collect_selected*({index});',
                              f'\ttempVar1 = item_check_pouch*("{name}", true);',
                              f"\t{query_flags[position]} *= tempVar1;", "\ttempVar0 = tempVar0 && tempVar1;", "\ttempVar1 = pouch_get_coin*();", "\ttempVar0 = tempVar0 && tempVar1 == localVar5;"])
        lines.extend(['\trando_peel_collect*(0, "SL_JUMP");', '\trando_peel_collect*(999, "SL_JUMP");'])
        lines.extend(["\ttempVar1 = pouch_get_coin*();", f"\ttempVar0 = tempVar0 && tempVar1 == {initial_expected};" if args.exercise_pending else "\ttempVar0 = tempVar0 && tempVar1 == localVar5;", "\tgf_rando_peel_probe_return *= tempVar0;", "\tgf_rando_peel_probe_done *= true;",
                      "\tif ( gf_rando_peel_probe_first && gf_rando_peel_probe_return ) {", "\t\tgf_rando_peel_probe_saved *= true;", "\t\te_wm_save_execute*();", "\t}", "}"])
        if args.exercise_pending:
            # Stage a full album after a successful preflight using game-owned
            # grants. The committed return must survive a save and process restart.
            body = ["\trando_peel_probe_reload_started = true;", "\trando_peel_can_return*(1);"]
            for _ in range(3):
                body.extend(f'\trando_item_grant*("{name}");' for name in names)
            body.extend(['\trando_peel_collect_selected*(0);',
                         "\tlocal localVar6 = gs_rando_peel_pending == 1;", "\tgf_rando_peel_probe_pending_held *= localVar6;",
                         f"\ttempVar1 = rando_peel_can_return*({deferred_selector});",
                         f"\trando_peel_collect_selected*({len(checks) - 1});",
                         "\tlocal localVar7 = pouch_get_coin*();",
                         f"\tlocalVar7 = tempVar1 && localVar7 == {expected} && gs_rando_peel_pending == 1;",
                         "\tgf_rando_peel_probe_pending_first *= localVar7;",
                         "\tgf_rando_peel_probe_done *= false;",
                         "\tgf_rando_peel_probe_pending_saved *= true;", "\te_wm_save_execute*();"])
            lines[-1:-1] = body
            source = prepend_body(source, "rando_deliver", "\tif ( gf_rando_peel_probe_pending_saved && rando_peel_probe_reload_started == false ) {\n\t\trando_peel_probe_reload_started = true;\n\t\tthread rando_peel_probe_resume*();\n\t}\n")
            lines.extend(["private rando_peel_probe_resume() {", "\tsleep_frames* 600;",
                          "\tlocal localVar1 = gs_rando_peel_pending == 1;", "\tgf_rando_peel_probe_pending_survived *= localVar1;",
                          "\tlocal localVar0 = gs_rando_peel_pending == 1 && gf_rando_peel_probe_pending_survived;", "\tgf_rando_peel_probe_return *= localVar0;",
                          "\tgf_rando_peel_probe_done *= true;", "\te_wm_save_execute*();", "}"])
        nonce_fields = [entry["name"] for entry in report["allocated_saved_bytes"] if entry["name"].startswith("gs_rando_rpc_save_")]
        nonce_empty = " && ".join(f"{name} == 0" for name in nonce_fields)
        if not nonce_fields:
            raise ValueError("Probe identity persistence requires the saved-byte mailbox")
        lines = [line.replace("e_wm_save_execute*();", f"while ( {nonce_empty} ) {{\n\t\tsleep_frames* 1;\n\t}}\n\te_wm_save_execute*();\n\tsleep_frames* 120;") for line in lines]
        source += "\n" + "\n".join(lines) + "\n"
        script.source.write_text(source, encoding="utf-8")
        header = add_declarations(script.header.read_text(encoding="utf-8"), flags + tuple(nonce_fields) + ("gf_evt_mac_mario_wakeup", "gf_evt_mac_battle_tutorial_end", "gf_mac_1_roll_evt_end"), imports)
        if args.exercise_pending:
            header += "\nstatic bool rando_peel_probe_reload_started = false;\n"
        script.header.write_text(header, encoding="utf-8")
        compiled = compile_checked(script, args.compiler, flags)
        (mod / "romfs" / RUNTIME_SCRIPT).write_bytes(compiled)
        report["allocated_flags"] += [asdict(flag) for flag in allocated]
        report["script_hashes"][RUNTIME_SCRIPT] = hashlib.sha256(compiled).hexdigest()
        report["native_peel_probe"] = {"pending_return": args.exercise_pending, "first_while_pending": args.exercise_pending, "checks": len(checks), "inventory_items": list(dict.fromkeys(names)), "coins": expected, "queries": {flag: variants[i][1] for i, flag in enumerate(query_flags)}}
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        publish_directory(mod, args.output.absolute())
    print(args.output)


if __name__ == "__main__":
    main()
