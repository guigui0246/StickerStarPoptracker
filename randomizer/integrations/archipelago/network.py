"""Reconnecting WebSocket runner for the durable AP protocol engine.

The websocket dependency is loaded only when a network connection is requested.
Standalone reward delivery does not import or start this runner.
"""

import asyncio
from collections.abc import Awaitable, Callable
import json
import importlib
import logging
from typing import Protocol, cast
from urllib.parse import urlparse

from .runtime import GameDelivery, ProtocolClient
from ...data.catalog import Json

LOG = logging.getLogger(__name__)


class Socket(Protocol):
    async def recv(self) -> str | bytes: ...
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...


Connector = Callable[[str], Awaitable[Socket]]


async def connect_websocket(url: str) -> Socket:
    try:
        module = importlib.import_module("websockets.asyncio.client")
        exceptions = importlib.import_module("websockets.exceptions")
    except ImportError as error:
        raise RuntimeError("Install websockets>=13 to use the Archipelago connection") from error
    connection = await module.connect(url, max_size=4 * 1024 * 1024, open_timeout=15, ping_interval=20, ping_timeout=20)
    class WebSocket:
        async def recv(self) -> str | bytes:
            try:
                return cast(str | bytes, await connection.recv())
            except exceptions.ConnectionClosed as error:
                raise ConnectionError(str(error)) from error
        async def send(self, message: str) -> None:
            try:
                await connection.send(message)
            except exceptions.ConnectionClosed as error:
                raise ConnectionError(str(error)) from error
        async def close(self) -> None:
            await connection.close()
    return WebSocket()


async def run_client(client: ProtocolClient, url: str, game: GameDelivery,
                     stop: asyncio.Event, connector: Connector = connect_websocket) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a ws:// or wss:// server URL without embedded credentials")
    delay = 1.0
    while not stop.is_set():
        socket: Socket | None = None
        client.connected = False
        client.room_validated = False
        try:
            client.ledger.flush(game)
            socket = await connector(url)
            last_checks: tuple[int, ...] = ()
            last_won = False
            while not stop.is_set():
                try:
                    message = await asyncio.wait_for(socket.recv(), timeout=0.25)
                except TimeoutError:
                    message = None
                if message is not None:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8")
                    replies = client.decode(message)
                    if replies:
                        await socket.send(json.dumps(replies))
                    if client.connected:
                        delay = 1.0
                client.ledger.flush(game)
                if client.connected:
                    checks = tuple(client.ledger.checks)
                    won = client.ledger.won
                    updates: list[dict[str, Json]] = []
                    if checks != last_checks:
                        updates.append({"cmd": "LocationChecks", "locations": list(checks)})
                    if won and not last_won:
                        updates.append({"cmd": "StatusUpdate", "status": 30})
                    if updates:
                        await socket.send(json.dumps(updates))
                    last_checks, last_won = checks, won
        except (OSError, ConnectionError, TimeoutError) as error:
            LOG.warning("Archipelago disconnected: %s", error)
        finally:
            client.connected = False
            if socket is not None:
                await socket.close()
        # Identity/protocol failures propagate; never reconnect to a wrong seed.
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            delay = min(delay * 2, 30.0)
