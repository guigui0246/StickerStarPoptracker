import struct
import unittest

from ..integrations.rom.kdm import KdmDocument
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind, PickupReward
from ..integrations.rom.script_build import replace_body
from ..integrations.rom.switches import global_flags, register_flags
from .test_rom_formats import small_kdm


def small_switch_registry() -> bytes:
    names = ("gf_mobj_item_start", "gf_mobj_item_end", "gf_existing", "gfSwitchTable", "gsSwitchTable", "gs_existing")
    strings = bytearray(struct.pack("<I", len(names)))
    pointers = {}
    for name in names:
        pointers[name] = 40 + len(strings)
        raw = name.encode() + b"\0"
        strings.extend(raw + bytes((-len(raw)) % 4))
    sections = [40]
    cursor = 40 + len(strings)
    sections.extend((cursor, cursor + 4, cursor + 8, cursor + 12))
    definition = struct.pack("<IHH4I", 1, 21, 2, 0, 0, 3, 1)
    sections.append(cursor + 12 + len(definition))
    sections.append(sections[-1] + 4)
    tables = bytearray(struct.pack("<III", 2, pointers["gfSwitchTable"], pointers["gsSwitchTable"]))
    tables.extend(struct.pack("<4H", 22, 8, 21, 2))
    for name, index in (("gf_mobj_item_start", 16), ("gf_mobj_item_end", 31), ("gf_existing", 0), ("", 0)):
        tables.extend(struct.pack("<Ii", pointers.get(name, 0), index))
    tables.extend(struct.pack("<4H", 23, 4, 21, 2))
    for name, index in (("gs_existing", 7), ("", 0)):
        tables.extend(struct.pack("<Ii", pointers.get(name, 0), index))
    sections.append(sections[-1] + len(tables))
    return b"KDMR\x00\x01\x01\x00" + struct.pack("<8I", *(value // 4 for value in sections)) + strings + bytes(12) + definition + bytes(4) + tables + bytes(4)


class SwitchRegistryTests(unittest.TestCase):
    def test_new_strings_relocate_nested_array_pointers(self) -> None:
        original = KdmDocument(small_kdm())
        patched = KdmDocument(original.add_strings(("new_string", "new_string", "A")))
        reference = patched.tables["Table"].values[0].value
        fields = patched.pointed_array(reference).values[0].value
        self.assertEqual(tuple(field.value for field in fields), ("A", 7, "B"))
        self.assertEqual(len(patched.strings), len(original.strings) + 1)
        self.assertEqual(patched.add_strings(("A",)), patched.data)
        with self.assertRaises(ValueError):
            original.add_strings(("bad\0value",))

    def test_registration_preserves_other_tables_and_existing_flags(self) -> None:
        source = small_switch_registry()
        old = KdmDocument(source)
        patched, allocated = register_flags(source, ("gf_rando_check_0000", "gf_rando_delivered_0000"))
        new = KdmDocument(patched)
        self.assertEqual(global_flags(new), global_flags(old) + allocated)
        self.assertEqual([flag.index for flag in allocated], [1, 2])
        self.assertEqual(tuple(tuple(f.value for f in row.value) for row in old.tables["gsSwitchTable"].values), tuple(tuple(f.value for f in row.value) for row in new.tables["gsSwitchTable"].values))
        self.assertEqual(register_flags(source, ()), (source, ()))

    def test_flag_capacity_and_names_are_checked(self) -> None:
        for names in (("gf_existing",), ("gf_rando_x", "gf_rando_x"), ("gf_rando_x; injected",), tuple(f"gf_rando_{index}" for index in range(17))):
            with self.assertRaises(ValueError):
                register_flags(small_switch_registry(), names)
        patched, _ = register_flags(small_switch_registry(), ("gf_rando_x",))
        with self.assertRaises(ValueError):
            register_flags(patched, ("gf_rando_x",))


class NativeDeliveryTests(unittest.TestCase):
    def test_mini_star_receipt_controls_revisits_independently_of_received_route(self) -> None:
        check = GoalBlockReward("map", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 20))
        body = DeliveryPlan((check,)).goal_block_body()
        self.assertLess(body.index("localVar1 = gf_rando_check_0000"), body.index("if ( localVar1 == false )"))
        self.assertEqual(body.count("pouch_add_comet_num*();"), 1)
        self.assertIn("if ( tempVar3 == false )", body)
    def test_pickup_and_star_dispatch_keep_independent_receipt_indices(self) -> None:
        reward = NativeReward(NativeRewardKind.COINS, 20)
        pickup = PickupReward("hei_2_D1", "K_REAL", "REAL_BED", reward)
        star = GoalBlockReward("hei_5_03", "GF_WM_A01_A02", reward)
        plan = DeliveryPlan((pickup, star))
        self.assertIn("gf_rando_check_0000", plan.pickup_function())
        self.assertNotIn("gf_rando_check_0001", plan.pickup_function())
        self.assertIn("gf_rando_check_0001", plan.goal_block_body())
        self.assertNotIn("gf_rando_check_0000", plan.goal_block_body())
        self.assertIn('tempVar0 == "K_REAL"', plan.pickup_function())
        self.assertNotEqual(plan.fingerprint, DeliveryPlan((star, pickup)).fingerprint)
        with self.assertRaises(ValueError):
            PickupReward("hei_2_D1", 'K_REAL";bad', "REAL_BED", reward)

    def test_rewards_reject_code_injection_invalid_counts_and_unsafe_pages(self) -> None:
        for kind, value in ((NativeRewardKind.ITEM, 'SL_JUMP"); injected();'), (NativeRewardKind.ITEM, "SL_PAGE"), (NativeRewardKind.COINS, True), (NativeRewardKind.COINS, 0), (NativeRewardKind.MINI_STAR, "GF_TUTORIAL"), (NativeRewardKind.ROYAL, 7)):
            with self.assertRaises(ValueError):
                NativeReward(kind, value)

    def test_source_and_receipt_state_are_separate_and_seed_bound(self) -> None:
        source = GoalBlockReward("hei_5_03", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 20))
        other = GoalBlockReward("hei_5_03", "GF_WM_A01_A02", NativeReward(NativeRewardKind.ITEM, "SL_JUMP"))
        plan = DeliveryPlan((source,))
        self.assertNotEqual(plan.fingerprint, DeliveryPlan((other,)).fingerprint)
        self.assertEqual(len(plan.flags), 131)
        self.assertIn("gf_rando_delivered_0000 == false", plan.delivery_body())
        self.assertIn("tempVar3 == false", plan.goal_block_body())
        with self.assertRaises(ValueError):
            DeliveryPlan((source, source))
        with self.assertRaises(ValueError):
            GoalBlockReward(None, "GF_WM_A01_A02", source.reward)

    def test_function_replacement_preserves_strings_and_other_functions(self) -> None:
        source = 'public target(temp tempVar0)  {\n\ttext("}");\n\tif ( true ) { old(); }\n}\nprivate untouched()  { keep(); }\n'
        result = replace_body(source, "target", "\tnew();")
        self.assertIn("public target(temp tempVar0)  {\n\tnew();\n}", result)
        self.assertIn("private untouched()  { keep(); }", result)
        with self.assertRaises(ValueError):
            replace_body(source, "missing", "")
        with self.assertRaises(ValueError):
            replace_body(source + source, "target", "")


if __name__ == "__main__":
    unittest.main()
