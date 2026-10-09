"""Game-owned receipts and checks bridged through an isolated native mailbox.

All rewards are granted by KSM code. The host writes only dedicated mailbox
words and a persistent save nonce, never inventory or native receipt flags.
"""

from dataclasses import dataclass, field
from contextlib import contextmanager
from collections.abc import Iterator, Sequence
import hashlib
from pathlib import Path
import json
import secrets
from typing import Protocol

from ...data.catalog import array, obj, string
from ..archipelago.runtime import ReceivedItem, Session, integer
from ..rom.mailbox import RemoteReward, RemoteSession
from ..rom.native_delivery import NativeReward, NativeRewardKind, capability_receipt
from ..rom.sticker_guard import INSERTION_HOOKS


class Memory(Protocol):
    def read(self, address: int, size: int) -> bytes: ...
    def write(self, address: int, data: bytes) -> None: ...


@dataclass(frozen=True)
class CheckFlags:
    collected: int
    delivered: int | None


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
    saved_bytes: dict[str, int] = field(default_factory=dict)
    priority_pages: bool = False
    game_saved_bytes: dict[str, int] = field(default_factory=dict)
    priority_capabilities: bool = False
    shuffle_royals: bool = False

    @classmethod
    def load(cls, path: Path, *, standalone_catalog_hash: str | None = None) -> "NativeProfile":
        data = obj(json.loads(path.read_text(encoding="utf-8")))
        if data.get("format_version") != 1 or data.get("title_id") != "00040000000A5F00":
            raise ValueError("Unsupported native patch report")
        profile = obj(data.get("rpc_memory_profile"))
        standalone = data.get("remote_session") is None
        if standalone:
            if standalone_catalog_hash is None or data.get("catalog_hash") != standalone_catalog_hash:
                raise ValueError("Standalone observation requires the bound catalog hash")
            session = RemoteSession(string(data.get("seed_name")), 0, 1, standalone_catalog_hash)
        else:
            if standalone_catalog_hash is not None:
                raise ValueError("Standalone observation cannot attach to a network patch")
            remote_session = obj(data.get("remote_session"))
            session = RemoteSession(
                string(remote_session.get("seed")),
                integer(remote_session.get("team")),
                integer(remote_session.get("slot")),
                string(remote_session.get("catalog_hash")),
            )
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
            checked = integer(row.get("checked"))
            delivered = integer(row.get("delivered")) if row.get("delivered") is not None else None
            if identifier in checks or not 0 <= checked < 3072 or (delivered is not None and not 0 <= delivered < 3072):
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
            selector_rewards[item] = NativeReward(
                NativeRewardKind(string(reward.get("kind"))), integer(value) if type(value) is int else string(value)
            )
            RemoteReward(item, selector_rewards[item])
        raw_checks = array(data.get("checks"))
        if len(raw_checks) != len(checks):
            raise ValueError("Native check reward table does not match the flag mapping")
        check_rewards = {}
        for identifier, raw in zip(checks, raw_checks, strict=True):
            reward = obj(obj(raw).get("reward"))
            value = reward.get("value")
            check_rewards[identifier] = NativeReward(
                NativeRewardKind(string(reward.get("kind"))), integer(value) if type(value) is int else string(value)
            )
            if checks[identifier].delivered is None and check_rewards[identifier].kind not in {
                NativeRewardKind.REMOTE,
                NativeRewardKind.EVENT,
            }:
                raise ValueError("Local rewards require a native delivery receipt")
        fingerprint = bytes.fromhex(string(data.get("save_seed_fingerprint")))
        if len(fingerprint) != 16 or (not selectors and not standalone) or (standalone and selectors):
            raise ValueError("Patch does not contain a remote-delivery mailbox")
        patch = data.get("code_patch")
        signatures = (
            tuple(
                CodeSignature(integer(obj(raw).get("address")), integer(obj(raw).get("size")), string(obj(raw).get("sha256")))
                for raw in array(obj(patch).get("signatures"))
            )
            if patch is not None
            else ()
        )
        saved_bytes: dict[str, int] = {}
        game_saved_bytes: dict[str, int] = {}
        if data.get("allocated_saved_bytes"):
            if (profile.get("saved_bytes_offset"), profile.get("saved_bytes_count")) != (4, 256):
                raise ValueError("Unsupported saved-byte mailbox memory revision")
            for raw in array(data.get("allocated_saved_bytes")):
                entry = obj(raw)
                name, index = string(entry.get("name")), integer(entry.get("index"))
                if (
                    name in saved_bytes
                    or name in game_saved_bytes
                    or index in (*saved_bytes.values(), *game_saved_bytes.values())
                    or not (name.startswith("gs_rando_rpc_") or name == "gs_rando_peel_pending")
                    or not 220 <= index < 256
                ):
                    raise ValueError("Duplicate or invalid mailbox saved byte")
                (game_saved_bytes if name == "gs_rando_peel_pending" else saved_bytes)[name] = index
            signature = obj(profile.get("saved_byte_signature"))
            if (signature.get("address"), signature.get("size")) != (0x29404C, 0x24):
                raise ValueError("Unsupported saved-byte setter signature")
            signatures += (CodeSignature(0x29404C, 0x24, string(signature.get("sha256"))),)
        if standalone and saved_bytes:
            raise ValueError("Standalone observation cannot own an RPC mailbox")
        if bool(game_saved_bytes) != bool(data.get("peeled_scrap_sources")):
            raise ValueError("Peel sources require their game-owned pending-return byte")
        if any(
            reward.kind == NativeRewardKind.ABILITY for reward in (*check_rewards.values(), *selector_rewards.values())
        ) and 0x2D81C0 not in {signature.address for signature in signatures}:
            raise ValueError("Ability rewards require executable guard signatures")
        policy = data.get("sticker_policy")
        guarded_generics = policy is not None and obj(policy).get("randomize_generic", True) is not False
        if guarded_generics and not INSERTION_HOOKS <= {signature.address for signature in signatures}:
            raise ValueError("Sticker policies require executable insertion guard signatures")
        result = cls(
            integer(profile.get("pointer_address")),
            integer(profile.get("global_flags_offset")),
            integer(profile.get("flag_count")),
            integer(profile.get("signature_address")),
            integer(profile.get("signature_size")),
            string(profile.get("signature_sha256")),
            fingerprint,
            flags,
            checks,
            selectors,
            session,
            check_rewards,
            selector_rewards,
            signatures,
            saved_bytes,
            data.get("priority_pages") is True,
            game_saved_bytes,
            data.get("priority_capabilities") is True,
            data.get("shuffle_royals") is True,
        )
        if (
            result.pointer_address,
            result.flags_offset,
            result.flag_count,
            result.signature_address,
            result.signature_size,
        ) != (0x43C190, 0x144, 3072, 0x282C98, 0x160):
            raise ValueError("Unsupported game memory revision")
        if len(result.signature_sha256) != 64:
            raise ValueError("Invalid executable signature hash")
        if not standalone:
            for name in ("item", "sequence", "ready", "ack", "ack_ready", "save_a", "save_b", "save_c", "save_d"):
                result.word_index(name)
            result.validate_word_ownership()
        elif any(reward.kind == NativeRewardKind.REMOTE for reward in check_rewards.values()):
            raise ValueError("Standalone observation cannot contain foreign-owned checks")
        return result

    def word_index(self, name: str) -> int:
        if self.saved_bytes:
            from ..rom.mailbox import byte_fields

            positions = [self.saved_bytes[field] for field in byte_fields(name)]
            if positions != list(range(positions[0], positions[0] + len(positions))):
                raise ValueError("Saved mailbox bytes are not contiguous")
            return 3072 + positions[0] * 8
        bits = self.word_bits(name)
        positions = [self.flags[f"gf_rando_rpc_{name}_{bit:02d}"] for bit in range(bits)]
        alignment = 1 if bits == 1 else 8 if bits < 32 else 32
        if positions[0] % alignment or positions != list(range(positions[0], positions[0] + bits)):
            raise ValueError("Mailbox word is not aligned or has shared ownership")
        return positions[0]

    def word_bits(self, name: str) -> int:
        if self.saved_bytes:
            from ..rom.mailbox import byte_fields

            return len(byte_fields(name)) * 8
        prefix = f"gf_rando_rpc_{name}_"
        bits = len([flag for flag in self.flags if flag.startswith(prefix) and flag[len(prefix) :].isdigit()])
        allowed = {"item": {16, 32}, "ready": {8, 32}, "ack_ready": {1, 32}}.get(name, {32})
        if bits not in allowed:
            raise ValueError("Unsupported native mailbox field width")
        return bits

    def word_size(self, name: str) -> int:
        return max(1, self.word_bits(name) // 8)

    def word_offset(self, name: str) -> int:
        if self.saved_bytes:
            return 4 - self.flags_offset + (self.word_index(name) - 3072) // 8
        return self.word_index(name) // 8

    def validate_word_ownership(self) -> None:
        if (
            set(self.game_saved_bytes) - {"gs_rando_peel_pending"}
            or len(set(self.game_saved_bytes.values())) != len(self.game_saved_bytes)
            or any(not 220 <= index < 256 or index in self.saved_bytes.values() for index in self.game_saved_bytes.values())
        ):
            raise ValueError("Game-owned saved bytes overlap host mailbox fields")
        if self.priority_capabilities and not self.priority_pages:
            raise ValueError("Priority capabilities require the independent receipt protocol")
        if self.saved_bytes:
            from ..rom.mailbox import saved_mailbox_bytes

            if set(self.saved_bytes) != set(saved_mailbox_bytes(self.priority_pages)) or any(
                flag.startswith("gf_rando_rpc_") for flag in self.flags
            ):
                raise ValueError("Saved-byte mailbox has missing or conflicting fields")
            if len(set(self.saved_bytes.values())) != len(self.saved_bytes) or any(
                not 220 <= index < 256 for index in self.saved_bytes.values()
            ):
                raise ValueError("Saved-byte mailbox overlaps native slots")
            if self.priority_pages and not any(
                reward.kind == NativeRewardKind.PAGE for reward in self.selector_rewards.values()
            ):
                raise ValueError("Priority page profile has no page selector")
            if self.priority_pages and any(f"gf_rando_remote_page_{index}" not in self.flags for index in range(6)):
                raise ValueError("Independent remote page receipts are missing")
            return
        if self.priority_pages:
            raise ValueError("Priority pages require the saved-byte mailbox")
        host_fields = ("item", "sequence", "ready", "save_a", "save_b", "save_c", "save_d")
        host_flags = {f"gf_rando_rpc_{name}_{bit:02d}" for name in host_fields for bit in range(self.word_bits(name))}
        host_flags.update(flag for flag in self.flags if flag.startswith("gf_rando_rpc_reserved_"))
        host_words = {self.flags[flag] // 32 for flag in host_flags}
        game_words = {index // 32 for flag, index in self.flags.items() if flag not in host_flags}
        game_words.update(check.collected // 32 for check in self.checks.values())
        game_words.update(check.delivered // 32 for check in self.checks.values() if check.delivered is not None)
        if game_words & host_words:
            raise ValueError("Host mailbox fields share a native game-owned flag word")


class NativeGame:
    def __init__(
        self,
        memory: Memory,
        profile: NativeProfile,
        seed: str,
        team: int,
        slot: int,
        catalog_hash: str,
        location_ids: dict[str, int],
    ) -> None:
        if set(location_ids) - profile.checks.keys() or len(set(location_ids.values())) != len(location_ids):
            raise ValueError("Location mapping is unknown or ambiguous")
        if (seed, team, slot, catalog_hash) != (
            profile.session.seed,
            profile.session.team,
            profile.session.slot,
            profile.session.catalog_hash,
        ):
            raise ValueError("Client identity does not match the installed native patch")
        self.memory, self.profile = memory, profile
        self.seed, self.team, self.slot, self.catalog_hash = seed, team, slot, catalog_hash
        self.locations = {location: profile.checks[key] for key, location in location_ids.items()}
        self.signature_verified = False
        self._local_receipts: set[int] | None = None
        self._page_ranks: dict[int, int] = {}
        self._page_items: dict[int, ReceivedItem] = {}
        self._capability_items: dict[int, ReceivedItem] = {}
        self._capability_flags: dict[int, str] = {}

    @contextmanager
    def cached_local_receipts(self) -> Iterator[None]:
        if self._local_receipts is not None:
            raise RuntimeError("Native receipt polling cannot be nested")
        _, data = self.snapshot()
        self._local_receipts = {
            location
            for location, flags in self.locations.items()
            if flags.delivered is not None and self.bit(data, flags.delivered)
        }
        try:
            yield
        finally:
            self._local_receipts = None

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
        if self.profile.saved_bytes or self.profile.game_saved_bytes:
            data += self.memory.read(pointer + 4, 256)
        return base, data

    def word(self, data: bytes, name: str) -> int:
        index = self.profile.word_index(name)
        if self.profile.word_bits(name) == 1:
            return int(self.bit(data, index))
        return int.from_bytes(data[index // 8 : index // 8 + self.profile.word_size(name)], "little")

    def write_host_word(self, base: int, name: str, value: int) -> None:
        if name not in {"item", "sequence", "ready", "save_a", "save_b", "save_c", "save_d", "page_rank"}:
            raise ValueError("Host may not modify native acknowledgement or inventory")
        # ROM reloads can replace executable guards while retaining this save's
        # fingerprint. Recheck installed code before each host-owned write.
        self.verify_executable()
        self.memory.write(base + self.profile.word_offset(name), value.to_bytes(self.profile.word_size(name), "little"))

    def identity(self) -> Session:
        base, data = self.snapshot()
        names = ("save_a", "save_b", "save_c", "save_d")
        nonce = b"".join(self.word(data, name).to_bytes(4, "little") for name in names)
        if nonce == bytes(16):
            nonce = secrets.token_bytes(16)
            for index, name in enumerate(names):
                self.write_host_word(base, name, int.from_bytes(nonce[index * 4 : index * 4 + 4], "little"))
            _, verified = self.snapshot()
            if b"".join(self.word(verified, name).to_bytes(4, "little") for name in names) != nonce:
                raise RuntimeError("Save identity was not accepted by the native mailbox")
        return Session(self.seed, self.team, self.slot, self.catalog_hash, nonce.hex())

    def received(self, receipt: str) -> bool:
        kind, separator, value = receipt.partition("/")
        if not separator or not value.isdecimal():
            raise ValueError("Unsupported receipt identifier")
        index = int(value)
        if kind == "local":
            if index not in self.locations:
                raise ValueError("Local receipt refers to an unknown location")
            if self._local_receipts is not None:
                return index in self._local_receipts
            _, data = self.snapshot()
            delivered = self.locations[index].delivered
            return delivered is not None and self.bit(data, delivered)
        if kind != "ap" or not 0 <= index < 0x7FFFFFFE:
            raise ValueError("Unsupported AP receipt index")
        base, data = self.snapshot()
        if index in self._capability_flags:
            return self.bit(data, self.profile.flags[self._capability_flags[index]])
        if index in self._page_ranks:
            return self.bit(data, self.profile.flags[f"gf_rando_remote_page_{self._page_ranks[index]}"])
        # Read the commit guard around the acknowledgement and confirm its
        # value again. A chunked flag snapshot alone can see a torn VM update.
        ready_address = base + self.profile.word_offset("ack_ready")
        ack_address = base + self.profile.word_offset("ack")
        ready_size = self.profile.word_size("ack_ready")
        ready_mask = 1 << (self.profile.word_index("ack_ready") % 8)
        before = int.from_bytes(self.memory.read(ready_address, ready_size), "little")
        acknowledged = int.from_bytes(self.memory.read(ack_address, 4), "little")
        after = int.from_bytes(self.memory.read(ready_address, ready_size), "little")
        confirmed = int.from_bytes(self.memory.read(ack_address, 4), "little")
        return bool(before & after & ready_mask) and acknowledged == confirmed and index < acknowledged <= 0x7FFFFFFE

    def prepare_pages(self, items: Sequence[tuple[int, ReceivedItem]]) -> None:
        if not self.profile.priority_pages:
            return
        pages = {
            index: item
            for index, item in items
            if self.profile.selector_rewards.get(item.item) == NativeReward(NativeRewardKind.PAGE, 1)
        }
        if (
            any(not 0 <= index < 0x7FFFFFFE for index in pages)
            or len(pages) > 6
            or any(index not in pages or pages[index] != item for index, item in self._page_items.items())
        ):
            raise ValueError("Remote page stream changed or exceeds native capacity")
        ordered = sorted(pages)
        ranks = {index: rank for rank, index in enumerate(ordered)}
        if any(ranks[index] != rank for index, rank in self._page_ranks.items()):
            raise ValueError("Remote page receipt ordering changed")
        if self.profile.priority_capabilities:
            capabilities = {
                index: item
                for index, item in items
                if item.item in self.profile.selector_rewards
                and capability_receipt(self.profile.selector_rewards[item.item], self.profile.shuffle_royals)
            }
            if any(index not in capabilities or capabilities[index] != item for index, item in self._capability_items.items()):
                raise ValueError("Remote capability stream changed")
            capability_flags: dict[int, str] = {}
            for index, item in capabilities.items():
                flag = capability_receipt(self.profile.selector_rewards[item.item], self.profile.shuffle_royals)
                if not 0 <= index < 0x7FFFFFFE or flag is None or flag not in self.profile.flags:
                    raise ValueError("Remote capability lacks a native receipt")
                capability_flags[index] = flag
            self._capability_flags, self._capability_items = capability_flags, capabilities
        self._page_items, self._page_ranks = pages, ranks

    def is_priority_item(self, item: ReceivedItem) -> bool:
        reward = self.profile.selector_rewards.get(item.item)
        return self.profile.priority_pages and (
            reward == NativeReward(NativeRewardKind.PAGE, 1)
            or (
                self.profile.priority_capabilities
                and reward is not None
                and capability_receipt(reward, self.profile.shuffle_royals) is not None
            )
        )

    def deliver_priority(self, receipt: str, item: ReceivedItem) -> bool:
        if not receipt.startswith("ap/") or not receipt[3:].isdecimal():
            raise ValueError("Unsupported priority receipt")
        index = int(receipt[3:])
        if index not in self._page_ranks and index not in self._capability_flags:
            return False
        if (self._page_items | self._capability_items)[index] != item:
            raise ValueError("Page request conflicts with the durable stream")
        if self.received(receipt):
            return True
        base, data = self.snapshot()
        if self.word(data, "ready") == 2:
            return False
        self._publish(base, index + 1, self.profile.selectors[item.item], 2, self._page_ranks.get(index))
        return False

    def _publish(self, base: int, sequence: int, selector: int, ready: int, page_rank: int | None = None) -> None:
        self.write_host_word(base, "ready", 0)
        self.write_host_word(base, "item", selector)
        self.write_host_word(base, "sequence", sequence)
        if page_rank is not None:
            self.write_host_word(base, "page_rank", page_rank)
        self.write_host_word(base, "ready", ready)

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
        if self.profile.priority_pages and self.word(data, "ready") == 2:
            pending_index = self.word(data, "sequence") - 1
            if not self.received(f"ap/{pending_index}"):
                return False
        if self.word(data, "ready") == 1 and self.word(data, "sequence") == index and self.word(data, "item") == selector:
            return False  # wait for game-owned acknowledgement; do not republish
        page_rank = self._page_ranks.get(index - 1)
        if (
            self.profile.priority_pages
            and self.profile.selector_rewards.get(item.item) == NativeReward(NativeRewardKind.PAGE, 1)
            and page_rank is None
        ):
            raise ValueError("Page stream must be prepared before native delivery")
        self._publish(base, index, selector, 1, page_rank)
        return False

    def collected(self) -> set[int]:
        _, data = self.snapshot()
        return {location for location, flags in self.locations.items() if self.bit(data, flags.collected)}

    def observe(self) -> tuple[set[int], set[int], bool]:
        """Read tracker checks and native receipts together without per-item RPC."""
        _, data = self.snapshot()
        collected = {location for location, flags in self.locations.items() if self.bit(data, flags.collected)}
        delivered = {
            location
            for location, flags in self.locations.items()
            if flags.delivered is not None and self.bit(data, flags.delivered)
        }
        victory = self.profile.flags.get("gf_rando_victory")
        return collected, delivered, victory is not None and self.bit(data, victory)

    def won(self) -> bool:
        _, data = self.snapshot()
        index = self.profile.flags.get("gf_rando_victory")
        return index is not None and self.bit(data, index)
