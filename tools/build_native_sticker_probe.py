"""Build a separate, one-shot native insertion probe from an experimental mod.

This is a test fixture, not a seed. Run only in a new isolated emulator profile.
The probe uses native script calls; the host does not write inventory or flags.
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
from randomizer.integrations.rom.shared_runtime import RUNTIME_SCRIPT, item_grant_function
from randomizer.integrations.rom.project import publish_directory
from randomizer.integrations.rom.script_build import ScriptSource, add_declarations, compile_checked, prepend_body
from randomizer.integrations.rom.sticker_guard import NORMAL_ADD, FORCED_ADD
from randomizer.integrations.rom.switches import register_flags
from randomizer.integrations.rom.tutorial_skip import compile_script


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod", type=Path)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--normal-only", action="store_true", help="Isolate direct insertion from the forced placement interface"
    )
    parser.add_argument(
        "--exercise-retry",
        action="store_true",
        help="Fill the disposable album, reject a grant, remove one copy natively and retry",
    )
    parser.add_argument("--removal-header", type=Path, help="Your extracted battle_cyucyu.hksm, required for the retry fixture")
    parser.add_argument(
        "--save-probe", action="store_true", help="Save the disposable world-map fixture through the original game script"
    )
    args = parser.parse_args()
    report = json.loads((args.mod / "patch-report.json").read_text())
    signatures = report.get("code_patch", {}).get("signatures", [])
    if (
        not {NORMAL_ADD, FORCED_ADD} <= {row["address"] for row in signatures}
        or report.get("complete_randomizer") is not False
    ):
        parser.error("Input must be an experimental mod with both native sticker guards")
    if args.output.exists():
        parser.error("Use a new output directory")
    if args.exercise_retry and args.removal_header is None:
        parser.error("Retry verification requires the original native removal import")
    if args.save_probe and not report.get("startup", {}).get("post_tutorial_world_map"):
        parser.error("The autosave probe requires the isolated world-map startup fixture")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    flags = tuple(f"gf_rando_probe_{name}" for name in ("started", "normal", "forced", "unlock", "done"))
    if args.normal_only:
        flags = tuple(flag for flag in flags if flag != "gf_rando_probe_forced")
    if args.exercise_retry:
        flags += ("gf_rando_probe_full_rejected", "gf_rando_probe_retry_delivered")
    if args.save_probe:
        flags += ("gf_rando_probe_saved",)
    with tempfile.TemporaryDirectory(prefix=".sticker-probe-", dir=args.output.parent) as temporary:
        root = Path(temporary)
        mod = root / "mod"
        shutil.copytree(args.mod, mod)
        registry = mod / "romfs/Data/kdm_switch.bin"
        data, allocated = register_flags(registry.read_bytes(), flags)
        registry.write_bytes(data)
        binary = root / "ksm_item.bin"
        original = (mod / "romfs" / RUNTIME_SCRIPT).read_bytes()
        binary.write_bytes(original)
        compile_script(args.compiler, binary)
        script = ScriptSource(
            binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"), hashlib.sha256(original).hexdigest()
        )
        header = script.header.read_text(encoding="utf-8")
        if "#import function item_try_addpouch " not in header:
            raise ValueError("Probe input lacks the native item delivery import")
        imports = {}
        if args.exercise_retry:
            assert args.removal_header is not None
            name = "pouch_current_page_low_price_delete_seal"
            declarations = [
                line
                for line in args.removal_header.read_text(encoding="utf-8").splitlines()
                if line.startswith(f"#import function {name} ")
            ]
            if len(declarations) != 1:
                raise ValueError("Missing original native sticker removal import")
            imports[name] = declarations[0]
        if args.save_probe:
            name = "e_wm_save_execute"
            imports[name] = f"#import function {name} from 0x{sum(map(ord, name[len(name) // 2 :])) & 511:x} {{0x0}};"
        script.header.write_text(add_declarations(header, flags, imports), encoding="utf-8")
        body = """\ttemp tempVar95 = rando_seed_valid*();
