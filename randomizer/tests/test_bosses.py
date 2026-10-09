import unittest

from ..integrations.rom.bosses import BossGate, gate_boss
from ..integrations.rom.mailbox import RemoteReward, remote_function
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind


class BossTests(unittest.TestCase):
    def test_final_boss_requires_the_first_five_royals_before_player_stop(self) -> None:
        source = 'private main()  {\n\tplayer_stop*("mario");\n}\n'
        result = gate_boss(source, BossGate("w6", "Script/Map/test.bin", "main"), require_royals=True)
        self.assertIn("rando_royal_gate_count*()", result)
        self.assertIn("if ( tempVar91 < 5 )", result)
        self.assertLess(result.index("tempVar91 < 5"), result.index("player_stop*"))

    def test_cancelled_once_trigger_is_restored_only_when_gate_owned_it(self) -> None:
        source = """private init()  {
\tcase_entry_detail*("zone", "boss_main", hit_place_foot, case_type_trigger, case_flg_once, 0);
}
private boss_main()  {
\tplayer_stop_wait*("mario");
\tcase_cancel*("zone", "boss_main");
\toriginal_battle*();
}
"""
        result = gate_boss(source, BossGate("w1", "Script/Map/test.bin", "boss_main", "zone", "boss_main", 1))
        self.assertIn("case_flg_once, 0", result)
        self.assertIn('case_cancel*("zone", "boss_main");\n\toriginal_battle*();', result)
        self.assertLess(result.index("gf_rando_boss_w1 == false"), result.index("player_stop_wait"))
        self.assertIn("gf_rando_boss_pending_w1 *= true", result)
        self.assertIn("if ( gf_rando_boss_pending_w1 ) {\n\t\t\tcase_uncancel*", result)
        self.assertIn("gf_rando_boss_pending_w1 *= false", result)
        with self.assertRaises(ValueError):
            gate_boss(source, BossGate("w1", "Script/Map/test.bin", "boss_main", "zone", "boss_main", 2))

    def test_unlock_is_distinct_from_boss_victory_and_royal_ownership(self) -> None:
        reward = NativeReward(NativeRewardKind.BOSS_ACCESS, "w1")
        plan = DeliveryPlan((GoalBlockReward("map", "GF_WM_A01_A02", reward),))
        self.assertIn("gf_rando_boss_w1 *= true", plan.delivery_body())
        self.assertNotIn("pouch_set_royal_seal", plan.delivery_body())
        self.assertNotIn("gf_evt_1_6", plan.delivery_body())
        self.assertNotIn("gf_rando_boss_pending_w1", plan.required_references)
        self.assertIn("gf_rando_boss_pending_w1", plan.flags)
        remote = remote_function((RemoteReward(100, reward),))
        self.assertIn("gf_rando_boss_w1 *= true", remote)
        self.assertNotIn("pouch_set_royal_seal", remote)
        for value in ("w0", "w7", True):
            with self.assertRaises(ValueError):
                NativeReward(NativeRewardKind.BOSS_ACCESS, value)

    def test_harbor_guard_runs_before_stopping_player(self) -> None:
        source = 'private action_dekapuku()  {\n\tplayer_stop*("mario", "battle");\n\tenemy_action*(self);\n}\n'
        result = gate_boss(source, BossGate("harbor", "Script/Map/test.bin", "action_dekapuku"))
        self.assertLess(result.index("return*;"), result.index("player_stop*"))
        self.assertNotIn("rando_boss_pending", result)
