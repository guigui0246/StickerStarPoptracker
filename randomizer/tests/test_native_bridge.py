import hashlib
import unittest
from dataclasses import replace

from ..integrations.archipelago.runtime import ReceivedItem
from ..integrations.citra.native import CheckFlags, CodeSignature, NativeGame, NativeProfile
from ..integrations.rom.mailbox import RemoteSession, mailbox_flags, word_flags


class FakeMemory:
    def __init__(self, profile: NativeProfile) -> None:
        self.profile = profile
        self.pointer = 0x08010000
        self.buffer = bytearray(384)
        self.signature = b"A" * 0x160
        self.writes: list[tuple[int, bytes]] = []
        self.ack_reads: list[int] = []
        self.code: dict[int, bytes] = {}
        self.set_flag(profile.flags["gf_rando_seed_initialized"], True)
        for index in range(128):
            self.set_flag(profile.flags[f"gf_rando_seed_{index:02d}"], bool(profile.fingerprint[index // 8] & (1 << (index % 8))))

    @property
    def base(self) -> int:
        return self.pointer + 0x144

    def set_flag(self, index: int, value: bool) -> None:
        mask = 1 << (index % 8)
        self.buffer[index // 8] = (self.buffer[index // 8] | mask) if value else (self.buffer[index // 8] & ~mask)

    def set_word(self, name: str, value: int) -> None:
        if self.profile.word_bits(name) == 1:
            self.set_flag(self.profile.word_index(name), bool(value))
            return
        offset = self.profile.word_index(name) // 8
        size = self.profile.word_size(name)
        self.buffer[offset:offset + size] = value.to_bytes(size, "little")

    def read(self, address: int, size: int) -> bytes:
        if address in self.code:
            return self.code[address][:size]
        if address == self.profile.signature_address:
            return self.signature[:size]
        if address == self.profile.pointer_address:
            return self.pointer.to_bytes(4, "little")
        if address == self.base + self.profile.word_index("ack") // 8 and size == 4 and self.ack_reads:
            return self.ack_reads.pop(0).to_bytes(4, "little")
        offset = address - self.base
        if not 0 <= offset <= offset + size <= len(self.buffer):
            raise ValueError("Read outside test memory")
        return bytes(self.buffer[offset:offset + size])

    def write(self, address: int, data: bytes) -> None:
        offset = address - self.base
        if not 0 <= offset <= offset + len(data) <= len(self.buffer):
            raise ValueError("Write outside test memory")
        self.writes.append((address, data))
        self.buffer[offset:offset + len(data)] = data


class NativeBridgeTests(unittest.TestCase):
    def test_compact_request_and_acknowledgement_words_keep_distinct_writers(self) -> None:
        self.profile.validate_word_ownership()
        self.assertEqual(self.profile.word_bits("item"), 16)
        self.assertEqual(self.profile.word_bits("ready"), 8)
        self.assertEqual(self.profile.word_bits("ack_ready"), 1)
        self.assertEqual(self.profile.word_index("item") // 32, self.profile.word_index("ready") // 32)
        self.assertNotEqual(self.profile.word_index("item") // 32, self.profile.word_index("ack_ready") // 32)
        self.profile.flags["gf_rando_bad_game_flag"] = self.profile.word_index("item") + 31
        with self.assertRaisesRegex(ValueError, "game-owned"):
            self.profile.validate_word_ownership()

    def test_compact_ack_guard_can_use_a_nonzero_bit_without_false_acknowledgement(self) -> None:
        flags = {name: index for name, index in self.profile.flags.items() if not name.startswith("gf_rando_rpc_")}
        flags.update({name: index for index, name in enumerate(mailbox_flags(1605), 1605)})
        profile = replace(self.profile, flags=flags)
        memory = FakeMemory(profile)
        game = NativeGame(memory, profile, "seed", 0, 1, "a" * 64, {})
        memory.set_word("ack", 1)
        self.assertFalse(game.received("ap/0"))
        memory.set_word("ack_ready", 1)
        self.assertTrue(game.received("ap/0"))

    def test_network_only_collection_never_becomes_a_local_receipt(self) -> None:
        profile = replace(self.profile, checks={"star": CheckFlags(1580, None)})
        memory = FakeMemory(profile)
        memory.set_flag(1580, True)
        game = NativeGame(memory, profile, "seed", 0, 1, "a" * 64, {"star": 9})
        self.assertEqual(game.observe(), ({9}, set(), False))
        self.assertFalse(game.received("local/9"))
        self.assertEqual(memory.writes, [])

    def setUp(self) -> None:
        flags = {"gf_rando_seed_initialized": 1446}
        flags.update({f"gf_rando_seed_{index:02d}": 1447 + index for index in range(128)})
        for index, flag in enumerate(mailbox_flags(1600), 1600):
            flags[flag] = index
        self.profile = NativeProfile(0x43C190, 0x144, 3072, 0x282C98, 0x160,
            hashlib.sha256(b"A" * 0x160).hexdigest(), bytes(range(16)), flags,
            {"star": CheckFlags(1580, 1581)}, {100: 1}, RemoteSession("seed", 0, 1, "a" * 64))
        self.memory = FakeMemory(self.profile)
        self.game = NativeGame(self.memory, self.profile, "seed", 0, 1, "a" * 64, {"star": 200})

    def test_save_identity_is_persistent_and_client_identity_is_bound(self) -> None:
        first = self.game.identity()
        self.assertEqual(self.game.identity(), first)
        self.assertEqual(len(self.memory.writes), 4)
        with self.assertRaises(ValueError):
            NativeGame(self.memory, self.profile, "other", 0, 1, "a" * 64, {"star": 200})

    def test_executable_guard_is_verified_before_any_host_write(self) -> None:
        signature = CodeSignature(0x2D81C0, 4, hashlib.sha256(b"good").hexdigest())
        profile = replace(self.profile, code_signatures=(signature,))
        game = NativeGame(self.memory, profile, "seed", 0, 1, "a" * 64, {"star": 200})
        self.memory.code[signature.address] = b"old!"
        with self.assertRaises(ValueError):
            game.identity()
        self.assertFalse(self.memory.writes)
        self.memory.code[signature.address] = b"good"
        game.identity()
        self.assertEqual(len(self.memory.writes), 4)

    def test_reloaded_executable_is_rechecked_before_request_writes(self) -> None:
        self.game.identity()
        writes = len(self.memory.writes)
        self.memory.signature = b"B" * 0x160
        with self.assertRaises(ValueError):
            self.game.deliver("ap/0", ReceivedItem(100, 201, 2, 1))
        self.assertEqual(len(self.memory.writes), writes)

    def test_request_is_not_a_receipt_and_acknowledgement_deduplicates(self) -> None:
        item = ReceivedItem(100, 201, 2, 1)
        self.assertFalse(self.game.deliver("ap/0", item))
        self.assertFalse(self.game.received("ap/0"))
        writes = len(self.memory.writes)
        self.assertFalse(self.game.deliver("ap/0", item))
        self.assertEqual(len(self.memory.writes), writes)
        self.memory.set_word("ack", 1)
        self.memory.set_word("ack_ready", 1)
        self.assertTrue(self.game.received("ap/0"))
        self.assertTrue(self.game.deliver("ap/0", item))
        self.assertEqual(len(self.memory.writes), writes)

    def test_native_checks_and_local_receipts_remain_independent(self) -> None:
        self.memory.set_flag(1580, True)
        self.assertEqual(self.game.collected(), {200})
        self.assertEqual(self.game.observe(), ({200}, set(), False))
        self.assertFalse(self.game.received("local/200"))
        self.assertFalse(self.game.deliver("local/200", ReceivedItem(100, 200, 1, 1)))
        self.assertFalse(self.memory.writes)
        self.memory.set_flag(1581, True)
        self.assertTrue(self.game.received("local/200"))
        self.assertEqual(self.game.observe(), ({200}, {200}, False))

    def test_torn_native_acknowledgement_cannot_skip_future_items(self) -> None:
        self.memory.set_word("ack_ready", 1)
        self.memory.ack_reads = [255, 128]
        self.assertFalse(self.game.received("ap/129"))

    def test_wrong_game_seed_and_host_receipt_writes_are_rejected(self) -> None:
        self.memory.signature = b"B" * 0x160
        with self.assertRaises(ValueError):
            self.game.identity()
        self.assertFalse(self.memory.writes)
        self.memory.signature = b"A" * 0x160
        self.memory.set_flag(self.profile.flags["gf_rando_seed_00"], True)
        with self.assertRaises(ValueError):
            self.game.deliver("ap/0", ReceivedItem(100, 201, 2, 1))
        with self.assertRaises(ValueError):
            self.game.write_host_word(self.memory.base, "ack", 1)

    def test_mailbox_words_are_aligned_and_never_share_native_writes(self) -> None:
        flags = mailbox_flags(1446)
        self.assertEqual((1446 + flags.index(word_flags("item")[0])) % 32, 0)
        self.profile.flags[word_flags("item")[-1]] += 1
        with self.assertRaises(ValueError):
            self.profile.word_index("item")
