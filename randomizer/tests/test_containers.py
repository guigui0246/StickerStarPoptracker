from typing import Any, cast
from dataclasses import replace
import unittest

from ..integrations.rom.containers import container_runtime, container_sources, hook_treasure_acquisition
from ..integrations.rom.kdm import KdmArray, KdmDocument, KdmField, KdmPointer, KdmStructure
from ..integrations.rom.native_delivery import ContainerReward, DeliveryPlan, NativeReward, NativeRewardKind
from ..integrations.rom.plan_io import decode_plan, encode_plan
from ..integrations.rom.pickups import item_pickups, production_pickups


def fixture() -> KdmDocument:
    document = KdmDocument.__new__(KdmDocument)
    schemas = {
        21: (3, 3),
        22: (3, 15, 1),
        23: (1, 15),
        24: (15, 15, 1, 1),
        29: (3, 1, 1, 1, 15, 15),
        36: (3, 3, 3, 0, 0, 0, 0, 4, 1, 1, 15, 15),
        38: (3, 15, 1),
        42: (3, 20, 1, 20, 1, 20, 1, 20, 1, 15),
    }
    document.structures = {
        identifier: KdmStructure(identifier, fields, len(fields) * 4, 4) for identifier, fields in schemas.items()
    }
    document.arrays = {}

    def ptr(address):
        return KdmPointer(address, 15)

    def row(address, identifier, values):
        fields = tuple(
            KdmField(address + 4 * index, kind, value)
            for index, (kind, value) in enumerate(zip(schemas[identifier], values, strict=True))
        )
        document.arrays[address] = KdmArray(
            address, address, identifier, len(fields), (KdmField(address, identifier, fields),)
        )

    row(100, 42, ["W2_YOS", ptr(0), 0, ptr(0), 0, ptr(200), 1, ptr(0), 0, ptr(0)])
    document.arrays[200] = KdmArray(200, 200, 15, 1, (KdmField(200, 15, ptr(300)),))
    row(300, 38, ["w2_yos_01", ptr(400), 1])
    row(400, 36, ["EXT_treasure", "TREASURE_FILE", "", 0.0, 0.0, 0.0, 0.0, True, 2819, -1, ptr(500), ptr(0)])
    row(500, 29, ["native_chest", 0, -1, -1, ptr(600), ptr(0)])
    row(600, 24, [ptr(700), ptr(0), 0, 0])
    row(700, 22, ["LIST_1", ptr(800), 1])
    row(800, 21, ["PK_FIELD_TOW_ENTRANCE_1", "LIST_1_1"])
    document.tables = {"all_disposDataTbl": KdmArray(900, 900, 15, 1, (KdmField(900, 15, ptr(100)),))}
    return document


class ContainerTests(unittest.TestCase):
    def test_item_sources_preserve_native_group_and_exclude_debug_gallery(self):
        document = fixture()
        document.structures[39] = KdmStructure(39, (3, 3, 15, 0, 0, 0, 0, 4, 1, 15), 40, 4)
        group = document.arrays[100]
        fields = list(cast(Any, group.values[0]).value)
        fields[0] = replace(fields[0], value="TST")
        fields[7] = replace(fields[7], value=KdmPointer(200, 15))
        document.arrays[100] = replace(group, values=(replace(group.values[0], value=tuple(fields)),))
        values = ("item_01", "REAL_FAN", KdmPointer(0, 15), 1.0, 2.0, 3.0, 0.0, True, 17, KdmPointer(0, 15))
        item_fields = tuple(
            KdmField(1000 + index * 4, kind, value)
            for index, (kind, value) in enumerate(zip(document.structures[39].fields, values, strict=True))
        )
        # Retain a normal-looking map name: group metadata, not a name prefix,
        # determines whether this is a production source.
        document.arrays[400] = KdmArray(400, 400, 39, 10, (KdmField(1000, 39, item_fields),))
        (pickup,) = item_pickups(document)
        self.assertEqual(pickup.group_name, "TST")
        self.assertEqual(production_pickups(document), ())
        updated = list(cast(Any, document.arrays[100].values[0]).value)
        updated[0] = replace(updated[0], value="W2_YOS")
        document.arrays[100] = replace(group, values=(replace(group.values[0], value=tuple(updated)),))
        self.assertEqual(len(production_pickups(document)), 1)

    def test_native_identity_uses_the_chest_not_its_temporary_item_actor(self):
        (source,) = container_sources(fixture())
        self.assertEqual(
            (source.map_name, source.object_name, source.source_item), ("w2_yos_01", "EXT_treasure", "PK_FIELD_TOW_ENTRANCE_1")
        )
        self.assertEqual(source.collection_flag, 2819)
        self.assertEqual(source.item_field_offset, 800)

    def test_ambiguous_loot_is_rejected_instead_of_becoming_a_guessed_check(self):
        document = fixture()
        old = document.arrays[800]
        document.arrays[800] = replace(old, values=old.values * 2)
        with self.assertRaisesRegex(ValueError, "deterministic"):
            container_sources(document)

    def test_reward_roundtrip_and_native_receipts_are_separate_from_the_chest_flag(self):
        check = ContainerReward(
            "w2_yos_01", "EXT_treasure", "PK_FIELD_TOW_ENTRANCE_1", NativeReward(NativeRewardKind.COINS, 25)
        )
        plan = DeliveryPlan((check,))
        self.assertEqual(decode_plan(encode_plan(plan)), plan)
        self.assertEqual(check.id, "container/w2_yos_01/EXT_treasure")
        source = container_runtime(plan)
        self.assertIn("gf_rando_check_0000 *= true", source)
        self.assertNotIn("2819", source)
        with self.assertRaises(ValueError):
            replace(check, container_type="BLOCK_HATENA")

    def test_native_animation_and_flag_effects_remain_and_both_grants_are_guarded(self):
        source = (
            "private action()  {\n\tmobj_set_flag*(self);\n\titem_try_addpouch*(tempVar8);\n"
            "\titem_disp_get_ui*(tempVar8, true, true, 60);\n\titem_try_addpouch*(tempVar8, true);\n"
            "\tchange_opened*(self);\n}\n"
        )
        patched = hook_treasure_acquisition(source)
        self.assertLess(patched.index("rando_container_collect*"), patched.index("mobj_set_flag*"))
        self.assertEqual(patched.count("if ( localVar92 == false )"), 3)
        self.assertIn("change_opened*(self)", patched)
        with self.assertRaises(ValueError):
            hook_treasure_acquisition(source.replace("tempVar8, true", "different, true"))
