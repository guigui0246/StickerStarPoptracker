import hashlib
import re
import struct
import unittest

from ..integrations.rom.abilities import CODE_BASE, TEXT_LIMIT, ability_patch
from ..integrations.rom.sticker_guard import (
    ALBUM_ADD,
    ALBUM_PREFIX,
    COMMIT_ADD,
    COMMIT_PREFIX,
    FORCED_ADD,
    FORCED_PREFIX,
    ITEM_LOOKUP,
    LOOKUP_PREFIX,
    NORMAL_ADD,
    NORMAL_PREFIX,
    sticker_guard_patch,
)
from ..integrations.rom.stickers import StickerPolicy
from .test_abilities import fixture


def sticker_fixture():
    original, flags = fixture()
    code = bytearray(original)
    for address, data in (
        (NORMAL_ADD, NORMAL_PREFIX),
        (FORCED_ADD, FORCED_PREFIX),
        (COMMIT_ADD, COMMIT_PREFIX),
        (ALBUM_ADD, ALBUM_PREFIX),
        (ITEM_LOOKUP, LOOKUP_PREFIX),
    ):
        code[address - CODE_BASE : address - CODE_BASE + len(data)] = data
    policy = StickerPolicy(("SL_JUMP", "SL_HAMMER", "SL_W6_SANDAL_S"), (("SL_FAN", "REAL_FAN"),))
    flags.update({policy.flag(item): 1600 + index for index, item in enumerate(policy.generic)})
    return bytes(code), flags, policy, {"SL_JUMP": 16, "SL_HAMMER": 15, "SL_W6_SANDAL_S": 81}


class StickerGuardTests(unittest.TestCase):
    def test_combined_guard_preserves_segments_and_every_assembly_word(self) -> None:
        code, flags, policy, indices = sticker_fixture()
        ability = ability_patch(code, flags, bytes(range(16)))
        patch = sticker_guard_patch(code, flags, bytes(range(16)), policy, indices, ability)
        result = bytearray(code)
        sections = patch.assembly.split(".section ")[1:]
        self.assertEqual(len(sections), len(patch.records))
        for section, (offset, data) in zip(sections, patch.records, strict=True):
            words = [int(word, 16) for word in re.findall(r"^    \.word 0x([0-9a-f]{8})", section, re.MULTILINE)]
            self.assertEqual(struct.pack(f"<{len(words)}I", *words), data)
            result[offset : offset + len(data)] = data
        self.assertEqual(hashlib.sha256(result).hexdigest(), patch.patched_sha256)
        self.assertLessEqual(CODE_BASE + patch.records[-1][0] + len(patch.records[-1][1]), TEXT_LIMIT)
        self.assertEqual(len(result), len(code))
        self.assertIn("ldrb r5, [r3, r1]", patch.assembly)
        self.assertIn("replacement name data", patch.assembly)

    def test_sticker_guard_also_builds_without_ability_ownership(self) -> None:
        code, flags, policy, indices = sticker_fixture()
        patch = sticker_guard_patch(code, flags, bytes(16), policy, indices)
        self.assertEqual(len(patch.records), 5)

    def test_unknown_revisions_and_ambiguous_or_unsafe_indices_fail(self) -> None:
        code, flags, policy, indices = sticker_fixture()
        for address in (NORMAL_ADD, FORCED_ADD, COMMIT_ADD, ALBUM_ADD, ITEM_LOOKUP):
            bad = bytearray(code)
            bad[address - CODE_BASE] ^= 1
            with self.assertRaises(ValueError):
                sticker_guard_patch(bytes(bad), flags, bytes(16), policy, indices)
        for mapping in ({}, indices | {"SL_HAMMER": 16}, indices | {"SL_JUMP": 201}):
            with self.assertRaises(ValueError):
                sticker_guard_patch(code, flags, bytes(16), policy, mapping)
        flags[policy.flag("SL_HAMMER")] = 2500
        with self.assertRaises(ValueError):
            sticker_guard_patch(code, flags, bytes(16), policy, indices)
