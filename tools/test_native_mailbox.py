"""Exercise the dedicated native-rpc-ability-v2 fixture in an isolated emulator.

Writes only the public NativeGame mailbox/save nonce, never inventory or receipts.
The fixture guard prevents running these synthetic server items on another seed.
"""

import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.archipelago.runtime import ReceivedItem
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile
from randomizer.integrations.rom.native_delivery import NativeReward, NativeRewardKind


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--port", type=int, default=45987)
    args = parser.parse_args()
    profile = NativeProfile.load(args.patch_report)
    expected = {100: NativeReward(NativeRewardKind.COINS, 25),
                101: NativeReward(NativeRewardKind.ABILITY, "hammer"),
                102: NativeReward(NativeRewardKind.ABILITY, "paperization")}
    if profile.session.seed != "native-rpc-ability-v2" or profile.selector_rewards != expected:
        raise ValueError("Run only against the dedicated fresh-save ability mailbox fixture")
    locations = {identifier: index for index, identifier in enumerate(profile.checks, 1000)}
    with CitraMemory(port=args.port, timeout=1) as memory:
        game = NativeGame(memory, profile, profile.session.seed, profile.session.team,
                          profile.session.slot, profile.session.catalog_hash, locations)
        identity = game.identity()  # verifies code guards and seed before any write
        original_checks = game.collected()
        pouch = memory.read_u32(0x4327F0)
        assert memory.read_u32(pouch + 0xCDC) == 8, "All-at-start fixture did not unlock eight native album pages"
        if memory.read_u32(pouch + 0x13C) & 5:
            raise ValueError("Fixture already owns an ability; use a fresh save")
        for index, item_id in enumerate(expected):
            receipt = f"ap/{index}"
            item = ReceivedItem(item_id, 9000 + index, 2, 1)
            deadline = time.monotonic() + 20
            while not game.deliver(receipt, item):
                if time.monotonic() > deadline:
                    raise TimeoutError(f"Native receipt did not commit: {receipt}")
                time.sleep(0.1)
            if index:
                bit = 1 if index == 1 else 4
                assert memory.read_u32(pouch + 0x13C) & bit, "Receipt committed without native accessory ownership"
            assert game.deliver(receipt, item), "Replay lost a native receipt"
            assert game.identity() == identity, "Mailbox altered save identity"
        assert game.collected() == original_checks, "Incoming items marked source checks"
        print("Eight native album pages, mailbox receipts, Hammer/Paperization accessories, replay and check separation passed.")
        print("Save-file persistence and source check collection still require separate gameplay tests.")


if __name__ == "__main__":
    main()
