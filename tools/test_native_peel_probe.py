"""Observe the controlled native peel helper test; never write inventory."""

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
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--startup-wait-seconds", type=int, default=10)
    parser.add_argument("--identity-output", type=Path)
    parser.add_argument("--expected-identity", type=Path)
    parser.add_argument("--expect-pending", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.startup_wait_seconds <= 60:
        parser.error("Startup wait must be between zero and 60 seconds")
    # The RPC listener starts before guest memory exists in this emulator build.
    # Querying it during that window crashes the emulator instead of returning an error.
    time.sleep(args.startup_wait_seconds)
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    if not report.get("native_peel_probe"):
        raise ValueError("Use only the controlled peel-helper probe")
    profile = NativeProfile.load(args.patch_report)
    locations = {identifier: 95000 + index for index, identifier in enumerate(profile.checks)}
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
        identity = None
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            try:
                _, data = game.snapshot()
                if identity is None:
                    identity = game.identity()
                finished = "gf_rando_peel_probe_pending_saved" if args.expect_pending else "gf_rando_peel_probe_done"
                if game.bit(data, profile.flags[finished]):
                    break
            except (OSError, RuntimeError):
                pass
            time.sleep(0.25)
        else:
            raise TimeoutError("Native first-peel/return/save probe did not pass")
        time.sleep(3)
        _, data = game.snapshot()
        assert identity is not None
        assert game.bit(data, profile.flags["gf_rando_peel_probe_first"])
        failed = [
            name
            for flag, name in report["native_peel_probe"].get("queries", {}).items()
            if not game.bit(data, profile.flags[flag])
        ]
        assert game.bit(data, profile.flags["gf_rando_peel_probe_return"]), failed
        if args.expect_pending:
            assert game.bit(data, profile.flags["gf_rando_peel_probe_pending_held"])
            assert data[384 + profile.game_saved_bytes["gs_rando_peel_pending"]] == 1
        elif report["native_peel_probe"].get("pending_return"):
            assert game.bit(data, profile.flags["gf_rando_peel_probe_pending_survived"])
            assert data[384 + profile.game_saved_bytes["gs_rando_peel_pending"]] == 1
        assert game.bit(data, profile.flags["gf_rando_peel_probe_saved"])
        if report["native_peel_probe"].get("first_while_pending"):
            assert game.bit(data, profile.flags["gf_rando_peel_probe_pending_first"])
        assert game.collected() == set(locations.values())
        assert all(game.received(f"local/{location}") for location in locations.values())
        if args.expected_identity:
            expected = json.loads(args.expected_identity.read_text(encoding="utf-8"))
            assert identity.save_id == expected["save_id"]
        if args.identity_output:
            args.identity_output.write_text(json.dumps({"save_id": identity.save_id}), encoding="utf-8")
        if report["native_peel_probe"].get("pending_return"):
            print(
                "Native first-peel receipts, full-album deferred return and saved "
                "identity passed; inventory remains untouched during reload"
            )
        else:
            print("Native first-peel rewards, all returned variants, bounded native returns and replay rejection passed")


if __name__ == "__main__":
    main()
