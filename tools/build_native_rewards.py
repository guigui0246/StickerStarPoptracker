"""Build native goal-block reward hooks from explicit observed placements."""

import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.project import RomProject
from randomizer.integrations.rom.reward_patch import build_reward_mod
from randomizer.settings import AlbumPages


from randomizer.integrations.rom.plan_io import load_plan_files as load_plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--placements", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--album-pages", choices=("all_at_start", "randomized"))
    parser.add_argument("--shuffle-royals", action="store_true")
    parser.add_argument("--remote-rewards", type=Path)
    parser.add_argument("--ap-session", type=Path)
    args = parser.parse_args()
    try:
        mode = AlbumPages(args.album_pages) if args.album_pages else None
        result = build_reward_mod(RomProject(args.rom), load_plan(args.placements, mode, args.shuffle_royals, args.remote_rewards, args.ap_session), args.compiler, args.output)
        print(f"Built native reward hooks in {result}")
        print("Emulator validation and full-game integration remain pending.")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Cannot build native reward hooks: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
