"""Generate or apply an asset-free experimental .stickerpatch recipe."""

import argparse
from pathlib import Path
import sys
import subprocess
import json

from .integrations.rom.project import RomProject
from .integrations.rom.seed_patch import (
    apply_recipe, create_recipe, decode_recipe, write_recipe, unique_object,
)
from .data.catalog import obj
from .integrations.rom.native_recipe import MAX_NATIVE_RECIPE_BYTES, apply_native_recipe, create_native_recipe, decode_native_recipe
from .integrations.rom.plan_io import load_plan_files
from .settings import AlbumPages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Create a shareable combat-shuffle recipe")
    generate.add_argument("rom", type=Path)
    generate.add_argument("--seed", required=True)
    generate.add_argument("--tutorial-skip", action="store_true")
    generate.add_argument("--output", type=Path, required=True)
    native = commands.add_parser("generate-native", help="Create an asset-free native reward recipe from explicit observed checks")
    native.add_argument("rom", type=Path)
    native.add_argument("--seed", required=True)
    native.add_argument("--placements", type=Path, required=True)
    native.add_argument("--album-pages", choices=("all_at_start", "randomized"), default="all_at_start")
    native.add_argument("--shuffle-royals", action="store_true")
    native.add_argument("--remote-rewards", type=Path)
    native.add_argument("--ap-session", type=Path)
    native.add_argument("--output", type=Path, required=True)
    apply = commands.add_parser("apply", help="Apply a recipe to your own decrypted European ROM")
    apply.add_argument("patch", type=Path)
    apply.add_argument("rom", type=Path)
    apply.add_argument("--compiler", type=Path)
    apply.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        project = RomProject(args.rom)
        if args.command == "generate":
            recipe = create_recipe(project, args.seed, args.tutorial_skip)
            write_recipe(recipe, args.output)
            print(f"Wrote asset-free recipe to {args.output}")
        elif args.command == "generate-native":
            plan = load_plan_files(args.placements, AlbumPages(args.album_pages), args.shuffle_royals, args.remote_rewards, args.ap_session)
            native_recipe = create_native_recipe(project, args.seed, plan)
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
            if header.get("format_version") == 2:
                if args.compiler is None:
                    raise ValueError("Native recipes require --compiler pointing to Gibberish main.py")
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
