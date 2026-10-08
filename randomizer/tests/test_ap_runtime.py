import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..integrations.archipelago.runtime import Ledger, ProtocolClient, ReceivedItem, Session
from ..integrations.archipelago.network import run_client


SESSION = Session("test-seed", 0, 1, "a" * 64, "save-one")
ITEM = ReceivedItem(100, 200, 2, 1)


class FakeGame:
    def __init__(self) -> None:
        self.session = SESSION
        self.receipts: set[str] = set()
        self.grants: list[int] = []
        self.full = False

    def identity(self) -> Session:
        return self.session

    def received(self, receipt: str) -> bool:
        return receipt in self.receipts

    def deliver(self, receipt: str, item: ReceivedItem) -> bool:
        if self.full:
            return False
        if receipt not in self.receipts:
            self.grants.append(item.item)
            self.receipts.add(receipt)
        return True


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.path = Path(self.temp.name) / "ledger.sqlite"
        self.ledger = Ledger(self.path, SESSION)
        self.client = ProtocolClient(self.ledger, "Player", "Test", "client-one")

    def tearDown(self) -> None:
        self.ledger.close()
        self.temp.cleanup()

    def authenticate(self) -> None:
        packets = self.client.handle({"cmd": "RoomInfo", "seed_name": SESSION.seed})
        self.assertEqual(packets[0]["items_handling"], 7)
        self.client.handle({"cmd": "Connected", "team": 0, "slot": 1,
                            "slot_data": {"format_version": 1, "catalog_hash": SESSION.catalog_hash}})

    def test_overlap_and_conflicting_replay_are_atomic(self) -> None:
        self.assertTrue(self.ledger.receive(0, (ITEM,)))
        self.assertTrue(self.ledger.receive(0, (ITEM, ITEM)))
        self.assertEqual(self.ledger.count, 2)
        with self.assertRaises(ValueError):
            self.ledger.receive(1, (ReceivedItem(999, 200, 2, 1), ITEM))
        self.assertEqual(self.ledger.count, 2)
        self.assertFalse(self.ledger.receive(3, (ITEM,)))

    def test_empty_local_table_is_bound_across_restarts(self) -> None:
        self.ledger.bind_local_rewards({})
        self.ledger.close()
        self.ledger = Ledger(self.path, SESSION)
        self.ledger.bind_local_rewards({})
        with self.assertRaises(ValueError):
            self.ledger.bind_local_rewards({200: ReceivedItem(100, 200, 1, 1)})

    def test_full_inventory_retry_restart_and_save_rollback(self) -> None:
        self.ledger.receive(0, (ITEM, ITEM))
        game = FakeGame()
        game.full = True
        self.assertEqual(self.ledger.flush(game), 0)
        game.full = False
        self.assertEqual(self.ledger.flush(game), 2)
        self.ledger.close()
        self.ledger = Ledger(self.path, SESSION)
        self.assertEqual(self.ledger.flush(game), 0)
        game.receipts.remove("ap/1")
        self.assertEqual(self.ledger.flush(game), 1)
        self.assertEqual(game.grants, [100, 100, 100])

    def test_wrong_game_and_ledger_identity(self) -> None:
        game = FakeGame()
        game.session = Session("other", 0, 1, "a" * 64, "save-one")
        with self.assertRaises(ValueError):
            self.ledger.flush(game)
        with self.assertRaises(ValueError):
            Ledger(self.path, game.session)

    def test_local_delivery_offline_and_server_echo_deduplication(self) -> None:
        local = ReceivedItem(101, 201, 1, 1)
        self.ledger.bind_local_rewards({201: local})
        self.ledger.record_check(201)
        game = FakeGame()
        self.assertEqual(self.ledger.flush(game), 1)
        self.ledger.receive(0, (local, ITEM))
        self.assertEqual(self.ledger.flush(game), 1)
        self.assertEqual(game.grants, [101, 100])
        self.assertEqual(self.ledger.flush(game), 0)

    def test_remote_local_table_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.bind_local_rewards({200: ITEM})

    def test_handshake_reconnect_and_victory(self) -> None:
        self.ledger.record_check(200)
        self.ledger.victory()
        self.authenticate()
        self.assertEqual(self.client.reconnect_packets(), [
            {"cmd": "Sync"}, {"cmd": "LocationChecks", "locations": [200]},
            {"cmd": "StatusUpdate", "status": 30}])
        self.assertEqual(self.client.decode(json.dumps([{"cmd": "ReceivedItems", "index": 3, "items": [[100, 200, 2, 1]]}])), [{"cmd": "Sync"}])

    def test_wrong_seed_catalog_and_unauthenticated_items(self) -> None:
        with self.assertRaises(ValueError):
            self.client.handle({"cmd": "RoomInfo", "seed_name": "other"})
        with self.assertRaises(ValueError):
            self.client.handle({"cmd": "ReceivedItems", "index": 0, "items": []})
        self.client.handle({"cmd": "RoomInfo", "seed_name": SESSION.seed})
        with self.assertRaises(ValueError):
            self.client.handle({"cmd": "Connected", "team": 0, "slot": 1,
                                "slot_data": {"format_version": 1, "catalog_hash": "b" * 64}})

    def test_invalid_packet_does_not_mutate_items(self) -> None:
        self.authenticate()
        with self.assertRaises(ValueError):
            self.client.decode(json.dumps([{"cmd": "ReceivedItems", "index": 0, "items": [[100, 200, 2, 1], [True, 200, 2, 1]]}]))
        self.assertEqual(self.ledger.count, 0)

    def test_actual_ap_named_tuple_wire_shape(self) -> None:
        self.authenticate()
        self.client.decode(json.dumps([{"cmd": "ReceivedItems", "index": 0,
            "items": [{"class": "NetworkItem", "item": 100, "location": 200, "player": 2, "flags": 1}]}]))
        self.assertEqual(self.ledger.count, 1)

    def test_network_runner_handshake_and_delivery(self) -> None:
        async def scenario() -> None:
            stop = asyncio.Event()
            messages = [
                [{"cmd": "RoomInfo", "seed_name": SESSION.seed}],
                [{"cmd": "Connected", "team": 0, "slot": 1, "slot_data": {"format_version": 1, "catalog_hash": SESSION.catalog_hash}}],
                [{"cmd": "ReceivedItems", "index": 0, "items": [[100, 200, 2, 1]]}],
            ]
            class FakeSocket:
                closed = False
                sent: list[str] = []
                async def recv(self) -> str:
                    if messages:
                        return json.dumps(messages.pop(0))
                    stop.set()
                    return "[]"
                async def send(self, message: str) -> None:
                    self.sent.append(message)
                async def close(self) -> None:
                    self.closed = True
            socket = FakeSocket()
            async def connect(url: str) -> FakeSocket:
                return socket
            game = FakeGame()
            await run_client(self.client, "ws://localhost:38281", game, stop, connect)
            self.assertEqual(game.grants, [100])
            self.assertTrue(socket.closed)
            self.assertEqual(json.loads(socket.sent[0])[0]["cmd"], "Connect")
        asyncio.run(scenario())
