"""Survey production sources or bind a reviewed full catalog to the user's ROM."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import subprocess
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.production_sources import production_sources, reward_id
from randomizer.integrations.rom.project import RomProject
from randomizer.integrations.rom.script_build import decompile
from randomizer.integrations.rom.seed_patch import unique_object


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("survey", "bind"))
    parser.add_argument("rom", type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--catalog", type=Path, help="Reviewed typed catalog; required for bind")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "bind" and args.catalog is None:
        parser.error("Binding requires --catalog with independently reviewed access rules")
    if args.output.exists():
        parser.error("Use a new output file")
    try:
        project = RomProject(args.rom)
        compiler = args.compiler.resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix=".production-catalog-") as directory:
            work = Path(directory)

            def read_source(name: str) -> str:
                return decompile(project, name, work, compiler).source.read_text(encoding="utf-8")

            sources = production_sources(project, read_source)
        if args.command == "bind":
            catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
            bindings = sources.bind(catalog)
            result = {
                "format_version": 1, "catalog_sha256": bindings.catalog_hash,
                "items": {identifier: asdict(reward) for identifier, reward in bindings.items.items()},
                "locations": [
                    {"location": identifier, "source": {key: value for key, value in asdict(check).items() if key != "reward"}}
                    for identifier, check in bindings.locations.items()
                ],
            }
        else:
            result = {
                "format_version": 1, "access_rules_verified": False,
                "source_hashes": sources.source_hashes,
                "checks": [{"id": check.id, **{key: value for key, value in asdict(check).items() if key != "reward"}}
                           for check in sources.checks],
                "rewards": [{"id": reward_id(reward), **asdict(reward)} for reward in sources.rewards],
                "story_flags": sorted(sources.story_flags),
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Cannot {args.command} production catalog: {error}\n")


if __name__ == "__main__":
    main()
