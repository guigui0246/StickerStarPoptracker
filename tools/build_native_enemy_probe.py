"""Exercise the real shared encounter-state helpers in a disposable fixture."""

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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory")
    with tempfile.TemporaryDirectory(prefix=".enemy-probe-", dir=args.output.parent) as directory:
        root = Path(directory)
        mod = root / "mod"
        shutil.copytree(args.mod, mod)
        report = json.loads((mod / "patch-report.json").read_text(encoding="utf-8"))
        if report.get("complete_randomizer") is not False:
            raise ValueError("Use only an experimental fixture")
        indices = [index for index, check in enumerate(report["checks"]) if "unit_id" in check]
        if not indices:
            raise ValueError("Fixture has no enemy checks")
        flags = ("gf_rando_probe_enemy_done", "gf_rando_probe_enemy_passed")
        registry = mod / "romfs/Data/kdm_switch.bin"
        raw, allocated = register_flags(registry.read_bytes(), flags)
        registry.write_bytes(raw)
        binary = root / "ksm_item.bin"
        binary.write_bytes((mod / "romfs" / RUNTIME_SCRIPT).read_bytes())
        compile_script(args.compiler, binary)
        script = ScriptSource(binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"), hashlib.sha256(binary.read_bytes()).hexdigest())
        script.header.write_text(add_declarations(script.header.read_text(encoding="utf-8"), flags, {}), encoding="utf-8")
        source = prepend_body(script.source.read_text(encoding="utf-8"), "rando_deliver", "\trando_enemy_probe*();\n")
        source += "\nprivate rando_enemy_probe()  {\n\ttemp tempVar0 = rando_seed_valid*();\n\tif ( tempVar0 == false || gf_rando_probe_enemy_done ) {\n\t\treturn*;\n\t}\n\tgf_rando_probe_enemy_done *= true;\n\trando_enemy_reset*();\n"
        for index in indices:
            source += f"\ttempVar0 = rando_enemy_get*({index});\n\tif ( tempVar0 ) {{\n\t\treturn*;\n\t}}\n\trando_enemy_mark*({index});\n"
        for index in indices:
            source += f"\ttempVar0 = rando_enemy_get*({index});\n\tif ( tempVar0 == false ) {{\n\t\treturn*;\n\t}}\n"
        source += "\trando_enemy_reset*();\n"
        for index in indices:
            source += f"\ttempVar0 = rando_enemy_get*({index});\n\tif ( tempVar0 ) {{\n\t\treturn*;\n\t}}\n"
        source += "\tgf_rando_probe_enemy_passed *= true;\n}\n"
        script.source.write_text(source, encoding="utf-8")
        compiled = compile_checked(script, args.compiler, flags)
        (mod / "romfs" / RUNTIME_SCRIPT).write_bytes(compiled)
        report["allocated_flags"] += [asdict(flag) for flag in allocated]
        report["script_hashes"][RUNTIME_SCRIPT] = hashlib.sha256(compiled).hexdigest()
        report["native_enemy_probe"] = indices
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        publish_directory(mod, args.output.absolute())


if __name__ == "__main__":
    main()
