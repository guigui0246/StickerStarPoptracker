"""Generate or apply an asset-free experimental .stickerpatch recipe."""

import argparse
from pathlib import Path
import sys
import subprocess
import json
import tempfile
from dataclasses import asdict, replace
from random import Random

from .integrations.rom.project import RomProject
from .integrations.rom.seed_patch import (
    apply_recipe,
    create_recipe,
    decode_recipe,
    write_recipe,
    unique_object,
)
from .data.catalog import load_catalog, load_catalog_data, obj
from .integrations.rom.native_generation import NativeBindings, configure_catalog, generate_native_seed
from .integrations.rom.native_recipe import (
    MAX_NATIVE_RECIPE_BYTES,
    apply_native_recipe,
    create_native_recipe,
    decode_native_recipe,
)
from .integrations.rom.plan_io import load_plan_files, scene_skips
from .settings import AlbumPages, Banners, DoorStickers, EnemyRewards, GenericStickers, Museum, Settings as NativeSettings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Create a shareable combat-shuffle recipe")
    generate.add_argument("rom", type=Path)
    generate.add_argument("--seed", required=True)
    generate.add_argument("--tutorial-skip", action="store_true")
    generate.add_argument("--output", type=Path, required=True)
    native = commands.add_parser(
        "generate-native", help="Create an asset-free native reward recipe from explicit observed checks"
    )
    native.add_argument("rom", type=Path)
    native.add_argument("--seed", required=True)
    native.add_argument("--placements", type=Path, required=True)
    native.add_argument("--album-pages", choices=("all_at_start", "randomized"), default="all_at_start")
    native.add_argument("--shuffle-royals", action="store_true")
    native.add_argument("--remote-rewards", type=Path)
    native.add_argument("--ap-session", type=Path)
    native.add_argument("--output", type=Path, required=True)
    catalog_native = commands.add_parser(
        "generate-native-catalog", help="Solve a typed catalog and bind its seed to observed native checks"
    )
    catalog_native.add_argument("rom", type=Path)
    catalog_native.add_argument("--catalog", type=Path, required=True)
    catalog_native.add_argument("--bindings", type=Path, required=True)
    catalog_native.add_argument("--seed", required=True)
    catalog_native.add_argument("--album-pages", choices=("vanilla", "all_at_start", "randomized"), default="all_at_start")
    catalog_native.add_argument("--banners", choices=("original", "reduced", "off"), default="original")
    catalog_native.add_argument("--shuffle-royals", action="store_true")
    catalog_native.add_argument("--output", type=Path, required=True)
    catalog_native.add_argument("--registry", type=Path, help="Existing append-only tracker/AP identifier registry")
    catalog_native.add_argument("--open-ground-routes", action=argparse.BooleanOptionalAction, default=False,
                                help="Independent ground navigation")
    no_logic = commands.add_parser("generate-no-logic", help="Build a full observed-source seed without access logic")
    no_logic.add_argument("rom", type=Path)
    no_logic.add_argument("--compiler", type=Path, required=True)
    no_logic.add_argument("--seed", required=True)
    no_logic.add_argument("--album-pages", choices=("vanilla", "all_at_start", "randomized"), default="all_at_start")
    no_logic.add_argument("--banners", choices=("original", "reduced", "off"), default="original")
    no_logic.add_argument("--output", type=Path, required=True)
    no_logic.add_argument("--registry", type=Path)
    no_logic.add_argument("--starting-level", choices=("decalburg", "random"), default="decalburg")
    no_logic.add_argument(
        "--open-ground-routes", action=argparse.BooleanOptionalAction, default=True,
        help="Independent ground navigation (enabled by default)",
    )
    no_logic.add_argument("--start-with", action="append", default=[], help="Observed reward ID to precollect; repeatable")
    for catalog_command in (catalog_native, no_logic):
        catalog_command.add_argument("--scene-skips", type=Path, help="JSON list of explicit scene entry/cleanup bindings")
        catalog_command.add_argument("--museum", choices=tuple(mode.value for mode in Museum), default="all")
        catalog_command.add_argument("--enemy-rewards", choices=("on", "off"), default="on")
        catalog_command.add_argument("--door-stickers", choices=("randomized", "vanilla"), default="randomized")
        catalog_command.add_argument("--generic-stickers", choices=("enabled", "disabled"), default="enabled")
    apply = commands.add_parser("apply", help="Apply a recipe to your own decrypted European ROM")
    apply.add_argument("patch", type=Path, help="Recipe from patch generate or patch generate-native-catalog; not seed JSON")
    apply.add_argument("rom", type=Path)
    apply.add_argument("--compiler", type=Path)
    apply.add_argument("--output", type=Path, required=True, help="New mod directory or .zip with title-ID install folder")
    args = parser.parse_args(argv)
    try:
        project = RomProject(args.rom)
        if args.command == "generate":
            recipe = create_recipe(project, args.seed, args.tutorial_skip)
            write_recipe(recipe, args.output)
            print(f"Wrote asset-free recipe to {args.output}")
        elif args.command in {"generate-native", "generate-native-catalog", "generate-no-logic"}:
            catalog_mode = args.command != "generate-native"
            starting_stage = None
            if catalog_mode:
                if args.command == "generate-no-logic":
                    from .data.no_logic import build_no_logic_catalog
                    from .integrations.rom.production_sources import production_sources
                    from .integrations.rom.script_build import decompile

                    with tempfile.TemporaryDirectory(prefix=".no-logic-") as directory:
                        work = Path(directory)

                        def read_source(name: str) -> str:
                            return decompile(project, name, work, args.compiler).source.read_text(encoding="utf-8")

                        sources = production_sources(project, read_source)
                        if args.starting_level == "random":
                            candidates = sorted(str(reward.value) for reward in sources.rewards
                                                if reward.kind.value == "stage_access" and str(reward.value)[0] in "ABCDE")
                            if not candidates:
                                raise ValueError("No grounded starting stages are available")
                            starting_stage = Random("starting-stage/" + args.seed).choice(candidates)
                        catalog, game, bindings = build_no_logic_catalog(sources, starting_stage, tuple(args.start_with))
                else:
                    catalog = load_catalog_data(args.catalog)
                    game = load_catalog(args.catalog)
                    bindings = NativeBindings.load(args.bindings, catalog)
                settings = NativeSettings(
                    AlbumPages(args.album_pages), Banners(args.banners), Museum(args.museum),
                    EnemyRewards(args.enemy_rewards), DoorStickers(args.door_stickers),
                    GenericStickers(args.generic_stickers),
                )
                generated, plan = generate_native_seed(
                    game, bindings, args.seed, settings,
                    shuffle_royals=args.command == "generate-no-logic" or args.shuffle_royals,
                )
                plan = replace(plan, open_ground_routes=args.open_ground_routes, starting_stage=starting_stage)
                if args.scene_skips is not None:
                    plan = replace(plan, scene_skips=scene_skips(json.loads(
                        args.scene_skips.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                    )))
            else:
                plan = load_plan_files(
                    args.placements, AlbumPages(args.album_pages), args.shuffle_royals, args.remote_rewards, args.ap_session
                )
            native_recipe = create_native_recipe(project, args.seed, plan, settings if catalog_mode else None)
            if catalog_mode:
                from .integrations.archipelago.native_catalog import NativeAPRegistry, allocate_registry
                from .integrations.archipelago.tracker_catalog import TrackerCatalog
                from .integrations.archipelago.tracker_pack import write_tracker_pack

                registry_path = args.registry or Path(str(args.output) + ".registry.json")
                previous = (
                    NativeAPRegistry.parse(
                        json.loads(registry_path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
                    )
                    if registry_path.exists()
                    else None
                )
                registry = allocate_registry(game, previous)
                enabled, enabled_bindings = configure_catalog(game, bindings, settings)
                if bindings.catalog_hash is None:
                    raise ValueError("Standalone tracking requires a bound catalog")
                options = {
                    "starting_stage": plan.starting_stage or "native_default",
                    "open_ground_routes": "on" if plan.open_ground_routes else "off",
                    "scene_skips": str(len(plan.scene_skips)),
                }
                tracker = TrackerCatalog(enabled, registry, bindings.catalog_hash, settings, options)
                tracking = {
                    "format_version": 1,
                    "seed": args.seed,
                    "catalog_hash": bindings.catalog_hash,
                    "save_seed_fingerprint": native_recipe.plan.fingerprint.hex(),
                    "locations": {
                        enabled_bindings.locations[identifier].id: registry.locations[identifier]
                        for identifier in generated.placements
                    },
                    "rewards": {
                        enabled_bindings.locations[identifier].id: {
                            "item": registry.items[item],
                            "reward": asdict(bindings.items[item]),
                        }
                        for identifier, item in generated.placements.items()
                    },
                    "starting": [
                        {"item": registry.items[item], "reward": asdict(bindings.items[item])}
                        for item in enabled.starting_items
                    ],
                }
                sidecars = (
                    (".catalog.json", catalog),
                    (".bindings.json", {
                        "format_version": 1, "catalog_sha256": bindings.catalog_hash,
                        "items": {identifier: asdict(reward) for identifier, reward in bindings.items.items()},
                        "locations": [{"location": identifier, "source": {
                            key: value for key, value in asdict(check).items() if key != "reward"
                        }} for identifier, check in bindings.locations.items()],
                    }),
                    (".tracking.json", tracking),
                    (".tracker.json", tracker.definitions()),
                    (".tracker-data.json", tracker.data_package()),
                )
                targets = [args.output] + [Path(str(args.output) + suffix) for suffix, _ in sidecars]
                targets += [Path(str(args.output) + suffix) for suffix in (".tracker.lua", ".tracker.zip")]
                if registry_path.resolve() in {target.resolve() for target in targets}:
                    raise ValueError("The registry path must be separate from the seed and tracker outputs")
                for target in targets:
                    if target.exists() or target.is_symlink():
                        raise FileExistsError(f"Use new output paths; existing file is preserved: {target}")
                registry_path.parent.mkdir(parents=True, exist_ok=True)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("xb") as stream:
                    stream.write(native_recipe.encode())
                for suffix, value in sidecars:
                    with Path(str(args.output) + suffix).open("x", encoding="utf-8") as stream:
                        stream.write(json.dumps(value, indent=2) + "\n")
                with Path(str(args.output) + ".tracker.lua").open("x", encoding="utf-8") as stream:
                    stream.write(tracker.lua())
                write_tracker_pack(tracker, Path(str(args.output) + ".tracker.zip"))
                registry_path.write_text(json.dumps(registry.encode(), indent=2) + "\n", encoding="utf-8")
            else:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("xb") as stream:
                    stream.write(native_recipe.encode())
            print(f"Wrote asset-free native reward recipe to {args.output}")
        else:
            with args.patch.open("rb") as stream:
                data = stream.read(MAX_NATIVE_RECIPE_BYTES + 1)
            if len(data) > MAX_NATIVE_RECIPE_BYTES:
                raise ValueError("Stickerpatch exceeds the supported size")
            header = obj(json.loads(data, object_pairs_hook=unique_object))
            if "placements" in header and "source_hashes" not in header:
                raise ValueError(
                    "This is a logic seed JSON, not a ROM patch recipe. For a combat-sticker shuffle use "
                    "patch generate ROM --seed SEED --output seed.stickerpatch, then apply that recipe. "
                    "Native progression requires generate-native-catalog with a reviewed catalog and bindings. "
                    "--output is a new mod directory, not a ZIP archive."
                )
            if header.get("format_version") == 2:
                if args.compiler is None:
                    raise ValueError("Native recipes require --compiler pointing to Gibberish main.py")
                if args.output.suffix.lower() == ".zip":
                    from .integrations.rom.mod_archive import build_mod_archive

                    build_mod_archive(project, decode_native_recipe(data), args.output, args.compiler)
                else:
                    apply_native_recipe(project, decode_native_recipe(data), args.output, args.compiler)
            else:
                recipe = decode_recipe(data)
                apply_recipe(project, recipe, args.output, args.compiler)
            print(f"Built mod in {args.output}")
        print("Experimental patch. Full-game access logic and gameplay validation remain unfinished.")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Cannot {args.command} patch: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
