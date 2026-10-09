"""Create a native full-album/local-reward/remote-page regression fixture."""

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
    parser.add_argument("--remote-sticker", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory")
    with tempfile.TemporaryDirectory(prefix=".local-page-probe-", dir=args.output.parent) as directory:
        root = Path(directory)
        mod = root / "mod"
        shutil.copytree(args.mod, mod)
        report = json.loads((mod / "patch-report.json").read_text(encoding="utf-8"))
        if report.get("complete_randomizer") is not False or not report.get("saved_byte_mailbox"):
            raise ValueError("Use an experimental saved-byte mailbox fixture")
        if report["checks"][0]["reward"] != {"kind": "coins", "value": 25}:
            raise ValueError("Fixture first check must have the known coin reward")
        flags = ("gf_rando_probe_local_started", "gf_rando_probe_local_ready")
        registry = mod / "romfs/Data/kdm_switch.bin"
        raw, allocated = register_flags(registry.read_bytes(), flags)
        registry.write_bytes(raw)
        binary = root / "ksm_item.bin"
        binary.write_bytes((mod / "romfs" / RUNTIME_SCRIPT).read_bytes())
        compile_script(args.compiler, binary)
        script = ScriptSource(binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"), hashlib.sha256(binary.read_bytes()).hexdigest())
        source = script.source.read_text(encoding="utf-8")
        pattern = r"if \(\s*gf_rando_check_0000 && gf_rando_delivered_0000 == false\s*\)\s*\{\s*pouch_add_coin\*?\(25\);\s*gf_rando_delivered_0000 \*= true;\s*\}"
        replacement = '''if ( gf_rando_check_0000 && gf_rando_delivered_0000 == false ) {
        gf_rando_unlock_sl_hammer *= true;
        tempVar0 = rando_item_grant*("SL_HAMMER");
        if ( tempVar0 ) {
            gf_rando_delivered_0000 *= true;
        }
    }'''
        source, count = re.subn(pattern, replacement, source)
        if count != 1:
            raise ValueError("Native delivery case no longer matches the inspected fixture")
        source = prepend_body(source, "rando_deliver", '''
    temp tempVar95 = rando_seed_valid*();
    if ( tempVar95 && gf_rando_album_initialized && gf_rando_probe_local_started == false ) {
        gf_rando_probe_local_started *= true;
        thread rando_local_page_probe*();
    }
''')
        source += '''
private rando_local_page_probe()  {
    sleep_frames* 600;
    temp tempVar0 = true;
    temp tempVar1 = 0;
    temp tempVar2 = true;
    while* tempVar0 {
        tempVar2 = rando_item_grant*("SL_W6_SANDAL_S");
        tempVar1 = tempVar1 + 1;
        tempVar0 = tempVar2 && tempVar1 < 128;
    }
    if ( tempVar2 == false ) {
        gf_rando_check_0000 *= true;
        gf_rando_probe_local_ready *= true;
    }
}
'''
        if args.remote_sticker:
            source = source.replace("        gf_rando_check_0000 *= true;\n        gf_rando_probe_local_ready", "        gf_rando_probe_local_ready")
            report["native_remote_page_probe"] = True
        script.header.write_text(add_declarations(script.header.read_text(encoding="utf-8"), flags, {}), encoding="utf-8")
        script.source.write_text(source, encoding="utf-8")
        compiled = compile_checked(script, args.compiler, flags + ("gf_rando_check_0000", "gf_rando_delivered_0000", "gf_rando_unlock_sl_hammer"))
        (mod / "romfs" / RUNTIME_SCRIPT).write_bytes(compiled)
        report["allocated_flags"] += [asdict(flag) for flag in allocated]
        report["script_hashes"][RUNTIME_SCRIPT] = hashlib.sha256(compiled).hexdigest()
        report["checks"][0]["reward"] = {"kind": "sticker_unlock", "value": "SL_HAMMER"}
        report["native_local_page_probe"] = report["check_flags"][0]["id"]
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        publish_directory(mod, args.output.absolute())


if __name__ == "__main__":
    main()
