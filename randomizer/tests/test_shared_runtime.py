import unittest

from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind
from ..integrations.rom.shared_runtime import item_grant_function, runtime_functions, shared_imports


class SharedRuntimeTests(unittest.TestCase):
    def test_inventory_commit_is_conditional_on_successful_fit(self) -> None:
        source = item_grant_function()
        self.assertIn("tempVar1 = item_try_addpouch*(tempVar0, false)", source)
        self.assertIn("if ( tempVar1 ) {\n\t\ttempVar1 = item_try_addpouch*(tempVar0, true)", source)
        self.assertIn("return* tempVar1", source)

    def test_runtime_exports_one_seed_and_delivery_engine(self) -> None:
        plan = DeliveryPlan((GoalBlockReward("map", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 20)),))
        source = runtime_functions(plan)
        self.assertEqual(source.count("public rando_seed_valid("), 1)
        self.assertEqual(source.count("public rando_deliver("), 1)
        self.assertIn("gf_rando_seed_127", source)
        self.assertNotIn("private rando_seed_valid(", source)
        self.assertNotIn("rando_delivery_poll", source)

    def test_shared_imports_use_original_name_bucket_rule(self) -> None:
        # The known original mobj public helper uses bucket 0x24.
        name = "mobj_goal_block_exit"
        self.assertEqual(sum(map(ord, name[len(name) // 2:])) & 511, 0x24)
        for name, declaration in shared_imports().items():
            self.assertIn(f"from 0x{sum(map(ord, name[len(name) // 2:])) & 511:x}", declaration)
