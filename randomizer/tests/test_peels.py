from dataclasses import replace
import struct
import unittest

from ..integrations.rom.kdm import KdmArray, KdmDocument, KdmField, KdmPointer, KdmStructure
from ..integrations.rom.native_delivery import DeliveryPlan, NativeReward, NativeRewardKind, PeelReward
from ..integrations.rom.peels import gate_peel_selection, hook_peel_callback, peel_runtime, peel_sources, resolve_peels, suppress_peel_grants
from ..integrations.rom.plan_io import decode_plan, encode_plan


def fixture(variants: bool = False) -> KdmDocument:
    document = KdmDocument.__new__(KdmDocument)
    types = [1] * 72
    for index in (0, 11, *range(40, 48), 57, *range(60, 72)):
        types[index] = 3
    document.structures = {21: KdmStructure(21, tuple(types), 288, 4)}
    document.arrays = {}
    references = []
    raw = bytearray(1024)
    for index in range(2 if variants else 1):
        offset = 100 + index * 300
        values = [0] * 72
        for position in (0, 11, *range(40, 48), 57, *range(60, 72)):
            values[position] = ""
        values[0], values[1], values[2] = f"key_{index}", index + 1, True
        values[11], values[42], values[44] = "room", "after", "GF_PICKUP"
        values[43] = "cancel"
        values[57] = values[60] = f"PK_PIECE_{index}"
        row = tuple(KdmField(offset + position * 4, types[position], value) for position, value in enumerate(values))
        document.arrays[offset] = KdmArray(index, offset, 21, 72, (KdmField(offset, 21, row),))
        references.append(KdmField(800 + index * 4, 15, KdmPointer(offset, 15)))
        struct.pack_into("<I", raw, row[57].offset, 0x1234 + index)
        struct.pack_into("<I", raw, row[60].offset, 0x1234 + index)
    references.append(KdmField(820, 15, KdmPointer(0, 15)))
    document.tables = {"lockDataTable": KdmArray(9, 800, 15, len(references), tuple(references))}
    document.strings = {}
    document.data = bytes(raw)
    return document


