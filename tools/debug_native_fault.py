"""Capture a null-object native call through the isolated emulator's GDB stub.

Uses the standard GDB remote protocol. It reads registers and stack bytes and
temporarily installs a debugger breakpoint; it never edits game inventory.
Enable the stub only in a disposable test profile before launching the game.
"""

import argparse
import json
from pathlib import Path
import socket
import struct
import time


class RemoteDebugger:
    def __init__(self, connection: socket.socket):
        self.connection = connection

    def send(self, command: str) -> None:
        payload = command.encode("ascii")
        self.connection.sendall(b"$" + payload + b"#" + f"{sum(payload) & 255:02x}".encode("ascii"))

    def receive(self) -> str:
        while (value := self.connection.recv(1)) != b"$":
            if not value:
                raise ConnectionError("Debugger disconnected")
        payload = bytearray()
        while (value := self.connection.recv(1)) != b"#":
            if not value:
                raise ConnectionError("Debugger disconnected")
            payload.extend(value)
        checksum = bytearray()
        while len(checksum) < 2:
            value = self.connection.recv(2 - len(checksum))
            if not value:
                raise ConnectionError("Debugger disconnected")
            checksum.extend(value)
        if int(checksum, 16) != sum(payload) & 255:
            self.connection.sendall(b"-")
            raise ValueError("Invalid debugger packet checksum")
        self.connection.sendall(b"+")
        return payload.decode("ascii")

    def command(self, command: str) -> str:
        self.send(command)
        return self.receive()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=24689)
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x24FD30)
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.wait_seconds <= 600:
        parser.error("Use a new output file and a wait between 1 and 600 seconds")
    deadline = time.monotonic() + args.wait_seconds
    with socket.create_connection(("127.0.0.1", args.port), timeout=10) as connection:
        debugger = RemoteDebugger(connection)
        debugger.command("?")
        breakpoint = f"1,{args.address:x},4"
        if debugger.command("Z" + breakpoint) != "OK":
            raise RuntimeError("Emulator did not accept the instruction breakpoint")
        calls = []
        try:
            while time.monotonic() < deadline:
                debugger.send("c")
                connection.settimeout(max(1, deadline - time.monotonic()))
                stop = debugger.receive()
                packet = debugger.command("g")
                registers = struct.unpack("<16I", bytes.fromhex(packet[:128]))
                state = {f"r{index}": f"0x{value:08x}" for index, value in enumerate(registers)}
                state.update({"stop": stop, "sp": state["r13"], "lr": state["r14"], "pc": state["r15"]})
                calls.append(state)
                if registers[0] == 0:
                    state["stack"] = debugger.command(f"m{registers[13]:x},100")
                    args.output.write_text(json.dumps({"address": args.address, "calls": calls}, indent=2) + "\n")
                    print(json.dumps(state))
                    return
                if debugger.command("z" + breakpoint) != "OK":
                    raise RuntimeError("Emulator did not remove the instruction breakpoint")
                debugger.send("s")
                debugger.receive()
                if debugger.command("Z" + breakpoint) != "OK":
                    raise RuntimeError("Emulator did not restore the instruction breakpoint")
            raise TimeoutError("No null-object call reached the selected native instruction")
        finally:
            connection.settimeout(5)
            try:
                debugger.command("z" + breakpoint)
                debugger.command("D")
            except (OSError, ValueError, ConnectionError):
                pass


if __name__ == "__main__":
    main()
