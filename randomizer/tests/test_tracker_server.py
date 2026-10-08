import asyncio
import json
import unittest

from ..integrations.archipelago.runtime import ReceivedItem, Session
from ..integrations.archipelago.tracker_server import TrackerServer, TrackingSnapshot


class FakeSocket:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.closed = False

    async def send(self, data):
        for packet in json.loads(data):
            await self.outgoing.put(packet)

    async def recv(self):
        return await self.incoming.get()

    async def close(self):
        self.closed = True

    async def input(self, packet):
        await self.incoming.put(json.dumps([packet]))

    async def output(self):
        return await asyncio.wait_for(self.outgoing.get(), 2)


class TrackerServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = Session("standalone", 0, 1, "a" * 64, "save")
        self.data = {"catalog_hash": self.session.catalog_hash, "items": {"Hammer": 100}, "locations": {"Check": 200},
                     "tracker": {"format_version": 1, "catalog_hash": self.session.catalog_hash,
                                 "items": {"100": {"code": "hammer", "type": "toggle"}}, "locations": {"200": "@Stage/Check"}}}
        self.snapshot = TrackingSnapshot()
        self.server = TrackerServer(self.session, "Player", "Sticker Star", self.data, lambda: self.snapshot)

    async def test_check_packet_cannot_grant_items_and_native_receipt_is_separate(self):
        socket = FakeSocket()
        task = asyncio.create_task(self.server.handle(socket))
        try:
            self.assertEqual((await socket.output())["cmd"], "RoomInfo")
            await socket.input({"cmd": "GetDataPackage"})
            self.assertEqual((await socket.output())["cmd"], "DataPackage")
            await socket.input({"cmd": "Connect", "name": "Player", "game": ""})
            self.assertEqual((await socket.output())["cmd"], "Connected")
            self.assertEqual((await socket.output())["items"], [])
            await socket.input({"cmd": "LocationChecks", "locations": [200]})
            await socket.input({"cmd": "Sync"})
            self.assertEqual((await socket.output())["items"], [])
            self.assertEqual(self.snapshot.checks, ())
            self.snapshot = TrackingSnapshot((200,), ())
            self.assertEqual((await socket.output())["cmd"], "RoomUpdate")
            self.snapshot = TrackingSnapshot((200,), (ReceivedItem(100, 200, 1, 1),))
            received = await socket.output()
            self.assertEqual(received["index"], 0)
            self.assertEqual(received["items"][0]["item"], 100)
            await socket.input({"cmd": "Sync"})
            self.assertEqual((await socket.output())["index"], 0)
            self.snapshot = TrackingSnapshot()
            await asyncio.wait_for(task, 2)
            self.assertTrue(socket.closed)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def test_wrong_catalog_and_unknown_native_ids_are_rejected(self):
        data = dict(self.data, catalog_hash="b" * 64)
        with self.assertRaises(ValueError):
            TrackerServer(self.session, "Player", "Sticker Star", data, lambda: self.snapshot)
        self.snapshot = TrackingSnapshot((999,), ())
        with self.assertRaises(ValueError):
            self.server.current()


if __name__ == "__main__":
    unittest.main()
