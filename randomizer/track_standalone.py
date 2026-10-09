"""Serve optional PopTracker observations without writing to the game."""

import argparse
import asyncio
import json
from pathlib import Path

from .data.catalog import Json, obj, string
from .integrations.archipelago.runtime import Session, integer
from .integrations.archipelago.standalone_tracking import StandaloneObservation
from .integrations.archipelago.tracker_server import TrackerServer, TrackingSnapshot
from .integrations.citra.memory import CitraMemory
from .integrations.citra.native import NativeGame, NativeProfile
from .integrations.rom.seed_patch import unique_object


class ReadOnlyMemory:
    def __init__(self, memory: CitraMemory) -> None:
        self.memory = memory

    def read(self, address: int, size: int) -> bytes:
        return self.memory.read(address, size)

    def write(self, address: int, data: bytes) -> None:
        raise RuntimeError("Standalone tracking cannot modify game memory")


async def run(args: argparse.Namespace) -> None:
    def load(path: Path) -> Json:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Tracking configuration exceeds the supported size")
        result: Json = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        return result

    config = obj(load(args.config))
    profile = NativeProfile.load(args.patch_report, standalone_catalog_hash=string(config.get("catalog_hash")))
    locations = {key: integer(value) for key, value in obj(config.get("locations")).items()}
    with CitraMemory("127.0.0.1", args.emulator_port, timeout=2) as memory:
        game = NativeGame(ReadOnlyMemory(memory), profile, profile.session.seed, 0, 1, profile.session.catalog_hash, locations)
        observer = StandaloneObservation(config, profile, game, load(args.patch_report))
        session = Session(profile.session.seed, 0, 1, profile.session.catalog_hash, profile.fingerprint.hex())
        snapshot = TrackingSnapshot()
        stop = asyncio.Event()
        server = TrackerServer(
            session, args.name, "Paper Mario: Sticker Star (Native Catalog)", load(args.tracker_data), lambda: snapshot
        )

        async def poll() -> None:
            nonlocal snapshot
            while not stop.is_set():
                try:
                    snapshot = observer.snapshot()
                except (RuntimeError, OSError):
                    # During reset/load there is no current native inventory.
                    # Clearing the view triggers the normal tracker replay.
                    snapshot = TrackingSnapshot()
                await asyncio.sleep(0.5)

        tasks = [asyncio.create_task(poll()), asyncio.create_task(server.run(args.tracker_port, stop))]
        try:
            await asyncio.gather(*tasks)
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, help="Generated .stickerpatch; locates matching tracker sidecars")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--patch-report", type=Path, help="Defaults to the report beside --seed")
    parser.add_argument("--tracker-data", type=Path)
    parser.add_argument("--name", default="Player")
    parser.add_argument("--emulator-port", type=int, default=45987)
    parser.add_argument("--tracker-port", type=int, default=38281)
    args = parser.parse_args(argv)
    if args.seed is not None:
        if args.config is not None or args.tracker_data is not None:
            parser.error("Use --seed or explicit --config and --tracker-data")
        args.config = Path(str(args.seed) + ".tracking.json")
        args.tracker_data = Path(str(args.seed) + ".tracker-data.json")
        args.patch_report = args.patch_report or Path(str(args.seed) + ".patch-report.json")
    elif args.config is None or args.tracker_data is None:
        parser.error("Use --seed or provide both --config and --tracker-data")
    if args.patch_report is None:
        parser.error("Explicit tracker configuration also requires --patch-report")
    if not args.patch_report.is_file():
        parser.error("Patch report is missing; use a seed from generate or supply --patch-report")
    print(f"Standalone auto tracking: connect PopTracker to localhost:{args.tracker_port} as {args.name}", flush=True)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
