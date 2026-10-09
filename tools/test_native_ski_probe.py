"""Observe the native Curling Stone initializer/shared-acquisition test."""

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
    parser.add_argument("--wait-seconds", type=int, default=240)
    parser.add_argument("--startup-wait-seconds", type=int, default=30)
    args = parser.parse_args()
    if not 0 <= args.startup_wait_seconds <= 60:
        parser.error("Startup wait must be between zero and 60 seconds")
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    probe = report.get("native_ski_probe")
    if not probe:
        raise ValueError("Use only the controlled native skiing probe")
    profile = NativeProfile.load(args.patch_report)
    locations = {identifier: 95000 + index for index, identifier in enumerate(profile.checks)}
    time.sleep(args.startup_wait_seconds)
    with CitraMemory(timeout=1) as memory:
        game = NativeGame(
            memory,
            profile,
            profile.session.seed,
            profile.session.team,
            profile.session.slot,
            profile.session.catalog_hash,
            locations,
        )
        deadline = time.monotonic() + args.wait_seconds
        checkpoints = {}
        while time.monotonic() < deadline:
            try:
                _, data = game.snapshot()
                checkpoints = {
                    name: game.bit(data, index)
                    for name, index in profile.flags.items()
                    if name.startswith("gf_rando_ski_probe_")
                }
                if checkpoints.get("gf_rando_ski_probe_done"):
                    break
            except (OSError, RuntimeError):
                pass
            time.sleep(0.25)
        else:
            raise TimeoutError("Native skiing probe did not finish: " + json.dumps(checkpoints, sort_keys=True))
        failed = [name for name, value in checkpoints.items() if not value]
        assert not failed, failed
        location = locations[probe["check"]]
        assert location in game.collected()
        assert game.received(f"local/{location}")
        method = "original acquisition callback and carrier cleanup" if probe.get("full_callback") else "shared acquisition"
        limit = (
            "skiing controls remain unverified"
            if probe.get("full_callback")
            else "skiing controls and event cleanup remain unverified"
        )
        print(
            "Native Curling Stone initializer, received ownership, s"
            "ource eligibility, "
            f"{method}"
            ", replacement prize and replay passed; "
            f"{limit}"
        )


if __name__ == "__main__":
    main()
