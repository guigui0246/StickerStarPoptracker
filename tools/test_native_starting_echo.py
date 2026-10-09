"""Verify AP's precollected-item prefix acknowledges native starting receipts.

Run only against a fresh disposable generated-patch profile. Host writes are
limited to the request mailbox and save nonce; inventory remains game-owned.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.archipelago.runtime import ReceivedItem
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile
from tools.test_native_remote_inventory import album


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--port", type=int, default=45987)
    args = parser.parse_args()
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    starting = report.get("starting_item_ids", [])
    receipts = report.get("starting_flags", [])
    if not starting or len(starting) != len(receipts):
        raise ValueError("Patch must contain an AP-bound starting inventory")
    profile = NativeProfile.load(args.patch_report)
    session = profile.session
    with CitraMemory(port=args.port, timeout=1) as memory:
        game = NativeGame(memory, profile, session.seed, session.team, session.slot, session.catalog_hash, {})
        deadline = time.monotonic() + 180
        while True:
            try:
                _, flags = game.snapshot()
                if all(game.bit(flags, position) for position in receipts):
                    break
            except (RuntimeError, TimeoutError):
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("Native starting inventory did not initialize")
            time.sleep(0.25)
        game.identity()

        def inventory() -> tuple[object, int]:
            pouch = memory.read_u32(0x4327F0)
            return album(memory), memory.read_u32(pouch + 0x13C)

        before = inventory()
        for index, identifier in enumerate(starting):
            item = ReceivedItem(identifier, -2, 0, 1)
            deadline = time.monotonic() + 20
            while not game.deliver(f"ap/{index}", item):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Starting-item echo was not acknowledged")
                time.sleep(0.1)
            assert inventory() == before, "Starting-item echo changed native inventory"
            assert game.deliver(f"ap/{index}", item), "Starting-item replay lost its receipt"
            assert inventory() == before, "Starting-item replay changed native inventory"
        print(
            json.dumps(
                {"starting_echo_passed": True, "precollected_receipts": len(starting), "host_inventory_writes": 0}, indent=2
            )
        )


if __name__ == "__main__":
    main()
