"""Read the one-shot native sticker probe; never write emulator memory."""

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--port", type=int, default=45987)
    parser.add_argument("--wait-seconds", type=int, default=90)
    args = parser.parse_args()
    report = json.loads(args.patch_report.read_text())
    probe = report.get("native_sticker_probe", {})
    if probe not in ({"normal_item": "SL_JUMP", "forced_item": forced, "unlock_item": "SL_HAMMER"} for forced in (None, "SL_JUMP")):
        raise ValueError("Use only the dedicated one-shot sticker probe fixture")
    profile = NativeProfile.load(args.patch_report)
    locations = {identifier: index for index, identifier in enumerate(profile.checks, 1000)}
    with CitraMemory(port=args.port, timeout=1) as memory:
        game = NativeGame(memory, profile, profile.session.seed, profile.session.team,
                          profile.session.slot, profile.session.catalog_hash, locations)
        deadline = time.monotonic() + args.wait_seconds
        last_error = "Probe has not completed"
        while time.monotonic() < deadline:
            try:
                _, flags = game.snapshot()
                if game.bit(flags, profile.flags["gf_rando_probe_done"]):
                    break
            except (RuntimeError, ValueError, TimeoutError, OSError) as error:
                last_error = str(error)
            time.sleep(0.5)
        else:
            raise TimeoutError(last_error)
        tested = ("normal", "unlock", "forced") if probe["forced_item"] else ("normal", "unlock")
        assert all(game.bit(flags, profile.flags[f"gf_rando_probe_{name}"]) for name in tested), "A native insertion failed"
        assert not game.bit(flags, profile.flags["gf_rando_unlock_sl_jump"]), "Ordinary Jump copies unlocked Jump"
        assert game.bit(flags, profile.flags["gf_rando_unlock_sl_hammer"]), "Unlock reward lost ownership"
        pouch = memory.read_u32(0x4327F0)
        pages = memory.read_u32(pouch + 0xCDC)
        assert pages == 2, "Randomized mode did not preserve the two base pages"
        album = memory.read(pouch + 0x198, pages * 160)
        counts = Counter()
        for offset in (page * 160 + slot * 10 for page in range(pages) for slot in range(15)):
            item = struct.unpack_from("<H", album, offset)[0] & 0x3FFF
            position = struct.unpack_from("<H", album, offset + 4)[0] & 0x3FFF
            if position != 0x3FFF:
                counts[item] += 1
        assert counts[16] == 0, "Locked ordinary Jump entered inventory"
        assert counts[81] >= (2 if probe["forced_item"] else 1), "Locked copies did not become Sandals"
        retry = report.get("native_probe_retry", False)
        if retry:
            assert game.bit(flags, profile.flags["gf_rando_probe_full_rejected"]), "A full album accepted an extra sticker"
            assert game.bit(flags, profile.flags["gf_rando_probe_retry_delivered"]), "The pending copy failed to retry after space was freed"
        assert counts[43] == (2 if retry else 1), "Hammer copy delivery was lost or duplicated"
        print(json.dumps({"native_probe_passed": True, "album_pages": pages,
                          "jump_copies": counts[16], "sandal_copies": counts[81], "hammer_copies": counts[43],
                          "forced_insertion_tested": bool(probe["forced_item"]),
                          "full_album_retry_tested": bool(retry),
                          "host_memory_writes": 0}, indent=2))


if __name__ == "__main__":
    main()
