"""Game-owned receipts and checks bridged through an isolated native mailbox.

All rewards are granted by KSM code. The host writes only dedicated mailbox
words and a persistent save nonce, never inventory or native receipt flags.
"""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import json
import secrets
from typing import Protocol

from ...data.catalog import array, obj, string
from ..archipelago.runtime import ReceivedItem, Session, integer
from ..rom.mailbox import RemoteSession
from ..rom.native_delivery import NativeReward, NativeRewardKind


class Memory(Protocol):
    def read(self, address: int, size: int) -> bytes: ...
    def write(self, address: int, data: bytes) -> None: ...


@dataclass(frozen=True)
class CheckFlags:
    collected: int
    delivered: int


@dataclass(frozen=True)
class CodeSignature:
    address: int
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not 0x100000 <= self.address < self.address + self.size <= 0x3D7000 or self.size > 4096:
            raise ValueError("Invalid executable patch signature range")
        if len(self.sha256) != 64 or any(character not in "0123456789abcdef" for character in self.sha256):
            raise ValueError("Invalid executable patch signature hash")


@dataclass(frozen=True)
class NativeProfile:
    pointer_address: int
    flags_offset: int
    flag_count: int
    signature_address: int
    signature_size: int
    signature_sha256: str
    fingerprint: bytes
    flags: dict[str, int]
    checks: dict[str, CheckFlags]
    selectors: dict[int, int]
    session: RemoteSession
    check_rewards: dict[str, NativeReward] = field(default_factory=dict)
    selector_rewards: dict[int, NativeReward] = field(default_factory=dict)
    code_signatures: tuple[CodeSignature, ...] = ()

    @classmethod
    def load(cls, path: Path) -> "NativeProfile":
        data = obj(json.loads(path.read_text(encoding="utf-8")))
        if data.get("format_version") != 1 or data.get("title_id") != "00040000000A5F00":
            raise ValueError("Unsupported native patch report")
        profile = obj(data.get("rpc_memory_profile"))
        remote_session = obj(data.get("remote_session"))
        session = RemoteSession(string(remote_session.get("seed")), integer(remote_session.get("team")),
                                integer(remote_session.get("slot")), string(remote_session.get("catalog_hash")))
        flags: dict[str, int] = {}
        for raw in array(data.get("allocated_flags")):
            flag = obj(raw)
            name, index = string(flag.get("name")), integer(flag.get("index"))
            if name in flags or index in flags.values() or not name.startswith("gf_rando_") or not 1446 <= index < 2560:
                raise ValueError("Duplicate or invalid native flag")
            flags[name] = index
        checks = {}
        for raw in array(data.get("check_flags")):
            row = obj(raw)
            identifier = string(row.get("id"))
            checked, delivered = integer(row.get("checked")), integer(row.get("delivered"))
            if identifier in checks or not 0 <= checked < 3072 or not 0 <= delivered < 3072:
                raise ValueError("Invalid native check mapping")
            checks[identifier] = CheckFlags(checked, delivered)
        selectors = {}
        selector_rewards = {}
        for index, raw in enumerate(array(data.get("remote_rewards")), 1):
            item = integer(obj(raw).get("item_id"))
            if item in selectors or item < 1:
                raise ValueError("Invalid remote selector registry")
            selectors[item] = index
            reward = obj(obj(raw).get("reward"))
            value = reward.get("value")
            selector_rewards[item] = NativeReward(NativeRewardKind(string(reward.get("kind"))), integer(value) if type(value) is int else string(value))
        raw_checks = array(data.get("checks"))
        if len(raw_checks) != len(checks):
            raise ValueError("Native check reward table does not match the flag mapping")
        check_rewards = {}
        for identifier, raw in zip(checks, raw_checks, strict=True):
            reward = obj(obj(raw).get("reward"))
            value = reward.get("value")
            check_rewards[identifier] = NativeReward(NativeRewardKind(string(reward.get("kind"))), integer(value) if type(value) is int else string(value))
        fingerprint = bytes.fromhex(string(data.get("save_seed_fingerprint")))
        if len(fingerprint) != 16 or not selectors:
            raise ValueError("Patch does not contain a remote-delivery mailbox")
        patch = data.get("code_patch")
        signatures = tuple(CodeSignature(integer(obj(raw).get("address")), integer(obj(raw).get("size")), string(obj(raw).get("sha256")))
                           for raw in array(obj(patch).get("signatures"))) if patch is not None else ()
        if any(reward.kind == NativeRewardKind.ABILITY for reward in (*check_rewards.values(), *selector_rewards.values())) and not signatures:
            raise ValueError("Ability rewards require executable guard signatures")
        result = cls(integer(profile.get("pointer_address")), integer(profile.get("global_flags_offset")),
                     integer(profile.get("flag_count")), integer(profile.get("signature_address")),
                     integer(profile.get("signature_size")), string(profile.get("signature_sha256")),
                     fingerprint, flags, checks, selectors, session, check_rewards, selector_rewards, signatures)
        if (result.pointer_address, result.flags_offset, result.flag_count, result.signature_address, result.signature_size) != (0x43C190, 0x144, 3072, 0x282C98, 0x160):
            raise ValueError("Unsupported game memory revision")
        if len(result.signature_sha256) != 64:
            raise ValueError("Invalid executable signature hash")
        for name in ("item", "sequence", "ready", "ack", "ack_ready", "save_a", "save_b", "save_c", "save_d"):
            result.word_index(name)
        return result

    def word_index(self, name: str) -> int:
        positions = [self.flags[f"gf_rando_rpc_{name}_{bit:02d}"] for bit in range(32)]
        if positions[0] % 32 or positions != list(range(positions[0], positions[0] + 32)):
            raise ValueError("Mailbox word is not aligned or has shared ownership")
        return positions[0]


