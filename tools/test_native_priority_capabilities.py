"""Verify incoming entitlements pass a blocked native scrap delivery.

Use only a disposable completed pending-peel fixture. The host writes the
dedicated request mailbox and save identity; game code owns all inventory,
accessory flags, capability receipts and acknowledgements.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.archipelago.runtime import ReceivedItem
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile
from randomizer.integrations.rom.native_delivery import NativeReward, NativeRewardKind


def scrap_album(memory: CitraMemory) -> Counter[int]:
    pouch = memory.read_u32(0x4327F0)
    if not 0x08000000 <= pouch <= 0x40000000 - 0xC40 or pouch % 4:
        raise ValueError("Native pouch is not loaded")
    raw = memory.read(pouch + 0x698, 9 * 160)
    counts: Counter[int] = Counter()
    for page in range(9):
        for slot in range(15):
            item, _, position, _, _ = struct.unpack_from("<5H", raw, page * 160 + slot * 10)
            if position & 0x3FFF != 0x3FFF:
                counts[item & 0x3FFF] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    if not report.get("priority_capabilities") or not report.get("native_peel_probe", {}).get("pending_return"):
        raise ValueError("Use the isolated priority-capability pending-peel fixture")
    profile = NativeProfile.load(args.patch_report)
    session = profile.session
    wanted = (
        NativeReward(NativeRewardKind.ITEM, report["checks"][0]["source_item"]),
        NativeReward(NativeRewardKind.ABILITY, "paperization"),
        NativeReward(NativeRewardKind.STAGE_ACCESS, "X00"),
        NativeReward(NativeRewardKind.ABILITY, "hammer"),
    )
    identifiers = [
        next(identifier for identifier, reward in profile.selector_rewards.items() if reward == expected)
        for expected in wanted
    ]
    incoming = tuple((index, ReceivedItem(identifier, 98000 + index, 2, 1)) for index, identifier in enumerate(identifiers))
    with CitraMemory(timeout=1) as memory:
        game = NativeGame(
            memory,
            profile,
            session.seed,
            session.team,
            session.slot,
            session.catalog_hash,
            {identifier: 95000 + index for index, identifier in enumerate(profile.checks)},
        )
        identity = game.identity()
        _, data = game.snapshot()
        if not game.bit(data, profile.flags["gf_rando_peel_probe_pending_held"]):
            raise ValueError("The native full-album fixture has not completed")
        before = scrap_album(memory)
        if game.word(data, "ack_ready") or game.word(data, "ack"):
            raise ValueError("Use a fixture with an unused incoming stream")
        game.prepare_pages(incoming)
        blocked = incoming[0][1]
        for index, item in incoming[1:]:
            receipt = f"ap/{index}"
            deadline = time.monotonic() + 20
            while not game.received(receipt):
                if game.deliver("ap/0", blocked):
                    raise AssertionError("Full scrap album accepted the blocked prefix item")
                game.deliver_priority(receipt, item)
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Native priority capability did not arrive: {receipt}")
                time.sleep(0.1)
            assert game.deliver_priority(receipt, item)
            assert not game.received("ap/0")
            _, data = game.snapshot()
            assert game.word(data, "ack") == 0
            assert data[384 + profile.game_saved_bytes["gs_rando_peel_pending"]] == 1
            assert scrap_album(memory) == before
        pouch = memory.read_u32(0x4327F0)
        assert memory.read_u32(pouch + 0x13C) & 5 == 5
        assert game.bit(game.snapshot()[1], profile.flags["gf_rando_stage_x00"])
        assert game.identity() == identity
        print("Native full-scrap-album Paperization, town access, Hammer, replay and unchanged prefix/inventory passed")


if __name__ == "__main__":
    main()
