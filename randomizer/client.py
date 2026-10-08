"""Run the native Citra mailbox and Archipelago connection."""

import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path

from .data.catalog import array, obj
from .integrations.archipelago.network import run_client
from .integrations.archipelago.runtime import Ledger, ProtocolClient, ReceivedItem, integer
from .integrations.archipelago.tracker_server import TrackerServer, TrackingSnapshot
from .integrations.citra.memory import CitraMemory
from .integrations.citra.native import NativeGame, NativeProfile


async def run(args: argparse.Namespace) -> None:
    profile = NativeProfile.load(args.patch_report)
    locations = {key: integer(value) for key, value in obj(json.loads(args.locations.read_text(encoding="utf-8"))).items()}
    with CitraMemory(args.emulator_host, args.emulator_port, timeout=2) as memory:
        config = profile.session
        game = NativeGame(memory, profile, config.seed, config.team, config.slot, config.catalog_hash, locations)
        session = game.identity()
        local_rewards = {}
        native_ids = {location: key for key, location in locations.items()}
        for raw in array(json.loads(args.local_rewards.read_text(encoding="utf-8"))):
            item = ReceivedItem.parse(raw)
            if item.location not in native_ids or item.item not in profile.selector_rewards or profile.check_rewards[native_ids[item.location]] != profile.selector_rewards[item.item]:
                raise ValueError("Local reward table does not match installed native placements")
            if item.location in local_rewards:
                raise ValueError("Duplicate local reward location")
            local_rewards[item.location] = item
        snapshot = TrackingSnapshot()
        tracker = None
        if args.tracker_data:
            if args.server:
                raise ValueError("The standalone tracker endpoint requires offline mode")
            tracker = TrackerServer(session, args.name, args.game, json.loads(args.tracker_data.read_text(encoding="utf-8")), lambda: snapshot)
        ledger = Ledger(args.state, session)
        try:
            ledger.bind_local_rewards(local_rewards)
        except Exception:
            ledger.close()
            raise
        stop = asyncio.Event()
        uuid = hashlib.sha256(f"{session.seed}/{session.team}/{session.slot}/{session.save_id}".encode()).hexdigest()
        client = ProtocolClient(ledger, args.name, args.game, uuid, args.password)

        async def watch() -> None:
            nonlocal snapshot
            while not stop.is_set():
                if game.identity() != session:
                    raise ValueError("Save changed while the client was connected")
                for location in game.collected():
                    ledger.record_check(location)
                if game.won():
                    ledger.victory()
                ledger.flush(game)
                if tracker:
                    checked, delivered, won = game.observe()
                    previous = {(item.location, item.item): item for item in snapshot.items if item.location in delivered}
                    for location, item in local_rewards.items():
                        if location in delivered:
                            previous[(item.location, item.item)] = item
                    snapshot = TrackingSnapshot(tuple(sorted(checked)), tuple(previous.values()), won)
                await asyncio.sleep(0.25)

        watcher = asyncio.create_task(watch())
        tasks = [watcher]
        if args.server:
            tasks.append(asyncio.create_task(run_client(client, args.server, game, stop)))
        if tracker:
            tasks.append(asyncio.create_task(tracker.run(args.tracker_port, stop)))
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            ledger.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--locations", type=Path, required=True, help="Native check ID to AP location ID JSON mapping")
    parser.add_argument("--local-rewards", type=Path, required=True, help="NetworkItem array of locally owned placements, for offline delivery and echo deduplication")
    parser.add_argument("--server", help="AP server URL; omit for standalone offline delivery")
    parser.add_argument("--name", required=True)
    parser.add_argument("--game", default="Paper Mario: Sticker Star")
    parser.add_argument("--password")
    parser.add_argument("--tracker-data", type=Path, help="Optional standalone tracker names and catalog mappings JSON")
    parser.add_argument("--tracker-port", type=int, default=38281)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--emulator-host", default="127.0.0.1")
    parser.add_argument("--emulator-port", type=int, default=45987)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        parser.exit(2, f"Client stopped: {error}\n")


if __name__ == "__main__":
    main()
