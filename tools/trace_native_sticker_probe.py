"""Trace native grant calls through an isolated Citra GDB stub.

Only debugger breakpoints, register/memory reads and resume commands are used.
Never writes game inventory or save flags. Not a gameplay client.
"""

import argparse
import json
import socket
import struct
import time


class Debugger:
    def __init__(self, port: int) -> None:
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=2)
        self.socket.settimeout(180)

    def send(self, command: str) -> None:
        payload = command.encode("ascii")
        self.socket.sendall(b"$" + payload + b"#" + f"{sum(payload) & 255:02x}".encode())

    def receive(self) -> str:
        while self.socket.recv(1) != b"$":
            pass
        payload = bytearray()
        while (byte := self.socket.recv(1)) != b"#":
            if not byte:
                raise EOFError("Debugger disconnected")
            payload.extend(byte)
        checksum = self.socket.recv(2)
        if checksum != f"{sum(payload) & 255:02x}".encode():
            raise ValueError("Invalid debugger packet checksum")
        self.socket.sendall(b"+")
        return payload.decode("ascii")

    def request(self, command: str) -> str:
        self.send(command)
        return self.receive()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=24689)
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    debugger = Debugger(args.port)
    points = (0x356320, 0x3514CC, 0x278E90, 0x279064, 0x2790A0)
    try:
        print(debugger.request("?"), flush=True)
        for address in points:
            response = debugger.request(f"Z0,{address:x},4")
            if response != "OK":
                raise RuntimeError(f"Breakpoint rejected: {response}")
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            stop = debugger.request("c")
            if not stop.startswith(("T", "S")):
                raise RuntimeError(stop)
            raw = bytes.fromhex(debugger.request("g"))
            registers = struct.unpack_from("<16I", raw)
            pc = registers[15]
            print(json.dumps({"pc": hex(pc), "r0_r3": [hex(v) for v in registers[:4]], "lr": hex(registers[14])}), flush=True)
            if pc not in points:
                break
            debugger.request(f"z0,{pc:x},4")
            debugger.request("s")
            debugger.request(f"Z0,{pc:x},4")
    finally:
        for address in points:
            debugger.request(f"z0,{address:x},4")
        debugger.send("D")
        debugger.socket.close()


if __name__ == "__main__":
    main()
