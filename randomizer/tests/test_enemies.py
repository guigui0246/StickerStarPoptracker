import unittest

from ..integrations.rom.enemies import death_hook, reset_hook, victory_hook
from ..integrations.rom.native_delivery import DeliveryPlan, EnemyReward, NativeReward, NativeRewardKind
from ..integrations.rom.plan_io import decode_plan, encode_plan


class EnemyTests(unittest.TestCase):
    def setUp(self):
        reward = NativeReward(NativeRewardKind.COINS, 20)
        self.checks = (EnemyReward("クリボー", "Script/Battle/Enemy/btl_kuriboo.bin", "kuriboo_dead", reward),
                       EnemyReward("別のクリボー", "Script/Battle/Enemy/btl_kuriboo.bin", "kuriboo_dead", reward))
        self.plan = DeliveryPlan(self.checks)

    def test_death_records_exact_type_and_leaves_reward_until_victory(self):
        source = 'private kuriboo_dead()  {\n\tbattle_enemy_default_dead_func*(0);\n}\n'
        result = death_hook(source, "kuriboo_dead", list(enumerate(self.checks)), self.plan)
        self.assertIn("battle_unit_get_hp*(self)", result)
        self.assertIn("tempVar91 <= 0", result)
        self.assertIn("battle_unit_get_unit_data_id*(self)", result)
        self.assertIn('tempVar92 == "クリボー"', result)
        self.assertIn("gf_rando_enemy_pending_0000 *= true", result)
        self.assertNotIn("gf_rando_check_0000 *= true", result)
        self.assertNotIn("pouch_add_coin", result)
        self.assertIn("battle_enemy_default_dead_func*(0)", result)

    def test_new_battle_clears_pending_and_only_win_collects_outside_museum(self):
        reset = reset_hook('private init()  {\n\toriginal*();\n}\n', self.plan)
        win = victory_hook('public battle_win_event()  {\n\toriginal*();\n}\n', self.plan)
        self.assertIn("gf_rando_enemy_pending_0000 *= false", reset)
        self.assertNotIn("gf_rando_check_0000 *= false", reset)
        self.assertIn("battle_is_museum*()", win)
        self.assertIn("if ( tempVar90 == false )", win)
        self.assertIn("if ( gf_rando_enemy_pending_0000 )", win)
        self.assertIn("gf_rando_check_0000 *= true", win)
        self.assertIn("gf_rando_enemy_pending_0000 *= false", win)
        self.assertNotIn("pouch_add_coin", win)
        self.assertIn("pouch_add_coin*(20)", self.plan.delivery_body())
        self.assertEqual(decode_plan(encode_plan(self.plan)), self.plan)

    def test_enemy_ids_are_stable_and_invalid_hooks_are_rejected(self):
        self.assertNotEqual(self.checks[0].id, self.checks[1].id)
        self.assertEqual(self.checks[0].id, self.checks[0].id)
        with self.assertRaises(ValueError):
            EnemyReward('enemy"', "Script/Battle/Enemy/btl_kuriboo.bin", "dead", self.checks[0].reward)
        with self.assertRaises(ValueError):
            EnemyReward("enemy", "Script/Map/fake.bin", "dead", self.checks[0].reward)


if __name__ == "__main__":
    unittest.main()
