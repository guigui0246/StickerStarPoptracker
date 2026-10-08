import struct
import unittest

from ..integrations.rom.native_delivery import (
    BannerReward, DeliveryPlan, FlagReward, GoalBlockReward,
    NativeReward, NativeRewardKind, ScriptReward,
)
from ..integrations.rom.royal_patch import disable_book_restoration, suppress_royal_grant, FINAL_BOSS, INTERMISSIONS
from ..settings import Banners


def restoration_fixture() -> tuple[bytes, int, int]:
    name = b"royalseal_book_reset\0"
    name += bytes((-len(name)) % 4)
    function = struct.pack("<10I", 1, 0xFFFFFFFF, 0x1234, 0, 0, 0, 9, 0x20000000, 0, len(name) // 4) + name + bytes(12)
    instructions = struct.pack("<11I", 10, 5, 0x1234, 8, 0x10c, 0x5678, 0x11, 3, 0x40, 9, 1)
    sections = [bytes(4), function, bytes(4), bytes(4), bytes(4), bytes(4), bytes(4), instructions]
    offsets = []
    cursor = 44
    for section in sections:
        offsets.append(cursor)
        cursor += len(section)
    header = b"KSMR" + struct.pack("<I8II", 0x10300, *(offset // 4 for offset in offsets), 0)
    return header + b"".join(sections), offsets[-1] + 16, offsets[-1] + 36


class EventRewardTests(unittest.TestCase):
    def test_donation_signal_reuses_native_check_flag_and_keeps_delivery_distinct(self) -> None:
        check = FlagReward("museum", "gf_museum_btl_seal_001", NativeReward(NativeRewardKind.COINS, 10))
        plan = DeliveryPlan((check,))
        self.assertNotIn(check.source_flag, plan.flags)
        self.assertIn(check.source_flag, plan.references)
        self.assertEqual(plan.receipt(0), (check.source_flag, "gf_rando_delivered_0000"))
        self.assertIn("gf_museum_btl_seal_001 && gf_rando_delivered_0000 == false", plan.delivery_body())

    def test_reduced_banner_uses_exact_integer_comparison_and_native_max(self) -> None:
        filler = NativeReward(NativeRewardKind.COINS, 10)
        plan = DeliveryPlan((FlagReward("museum", "gf_museum_btl_seal_001", filler), BannerReward("million_coin", Banners.REDUCED, filler)))
        body = plan.delivery_body()
        self.assertIn("temp tempVar1;", body)
        self.assertIn("tempVar0 * 10 >= tempVar1", body)
        self.assertIn("pouch_honor_get_max*(honor_id_million_coin)", body)
        with self.assertRaises(ValueError):
            BannerReward("million_coin", Banners.OFF, filler)

    def test_victory_cannot_be_randomized_onto_an_ordinary_check(self) -> None:
        victory = NativeReward(NativeRewardKind.VICTORY, 1)
        with self.assertRaises(ValueError):
            DeliveryPlan((GoalBlockReward("hei_5_03", "GF_WM_A01_A02", victory),))
        final = ScriptReward("victory", FINAL_BOSS, "koopa_battle_after_event_init", victory)
        plan = DeliveryPlan((final,))
        self.assertIn("gf_rando_victory", plan.flags)
        self.assertIn("gf_rando_victory *= true", plan.delivery_body())

    def test_royal_shuffle_requires_complete_source_and_reward_coverage(self) -> None:
        reward = NativeReward(NativeRewardKind.ROYAL, 1)
        source = FlagReward("boss", "gf_evt_1_6_royal_seal", reward)
        with self.assertRaises(ValueError):
            DeliveryPlan((source,), shuffle_royals=True)

    def test_vanilla_grant_suppression_preserves_story_and_surrounding_calls(self) -> None:
        source = 'private finish_itm(local localVar0) {\ngf_story = true;\npouch_set_royal_seal(localVar0);\nmap_exit("royal");\n}'
        patched = suppress_royal_grant(INTERMISSIONS[0], source)
        self.assertIn("gf_story = true", patched)
        self.assertIn('map_exit("royal")', patched)
        self.assertNotIn("pouch_set_royal_seal", patched)
        with self.assertRaises(ValueError):
            suppress_royal_grant(INTERMISSIONS[0], source + source)

    def test_restoration_patch_preserves_every_other_byte_and_rejects_unknown_frames(self) -> None:
        original, start, end = restoration_fixture()
        patched = disable_book_restoration(original)
        self.assertEqual(original[:start], patched[:start])
        self.assertEqual(original[end:], patched[end:])
        self.assertEqual(struct.unpack_from("<2I", patched, start), (3, 0x40))
        self.assertEqual(len(original), len(patched))
        broken = bytearray(original)
        struct.pack_into("<I", broken, start - 4, 7)
        with self.assertRaises(ValueError):
            disable_book_restoration(bytes(broken))
