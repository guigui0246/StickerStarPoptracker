"""Typed client for Citra's bundled UDP memory RPC protocol.

Protocol version 1 matches scripting/citra.py in the user's 608383e build.
Reads are chunked at 32 bytes, writes at 24. Every reply is validated.
"""

from enum import IntEnum
import secrets
import socket
import struct
import time
from types import TracebackType
from typing import Self


class RequestType(IntEnum):
    READ = 1
    WRITE = 2


class CitraProtocolError(RuntimeError):
    pass


class CitraMemory:
    def __init__(
        self, host: str = "127.0.0.1", port: int = 45987, timeout: float = 2.0
    ) -> None:
        if timeout <= 0 or not 1 <= port <= 65535:
            raise ValueError("Invalid RPC endpoint or timeout")
        self.endpoint = (socket.gethostbyname(host), port)
        self.timeout = timeout
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.socket.close()

    @staticmethod
    def validate_range(address: int, size: int) -> None:
        if (
            type(address) is not int
            or type(size) is not int
            or address < 0
            or size < 0
            or address + size > 0x100000000
        ):
            raise ValueError("Memory range must fit within the 32-bit address space")

    def request(self, kind: RequestType, payload: bytes, expected_size: int) -> bytes:
        identifier = secrets.randbits(32)
        self.socket.sendto(
            struct.pack("<4I", 1, identifier, int(kind), len(payload)) + payload,
            self.endpoint,
        )
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Citra memory RPC did not answer the request")
            self.socket.settimeout(remaining)
            packet, sender = self.socket.recvfrom(49)
            if sender != self.endpoint or len(packet) < 16:
                continue
            version, reply_id, reply_kind, length = struct.unpack_from("<4I", packet)
            if reply_id != identifier:
                continue
            if (
                version != 1
                or reply_kind != kind
                or length != len(packet) - 16
                or length != expected_size
            ):
                raise CitraProtocolError("Invalid Citra RPC response")
            return packet[16:]

    def read(self, address: int, size: int) -> bytes:
        self.validate_range(address, size)
        result = bytearray()
        while len(result) < size:
            length = min(32, size - len(result))
            result.extend(
                self.request(
                    RequestType.READ,
                    struct.pack("<2I", address + len(result), length),
                    length,
                )
            )
        return bytes(result)

    def write(self, address: int, data: bytes) -> None:
        self.validate_range(address, len(data))
        for offset in range(0, len(data), 24):
            chunk = data[offset : offset + 24]
            self.request(
                RequestType.WRITE,
                struct.pack("<2I", address + offset, len(chunk)) + chunk,
                0,
            )

    def read_u32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little")
