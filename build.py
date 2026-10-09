import sys
import os
from typing import TypedDict
from subprocess import Popen

if __name__ != "__main__":
    print("This script should be run directly, not imported.", file=sys.stderr)
    sys.exit(1)

args = set(sys.argv[1:])

if not args:
    print("No arguments provided.\nAvailable options: cli_randomizer, apworld, randomizer, tracker", file=sys.stderr)
    sys.exit(1)


class Options(TypedDict):
    cli_randomizer: bool
    apworld: bool
    randomizer: bool
    tracker: bool


options = Options(
    cli_randomizer=False,
    apworld=False,
    randomizer=False,
    tracker=False
)

if 'cli_randomizer' in args:
    options["cli_randomizer"] = True
    args.discard('cli_randomizer')
if 'apworld' in args:
    options["apworld"] = True
    args.discard('apworld')
if 'randomizer' in args:
    options["randomizer"] = True
    args.discard('randomizer')
if 'tracker' in args:
    options["tracker"] = True
    args.discard('tracker')

if args:
    print(f"Unknown arguments: {', '.join(args)}", file=sys.stderr)
    sys.exit(1)

os.makedirs("generated", exist_ok=True)

# Generator, patch and pseudo server for autotracking as a cli
if options["cli_randomizer"]:
    # TODO: generate to executable of the machine's os
    ...

# .apworld file that does options, rules, patch and ap client
if options["apworld"]:
    # TODO: generate to apworld aka zip named .apworld with all the required configuration files
    ...

# cli_randomizer but with a graphical interface and a button to install the apworld
# Requires apworld to be compiled
if options["randomizer"]:
    # TODO: generate to executable of the machine's os
    ...

if options["tracker"]:
    Popen([".\\build_tracker.ps1"], shell=True, cwd=os.path.join(os.getcwd(), "tracker"))
