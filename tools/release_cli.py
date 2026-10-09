"""Frozen command dispatcher for the existing standalone tools."""

import argparse
import sys
from collections.abc import Callable

from randomizer.client import main as client
from randomizer.integrations.rom.compiler_driver import main as compile_script
from randomizer.patch import main as patch
from randomizer.standalone.__main__ import main as generate
from randomizer.track_standalone import main as track
from tools.production_catalog import main as catalog
from tools.build_sticker_patch import main as combat_patch
from tools.rebind_native_catalog import main as rebind

COMMANDS: dict[str, Callable[[], None]] = {
    "generate": generate,
    "patch": patch,
    "track": track,
    "client": client,
    "catalog": catalog,
    "rebind": rebind,
}


def main() -> None:
    if sys.argv[1:2] == ["_compile-script"]:
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        compile_script()
        return
    parser = argparse.ArgumentParser(description="Sticker Star generation, experimental sticker patching and tracking")
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args(sys.argv[1:2])
    sys.argv = [f"{sys.argv[0]} {args.command}", *sys.argv[2:]]
    if args.command == "patch" and "--seed" in sys.argv and sys.argv[1:2] and sys.argv[1] not in {
        "generate", "generate-native", "generate-native-catalog", "generate-no-logic", "apply",
    }:
        combat_patch()
        return
    COMMANDS[args.command]()


if __name__ == "__main__":
    main()