class NativeGame:
    def __init__(self, memory: Memory, profile: NativeProfile, seed: str, team: int, slot: int,
                 catalog_hash: str, location_ids: dict[str, int]) -> None:
        if set(location_ids) - profile.checks.keys() or len(set(location_ids.values())) != len(location_ids):
            raise ValueError("Location mapping is unknown or ambiguous")
        if (seed, team, slot, catalog_hash) != (profile.session.seed, profile.session.team, profile.session.slot, profile.session.catalog_hash):
            raise ValueError("Client identity does not match the installed native patch")
        self.memory, self.profile = memory, profile
        self.seed, self.team, self.slot, self.catalog_hash = seed, team, slot, catalog_hash
        self.locations = {location: profile.checks[key] for key, location in location_ids.items()}
        self.signature_verified = False

    @staticmethod
    def bit(data: bytes, index: int) -> bool:
        return bool(data[index // 8] & (1 << (index % 8)))

    def verify_executable(self) -> None:
        actual = self.memory.read(self.profile.signature_address, self.profile.signature_size)
        if hashlib.sha256(actual).hexdigest() != self.profile.signature_sha256:
            raise ValueError("Emulator is running a different executable revision")
        for signature in self.profile.code_signatures:
            actual = self.memory.read(signature.address, signature.size)
            if hashlib.sha256(actual).hexdigest() != signature.sha256:
                raise ValueError("Installed native executable guard is missing or belongs to another seed")
        self.signature_verified = True

    def snapshot(self) -> tuple[int, bytes]:
        if not self.signature_verified:
            self.verify_executable()
        pointer = int.from_bytes(self.memory.read(self.profile.pointer_address, 4), "little")
        if not 0x08000000 <= pointer <= 0x40000000 - self.profile.flags_offset - self.profile.flag_count // 8 or pointer % 4:
            raise RuntimeError("Game save state is not currently loaded")
        base = pointer + self.profile.flags_offset
        data = self.memory.read(base, self.profile.flag_count // 8)
        if not self.bit(data, self.profile.flags["gf_rando_seed_initialized"]):
            raise RuntimeError("Native randomizer has not initialized this save")
        fingerprint = bytearray(16)
        for bit in range(128):
            if self.bit(data, self.profile.flags[f"gf_rando_seed_{bit:02d}"]):
                fingerprint[bit // 8] |= 1 << (bit % 8)
        if bytes(fingerprint) != self.profile.fingerprint:
            raise ValueError("Loaded save belongs to a different native seed")
        return base, data

    def word(self, data: bytes, name: str) -> int:
        index = self.profile.word_index(name)
        return int.from_bytes(data[index // 8:index // 8 + 4], "little")

    def write_host_word(self, base: int, name: str, value: int) -> None:
        if name not in {"item", "sequence", "ready", "save_a", "save_b", "save_c", "save_d"}:
            raise ValueError("Host may not modify native acknowledgement or inventory")
        # ROM reloads can replace executable guards while retaining this save's
        # fingerprint. Recheck installed code before each host-owned write.
        self.verify_executable()
        self.memory.write(base + self.profile.word_index(name) // 8, value.to_bytes(4, "little"))

    def identity(self) -> Session:
        base, data = self.snapshot()
        names = ("save_a", "save_b", "save_c", "save_d")
        nonce = b"".join(self.word(data, name).to_bytes(4, "little") for name in names)
        if nonce == bytes(16):
            nonce = secrets.token_bytes(16)
            for index, name in enumerate(names):
                self.write_host_word(base, name, int.from_bytes(nonce[index * 4:index * 4 + 4], "little"))
            _, verified = self.snapshot()
            if b"".join(self.word(verified, name).to_bytes(4, "little") for name in names) != nonce:
                raise RuntimeError("Save identity was not accepted by the native mailbox")
        return Session(self.seed, self.team, self.slot, self.catalog_hash, nonce.hex())

    def received(self, receipt: str) -> bool:
        base, data = self.snapshot()
        kind, separator, value = receipt.partition("/")
        if not separator or not value.isdecimal():
            raise ValueError("Unsupported receipt identifier")
        index = int(value)
        if kind == "local":
            if index not in self.locations:
                raise ValueError("Local receipt refers to an unknown location")
            return self.bit(data, self.locations[index].delivered)
        if kind != "ap" or not 0 <= index < 0x7FFFFFFE:
            raise ValueError("Unsupported AP receipt index")
        # Read the commit guard around the acknowledgement and confirm its
        # value again. A chunked flag snapshot alone can see a torn VM update.
        ready_address = base + self.profile.word_index("ack_ready") // 8
        ack_address = base + self.profile.word_index("ack") // 8
        before = int.from_bytes(self.memory.read(ready_address, 4), "little")
        acknowledged = int.from_bytes(self.memory.read(ack_address, 4), "little")
        after = int.from_bytes(self.memory.read(ready_address, 4), "little")
        confirmed = int.from_bytes(self.memory.read(ack_address, 4), "little")
        return bool(before & after & 1) and acknowledged == confirmed and acknowledged > index

    def deliver(self, receipt: str, item: ReceivedItem) -> bool:
        if self.received(receipt):
            return True
        if receipt.startswith("local/"):
            return False  # the native collector delivers local rewards itself
        if item.item not in self.profile.selectors:
            raise ValueError("Server item has no installed native reward selector")
        index = int(receipt.split("/", 1)[1]) + 1
        base, data = self.snapshot()
        selector = self.profile.selectors[item.item]
        if self.word(data, "ready") & 1 and self.word(data, "sequence") == index and self.word(data, "item") == selector:
            return False  # wait for game-owned acknowledgement; do not republish
        self.write_host_word(base, "ready", 0)
        self.write_host_word(base, "item", selector)
        self.write_host_word(base, "sequence", index)
        self.write_host_word(base, "ready", 1)
        return False

    def collected(self) -> set[int]:
        _, data = self.snapshot()
        return {location for location, flags in self.locations.items() if self.bit(data, flags.collected)}

    def observe(self) -> tuple[set[int], set[int], bool]:
        """Read tracker checks and native receipts together without per-item RPC."""
        _, data = self.snapshot()
        collected = {location for location, flags in self.locations.items() if self.bit(data, flags.collected)}
        delivered = {location for location, flags in self.locations.items() if self.bit(data, flags.delivered)}
        victory = self.profile.flags.get("gf_rando_victory")
        return collected, delivered, victory is not None and self.bit(data, victory)

    def won(self) -> bool:
        _, data = self.snapshot()
        index = self.profile.flags.get("gf_rando_victory")
        return index is not None and self.bit(data, index)
