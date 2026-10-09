"""Durable AP protocol state, independent of network and emulator libraries.

Game adapters must acknowledge deliveries atomically in the game's save. The
ledger deliberately does not treat a successful memory write as a receipt.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Protocol

from ...data.catalog import Json, array, obj, string


def integer(value: Json) -> int:
    if type(value) is not int:
        raise ValueError("Expected an integer")
    return value


@dataclass(frozen=True)
class Session:
    seed: str
    team: int
    slot: int
    catalog_hash: str
    save_id: str

    def __post_init__(self) -> None:
        if not self.seed or not self.save_id or self.team < 0 or self.slot < 1:
            raise ValueError("Invalid session identity")
        if len(self.catalog_hash) != 64 or any(c not in "0123456789abcdef" for c in self.catalog_hash):
            raise ValueError("Expected a SHA-256 catalog identity")


@dataclass(frozen=True)
class ReceivedItem:
    item: int
    location: int
    player: int
    flags: int

    @classmethod
    def parse(cls, raw: Json) -> "ReceivedItem":
        if isinstance(raw, dict):
            if set(raw) != {"item", "location", "player", "flags", "class"} or raw["class"] != "NetworkItem":
                raise ValueError("Expected an AP NetworkItem object")
            values = [raw[key] for key in ("item", "location", "player", "flags")]
        else:
            values = array(raw)
        if len(values) != 4:
            raise ValueError("Expected an AP NetworkItem")
        result = cls(*(integer(value) for value in values))
        if result.player < 0 or result.flags < 0:
            raise ValueError("Invalid AP item metadata")
        return result


class GameDelivery(Protocol):
    def identity(self) -> Session: ...
    def received(self, receipt: str) -> bool: ...

    def deliver(self, receipt: str, item: ReceivedItem) -> bool:
        """Atomically grant and persist receipt, or return False to retry."""
        ...


class Ledger:
    def __init__(self, path: Path, session: Session) -> None:
        self.session = session
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS identity (value TEXT NOT NULL)")
        expected = json.dumps([session.seed, session.team, session.slot, session.catalog_hash, session.save_id])
        stored = self.db.execute("SELECT value FROM identity").fetchall()
        if stored and stored != [(expected,)]:
            self.db.close()
            raise ValueError("Ledger belongs to a different seed, player, catalog or save")
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS items (idx INTEGER PRIMARY KEY, item I"
                "NTEGER, location INTEGER, player INTEGER, flags INTEGER)"
            )
            self.db.execute("CREATE TABLE IF NOT EXISTS checks (location INTEGER PRIMARY KEY)")
            self.db.execute("CREATE TABLE IF NOT EXISTS status (won INTEGER NOT NULL)")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS local_rewards (location INTEGER PRIMARY KEY, item INTEGER, flags INTEGER)"
            )
            self.db.execute("CREATE TABLE IF NOT EXISTS local_binding (value TEXT NOT NULL)")
            if not stored:
                self.db.execute("INSERT INTO identity VALUES (?)", (expected,))
                self.db.execute("INSERT INTO status VALUES (0)")

    def close(self) -> None:
        self.db.close()

    @property
    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM items").fetchone()[0])

    def receive(self, index: int, items: tuple[ReceivedItem, ...]) -> bool:
        if index < 0:
            raise ValueError("Negative received-item index")
        if index > self.count:
            return False
        # Validate the entire overlap before committing any appended item.
        with self.db:
            for offset, item in enumerate(items, index):
                values = (item.item, item.location, item.player, item.flags)
                previous = self.db.execute("SELECT item,location,player,flags FROM items WHERE idx=?", (offset,)).fetchone()
                if previous is not None and previous != values:
                    raise ValueError("Server changed an already received item")
                if previous is None:
                    self.db.execute("INSERT INTO items VALUES (?,?,?,?,?)", (offset, *values))
        return True

    def record_check(self, location: int) -> None:
        if type(location) is not int:
            raise ValueError("Invalid location ID")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO checks VALUES (?)", (location,))

    def bind_local_rewards(self, rewards: dict[int, ReceivedItem]) -> None:
        """Install only rewards belonging to this player; remote checks are reports."""
        for location, item in rewards.items():
            if item.player != self.session.slot or item.location != location:
                raise ValueError("Local reward table contains a remote or mismatched reward")
        with self.db:
            existing = {
                int(row[0]): (int(row[1]), int(row[2]))
                for row in self.db.execute("SELECT location,item,flags FROM local_rewards")
            }
            expected = {location: (item.item, item.flags) for location, item in rewards.items()}
            binding = json.dumps(sorted((location, *values) for location, values in expected.items()))
            stored = self.db.execute("SELECT value FROM local_binding").fetchall()
            if (stored and stored != [(binding,)]) or (existing and existing != expected):
                raise ValueError("Local placement table changed for this seed")
            if not stored:
                self.db.execute("INSERT INTO local_binding VALUES (?)", (binding,))
            self.db.executemany(
                "INSERT OR IGNORE INTO local_rewards VALUES (?,?,?)",
                [(location, *values) for location, values in expected.items()],
            )

    @property
    def checks(self) -> list[int]:
        return [int(row[0]) for row in self.db.execute("SELECT location FROM checks ORDER BY location")]

    def victory(self) -> None:
        with self.db:
            self.db.execute("UPDATE status SET won=1")

    @property
    def won(self) -> bool:
        return bool(self.db.execute("SELECT won FROM status").fetchone()[0])

    def flush(self, game: GameDelivery) -> int:
        if game.identity() != self.session:
            raise ValueError("Connected game has the wrong save or seed")
        delivered = 0
        local = {
            int(row[0]): (int(row[1]), int(row[2])) for row in self.db.execute("SELECT location,item,flags FROM local_rewards")
        }
        rows = [
            (int(row[0]), ReceivedItem(*(int(value) for value in row[1:])))
            for row in self.db.execute("SELECT idx,item,location,player,flags FROM items ORDER BY idx")
        ]
        incoming = [(index, item) for index, item in rows if not (item.player == self.session.slot and item.location in local)]
        prepare_pages = getattr(game, "prepare_pages", None)
        if prepare_pages is not None:
            prepare_pages(incoming)
        # Direct local delivery runs even when the server has never connected.
        for location in self.checks:
            if location not in local:
                continue
            item, flags = local[location]
            receipt = f"local/{location}"
            if game.received(receipt):
                continue
            if not game.deliver(receipt, ReceivedItem(item, location, self.session.slot, flags)):
                # Local rewards have independent native receipts. A full album
                # must not block a remote page upgrade that can free capacity.
                continue
            if not game.received(receipt):
                raise RuntimeError("Game adapter did not persist its delivery receipt")
            delivered += 1
        for index, received_item in rows:
            item, location, player, flags = (
                received_item.item,
                received_item.location,
                received_item.player,
                received_item.flags,
            )
            receipt = f"ap/{index}"
            local_echo = False
            if player == self.session.slot and location in local:
                if local[location] != (item, flags):
                    raise ValueError("Server reward conflicts with the installed local placement")
                receipt = f"local/{location}"
                local_echo = True
            # Re-read native receipts on every pass, including after save rollback.
            if game.received(receipt):
                continue
            if not game.deliver(receipt, ReceivedItem(item, location, player, flags)):
                if local_echo:
                    continue
                priority = getattr(game, "deliver_priority", None)
                if priority is not None:
                    eligible = getattr(game, "is_priority_item", None)
                    for later_index, later_item in incoming:
                        if eligible is not None and not eligible(later_item):
                            continue
                        if later_index <= index or game.received(f"ap/{later_index}"):
                            continue
                        # Only the adapter can identify safe, independently saved
                        # page receipts. Ordinary rewards retain prefix ordering.
                        if priority(f"ap/{later_index}", later_item):
                            if not game.received(f"ap/{later_index}"):
                                raise RuntimeError("Priority grant lacks its native receipt")
                            delivered += 1
                break
            if not game.received(receipt):
                raise RuntimeError("Game adapter did not persist its delivery receipt")
            delivered += 1
        return delivered


class ProtocolClient:
    def __init__(self, ledger: Ledger, name: str, game: str, uuid: str, password: str | None = None) -> None:
        if not name or not game or not uuid:
            raise ValueError("Slot, game and client identity are required")
        self.ledger, self.name, self.game, self.uuid, self.password = ledger, name, game, uuid, password
        self.connected = False
        self.room_validated = False

    def reconnect_packets(self) -> list[dict[str, Json]]:
        packets: list[dict[str, Json]] = [{"cmd": "Sync"}]
        if self.ledger.checks:
            packets.append({"cmd": "LocationChecks", "locations": list(self.ledger.checks)})
        if self.ledger.won:
            packets.append({"cmd": "StatusUpdate", "status": 30})
        return packets

    def handle(self, packet: dict[str, Json]) -> list[dict[str, Json]]:
        command = string(packet.get("cmd"))
        if command == "RoomInfo":
            self.connected = False
            self.room_validated = False
            if string(packet.get("seed_name")) != self.ledger.session.seed:
                raise ValueError("Server seed does not match the installed patch")
            self.room_validated = True
            return [
                {
                    "cmd": "Connect",
                    "password": self.password,
                    "name": self.name,
                    "game": self.game,
                    "uuid": self.uuid,
                    "tags": ["AP"],
                    "version": {"major": 0, "minor": 6, "build": 8, "class": "Version"},
                    "items_handling": 7,
                    "slot_data": True,
                }
            ]
        if command == "ConnectionRefused":
            self.connected = False
            raise ValueError(f"Archipelago refused connection: {packet.get('errors')}")
        if command == "Connected":
            session = self.ledger.session
            if not self.room_validated or (integer(packet.get("team")), integer(packet.get("slot"))) != (
                session.team,
                session.slot,
            ):
                raise ValueError("Server assigned a different team or slot")
            slot_data = obj(packet.get("slot_data"))
            if slot_data.get("catalog_hash") != session.catalog_hash or slot_data.get("format_version") != 1:
                raise ValueError("Unsupported slot data or different catalog")
            self.connected = True
            return self.reconnect_packets()
        if command == "ReceivedItems":
            if not self.connected:
                raise ValueError("Items arrived before authenticated slot validation")
            items = tuple(ReceivedItem.parse(raw) for raw in array(packet.get("items")))
            if not self.ledger.receive(integer(packet.get("index")), items):
                return [{"cmd": "Sync"}]
        return []

    def decode(self, message: str) -> list[dict[str, Json]]:
        packets = array(json.loads(message))
        replies: list[dict[str, Json]] = []
        for packet in packets:
            replies.extend(self.handle(obj(packet)))
        return replies
