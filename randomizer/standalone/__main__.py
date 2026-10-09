"""One-command ROM generation and the backwards-compatible catalog engine."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import secrets
import sys
from zipfile import ZipFile
from ..data.example import example_game
from ..data.catalog import load_catalog
from .generation import generate_seed
from ..settings import AlbumPages, Banners, DoorStickers, EnemyRewards, GenericStickers, Museum


def bundled_compiler() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "bundled" / "gibberish" / "main.py"
    return Path(__file__).resolve().parents[2] / "vendor" / "gibberish" / "main.py"


def output_paths(output: Path | None, seed: str) -> tuple[Path, Path]:
    # Sanitize filenames only; record and generate from the exact original seed.
    safe_seed = re.sub(r"[^A-Za-z0-9_-]+", "_", seed).strip("_")[:64] or "seed"
    if output is not None and output.suffix.lower() == ".zip":
        return output.with_suffix(".stickerpatch"), output
    directory = output or Path("generated") / ("sticker-star-" + safe_seed)
    return directory / "seed.stickerpatch", directory / "mod.zip"


def copy_patch_report(mod: Path, recipe: Path) -> None:
    # Keep the exact compiled profile with the tracker sidecars. Auto-tracking
    # then needs no knowledge of archive layout or manually extracted reports.
    with ZipFile(mod) as archive:
        data = archive.read("reports/patch-report.json")
    with Path(str(recipe) + ".patch-report.json").open("xb") as stream:
        stream.write(data)


def generate_rom(args: argparse.Namespace, seed: str, rom: Path, catalog: Path | None, logic: str) -> None:
    recipe, mod = output_paths(args.output, seed)
    report = Path(str(recipe) + ".patch-report.json")
    if any(path.exists() or path.is_symlink() for path in (recipe, mod, report)):
        raise ValueError("This output already exists; choose another --output or --seed")
    compiler = args.compiler or bundled_compiler()
    if not compiler.is_file():
        raise ValueError("Included compiler is missing; restore vendor/gibberish or supply --compiler")
    from ..patch import main as patch

    command = "generate-no-logic" if logic == "no-logic" else "generate-native-catalog"
    options = [command, str(rom), "--seed", seed, "--output", str(recipe)]
    for name in ("album_pages", "banners", "museum", "enemy_rewards", "door_stickers", "generic_stickers"):
        options.extend(("--" + name.replace("_", "-"), getattr(args, name)))
    options.append("--no-open-ground-routes" if args.open_ground_routes is False else "--open-ground-routes")
    if logic == "no-logic":
        options.extend(("--compiler", str(compiler), "--starting-level", args.starting_level))
        for identifier in args.start_with:
            options.extend(("--start-with", identifier))
    else:
        options.extend(("--catalog", str(catalog), "--bindings", str(args.bindings)))
        if args.shuffle_royals:
            options.append("--shuffle-royals")
    for name in ("registry", "scene_skips"):
        value = getattr(args, name)
        if value is not None:
            options.extend(("--" + name.replace("_", "-"), str(value)))
    print(f"Seed: {seed}", flush=True)
    print("Generating seed and matching tracker...", flush=True)
    patch(options)
    print("Building installable mod...", flush=True)
    patch(["apply", str(recipe), str(rom), "--compiler", str(compiler), "--output", str(mod)])
    copy_patch_report(mod, recipe)
    print(f"Mod: {mod}")
    print(f"PopTracker pack: {recipe}.tracker.zip")
    print("Extract the mod ZIP and install its title-ID folder in the emulator's load/mods folder.")
    print("Enable emulator UDP RPC and start auto-tracking with:")
    print(f'python -m randomizer track --seed "{recipe}"')


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate a ROM mod and matching auto-tracker in one command.")
    parser.add_argument("input_path", nargs="?", type=Path, help="ROM .3ds path, or legacy catalog JSON")
    parser.add_argument("--rom", type=Path, help="ROM path (alternative to a positional ROM)")
    parser.add_argument("--logic", choices=("no-logic", "catalog", "demo"), help="Defaults to no-logic with a ROM")
    parser.add_argument("--catalog", type=Path, help="Reviewed version 2 JSON catalog")
    parser.add_argument("--bindings", type=Path, help="Native bindings for --logic catalog with a ROM")
    parser.add_argument("--seed", help="Reproducible seed; defaults to a random 64-bit seed")
    parser.add_argument("--output", type=Path, help="Output directory or mod .zip; default: generated/sticker-star-SEED")
    parser.add_argument("--compiler", type=Path, help="Advanced: override the included compiler")
    parser.add_argument("--registry", type=Path, help="Advanced: stable tracker/AP registry")
    parser.add_argument("--album-pages", choices=tuple(mode.value for mode in AlbumPages if mode != AlbumPages.INFINITE),
                        default="all_at_start")
    for name, enum, default in (
        ("banners", Banners, "original"), ("museum", Museum, "all"), ("enemy-rewards", EnemyRewards, "on"),
        ("door-stickers", DoorStickers, "randomized"), ("generic-stickers", GenericStickers, "enabled"),
    ):
        parser.add_argument("--" + name, choices=tuple(mode.value for mode in enum), default=default)
    parser.add_argument("--starting-level", choices=("decalburg", "random"), default="decalburg")
    parser.add_argument("--open-ground-routes", action=argparse.BooleanOptionalAction, default=None,
                        help="Independent ground routes; enabled by default for native generation")
    parser.add_argument("--start-with", action="append", default=[], help="Reward ID to precollect; repeatable")
    parser.add_argument("--scene-skips", type=Path, help="Advanced: scene entry/cleanup bindings")
    parser.add_argument("--shuffle-royals", action="store_true")
    args = parser.parse_args(argv)
    seed = args.seed if args.seed is not None else str(secrets.randbits(64))
    if not seed:
        parser.error("Seed cannot be empty")
    positional_rom = args.input_path if args.input_path and (
        args.logic == "no-logic" or args.input_path.suffix.lower() == ".3ds"
    ) else None
    if args.rom and positional_rom:
        parser.error("Use either --rom or a positional ROM, not both")
    rom = args.rom or positional_rom
    positional_catalog = args.input_path if positional_rom is None else None
    if args.catalog and positional_catalog:
        parser.error("Use either a positional catalog or --catalog, not both")
    catalog_path = args.catalog or positional_catalog
    if args.logic == "catalog" and catalog_path is None:
        catalog_path = Path(__file__).resolve().parents[1] / "data" / "game"
        if getattr(sys, "frozen", False):
            catalog_path = Path(getattr(sys, "_MEIPASS")) / "bundled" / "game"
    if args.bindings is None and catalog_path is not None and catalog_path.is_dir():
        args.bindings = catalog_path
    logic = args.logic or ("no-logic" if rom else "catalog" if catalog_path else "demo")
    if logic == "no-logic" and rom is None:
        parser.error("--logic no-logic requires a ROM: generate --logic no-logic \"ROM.3ds\"")
    if logic == "no-logic" and (catalog_path or args.bindings):
        parser.error("No-logic discovers its own catalog; use --logic catalog for authored logic")
    if logic == "demo" and (rom or catalog_path or args.bindings):
        parser.error("Demo mode does not use a ROM, catalog or bindings")
    if logic == "catalog" and catalog_path is None:
        parser.error("--logic catalog requires --catalog")
    if rom is not None:
        if logic == "catalog" and args.bindings is None:
            parser.error("A native catalog requires --bindings")
        if logic == "catalog" and (args.starting_level != "decalburg" or args.start_with):
            parser.error("Starting overrides currently require --logic no-logic; edit the catalog starting inventory instead")
        try:
            generate_rom(args, seed, rom, catalog_path, logic)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        return
    game = load_catalog(catalog_path) if catalog_path else example_game()
    result = generate_seed(game, seed)
    output = args.output or Path("generated") / ("logic-seed-" + re.sub(r"[^A-Za-z0-9_-]", "_", seed)[:64] + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["fixed_rewards"] = game.fixed_rewards
    payload["location_names"] = {location.id: location.name for location in game.locations}
    payload["item_names"] = {item.id: item.name for item in game.items}
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2) + "\n")
    print(f"Seed: {seed}")
    print(f"Wrote {len(result.placements)} randomized placements and {len(game.fixed_rewards)} fixed rewards to {output}")
    if catalog_path is None:
        print("Logic demo only. For a native mod use generate --logic no-logic ROM.3ds.")


if __name__ == "__main__":
    main()
