"""Exercise real WebSockets using Archipelago 0.6.8's actual wire serializer.

This validates client transport, not a playable multiworld session.
"""

import argparse
import asyncio
from pathlib import Path
import sys
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ap-root", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(project), str(args.ap_root.resolve()), str(args.dependencies.resolve())]
    from NetUtils import NetworkItem, encode, decode  # pyright: ignore[reportMissingImports]
    from Utils import version_tuple  # pyright: ignore[reportMissingImports]
    from websockets.asyncio.server import serve  # pyright: ignore[reportMissingImports]
    from websockets.asyncio.client import connect  # pyright: ignore[reportMissingImports]
    from websockets.exceptions import ConnectionClosed  # pyright: ignore[reportMissingImports]
    from randomizer.integrations.archipelago.runtime import Ledger, ProtocolClient, Session
    from randomizer.integrations.archipelago.network import run_client
    from randomizer.tests.test_ap_runtime import FakeGame
    from randomizer.integrations.archipelago.tracker_server import TrackerServer, TrackingSnapshot
    from randomizer.integrations.archipelago.runtime import ReceivedItem

    if tuple(version_tuple) != (0, 6, 8):
        raise ValueError("Expected Archipelago 0.6.8")

    async def scenario() -> None:
        session = Session("test-seed", 0, 1, "a" * 64, "save-one")
        stop = asyncio.Event()
        game = FakeGame()
        with tempfile.TemporaryDirectory(dir=project) as directory:
            ledger = Ledger(Path(directory) / "state.sqlite", session)
            ledger.record_check(200)
            ledger.victory()
            client = ProtocolClient(ledger, "Player", "Test", "test-client")

            async def handler(socket):
                await socket.send(encode([{"cmd": "RoomInfo", "seed_name": session.seed}]))
                connect = decode(await socket.recv())[0]
                assert connect["cmd"] == "Connect" and tuple(connect["version"]) == (0, 6, 8)
                assert connect["items_handling"] == 7
                await socket.send(
                    encode(
                        [
                            {
                                "cmd": "Connected",
                                "team": 0,
                                "slot": 1,
                                "slot_data": {"format_version": 1, "catalog_hash": session.catalog_hash},
                            }
                        ]
                    )
                )
                replay = decode(await socket.recv())
                assert {packet["cmd"] for packet in replay} == {"Sync", "LocationChecks", "StatusUpdate"}
                await socket.send(encode([{"cmd": "ReceivedItems", "index": 0, "items": [NetworkItem(100, 200, 2, 1)]}]))
                await socket.send(encode([{"cmd": "ReceivedItems", "index": 0, "items": [NetworkItem(100, 200, 2, 1)]}]))
                for _ in range(100):
                    if game.grants:
                        break
                    await asyncio.sleep(0.01)
                assert game.grants == [100]
                stop.set()

            try:
                async with serve(handler, "127.0.0.1", 0) as server:
                    port = server.sockets[0].getsockname()[1]
                    await asyncio.wait_for(run_client(client, f"ws://127.0.0.1:{port}", game, stop), 10)
                assert ledger.count == 1
            finally:
                ledger.close()
        print("AP 0.6.8 wire serialization, authentication, checks, victory and duplicate item delivery passed")
        session = Session("standalone", 0, 1, "a" * 64, "save-one")
        state = [TrackingSnapshot()]
        mappings = {
            "format_version": 1,
            "catalog_hash": session.catalog_hash,
            "items": {"100": {"code": "hammer", "type": "toggle"}},
            "locations": {"200": "@Stage/Check"},
        }
        tracker = TrackerServer(
            session,
            "Player",
            "Test",
            {
                "catalog_hash": session.catalog_hash,
                "items": {"Marteau éblouissant": 100},
                "locations": {"Check": 200},
                "tracker": mappings,
            },
            lambda: state[0],
        )

        async def tracker_handler(socket):
            try:
                await tracker.handle(socket)
            except ConnectionClosed:
                pass

        async with serve(tracker_handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as socket:
                room = decode(await socket.recv())[0]
                assert tuple(room["version"]) == (0, 6, 8)
                await socket.send(encode([{"cmd": "GetDataPackage"}]))
                package = decode(await socket.recv())[0]["data"]["games"]["Test"]
                import hashlib

                expected = hashlib.sha1(
                    encode({key: value for key, value in package.items() if key != "checksum"}).encode()
                ).hexdigest()
                assert package["checksum"] == expected == room["datapackage_checksums"]["Test"]
                await socket.send(encode([{"cmd": "Connect", "name": "Player", "tags": ["Tracker"], "game": ""}]))
                connected = decode(await socket.recv())
                assert connected[0]["cmd"] == "Connected" and connected[1]["items"] == []
                await socket.send(encode([{"cmd": "LocationChecks", "locations": [200]}, {"cmd": "Sync"}]))
                assert decode(await socket.recv())[0]["items"] == [] and not state[0].checks
                state[0] = TrackingSnapshot((200,), ())
                assert decode(await asyncio.wait_for(socket.recv(), 2))[0]["cmd"] == "RoomUpdate"
                state[0] = TrackingSnapshot((200,), (ReceivedItem(100, 200, 1, 1),))
                item = decode(await asyncio.wait_for(socket.recv(), 2))[0]["items"][0]
                assert item == NetworkItem(100, 200, 1, 1)
        print("Standalone tracker wire format, data-package checksum and separate native check/receipt reporting passed")

    asyncio.run(scenario())


if __name__ == "__main__":
    main()
