"""Exercise native PAGE/sticker mailbox grants in a disposable probe fixture.

The host writes only the existing request mailbox and save nonce. Inventory,
ownership and acknowledgements are changed exclusively by game scripts.
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
from randomizer.integrations.rom.native_delivery import NativeRewardKind


def album(memory: CitraMemory) -> tuple[int, Counter[int]]:
    pouch = memory.read_u32(0x4327F0)
    pages = memory.read_u32(pouch + 0xCDC)
    if not 2 <= pages <= 8:
        raise ValueError("Unexpected native album capacity")
    counts: Counter[int] = Counter()
    raw = memory.read(pouch + 0x198, pages * 160)
    for page in range(pages):
        for slot in range(15):
            item, _, position, _, _ = struct.unpack_from("<5H", raw, page * 160 + slot * 10)
            if position & 0x3FFF != 0x3FFF:
                counts[item & 0x3FFF] += 1
    return pages, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--port", type=int, default=45987)
    args = parser.parse_args()
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    if not report.get("native_sticker_probe") or not report.get("native_probe_retry"):
        raise ValueError("Run only against the disposable completed full-album probe")
    profile = NativeProfile.load(args.patch_report)
    page_id = next(identifier for identifier, reward in profile.selector_rewards.items() if reward.kind == NativeRewardKind.PAGE)
    jump_id = next(identifier for identifier, reward in profile.selector_rewards.items() if reward.kind == NativeRewardKind.STICKER_UNLOCK and reward.value == "SL_JUMP")
    with CitraMemory(port=args.port, timeout=1) as memory:
        session = profile.session
        game = NativeGame(memory, profile, session.seed, session.team, session.slot, session.catalog_hash,
                          {identifier: index for index, identifier in enumerate(profile.checks, 1000)})
        game.identity()
        _, flags = game.snapshot()
        if not game.bit(flags, profile.flags["gf_rando_probe_done"]):
            raise ValueError("The native full-album probe has not completed")
        before_pages, before = album(memory)

        def grant(index: int, identifier: int) -> None:
            item = ReceivedItem(identifier, 9000 + index, session.slot, 1)
            receipt = f"ap/{index}"
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if game.deliver(receipt, item):
                    return
                time.sleep(0.1)
            raise TimeoutError(f"Native mailbox did not acknowledge sequence {index + 1}")

        # A nontrivial sequence also tests that nested grant calls preserve the
        # caller's sequence register rather than publishing a boolean as ACK.
        grant(16, page_id)
        grant(17, jump_id)
        pages, counts = album(memory)
        assert pages == before_pages + 1, "PAGE receipt did not increase capacity exactly once"
        assert counts[16] == before[16] + 1, "The generic unlock did not commit its Jump copy"
        grant(17, jump_id)
        assert album(memory) == (pages, counts), "Replayed native receipt duplicated inventory"
        _, flags = game.snapshot()
        assert game.bit(flags, profile.flags["gf_rando_unlock_sl_jump"]), "The received sticker did not unlock Jump"
        print(json.dumps({"native_remote_inventory_passed": True, "page_count": pages,
                          "jump_copies": counts[16], "acknowledged_sequence": 18,
                          "host_inventory_writes": 0}, indent=2))


if __name__ == "__main__":
    main()
