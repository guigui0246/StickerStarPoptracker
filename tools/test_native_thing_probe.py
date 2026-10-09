"""Read the controlled original Faucet sequence result without writing game state."""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=390)
    parser.add_argument("--startup-wait-seconds", type=int, default=30)
    args = parser.parse_args()
    if not 0 <= args.startup_wait_seconds <= 60:
        parser.error("Startup wait must be between zero and 60 seconds")
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    probe = report.get("native_thing_probe")
    if not probe:
        raise ValueError("Use only the controlled native Thing probe")
    profile = NativeProfile.load(args.patch_report)
    locations = {identifier: 95000 + index for index, identifier in enumerate(profile.checks)}
    time.sleep(args.startup_wait_seconds)  # RPC starts before valid guest memory exists.
    with CitraMemory(timeout=1) as memory:
        game = NativeGame(memory, profile, profile.session.seed, profile.session.team, profile.session.slot,
                          profile.session.catalog_hash, locations)
        deadline = time.monotonic() + args.wait_seconds
        checkpoints: dict[str, bool] = {}
        while time.monotonic() < deadline:
            try:
                _, data = game.snapshot()
                checkpoints = {name: game.bit(data, index) for name, index in profile.flags.items()
                               if name.startswith("gf_rando_thing_probe_")}
                if game.bit(data, profile.flags["gf_rando_thing_probe_done"]):
                    break
            except (OSError, RuntimeError):
                pass
            time.sleep(0.25)
        else:
            raise TimeoutError("Original Faucet acquisition probe did not finish; native checkpoints: "
                               + json.dumps(checkpoints, sort_keys=True))
        failed = [name for name in ("tap", "curling", "before", "acquired", "water", "replay", "dry", "uncollected", "owned", "visible", "present", "map")
                  if not game.bit(data, profile.flags["gf_rando_thing_probe_" + name])]
        if probe.get("full_event") and not game.bit(data, profile.flags["gf_rando_thing_probe_story"]):
            failed.append("story")
        assert not failed, failed
        location = locations[probe["faucet_check"]]
        assert location in game.collected()
        assert game.received(f"local/{location}")
        method = "full Faucet story event" if probe.get("full_event") else "Faucet acquisition"
        print(f"Native original {method}, independent source visibility, water effect, replacement prize and replay passed; hammer-button gameplay remains unverified")


if __name__ == "__main__":
    main()
