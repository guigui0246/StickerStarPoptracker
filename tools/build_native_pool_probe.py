"""Add the production variable-arena expansion to a disposable native fixture."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.abilities import CodePatch
from randomizer.integrations.rom.project import publish_directory
from randomizer.integrations.rom.runtime_pool import EXPANDED_LIMIT, expand_variable_pool


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod", type=Path)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output directory")
    with tempfile.TemporaryDirectory(prefix=".pool-probe-", dir=args.output.parent) as directory:
        mod = Path(directory) / "mod"
        shutil.copytree(args.mod, mod)
        report = json.loads((mod / "patch-report.json").read_text(encoding="utf-8"))
        if report.get("complete_randomizer") is not False:
            raise ValueError("Use only an experimental fixture")
        original = args.code.read_bytes()
        previous = None
        patch_data = report.get("code_patch")
        if patch_data:
            raw = (mod / "exefs/code.ips").read_bytes()
            if not raw.startswith(b"PATCH"):
                raise ValueError("Unsupported fixture patch")
            records = []
            cursor = 5
            rebuilt = bytearray(original)
            while raw[cursor:cursor + 3] != b"EOF":
                offset = int.from_bytes(raw[cursor:cursor + 3], "big")
                size = int.from_bytes(raw[cursor + 3:cursor + 5], "big")
                if not size or cursor + 5 + size > len(raw):
                    raise ValueError("Malformed fixture patch record")
                data = raw[cursor + 5:cursor + 5 + size]
                records.append((offset, data))
                rebuilt[offset:offset + size] = data
                cursor += 5 + size
            if hashlib.sha256(rebuilt).hexdigest() != patch_data["patched_sha256"]:
                raise ValueError("Fixture executable patch does not match its report")
            previous = CodePatch(tuple(records), patch_data["source_sha256"], patch_data["patched_sha256"],
                                 (mod / "exefs/code.S").read_text(encoding="utf-8"))
        patch = expand_variable_pool(original, previous)
        (mod / "exefs").mkdir(exist_ok=True)
        (mod / "exefs/code.ips").write_bytes(patch.ips())
        (mod / "exefs/code.S").write_text(patch.assembly, encoding="utf-8")
        if (mod / "exefs/abilities.S").exists():
            (mod / "exefs/abilities.S").write_text(patch.assembly, encoding="utf-8")
        report["code_patch"] = {"source_sha256": patch.source_sha256, "patched_sha256": patch.patched_sha256,
                                "signatures": patch.signatures}
        report["script_variable_pool_limit"] = EXPANDED_LIMIT
        (mod / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        publish_directory(mod, args.output.absolute())


if __name__ == "__main__":
    main()
