import hashlib
import struct
import re
import unittest

from ..integrations.rom.abilities import ATTACH_FUNCTION, CODE_BASE, ORIGINAL_ATTACH, TEXT_END, TEXT_LIMIT, ability_patch, branch, immediate
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind


def fixture(start: int = 1447) -> tuple[bytes, dict[str, int]]:
    code = bytearray(0x34E000)
    code[ATTACH_FUNCTION - CODE_BASE:ATTACH_FUNCTION - CODE_BASE + 16] = ORIGINAL_ATTACH
    flags = {f"gf_rando_seed_{bit:02d}": start + bit for bit in range(128)}
    flags.update(gf_rando_seed_initialized=start - 1, gf_rando_ability_hammer=start + 128, gf_rando_ability_paperization=start + 129)
    return bytes(code), flags


class AbilityTests(unittest.TestCase):
    def test_reviewable_assembly_matches_every_ips_word(self) -> None:
        for start in (1447, 1456, 1472):
            code, flags = fixture(start)
            patch = ability_patch(code, flags, bytes(range(16)))
            sections = patch.assembly.split('.section ')[1:]
            self.assertEqual(len(sections), len(patch.records))
            for section, (_, data) in zip(sections, patch.records):
                words = [int(value, 16) for value in re.findall(r'^    \.word 0x([0-9a-f]{8})', section, re.MULTILINE)]
                self.assertEqual(struct.pack(f'<{len(words)}I', *words), data)
            self.assertIn('bx lr', patch.assembly)
            self.assertIn('literal data', patch.assembly)

    def test_patch_stays_in_original_text_padding_and_ips_roundtrips(self) -> None:
        code, flags = fixture()
        patch = ability_patch(code, flags, bytes(range(16)))
        ips = patch.ips()
        self.assertEqual(ips[:5], b"PATCH")
        result = bytearray(code)
        cursor = 5
        while ips[cursor:cursor + 3] != b"EOF":
            offset = int.from_bytes(ips[cursor:cursor + 3], "big")
            size = int.from_bytes(ips[cursor + 3:cursor + 5], "big")
            result[offset:offset + size] = ips[cursor + 5:cursor + 5 + size]
            cursor += 5 + size
        self.assertEqual(cursor + 3, len(ips))
        self.assertEqual(hashlib.sha256(result).hexdigest(), patch.patched_sha256)
        self.assertEqual(len(result), len(code))
        offset, data = patch.records[1]
        self.assertEqual(CODE_BASE + offset, TEXT_END)
        self.assertLessEqual(TEXT_END + len(data), TEXT_LIMIT)
        self.assertEqual(struct.unpack("<I", patch.records[0][1])[0], branch(ATTACH_FUNCTION, TEXT_END))

    def test_revision_and_reserved_storage_are_rejected(self) -> None:
        code, flags = fixture()
        for bad in (bytes(len(code)), code[:-1], code[:TEXT_END - CODE_BASE] + b"A" + code[TEXT_END - CODE_BASE + 1:]):
            with self.assertRaises(ValueError):
                ability_patch(bad, flags, bytes(16))
        flags["gf_rando_ability_hammer"] = 2560
        with self.assertRaises(ValueError):
            ability_patch(code, flags, bytes(16))

    def test_ability_pool_and_initialization_are_explicit(self) -> None:
        checks = tuple(GoalBlockReward(f"map_{index}", f"GF_WM_A0{index + 1}_A0{index + 2}", NativeReward(NativeRewardKind.ABILITY, value)) for index, value in enumerate(("hammer", "paperization")))
        plan = DeliveryPlan(checks)
        self.assertTrue(plan.ability_mode)
        self.assertIn("tempVar0 = pouch_hammer | pouch_lucie", plan.delivery_body())
        self.assertIn("pouch_detach_accessory*(tempVar0)", plan.delivery_body())
        self.assertIn("gf_rando_ability_hammer *= true", plan.delivery_body())
        with self.assertRaises(ValueError):
            DeliveryPlan(checks[:1])

    def test_arm_immediate_handles_every_flag_bit(self) -> None:
        for bit in range(32):
            encoded = immediate(1 << bit)
            shift = (encoded >> 8) * 2
            value = encoded & 255
            decoded = ((value >> shift) | (value << (32 - shift))) & 0xFFFFFFFF if shift else value
            self.assertEqual(decoded, 1 << bit)
