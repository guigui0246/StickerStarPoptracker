"""Source entry point sharing the bundled command implementations."""

import sys

from .standalone.__main__ import main as generate


def main() -> None:
    from tools.release_cli import COMMANDS, main as dispatch

    if sys.argv[1:2] and sys.argv[1] in COMMANDS:
        dispatch()
    else:
        generate()


if __name__ == "__main__":
    main()