\tif ( tempVar95 && gf_rando_album_initialized && gf_rando_probe_started == false ) {
\t\tgf_rando_probe_started *= true;
\t\ttempVar95 = rando_item_grant*("SL_JUMP");
\t\tgf_rando_probe_normal *= tempVar95;
\t\ttempVar95 = item_try_addpouch*("SL_JUMP", true);
\t\tgf_rando_probe_forced *= tempVar95;
\t\tgf_rando_unlock_sl_hammer *= true;
\t\ttempVar95 = rando_item_grant*("SL_HAMMER");
\t\tgf_rando_probe_unlock *= tempVar95;
\t\tgf_rando_probe_done *= true;
\t}
"""
        if args.normal_only:
            body = body.replace(
                '\t\ttempVar95 = item_try_addpouch*("SL_JUMP", true);\n\t\tgf_rando_probe_forced *= tempVar95;\n', ""
            )
        if args.exercise_retry:
            retry = """\t\ttemp tempVar93 = true;
\t\ttemp tempVar94 = 0;
\t\twhile* tempVar93 {
\t\t\ttempVar95 = rando_item_grant*("SL_W6_SANDAL_S");
\t\t\ttempVar94 = tempVar94 + 1;
\t\t\ttempVar93 = tempVar95 && tempVar94 < 128;
\t\t}
\t\ttempVar95 = rando_item_grant*("SL_HAMMER");
\t\tif ( tempVar95 == false ) {
\t\t\tgf_rando_probe_full_rejected *= true;
\t\t\tpouch_current_page_low_price_delete_seal*();
\t\t\ttempVar95 = rando_item_grant*("SL_HAMMER");
\t\t\tif ( tempVar95 ) {
\t\t\t\tgf_rando_probe_retry_delivered *= true;
\t\t\t}
\t\t}
"""
            body = body.replace("\t\tgf_rando_probe_done *= true;", retry + "\t\tgf_rando_probe_done *= true;")
        if args.save_probe:
            body = body.replace(
                "\t\tgf_rando_probe_done *= true;",
                "\t\tgf_rando_probe_done *= true;\n\t\tgf_rando_probe_saved *= true;\n\t\te_wm_save_execute*();",
            )
        # Startup calls run before the vanilla pouch reset. Run the fixture in
        # its own thread after startup, rather than blocking the calling init.
        launch = """\ttemp tempVar95 = rando_seed_valid*();
\tif ( tempVar95 && gf_rando_album_initialized && gf_rando_probe_started == false ) {
\t\tgf_rando_probe_started *= true;
\t\tthread rando_sticker_probe*();
\t}
"""
        body = body.replace("gf_rando_probe_started == false", "gf_rando_probe_done == false")
        source = prepend_body(script.source.read_text(encoding="utf-8"), "rando_deliver", launch)
        if "private rando_item_grant(" not in source:
            source += item_grant_function()
        source += "\nprivate rando_sticker_probe()  {\n\tsleep_frames* 600;\n" + body + "}\n"
        script.source.write_text(source, encoding="utf-8")
        result = compile_checked(script, args.compiler, flags)
        (mod / "romfs" / RUNTIME_SCRIPT).write_bytes(result)
        report["allocated_flags"] += [asdict(flag) for flag in allocated]
        report["script_hashes"][RUNTIME_SCRIPT] = hashlib.sha256(result).hexdigest()
        report["native_sticker_probe"] = {
            "normal_item": "SL_JUMP",
            "forced_item": None if args.normal_only else "SL_JUMP",
            "unlock_item": "SL_HAMMER",
        }
        report["native_probe_retry"] = args.exercise_retry
        report["native_probe_save"] = args.save_probe
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (mod / "README.txt").write_text(
            "ONE-SHOT NATIVE STICKER TEST FIXTURE. Use a new isolated emulator profile. Not a playable seed.\n",
            encoding="utf-8",
        )
        publish_directory(mod, args.output.absolute())
    print(args.output)


if __name__ == "__main__":
    main()
