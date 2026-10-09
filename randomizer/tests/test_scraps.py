import unittest

from ..integrations.rom.native_delivery import DeliveryPlan, NativeReward, NativeRewardKind, PickupReward
from ..integrations.rom.scraps import ScrapItem, scripted_scraps


class ScrapTests(unittest.TestCase):
    def test_local_names_are_function_scoped_and_custom_pickups_are_collectible(self) -> None:
        source = """private prop_init()  {
    local localVar2 *= "dummy";
    item_static_entry*(localVar2, "PK_FIELD_PROP", 0, 0, 0);
    item_set_flg*(localVar2, item_flg_no_get, true);
}
private pickup_init()  {
    local localVar2 *= "map_piece_a";
    item_static_entry*(localVar2, "PK_FIELD_W5_JUN_BRIDGE_2", 0, 0, 0);
    item_set_flg*(localVar2, item_flg_no_get, true);
    item_set_itemget_event*(localVar2, "get_piece_a");
}
private get_piece_a()  {
    temp tempVar0 = item_get_item_id*(self);
    item_get_evt_piece*(tempVar0);
}
"""
        self.assertEqual(
            [(item.object_name, item.field_item) for item in scripted_scraps("room", source)],
            [("map_piece_a", "PK_FIELD_W5_JUN_BRIDGE_2")],
        )

    def test_field_object_rewards_use_the_inventory_identity(self) -> None:
        item = ScrapItem("PK_FIELD_BRIDGE_KUSYA", "PK_HEI_5_BRIDGE")
        self.assertEqual(item.reward, NativeReward(NativeRewardKind.ITEM, "PK_HEI_5_BRIDGE"))

    def test_script_objects_require_unique_literal_names_and_exclude_nongivable_props(self) -> None:
        source = """var_0x123 = "bridge";
item_static_entry*(var_0x123, "PK_FIELD_BRIDGE_KUSYA", 0, 0, 0);
item_static_entry*("shelf", "PK_FIELD_SHELF", 0, 0, 0);
item_static_entry*(localVar0, "PK_FIELD_UNKNOWN", 0, 0, 0);
item_static_entry*("dummy", "PK_FIELD_DUMMY", 0, 0, 0);
item_set_flg*("dummy", item_flg_no_get, true);
"""
        items = scripted_scraps("room", source)
        self.assertEqual(
            [(item.object_name, item.field_item) for item in items],
            [("bridge", "PK_FIELD_BRIDGE_KUSYA"), ("shelf", "PK_FIELD_SHELF")],
        )

    def test_custom_callback_dispatch_uses_room_and_native_item_then_reuses_receipt(self) -> None:
        check = PickupReward("room", "bridge", "PK_FIELD_BRIDGE_KUSYA", NativeReward(NativeRewardKind.COINS, 25))
        source = DeliveryPlan((check,)).piece_pickup_function()
        self.assertIn('tempVar2 == "room" && tempVar0 == "PK_FIELD_BRIDGE_KUSYA"', source)
        self.assertIn("gf_rando_check_0000 *= true", source)
        self.assertIn("rando_deliver*()", source)

    def test_ambiguous_native_item_dispatch_is_rejected(self) -> None:
        reward = NativeReward(NativeRewardKind.COINS, 25)
        checks = tuple(PickupReward("room", name, "PK_FIELD_BRIDGE_KUSYA", reward) for name in ("a", "b"))
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            DeliveryPlan(checks).piece_pickup_function()
