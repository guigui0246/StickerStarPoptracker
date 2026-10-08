"""Loopback AP-compatible observation server for standalone PopTracker.

Tracker packets cannot collect checks or grant game rewards. Snapshots come
solely from the native game adapter; this endpoint is optional and local.
"""

import asyncio
from dataclasses import dataclass
import hashlib
import importlib
import json
from collections.abc import Callable
from typing import Protocol

from ...data.catalog import Json, array, obj, string
from .runtime import ReceivedItem, Session, integer


class Socket(Protocol):
    async def send(self, data: str) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class TrackingSnapshot:
    checks: tuple[int, ...] = ()
    items: tuple[ReceivedItem, ...] = ()
    won: bool = False


class TrackerServer:
    def __init__(self, session: Session, name: str, game: str, data: Json, snapshot: Callable[[], TrackingSnapshot]) -> None:
        self.session, self.name, self.game, self.snapshot = session, name, game, snapshot
        self.data = obj(data)
        if set(self.data) != {"catalog_hash", "items", "locations", "tracker"} or self.data["catalog_hash"] != session.catalog_hash:
            raise ValueError("Standalone tracker configuration does not match the catalog")
        items, locations = obj(self.data["items"]), obj(self.data["locations"])
        for names in (items, locations):
            ids = [integer(value) for value in names.values()]
            if any(value < 1 for value in ids) or len(set(ids)) != len(ids):
                raise ValueError("Tracker data package requires distinct positive IDs")
        tracker = obj(self.data["tracker"])
        if tracker.get("format_version") != 1 or tracker.get("catalog_hash") != session.catalog_hash:
            raise ValueError("Tracker mapping requires the bound catalog identity")
        if set(obj(tracker.get("items"))) != {str(value) for value in items.values()} or set(obj(tracker.get("locations"))) != {str(value) for value in locations.values()}:
            raise ValueError("Tracker mappings and AP data package disagree")
        package: dict[str, Json] = {"item_name_groups": {}, "item_name_to_id": items, "location_name_groups": {}, "location_name_to_id": locations}
        package["checksum"] = hashlib.sha1(json.dumps(package, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        self.package = package
        self.location_ids = frozenset(integer(value) for value in locations.values())
        self.item_ids = frozenset(integer(value) for value in items.values())

    @staticmethod
    async def send(socket: Socket, packets: list[dict[str, Json]]) -> None:
        await socket.send(json.dumps(packets, separators=(",", ":")))

    def current(self) -> TrackingSnapshot:
        value = self.snapshot()
        if set(value.checks) - self.location_ids or any(item.item not in self.item_ids or item.location not in self.location_ids or item.player != self.session.slot for item in value.items):
            raise ValueError("Native snapshot contains unknown tracker IDs")
        return value

    def connected(self, state: TrackingSnapshot) -> dict[str, Json]:
        player: dict[str, Json] = {"class": "NetworkPlayer", "team": self.session.team, "slot": self.session.slot, "alias": self.name, "name": self.name}
        slot: dict[str, Json] = {"class": "NetworkSlot", "name": self.name, "game": self.game, "type": 1, "group_members": []}
        return {"cmd": "Connected", "team": self.session.team, "slot": self.session.slot, "players": [player],
                "missing_locations": [location for location in sorted(self.location_ids - set(state.checks))], "checked_locations": list(state.checks),
                "slot_data": {"format_version": 1, "catalog_hash": self.session.catalog_hash, "tracker": self.data["tracker"]},
                "slot_info": {str(self.session.slot): slot}, "hint_points": 0}

    @staticmethod
    def received(state: TrackingSnapshot, index: int = 0) -> dict[str, Json]:
        return {"cmd": "ReceivedItems", "index": index,
                "items": [{"class": "NetworkItem", "item": item.item, "location": item.location, "player": item.player, "flags": item.flags} for item in state.items[index:]]}

    async def handle(self, socket: Socket) -> None:
        await self.send(socket, [{"cmd": "RoomInfo", "seed_name": self.session.seed, "password": False, "games": [self.game],
                                 "version": {"class": "Version", "major": 0, "minor": 6, "build": 8},
                                 "tags": ["AP", "Tracker"], "permissions": {"release": 0, "collect": 0, "remaining": 0},
                                 "hint_cost": 0, "location_check_points": 0, "datapackage_checksums": {self.game: self.package["checksum"]}, "players": []}])
        authenticated = False
        previous = TrackingSnapshot()
        receive = asyncio.create_task(socket.recv())
        try:
            while True:
                done, _ = await asyncio.wait((receive,), timeout=0.25)
                if done:
                    packets: Json = json.loads(receive.result())
                    for raw in array(packets):
                        packet = obj(raw)
                        command = string(packet.get("cmd"))
                        if command == "GetDataPackage":
                            await self.send(socket, [{"cmd": "DataPackage", "data": {"games": {self.game: self.package}}}])
                        elif command == "Connect":
                            if packet.get("name") != self.name or packet.get("game") not in (None, "", self.game):
                                await self.send(socket, [{"cmd": "ConnectionRefused", "errors": ["InvalidSlot"]}])
                                continue
                            previous = self.current()
                            await self.send(socket, [self.connected(previous), self.received(previous)])
                            authenticated = True
                        elif command == "Sync" and authenticated:
                            previous = self.current()
                            await self.send(socket, [self.received(previous)])
                        # LocationChecks, StatusUpdate, scouts and chat never
                        # change native snapshots, inventories or save flags.
                    receive = asyncio.create_task(socket.recv())
                if authenticated:
                    current = self.current()
                    if current.items[:len(previous.items)] != previous.items or not set(previous.checks) <= set(current.checks) or (previous.won and not current.won):
                        # A rollback requires a clear/replay. Disconnecting lets
                        # the standard AP client perform its normal reconnect.
                        await socket.close()
                        return
                    updates: list[dict[str, Json]] = []
                    if current.items != previous.items:
                        updates.append(self.received(current, len(previous.items)))
                    if current.checks != previous.checks or current.won != previous.won:
                        updates.append({"cmd": "RoomUpdate", "checked_locations": list(current.checks), "hint_points": 0})
                    if updates:
                        await self.send(socket, updates)
                    previous = current
        finally:
            receive.cancel()
            await asyncio.gather(receive, return_exceptions=True)

    async def run(self, port: int, stop: asyncio.Event) -> None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid standalone tracker port")
        try:
            server = importlib.import_module("websockets.asyncio.server")
            errors = importlib.import_module("websockets.exceptions")
        except ImportError as error:
            raise RuntimeError("Install websockets>=13 for the optional standalone tracker") from error
        async def handler(socket: Socket) -> None:
            try:
                await self.handle(socket)
            except errors.ConnectionClosed:
                pass
        async with server.serve(handler, "127.0.0.1", port, max_size=4 * 1024 * 1024):
            await stop.wait()
