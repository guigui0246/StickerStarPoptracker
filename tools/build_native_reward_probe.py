"""Add read-only native inventory queries to a disposable compiled fixture."""

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
from randomizer.integrations.rom.mailbox import byte_fields, decode_word, word_flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod", type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--query-header", action="append", required=True, type=Path)
    parser.add_argument("--item", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--save-after-sequence", type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory")
    import re

    if not args.item or any(not re.fullmatch(r"(?:PK|REAL|SL)_[A-Z0-9_]+", item) for item in args.item):
        parser.error("Provide exact native inventory item names")
    queries = {f"gf_rando_probe_item_{index:04d}": item for index, item in enumerate(args.item)}
    flags = (
        *queries,
        "gf_rando_probe_one_royal",
        "gf_rando_probe_25_coins",
        "gf_rando_probe_royal_gate_zero",
        "gf_rando_probe_royal_gate_five",
    )
    required_imports = ("item_check_pouch", "pouch_get_royal_seal_num", "pouch_get_coin")
    if args.save_after_sequence is not None:
        if not 1 <= args.save_after_sequence <= 0x7FFFFFFE:
            parser.error("Save probe requires a supported positive sequence")
        flags += ("gf_rando_probe_saved",)
        required_imports += ("backup_task_save",)
    imports = {}
    for header in args.query_header:
        for line in header.read_text(encoding="utf-8").splitlines():
            for name in required_imports:
                if line.startswith(f"#import function {name} "):
                    imports[name] = line
    if len(imports) != len(required_imports):
        raise ValueError("The original query headers do not cover all required native functions")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reward-probe-", dir=args.output.parent) as directory:
        root = Path(directory)
        mod = root / "mod"
        shutil.copytree(args.mod, mod)
        report = json.loads((mod / "patch-report.json").read_text(encoding="utf-8"))
        if not report.get("rpc_memory_profile") or report.get("complete_randomizer") is not False:
            raise ValueError("Use only an explicitly experimental native fixture")
        if not report.get("shuffle_royals"):
            flags = tuple(
                flag for flag in flags if flag not in {"gf_rando_probe_royal_gate_zero", "gf_rando_probe_royal_gate_five"}
            )
        registry = mod / "romfs/Data/kdm_switch.bin"
        raw, allocated = register_flags(registry.read_bytes(), flags)
        registry.write_bytes(raw)
        binary = root / "ksm_item.bin"
        original = (mod / "romfs" / RUNTIME_SCRIPT).read_bytes()
        binary.write_bytes(original)
        compile_script(args.compiler, binary)
        script = ScriptSource(
            binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"), hashlib.sha256(original).hexdigest()
        )
        saved_mailbox = report.get("saved_byte_mailbox", False)
        ack_fields = byte_fields("ack") if saved_mailbox else word_flags("ack")
        script.header.write_text(
            add_declarations(
                script.header.read_text(encoding="utf-8"), flags + (ack_fields if args.save_after_sequence else ()), imports
            ),
            encoding="utf-8",
        )
        source = prepend_body(script.source.read_text(encoding="utf-8"), "rando_deliver", "\trando_probe_queries*();\n")
        source += (
            "\nprivate rando_probe_queries()  {\n\ttemp tempVar0 = rando_seed_val"
            "id*();\n\tif ( tempVar0 == false ) {\n\t\treturn*;\n\t}\n"
        )
        for flag, item in queries.items():
            source += f'\ttempVar0 = item_check_pouch*("{item}", true);\n\t{flag} *= tempVar0;\n'
        source += (
            "\ttempVar0 = pouch_get_royal_seal_num*();\n\ttempVar0 = tempVar0 == 1;\n\tgf_rando_probe_one_royal *= tempVar0;\n"
        )
        source += "\ttempVar0 = pouch_get_coin*();\n\ttempVar0 = tempVar0 == 25;\n\tgf_rando_probe_25_coins *= tempVar0;\n"
        if report.get("shuffle_royals"):
            source += (
                "\ttempVar0 = rando_royal_gate_count*();\n\ttemp tempVar1 = tempVar0 "
                "== 0;\n\tgf_rando_probe_royal_gate_zero *= tempVar1;\n"
            )
            source += "\ttempVar1 = tempVar0 == 5;\n\tgf_rando_probe_royal_gate_five *= tempVar1;\n"
        if args.save_after_sequence:
            source += "\n".join(decode_word("ack", "tempVar0", saved_mailbox)) + "\n"
            source += (
                "\tif ( gf_rando_probe_saved == false && tempVar0 >= "
                f"{args.save_after_sequence}"
                " ) {\n\t\tgf_rando_probe_saved *= true;\n\t\tbackup_task_save"
                "*();\n\t}\n"
            )
        source += "}\n"
        script.source.write_text(source, encoding="utf-8")
        compiled = compile_checked(script, args.compiler, flags)
        (mod / "romfs" / RUNTIME_SCRIPT).write_bytes(compiled)
        report["allocated_flags"] += [asdict(flag) for flag in allocated]
        report["script_hashes"][RUNTIME_SCRIPT] = hashlib.sha256(compiled).hexdigest()
        report["native_reward_queries"] = queries
        if args.save_after_sequence:
            report["native_probe_save_sequence"] = args.save_after_sequence
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        publish_directory(mod, args.output.absolute())
    print(args.output)


if __name__ == "__main__":
    main()
