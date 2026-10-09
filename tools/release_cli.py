"""Frozen command dispatcher for the existing standalone tools."""

import argparse
import sys
from collections.abc import Callable

from randomizer.client import main as client
from randomizer.standalone.__main__ import main as generate
from randomizer.track_standalone import main as track
from tools.build_sticker_patch import main as patch

COMMANDS: dict[str, Callable[[], None]] = {
    "generate": generate,
    "patch": patch,
    "track": track,
    "client": client,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sticker Star generation, experimental sticker patching and tracking")
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args(sys.argv[1:2])
    sys.argv = [f"{sys.argv[0]} {args.command}", *sys.argv[2:]]
    COMMANDS[args.command]()


if __name__ == "__main__":
    main()