class PeelTests(unittest.TestCase):
    def test_shared_physical_variants_are_one_persistent_check(self) -> None:
        document = fixture(True)
        source, = peel_sources(document)
        check = source.check(NativeReward(NativeRewardKind.COINS, 25))
        self.assertEqual(len(check.hooks), 2)
        plan = DeliveryPlan((check,))
        self.assertEqual(decode_plan(encode_plan(plan)), plan)
        self.assertEqual(resolve_peels(document, plan)[0][1], check)
        with self.assertRaises(ValueError):
            resolve_peels(document, DeliveryPlan((replace(check, variants=()),)))

    def test_only_vanilla_reward_pointers_change(self) -> None:
        document = fixture(True)
        source, = peel_sources(document)
        patched = suppress_peel_grants(document, DeliveryPlan((source.check(NativeReward(NativeRewardKind.COINS, 25)),)))
        changed = {index for index, (old, new) in enumerate(zip(document.data, patched)) if old != new}
        expected = {100 + slot * 300 + 57 * 4 + byte for slot in range(2) for byte in range(4)}
        self.assertTrue(changed <= expected)
        for slot in range(2):
            offset = 100 + slot * 300
            self.assertEqual(struct.unpack_from("<I", patched, offset + 57 * 4)[0], 0)
            self.assertEqual(patched[offset + 60 * 4:offset + 60 * 4 + 4], document.data[offset + 60 * 4:offset + 60 * 4 + 4])

    def test_first_peel_delivers_reward_and_later_peels_return_the_native_piece(self) -> None:
        source, = peel_sources(fixture())
        check = source.check(NativeReward(NativeRewardKind.COINS, 25))
        plan = DeliveryPlan((check,))
        runtime = peel_runtime(plan)
        self.assertIn("gf_rando_check_0000 == false", runtime)
        self.assertIn("gf_rando_check_0000 *= true", runtime)
        self.assertIn('rando_item_grant*("PK_PIECE_0")', runtime)
        self.assertIn("gs_rando_peel_pending *= 1", runtime)
        self.assertIn("rando_peel_reserve == - 1", runtime)
        self.assertNotIn("gf_rando_delivered_0000 == false", runtime)
        self.assertNotIn("GF_PICKUP", runtime)
        result = hook_peel_callback("private after()  {\n\tkeep_original_effect*();\n}\nprivate cancel() {\n}\n", 0, check, source)
        self.assertIn("rando_peel_collect_selected*(0)", result)
        self.assertIn("keep_original_effect*();", result)
        self.assertNotIn("pepalyze_get_now_play_unlock_num", result)

    def test_pending_return_blocks_repeat_peels_but_not_a_new_first_reward(self) -> None:
        source, = peel_sources(fixture())
        runtime = peel_runtime(DeliveryPlan((source.check(NativeReward(NativeRewardKind.COINS, 25)),)))
        first = runtime.index("gf_rando_check_0000 == false")
        pending = runtime.index("if ( gs_rando_peel_pending != 0 )")
        capacity = runtime.index('item_try_addpouch*("PK_PIECE_0", false)')
        self.assertLess(first, pending)
        self.assertLess(pending, capacity)
        self.assertNotIn("gs_rando_peel_pending", runtime[:first])

    def test_reservation_cancellation_and_pending_return_preserve_original_effects(self) -> None:
        observed, = peel_sources(fixture())
        plan = DeliveryPlan((observed.check(NativeReward(NativeRewardKind.COINS, 25)),))
        source = hook_peel_callback("private after() {\noriginal_after*();\n}\nprivate cancel() {\noriginal_cancel*();\n}\n", 0, plan.checks[0], observed)
        self.assertLess(source.index("rando_peel_cancel*(0)"), source.index("original_cancel*()"))
        self.assertLess(source.index("rando_peel_collect_selected*(0"), source.index("original_after*()"))
        runtime = peel_runtime(plan)
        self.assertLess(runtime.index("gs_rando_peel_pending *= 1"), runtime.rindex("rando_peel_return_pending*()"))
        self.assertIn("if ( localVar0 ) {\n\t\t\tgs_rando_peel_pending *= 0", runtime)
        self.assertEqual(plan.saved_bytes, ("gs_rando_peel_pending",))
        gated = gate_peel_selection("private input() { decal_dokodemo_mario_control_main*(); }", plan)
        self.assertIn("rando_peel_can_return*(1)", gated)
        self.assertIn("return* pepalyze_pickup_miss", gated)
        with self.assertRaises(ValueError):
            gate_peel_selection("private input() {}", plan)

    def test_wrong_piece_and_duplicate_sources_are_rejected(self) -> None:
        source, = peel_sources(fixture())
        check = source.check(NativeReward(NativeRewardKind.COINS, 25))
        with self.assertRaises(ValueError):
            resolve_peels(fixture(), DeliveryPlan((replace(check, source_item="PK_WRONG"),)))
        with self.assertRaises(ValueError):
            PeelReward("room", "key", "PK_FIELD_FAKE", check.reward)
        with self.assertRaises(ValueError):
            DeliveryPlan((check, check))

    def test_omitted_native_targets_in_the_same_room_remain_selectable(self) -> None:
        document = fixture(True)
        source, = peel_sources(document)
        full_check = source.check(NativeReward(NativeRewardKind.COINS, 25))
        plan = DeliveryPlan((replace(full_check, variants=()),))
        gated = gate_peel_selection("private input() { decal_dokodemo_mario_control_main*(); }", plan, document)
        self.assertIn('pepalyze_get_access_number*("key_1")', gated)
        self.assertEqual(gated.count("rando_peel_can_return*("), 1)
        self.assertLess(gated.index('pepalyze_get_access_number*("key_1")'), gated.rindex("return* pepalyze_pickup_miss"))
