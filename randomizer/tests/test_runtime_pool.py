import hashlib
import re
import struct
import unittest

from ..integrations.rom.abilities import CODE_BASE
from ..integrations.rom.runtime_pool import CELL_SIZE, EXPANDED_LIMIT, ORIGINAL_LIMIT, POOL_SITES, expand_variable_pool


def fixture() -> bytes:
    code = bytearray(0x34E000)
    for address, original, _, _ in POOL_SITES:
        struct.pack_into("<I", code, address - CODE_BASE, original)
    return bytes(code)


def arm_immediate(word: int) -> int:
    rotation = ((word >> 8) & 15) * 2
    value = word & 255
    return ((value >> rotation) | (value << (32 - rotation))) & 0xFFFFFFFF


class RuntimePoolTests(unittest.TestCase):
    def test_allocation_clear_initialization_and_both_scans_share_the_new_bound(self):
        code = fixture()
        patch = expand_variable_pool(code)
        self.assertEqual(len(patch.records), 5)
        rebuilt = bytearray(code)
        for (offset, data), (_, original, value, _) in zip(patch.records, POOL_SITES, strict=True):
            word = struct.unpack("<I", data)[0]
            self.assertEqual(arm_immediate(word), value)
            self.assertEqual(word & ~0xFFF, original & ~0xFFF)
            rebuilt[offset : offset + 4] = data
        self.assertEqual(EXPANDED_LIMIT * CELL_SIZE, 0x90000)
        self.assertEqual((EXPANDED_LIMIT - ORIGINAL_LIMIT) * CELL_SIZE, 288 * 1024)
        self.assertEqual(hashlib.sha256(rebuilt).hexdigest(), patch.patched_sha256)
        words = [int(value, 16) for value in re.findall(r"\.word 0x([0-9a-f]{8})", patch.assembly)]
        self.assertEqual(words, [struct.unpack("<I", data)[0] for _, data in patch.records])
        changed_words = {index // 4 for index, (left, right) in enumerate(zip(code, rebuilt)) if left != right}
        self.assertEqual(changed_words, {(address - CODE_BASE) // 4 for address, _, _, _ in POOL_SITES})

    def test_mismatched_source_or_overlapping_patch_is_rejected(self):
        code = fixture()
        patched = expand_variable_pool(code)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            expand_variable_pool(code, patched)
        bad = bytearray(code)
        bad[POOL_SITES[0][0] - CODE_BASE] ^= 1
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            expand_variable_pool(bytes(bad))
        with self.assertRaisesRegex(ValueError, "same source"):
            expand_variable_pool(bytes(bad), patched)
