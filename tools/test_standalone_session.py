"""Compare a real loopback tracker connection with read-only native receipts.

Start the matching standalone game and `track` bridge before running this tool.
No native memory writes or inventory changes are performed.
"""

import argparse
import asyncio
import importlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.data.catalog import Json, array, obj, string
from randomizer.integrations.archipelago.standalone_tracking import StandaloneObservation
from randomizer.integrations.citra.memory import CitraMemory
from randomizer.integrations.citra.native import NativeGame, NativeProfile
from randomizer.integrations.rom.seed_patch import unique_object
from randomizer.track_standalone import ReadOnlyMemory


async def verify(args: argparse.Namespace) -> None:
    def load(path: Path) -> Json:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)

    config = obj(load(Path(str(args.seed) + ".tracking.json")))
    report = load(args.report)
    profile = NativeProfile.load(args.report, standalone_catalog_hash=string(config["catalog_hash"]))
    expected_data = obj(load(Path(str(args.seed) + ".tracker-data.json")))
    client = importlib.import_module("websockets.asyncio.client")
    with CitraMemory(port=args.emulator_port) as memory:
        game = NativeGame(
            ReadOnlyMemory(memory), profile, profile.session.seed, 0, 1, profile.session.catalog_hash,
            {key: int(str(value)) for key, value in obj(config["locations"]).items()},
        )
        observer = StandaloneObservation(config, profile, game, report)
        state = observer.snapshot()
        for reconnect in range(2):
            async with client.connect(f"ws://127.0.0.1:{args.port}", open_timeout=5) as socket:
                room = obj(array(json.loads(await asyncio.wait_for(socket.recv(), 5)))[0])
                if room.get("cmd") != "RoomInfo" or room.get("seed_name") != config["seed"]:
                    raise ValueError("Tracker server is observing a different seed")
                await socket.send(json.dumps([{"cmd": "GetDataPackage"}]))
                packet = obj(array(json.loads(await asyncio.wait_for(socket.recv(), 5)))[0])
                packages = obj(obj(packet["data"])["games"])
                package = obj(next(iter(packages.values())))
                if package["item_name_to_id"] != expected_data["items"]:
                    raise ValueError("Tracker item registry differs from the generated seed")
                if package["location_name_to_id"] != expected_data["locations"]:
                    raise ValueError("Tracker location registry differs from the generated seed")
                await socket.send(json.dumps([{"cmd": "Connect", "name": args.name}]))
                packets = [obj(value) for value in array(json.loads(await asyncio.wait_for(socket.recv(), 5)))]
                connected, received = packets
                if connected["checked_locations"] != list(state.checks):
                    raise ValueError("Tracker checks differ from native collected receipts")
                if obj(connected["slot_data"])["catalog_hash"] != config["catalog_hash"]:
                    raise ValueError("Tracker catalog identity differs from the native game")
                expected_items = [item.item for item in state.items]
                if [obj(item)["item"] for item in array(received["items"])] != expected_items:
                    raise ValueError("Tracker inventory differs from native delivery receipts")
                await socket.send(json.dumps([
                    {"cmd": "LocationChecks", "locations": list(obj(config["locations"]).values())}, {"cmd": "Sync"},
                ]))
                replay = obj(array(json.loads(await asyncio.wait_for(socket.recv(), 5)))[0])
                if replay != received or observer.snapshot() != state:
                    raise ValueError("Tracker client packets changed the native observation")
                print(f"Connection {reconnect + 1}: {len(state.items)} received items, {len(state.checks)} checks", flush=True)
        proof = {
            "seed": config["seed"], "catalog_hash": config["catalog_hash"],
            "save_seed_fingerprint": profile.fingerprint.hex(),
            "native_items": len(state.items), "native_checks": len(state.checks),
            "connections": 2, "client_packets_modify_native_state": False,
        }
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(proof, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--name", default="Player")
    parser.add_argument("--port", default=38281, type=int)
    parser.add_argument("--emulator-port", default=45987, type=int)
    asyncio.run(verify(parser.parse_args()))


if __name__ == "__main__":
    main()
