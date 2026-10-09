"""Read game-owned scrap inventory queries and exercise native Royal/coin grants."""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.archipelago.runtime import ReceivedItem
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile
from randomizer.integrations.rom.native_delivery import NativeRewardKind


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", required=True, type=Path)
    parser.add_argument("--port", type=int, default=45987)
    parser.add_argument(
        "--royal-gate", action="store_true", help="Receive Royal 6 first and verify it cannot replace Royals 1–5"
    )
    args = parser.parse_args()
    report = json.loads(args.patch_report.read_text(encoding="utf-8"))
    queries = report.get("native_reward_queries")
    if not queries:
        raise ValueError("Use only the disposable native query fixture")
    profile = NativeProfile.load(args.patch_report)
    session = profile.session
    with CitraMemory(port=args.port, timeout=1) as memory:
        game = NativeGame(memory, profile, session.seed, session.team, session.slot, session.catalog_hash, {})

        def wait_for(predicate, seconds: int = 120) -> bytes:
            deadline = time.monotonic() + seconds
            last_error = "Expected native condition is not yet true"
            while time.monotonic() < deadline:
                try:
                    _, data = game.snapshot()
                    if predicate(data):
                        return data
                except (RuntimeError, TimeoutError, OSError) as error:
                    last_error = str(error)
                time.sleep(0.25)
            raise TimeoutError(last_error)

        wait_for(lambda flags: all(game.bit(flags, profile.flags[name]) for name in queries))
        game.identity()
        pouch = memory.read_u32(0x4327F0)
        before_pages = memory.read_u32(pouch + 0xCDC)
        assert before_pages == 2, "The randomized-page fixture lost its two base pages"

        def grant(index: int, kind: NativeRewardKind, value: str | int) -> None:
            identifier = next(
                identifier
                for identifier, reward in profile.selector_rewards.items()
                if reward.kind == kind and reward.value == value
            )
            item = ReceivedItem(identifier, 9000 + index, session.slot, 1)
            wait_for(lambda _: game.deliver(f"ap/{index}", item), 20)
            assert game.deliver(f"ap/{index}", item), "Replay lost its native receipt"

        grant(0, NativeRewardKind.ROYAL, 6 if args.royal_gate else 1)
        wait_for(lambda flags: game.bit(flags, profile.flags["gf_rando_probe_one_royal"]), 10)
        assert memory.read_u32(pouch + 0xCDC) == before_pages, "Royal ownership unexpectedly granted an album page"
        _, flags = game.snapshot()
        assert not game.bit(flags, profile.checks["boss/gf_evt_1_6_royal_seal"].collected), (
            "Receiving a Royal Sticker completed its source boss"
        )
        if args.royal_gate:
            wait_for(lambda flags: game.bit(flags, profile.flags["gf_rando_probe_royal_gate_zero"]), 10)
            for index in range(1, 5):
                grant(index, NativeRewardKind.ROYAL, index)
            # Five total Royals including Royal 6 must still leave the gate shut.
            wait_for(lambda flags: not game.bit(flags, profile.flags["gf_rando_probe_royal_gate_zero"]), 10)
            _, flags = game.snapshot()
            assert not game.bit(flags, profile.flags["gf_rando_probe_royal_gate_five"]), (
                "Royal 6 substituted for a missing first-five Royal"
            )
            grant(5, NativeRewardKind.ROYAL, 5)
            wait_for(lambda flags: game.bit(flags, profile.flags["gf_rando_probe_royal_gate_five"]), 10)
        grant(6 if args.royal_gate else 1, NativeRewardKind.COINS, 25)
        wait_for(lambda flags: game.bit(flags, profile.flags["gf_rando_probe_25_coins"]), 10)
        print(
            json.dumps(
                {
                    "native_scrap_queries_passed": len(queries),
                    "royal_without_boss_or_page_passed": True,
                    "first_five_royals_gate_passed": args.royal_gate,
                    "coin_grant_and_replay_passed": True,
                    "host_inventory_writes": 0,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
