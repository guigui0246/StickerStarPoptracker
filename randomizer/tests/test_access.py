import unittest

from ..integrations.rom.access import gate_stage_entry
from ..integrations.rom.doors import DoorPlace, gate_door_fit
from ..integrations.rom.mailbox import RemoteReward, RemoteSession, remote_function
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind
from ..integrations.rom.startup import STARTUP_FLAGS, post_tutorial_start


class AccessTests(unittest.TestCase):
    def plan(self, kind: NativeRewardKind) -> DeliveryPlan:
        return DeliveryPlan((GoalBlockReward("hei_5_00", "GF_WM_A01_A02", NativeReward(kind, "A01")),))

    def test_admission_keeps_native_checks_after_ownership_guard(self) -> None:
        plan = self.plan(NativeRewardKind.STAGE_ACCESS)
        source = "public e_wm_map_access()  {\n\twm_check_map_access();\n\treturn true;\n}\n"
        result = gate_stage_entry(source, plan)
        self.assertLess(result.index("gf_rando_stage_a01"), result.index("wm_check_map_access"))
        self.assertIn("return* false", result)
        self.assertIn("gf_rando_stage_a01 *= true", plan.delivery_body())
        self.assertNotIn('wm_set_gf*("', plan.delivery_body())

    def test_door_targets_keep_cancel_and_other_mode_results(self) -> None:
        plan = self.plan(NativeRewardKind.DOOR_ACCESS)
        source = "public decal_dokodemo()  {\n" + "\ttempVar0 = decal_dokodemo_mario_control_main();\n" * 3 + "}\n"
        places = (DoorPlace("door1", "hei_5_06", "A01", "gf_done"), DoorPlace("door2", "hei_3_05", "A02", "gf_other"))
        result = gate_door_fit(source, plan, places)
        self.assertEqual(result.count("decal_dokodemo_mario_control_main*()"), 1)
        self.assertEqual(result.count("rando_door_control*()"), 3)
        self.assertIn('pepalyze_is_now_play_unlock*("door1")', result)
        self.assertNotIn('pepalyze_is_now_play_unlock*("door2")', result)
        self.assertIn("tempVar1 != pepalyze_mode_unlock", result)
        self.assertIn("tempVar0 == pepalyze_select_cancel", result)
        self.assertIn("return* pepalyze_miss", result)
        self.assertNotIn("gf_done *=", result)
        self.assertNotIn("pepalyze_get_now_play_unlock_num", result)
        self.assertNotIn("pepalyze_get_access_number", result)
        with self.assertRaises(ValueError):
            gate_door_fit(source.replace("decal_dokodemo_mario_control_main", "unknown"), plan, places)

    def test_every_selected_door_is_gated_in_a_multi_target_operation(self) -> None:
        places = (DoorPlace("door1", "room", "A01", "gf_one"), DoorPlace("door2", "room", "A01", "gf_two"))
        plan = DeliveryPlan((GoalBlockReward("hei_5_00", "GF_WM_A01_A02", NativeReward(NativeRewardKind.DOOR_ACCESS, "door1")),),
                            starting_rewards=(NativeReward(NativeRewardKind.DOOR_ACCESS, "door2"),))
        source = "public input() {\n" + "decal_dokodemo_mario_control_main();\n" * 3 + "}\n"
        gated = gate_door_fit(source, plan, places)
        self.assertEqual(gated.count("pepalyze_is_now_play_unlock*("), 2)
        self.assertIn("gf_rando_door_door1 == false", gated)
        self.assertIn("gf_rando_door_door2 == false", gated)
        self.assertNotIn("pepalyze_get_now_play_unlock_num", gated)

    def test_exact_door_rewards_do_not_unlock_other_places_in_the_same_stage(self) -> None:
        places = (DoorPlace("door1", "hei_5_06", "A01", "gf_done"), DoorPlace("door2", "hei_5_07", "A01", "gf_other"))
        source = "public decal_dokodemo() {\n" + "decal_dokodemo_mario_control_main();\n" * 3 + "}\n"
        plan = DeliveryPlan((GoalBlockReward("hei_5_00", "GF_WM_A01_A02", NativeReward(NativeRewardKind.DOOR_ACCESS, "door1")),))
        result = gate_door_fit(source, plan, places)
        self.assertIn("gf_rando_door_door1 == false", result)
        self.assertIn('pepalyze_is_now_play_unlock*("door1")', result)
        self.assertNotIn('pepalyze_is_now_play_unlock*("door2")', result)
        self.assertIn("gf_rando_door_door1 *= true", plan.delivery_body())
        from dataclasses import replace
        for rewards in ((NativeReward(NativeRewardKind.DOOR_ACCESS, "A01"),), (NativeReward(NativeRewardKind.DOOR_ACCESS, "unknown"),)):
            with self.assertRaises(ValueError):
                gate_door_fit(source, replace(plan, starting_rewards=rewards), places)

    def test_remote_gate_receipts_do_not_open_routes_or_grant_stickers(self) -> None:
        rewards = tuple(RemoteReward(index, NativeReward(kind, "A01")) for index, kind in enumerate((NativeRewardKind.STAGE_ACCESS, NativeRewardKind.DOOR_ACCESS), 1))
        checks = (GoalBlockReward("hei_5_00", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 10)),)
        plan = DeliveryPlan(checks, remote_rewards=rewards, remote_session=RemoteSession("seed", 0, 1, "a" * 64))
        source = remote_function(rewards)
        for flag in (*plan.stage_access_flags, *plan.door_access_flags):
            self.assertIn(f"{flag} *= true", source)
        self.assertNotIn("item_try_addpouch", source)
        self.assertNotIn("wm_set_gf", source)
        self.assertLess(source.index("gf_rando_door_a01 *= true"), source.index("gf_rando_rpc_ack_ready_00 *= true"))

    def test_startup_marks_tutorial_complete_without_progression_grants(self) -> None:
        source = "private sw_bero_enter_evt()  {\n\titem_try_addpouch*(\"IC_HAMMER\", true);\n}\n"
        result = post_tutorial_start(source)
        for flag in STARTUP_FLAGS:
            self.assertIn(f"{flag} *= true", result)
        self.assertNotIn("IC_HAMMER", result)
        self.assertNotIn("SL_", result)
        self.assertIn("pouch_attach_accessory*(2)", result)
        self.assertLess(result.index("rando_deliver"), result.index("gf_evt_mac_battle_tutorial *= true"))
