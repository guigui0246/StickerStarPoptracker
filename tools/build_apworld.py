"""Package the shared code and AP adapter without bundling game assets."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("dist/sticker_star.apworld")
    )
    parser.add_argument("--catalog", type=Path, help="Typed catalog for the native world; omit to build the logic demo")
    parser.add_argument("--bindings", type=Path, help="Native source/reward mappings bound to that catalog")
    parser.add_argument("--rom", type=Path, help="Your own target ROM; only its digest and native item identities enter the bundle")
    parser.add_argument("--registry", type=Path, help="Existing AP IDs to preserve; the output ID file is reused by default")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    bundle = None
    game_name = "Paper Mario: Sticker Star (Logic Demo)"
    if any(value is not None for value in (args.catalog, args.bindings, args.rom, args.registry)):
        if not all(value is not None for value in (args.catalog, args.bindings, args.rom)):
            parser.error("Native packaging requires --catalog, --bindings and --rom")
        sys.path.insert(0, str(root))
        from randomizer.data.catalog import parse_catalog
        from randomizer.integrations.archipelago.native_catalog import NativeAPCatalog, NativeAPRegistry, allocate_registry
        from randomizer.integrations.rom.native_generation import NativeBindings
        from randomizer.integrations.rom.native_recipe import source_digest
        from randomizer.integrations.rom.project import RomProject
        from randomizer.integrations.rom.stickers import sticker_policy
        catalog_data = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
        bindings_data = json.loads(args.bindings.read_text(encoding="utf-8"))
        game = parse_catalog(catalog_data)
        NativeBindings.parse(bindings_data, catalog_data).validate(game)
        registry_output = Path(str(args.output) + ".ids.json")
        previous_path = args.registry or (registry_output if registry_output.exists() else None)
        previous = NativeAPRegistry.parse(json.loads(previous_path.read_text(encoding="utf-8"))) if previous_path else None
        registry = allocate_registry(game, previous)
        project = RomProject(args.rom)
        bundle = {"format_version": 1, "catalog": catalog_data, "bindings": bindings_data,
                  "registry": registry.encode(), "rom_sha256": source_digest(project),
                  "sticker_policy": asdict(sticker_policy(project.read_file("Data/kdm_item_data.bin")))}
        bundle = json.loads(json.dumps(bundle))
        NativeAPCatalog.parse(bundle)
        registry_output.parent.mkdir(parents=True, exist_ok=True)
        registry_output.write_text(json.dumps(registry.encode(), indent=2) + "\n", encoding="utf-8")
        game_name = "Paper Mario: Sticker Star (Native Catalog)"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
        archive.write(root / "randomizer" / "settings.py", "sticker_star/settings.py")
        archive.write(root / "randomizer" / "client.py", "sticker_star/client.py")
        for folder in ("domain", "data", "integrations", "standalone"):
            for source in sorted((root / "randomizer" / folder).rglob("*.py")):
                archive.write(
                    source,
                    "sticker_star/"
                    + source.relative_to(root / "randomizer").as_posix(),
                )
        if bundle is None:
            entry = "from .integrations.archipelago.world import StickerStarWorld\n"
        else:
            archive.writestr("sticker_star/_native_catalog.py", "BUNDLE_JSON = " + repr(json.dumps(bundle, separators=(",", ":"))) + "\n")
            entry = ("import json\nfrom ._native_catalog import BUNDLE_JSON\n"
                     "from .integrations.archipelago.native_catalog import NativeAPCatalog\n"
                     "from .integrations.archipelago.native_world import create_native_world\n"
                     "StickerStarWorld = create_native_world(NativeAPCatalog.parse(json.loads(BUNDLE_JSON)))\n")
        archive.writestr("sticker_star/__init__.py", entry)
        archive.writestr(
            "sticker_star/archipelago.json",
            json.dumps(
                {
                    "game": game_name,
                    "world_version": "0.2.0" if bundle else "0.1.0",
                    "minimum_ap_version": "0.6.8",
                    "compatible_version": 7,
                    "version": 7,
                }
            ),
        )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
