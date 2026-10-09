"""Exercise the real AP ledger with a native pending local sticker and page."""

import argparse
import json
from pathlib import Path
import struct
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.archipelago.runtime import Ledger, ReceivedItem
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile
from randomizer.integrations.rom.native_delivery import NativeRewardKind


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=90)
    args = parser.parse_args()
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    remote = report.get("native_remote_page_probe", False)
    source = report.get("native_local_page_probe")
    if not source:
        raise ValueError("Use only the controlled full-album/local-page fixture")
    profile = NativeProfile.load(args.patch_report)
    writes = []
    with CitraMemory(timeout=1) as memory:
        original_write = memory.write

        def write(address, data):
            writes.append((address, len(data)))
            original_write(address, data)

        memory.write = write
        location = 91000
        game = NativeGame(
            memory,
            profile,
            profile.session.seed,
            profile.session.team,
            profile.session.slot,
            profile.session.catalog_hash,
            {source: location},
        )
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            try:
                base, flags = game.snapshot()
                if game.bit(flags, profile.flags["gf_rando_probe_local_ready"]):
                    break
            except (RuntimeError, OSError):
                pass
            time.sleep(0.25)
        else:
            raise TimeoutError("Full-album native fixture is not ready")
        assert game.collected() == (set() if remote else {location})
        assert not game.received(f"local/{location}")
        pouch = memory.read_u32(0x4327F0)
        assert memory.read_u32(pouch + 0xCDC) == 2

        def inventory():
            pages = memory.read_u32(pouch + 0xCDC)
            raw = memory.read(pouch + 0x198, pages * 160)
            return [
                struct.unpack_from("<H", raw, page * 160 + slot * 10)[0] & 0x3FFF
                for page in range(pages)
                for slot in range(15)
                if struct.unpack_from("<H", raw, page * 160 + slot * 10 + 4)[0] & 0x3FFF != 0x3FFF
            ]

        assert len(inventory()) == 30
        session = game.identity()
        hammer = next(
            identifier
            for identifier, reward in profile.selector_rewards.items()
            if reward.kind == NativeRewardKind.STICKER_UNLOCK and reward.value == "SL_HAMMER"
        )
        page = next(
            identifier for identifier, reward in profile.selector_rewards.items() if reward.kind == NativeRewardKind.PAGE
        )
        local = ReceivedItem(hammer, location, session.slot, 1)
        with tempfile.TemporaryDirectory(prefix=".local-page-ledger-", dir=args.patch_report.parent) as directory:
            ledger = Ledger(Path(directory) / "ledger.sqlite", session)
            try:
                if remote:
                    ledger.receive(
                        0,
                        (ReceivedItem(hammer, location, session.slot + 1, 1), ReceivedItem(page, 92000, session.slot + 1, 1)),
                    )
                else:
                    ledger.bind_local_rewards({location: local})
                    ledger.record_check(location)
                    ledger.receive(0, (local, ReceivedItem(page, 92000, session.slot + 1, 1)))
                if remote:
                    ledger.flush(game)
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline and not game.received("ap/1"):
                        time.sleep(0.1)
                    assert game.received("ap/1"), "Priority page did not arrive"
                    assert not game.received("ap/0"), "Page falsely acknowledged the blocked sticker"
                    assert game.word(game.snapshot()[1], "ack") == 0
                    assert memory.read_u32(pouch + 0xCDC) == 3
                    assert inventory().count(43) == 0
                    time.sleep(0.5)
                    assert memory.read_u32(pouch + 0xCDC) == 3, "Repeated priority command duplicated a page"
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    with game.cached_local_receipts():
                        ledger.flush(game)
                    if game.received("ap/0" if remote else f"local/{location}") and game.received("ap/1"):
                        break
                    time.sleep(0.25)
                else:
                    raise TimeoutError("Pending local reward blocked the remote page")
                assert memory.read_u32(pouch + 0xCDC) == 3
                assert inventory().count(43) == 1
                assert len(inventory()) == 31
                for _ in range(3):
                    with game.cached_local_receipts():
                        assert ledger.flush(game) == 0
                assert inventory().count(43) == 1
                assert memory.read_u32(pouch + 0xCDC) == 3
            finally:
                ledger.close()
        allowed = {
            (base + profile.word_offset(name), profile.word_size(name))
            for name in (
                ("save_a", "save_b", "save_c", "save_d", "sequence", "item", "ready", "page_rank")
                if profile.priority_pages
                else ("save_a", "save_b", "save_c", "save_d", "sequence", "item", "ready")
            )
        }
        assert set(writes) <= allowed
        print(
            "Native remote sticker/page priority and replay passed; no host inventory writes"
            if remote
            else "Native local sticker retry, remote page delivery and echo/replay passed; no host inventory writes"
        )


if __name__ == "__main__":
    main()
